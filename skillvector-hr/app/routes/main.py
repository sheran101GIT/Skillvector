from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from ..models import Job, Candidate
from sqlalchemy import func

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('landing.html')

@bp.route('/dashboard')
@login_required
def dashboard():
    jobs = Job.query.filter_by(recruiter_id=current_user.id).all()
    
    # Get all candidates for this user's jobs
    job_ids = [job.id for job in jobs]
    candidates_query = Candidate.query.filter(Candidate.job_id.in_(job_ids)) if job_ids else Candidate.query.filter(False)
    
    total_candidates = candidates_query.count()
    
    # Calculate stage counts
    stage_counts = {}
    if job_ids:
        counts = Candidate.query.filter(Candidate.job_id.in_(job_ids)).with_entities(
            Candidate.current_stage, func.count(Candidate.id)
        ).group_by(Candidate.current_stage).all()
        stage_counts = {stage: count for stage, count in counts}
    
    # Map stages to template variables (handle various stage name formats)
    def get_count(*stage_names):
        total = 0
        for name in stage_names:
            total += stage_counts.get(name, 0)
            total += stage_counts.get(name.lower(), 0)
            total += stage_counts.get(name.replace(' ', '_').lower(), 0)
        return total
    
    metrics = {
        'total_candidates': total_candidates,
        'applied': get_count('Applied', 'applied'),
        # Individual stages matching Move Stage modal
        'aptitude': get_count('Aptitude'),
        'screening': get_count('Screening'),
        'group_discussion': get_count('Group Discussion'),
        'technical_round': get_count('Technical Round'),
        'hr_round': get_count('HR Round'),
        'interview_scheduled': get_count('Interview Scheduled'),
        'interview_completed': get_count('Interview Completed'),
        'selected': get_count('Selected'),
        'offer_extended': get_count('Offer Extended'),
        'joined': get_count('Joined'),
        'rejected': get_count('Rejected'),
    }
    
    # Calculate total selected count for success rate (offer_extended + joined + selected)
    metrics['total_selected'] = metrics['offer_extended'] + metrics['joined'] + metrics['selected']
    
    # Calculate success rate
    if total_candidates > 0:
        metrics['success_rate'] = round((metrics['total_selected'] / total_candidates) * 100)
    else:
        metrics['success_rate'] = 0
    
    # Get top candidates for display
    top_candidates = candidates_query.order_by(Candidate.created_at.desc()).limit(5).all() if job_ids else []
    
    return render_template('dashboard.html', 
                           jobs=jobs, 
                           total_candidates=total_candidates,
                           metrics=metrics,
                           top_candidates=top_candidates,
                           candidates=candidates_query.all() if job_ids else [])
