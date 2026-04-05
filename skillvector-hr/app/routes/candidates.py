from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import Job, Candidate, Analysis, db
from ..pipeline import extract_text_from_pdf, generate_embedding, extract_skills
from .. import executor
from ..services import process_candidate_background
from sqlalchemy.sql.expression import func
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

bp = Blueprint('candidates', __name__, url_prefix='/candidates')

@bp.route('/upload/<int:job_id>', methods=['GET', 'POST'])
@login_required
def upload(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        github_url = request.form.get('github_url')
        linkedin_url = request.form.get('linkedin_url')
        file = request.files.get('resume')
        
        if file:
            try:
                # Determine file type
                filename = file.filename.lower()
                if filename.endswith('.pdf'):
                    text = extract_text_from_pdf(file)
                elif filename.endswith('.docx'):
                    from ..pipeline import extract_text_from_docx
                    text = extract_text_from_docx(file)
                else:
                    flash('Unsupported file format. Use PDF or DOCX.')
                    return redirect(request.url)

                # Create Candidate with pending status
                candidate = Candidate(
                    name=name,
                    email=email,
                    resume_text=text, # Store RAW text first
                    # skills=[], # Will be populated in background
                    github_url=github_url,
                    linkedin_url=linkedin_url,
                    job_id=job.id,
                    processing_status='pending'
                )
                db.session.add(candidate)
                db.session.commit()
                
                # Submit background task
                executor.submit(process_candidate_background, candidate.id, job.id)
                
                flash('Candidate uploaded! Processing started in background.')
                return redirect(url_for('candidates.view', candidate_id=candidate.id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error uploading file: {str(e)}')
                
    return render_template('candidate_upload.html', job=job)

@bp.route('/<int:candidate_id>')
@login_required
def view(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    # Check access via job -> recruiter
    if candidate.job and candidate.job.recruiter_id != current_user.id:
        return redirect(url_for('main.dashboard'))
        
    # Check for stale pending status (zombie job)
    if candidate.processing_status in ['pending', 'processing']:
        import datetime
        limit = datetime.datetime.utcnow() - datetime.timedelta(minutes=2)
        # Use updated_at if available, else created_at
        check_time = candidate.updated_at if candidate.updated_at else candidate.created_at
        if check_time < limit:
            candidate.processing_status = 'failed'
            candidate.error_message = 'Processing timeout (likely interrupted). Please re-upload.'
            db.session.commit()
        
    analysis = Analysis.query.filter_by(candidate_id=candidate.id).first()
        
    return render_template('candidate_view.html', candidate=candidate, analysis=analysis)

@bp.route('/all')
@login_required
def all_candidates():
    # Fetch candidates for jobs owned by current user
    candidates = Candidate.query.join(Job).filter(Job.recruiter_id == current_user.id).order_by(Candidate.created_at.desc()).all()
    
    # Fetch jobs for filter dropdown
    jobs = Job.query.filter_by(recruiter_id=current_user.id).all()
    
    # Calculate stats
    total = len(candidates)
    active = sum(1 for c in candidates if c.processing_status != 'rejected')
    joined = sum(1 for c in candidates if c.current_stage == 'Joined')
    
    # Count this week's applications
    from datetime import datetime, timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    this_week = sum(1 for c in candidates if c.created_at and c.created_at >= week_ago)
    
    return render_template('all_candidates.html', 
                           candidates=candidates,
                           jobs=jobs,
                           stats={'total': total, 'active': active, 'joined': joined, 'week': this_week})

@bp.route('/<int:candidate_id>/reanalyze', methods=['POST'])
@login_required
def reanalyze(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    if candidate.job and candidate.job.recruiter_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for('main.dashboard'))
        
    # Reset status
    candidate.processing_status = 'pending'
    candidate.error_message = None
    import datetime
    candidate.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    
    # Switch to background task
    executor.submit(process_candidate_background, candidate.id, candidate.job_id)
    
    flash(f"Restarted analysis for {candidate.name}", "success")
    return redirect(url_for('candidates.view', candidate_id=candidate.id))
