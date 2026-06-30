from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import Job, Candidate, db

bp = Blueprint('uploads', __name__, url_prefix='/uploads')

@bp.route('/')
@login_required
def index():
    from ..models import JobTemplate
    
    # Fetch all jobs belonging to the current user
    jobs = Job.query.filter_by(recruiter_id=current_user.id).order_by(Job.posted_at.desc()).all()
    
    # Fetch only candidates linked to the current user's jobs (data isolation fix)
    user_job_ids = [job.id for job in jobs]
    candidates = (
        Candidate.query
        .filter(Candidate.job_id.in_(user_job_ids))
        .order_by(Candidate.created_at.desc())
        .all()
    ) if user_job_ids else []
    
    # Auto-fail truly stuck jobs.
    # Pipeline includes: SpaCy load + Groq/Gemini LLM calls + embeddings + phrasing.
    # On Render free tier with cold starts this can take 10-15 min. Use 20 min threshold.
    import datetime
    stuck_threshold = datetime.datetime.utcnow() - datetime.timedelta(minutes=20)
    stuck_candidates = [c for c in candidates if c.processing_status in ['processing', 'pending'] and c.created_at < stuck_threshold]
    if stuck_candidates:
        for c in stuck_candidates:
            c.processing_status = 'failed'
            c.error_message = 'Processing timed out after 20 minutes. Please use Refresh Analysis to retry.'
        db.session.commit()

    # --- NEW: Pick up pending Google Forms candidates ---
    # Since JDBC inserts 'pending' candidates without triggering the Flask background app,
    # we need to check for them here and start processing.
    new_form_candidates = [c for c in candidates if c.processing_status == 'pending' and c.source == 'Google Forms']
    if new_form_candidates:
        from .. import executor
        from ..services import process_candidate_background
        count = 0
        for c in new_form_candidates:
            # Determine Job ID if not set (could default to a "General Application" job or 1st job)
            # Logic: If no job_id, try to assign to the first active job or leave null (if db allows)
            # But process_candidate_background needs a job_id for skill matching.
            target_job_id = c.job_id
            if not target_job_id and jobs:
                # Fallback: assign to most recent job if unknown
                target_job_id = jobs[0].id
                c.job_id = target_job_id
            
            if target_job_id:
                executor.submit(process_candidate_background, c.id, target_job_id)
                count += 1
        
        if count > 0:
            flash(f"Picked up {count} new application(s) from Google Forms", "success")
    
    # Calculate stats
    total = len(candidates)
    processed = sum(1 for c in candidates if c.processing_status == 'completed')
    processing = sum(1 for c in candidates if c.processing_status == 'processing')
    errors = sum(1 for c in candidates if c.processing_status == 'failed')

    stats = {
        'total': total,
        'processed': processed,
        'processing': processing,
        'errors': errors
    }

    # Analytics: Application counts per job
    job_analytics = {}
    for job in jobs:
        count = Candidate.query.filter_by(job_id=job.id).count()
        job_analytics[job.id] = count

    # Templates
    templates = JobTemplate.query.filter_by(created_by=current_user.id).all()

    # Google Forms
    from ..models import GoogleFormConnection
    google_forms = GoogleFormConnection.query.filter_by(recruiter_id=current_user.id).all()

    # API Pipeline stats: Today's Submissions vs Yesterday
    import datetime
    now = datetime.datetime.utcnow()
    today_start     = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - datetime.timedelta(days=1)

    today_count = sum(
        1 for c in candidates
        if c.created_at and c.created_at >= today_start
    )
    yesterday_count = sum(
        1 for c in candidates
        if c.created_at and yesterday_start <= c.created_at < today_start
    )
    yesterday_diff = today_count - yesterday_count

    api_stats = {
        'today_submissions': today_count,
        'yesterday_diff': yesterday_diff,
    }

    return render_template('uploads.html', jobs=jobs, candidates=candidates, stats=stats,
                           job_analytics=job_analytics, templates=templates,
                           google_forms=google_forms, api_stats=api_stats)

