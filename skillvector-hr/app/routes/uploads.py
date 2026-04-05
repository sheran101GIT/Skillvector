from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import Job, Candidate, db

bp = Blueprint('uploads', __name__, url_prefix='/uploads')

@bp.route('/')
@login_required
def index():
    from ..models import JobTemplate
    
    # Fetch all jobs
    jobs = Job.query.filter_by(recruiter_id=current_user.id).order_by(Job.posted_at.desc()).all()
    
    # Fetch all candidates (for uploaded resumes tab)
    candidates = Candidate.query.order_by(Candidate.created_at.desc()).all()
    
    # Auto-fail stuck jobs (> 2 mins)
    import datetime
    stuck_threshold = datetime.datetime.utcnow() - datetime.timedelta(minutes=2)
    stuck_candidates = [c for c in candidates if c.processing_status in ['processing', 'pending'] and c.created_at < stuck_threshold]
    if stuck_candidates:
        for c in stuck_candidates:
            c.processing_status = 'failed'
            c.error_message = 'Processing timed out (stuck).'
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
    
    return render_template('uploads.html', jobs=jobs, candidates=candidates, stats=stats, 
                           job_analytics=job_analytics, templates=templates, google_forms=google_forms)

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
    """Connect a Google Form to a job for automated resume collection"""
    from ..models import GoogleFormConnection
    
    job_id = request.form.get('job_id')
    form_url = request.form.get('form_url')
    form_title = request.form.get('form_title')
    
    if not job_id or not form_url:
        flash('Please select a job and provide a Google Form URL', 'error')
        return redirect(url_for('uploads.index'))
    
    job = Job.query.get_or_404(int(job_id))
    if job.recruiter_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for('uploads.index'))
    
    # Save connection
    title = form_title if form_title else f"{job.title} - Application Form"
    connection = GoogleFormConnection(
        recruiter_id=current_user.id,
        job_id=job.id,
        form_url=form_url,
        form_title=title
    )
    db.session.add(connection)
    db.session.commit()
    
    flash(f"Successfully connected Google Form: {title}", "success")
    return redirect(url_for('uploads.index'))

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
