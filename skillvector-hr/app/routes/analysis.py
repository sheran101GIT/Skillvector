from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import Candidate, Job, db

bp = Blueprint('analysis', __name__, url_prefix='/analysis')

@bp.route('/')
@login_required
def index():
    # Fetch candidates
    candidates = Candidate.query.join(Job).filter(Job.recruiter_id == current_user.id).order_by(Candidate.created_at.desc()).all()
    
    # Stats
    total = len(candidates)
    approved = sum(1 for c in candidates if c.decision_status == 'approved')
    rejected = sum(1 for c in candidates if c.decision_status == 'rejected')
    pending = sum(1 for c in candidates if c.decision_status == 'pending')
    
    return render_template('analysis.html', 
                           candidates=candidates,
                           stats={'total': total, 'approved': approved, 'rejected': rejected, 'pending': pending})

@bp.route('/decide/<int:candidate_id>/<action>', methods=['POST'])
@login_required
def decide(candidate_id, action):
    candidate = Candidate.query.get_or_404(candidate_id)
    if candidate.job.recruiter_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    
    if action == 'approve':
        candidate.decision_status = 'approved'
        flash(f"Approved {candidate.name}", "success")
    elif action == 'reject':
        candidate.decision_status = 'rejected'
        flash(f"Rejected {candidate.name}", "error")
    
    db.session.commit()
    return redirect(url_for('analysis.index'))