@bp.route('/upload', methods=['POST'])
@login_required
def upload_resumes():
    if 'resumes' not in request.files:
        flash('No files selected', 'error')
        return redirect(url_for('uploads.index'))
    
    files = request.files.getlist('resumes')
    job_id = request.form.get('job_id')
    
    # Convert job_id to int if provided
    job_id = int(job_id) if job_id else None
    
    if not files or files[0].filename == '':
        flash('No files selected', 'error')
        return redirect(url_for('uploads.index'))
    
    uploaded_count = 0
    for file in files:
        if file and file.filename:
            # Determine file type and extract text synchronously
            # This ensures we have the content even if we process it later
            text = "Extraction failed"
            filename = file.filename.lower()
            try:
                if filename.endswith('.pdf'):
                    from ..pipeline import extract_text_from_pdf
                    text = extract_text_from_pdf(file)
                elif filename.endswith('.docx'):
                    from ..pipeline import extract_text_from_docx
                    text = extract_text_from_docx(file)
            except Exception as e:
                print(f"Extraction Error: {e}")
                text = f"Error extracting text: {e}"

            candidate = Candidate(
                name=file.filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title(),
                resume_text=text,
                processing_status='pending',
                job_id=job_id
            )
            db.session.add(candidate)
            db.session.flush() # Get ID
            
            # Trigger background processing
            from .. import executor
            from ..services import process_candidate_background
            executor.submit(process_candidate_background, candidate.id, job_id)
            
            uploaded_count += 1
    
    db.session.commit()
    flash(f'Successfully uploaded {uploaded_count} resume(s)', 'success')
    return redirect(url_for('uploads.index'))

@bp.route('/delete/<int:candidate_id>', methods=['POST'])
@login_required
def delete_resume(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    
    # Optional: Check authorization if the candidate is linked to a job
    # Allow deleting Google Forms entries even if mis-assigned (e.g. via webhook default)
    if candidate.job and candidate.job.recruiter_id != current_user.id and candidate.source != 'Google Forms':
        flash("Unauthorized", "error")
        return redirect(url_for('uploads.index'))
    
    name = candidate.name
    db.session.delete(candidate)
    db.session.commit()
    flash(f"Deleted resume for {name}", "success")
    return redirect(url_for('uploads.index'))

@bp.route('/deactivate/<int:job_id>', methods=['POST'])
@login_required
def deactivate_job(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for('uploads.index'))
    
    job.is_active = False
    db.session.commit()
    flash(f"Deactivated {job.title}", "success")
    return redirect(url_for('uploads.index'))

@bp.route('/connect-form', methods=['POST'])
@login_required
def connect_form():
    """Connect a Google Form to a job. Extracts form_id and auto-detects field mapping."""
    from ..models import GoogleFormConnection
    from ..google_forms_service import (
        get_google_forms_service, extract_form_id_from_url, auto_detect_field_mapping
    )

    job_id   = request.form.get('job_id')
    form_url = request.form.get('form_url', '').strip()

    if not job_id or not form_url:
        flash('Please select a job and provide a Google Form URL', 'error')
        return redirect(url_for('uploads.index'))

    job = Job.query.get_or_404(int(job_id))
    if job.recruiter_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for('uploads.index'))

    # Extract form ID from URL
    form_id = extract_form_id_from_url(form_url)
    if not form_id:
        flash('Could not extract Form ID from the URL. Please paste the full Google Form URL.', 'error')
        return redirect(url_for('uploads.index'))

    # Fetch form metadata + auto-detect field mapping via the API
    form_title = f"{job.title} - Application Form"
    field_mapping = {}
    sync_status = 'pending_mapping'

    try:
        svc = get_google_forms_service()
        meta = svc.get_form_metadata(form_id)
        form_title = meta['title'] or form_title
        field_mapping = auto_detect_field_mapping(meta['questions'])
        sync_status = 'active'
        flash(f"Connected \"{form_title}\" — field mapping auto-detected. Review it below.", "success")
    except RuntimeError as e:
        # Service account not configured or API error — still save the connection
        err = str(e)
        if 'GOOGLE_SERVICE_ACCOUNT_JSON' in err:
            flash(
                'Google Forms connected (URL saved), but the Google Service Account is not configured. '
                'Add GOOGLE_SERVICE_ACCOUNT_JSON to your environment variables to enable API sync.',
                'warning'
            )
        else:
            flash(f'Form connected but could not fetch metadata: {err}', 'warning')
        sync_status = 'error'

    connection = GoogleFormConnection(
        recruiter_id=current_user.id,
        job_id=job.id,
        form_url=form_url,
        form_id=form_id,
        form_title=form_title,
        field_mapping=field_mapping,
        sync_status=sync_status,
        total_synced=0,
    )
    db.session.add(connection)
    db.session.commit()
    return redirect(url_for('uploads.index'))


@bp.route('/sync-form/<int:connection_id>', methods=['POST'])
@login_required
def sync_form(connection_id):
    """Manually trigger a sync for a connected Google Form."""
    from ..models import GoogleFormConnection
    from ..google_forms_service import get_google_forms_service

    conn = GoogleFormConnection.query.get_or_404(connection_id)
    if conn.recruiter_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for('uploads.index'))

    if not conn.form_id:
        flash("No Form ID — please reconnect this form.", "error")
        return redirect(url_for('uploads.index'))

    if not conn.field_mapping:
        flash("Field mapping is not configured yet. Please set it up first.", "warning")
        return redirect(url_for('uploads.index'))

    try:
        svc = get_google_forms_service()
        result = svc.sync_connection(conn, app_context=None)
        imported = result['imported']
        errors   = result['errors']

        if imported > 0:
            flash(f"Synced {imported} new candidate(s) from \"{conn.form_title}\"!", "success")
        else:
            flash(f"No new responses found in \"{conn.form_title}\".", "info")

        if errors:
            flash(f"{len(errors)} response(s) had errors: {errors[0]}", "warning")

    except RuntimeError as e:
        flash(f"Sync failed: {e}", "error")

    return redirect(url_for('uploads.index'))


@bp.route('/save-field-mapping/<int:connection_id>', methods=['POST'])
@login_required
def save_field_mapping(connection_id):
    """Save the recruiter-adjusted field mapping for a Google Form connection."""
    from ..models import GoogleFormConnection

    conn = GoogleFormConnection.query.get_or_404(connection_id)
    if conn.recruiter_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for('uploads.index'))

    # Collect mapping from form: field_map[question_id] = candidate_field
    new_mapping = {}
    for key, value in request.form.items():
        if key.startswith('mapping_'):
            q_id = key[len('mapping_'):]
            new_mapping[q_id] = value

    conn.field_mapping = new_mapping
    conn.sync_status = 'active'
    db.session.commit()
    flash(f"Field mapping saved for \"{conn.form_title}\".", "success")
    return redirect(url_for('uploads.index'))


@bp.route('/get-form-questions/<int:connection_id>', methods=['GET'])
@login_required
def get_form_questions(connection_id):
    """API endpoint: returns form questions + current mapping for the mapping modal."""
    from flask import jsonify
    from ..models import GoogleFormConnection
    from ..google_forms_service import get_google_forms_service

    conn = GoogleFormConnection.query.get_or_404(connection_id)
    if conn.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        svc = get_google_forms_service()
        meta = svc.get_form_metadata(conn.form_id)
        return jsonify({
            'form_title': meta['title'],
            'questions': meta['questions'],
            'current_mapping': conn.field_mapping or {},
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/disconnect-form/<int:connection_id>', methods=['POST'])
@login_required
def disconnect_form(connection_id):
    """Remove a Google Form connection"""
    from ..models import GoogleFormConnection

    conn = GoogleFormConnection.query.get_or_404(connection_id)
    if conn.recruiter_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for('uploads.index'))

    db.session.delete(conn)
    db.session.commit()
    flash("Disconnected Google Form", "success")
    return redirect(url_for('uploads.index'))

