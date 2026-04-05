from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from ..models import Job, Candidate, Analysis, CandidateJourney, db, User
from sqlalchemy import select
from ..pipeline import generate_embedding
from datetime import datetime

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/candidates/by-stage')
@login_required
def get_candidates_by_stage():
    """Get all candidates filtered by stage"""
    stage = request.args.get('stage', 'all')
    
    # Get jobs for current user
    jobs = Job.query.filter_by(recruiter_id=current_user.id).all()
    job_ids = [job.id for job in jobs]
    
    if not job_ids:
        return jsonify({'candidates': []})
    
    # Query candidates
    query = Candidate.query.filter(Candidate.job_id.in_(job_ids))
    
    if stage != 'all':
        query = query.filter(Candidate.current_stage == stage)
    
    candidates = query.order_by(Candidate.created_at.desc()).all()
    
    return jsonify({
        'stage': stage,
        'count': len(candidates),
        'candidates': [{
            'id': c.id,
            'name': c.name,
            'email': c.email,
            'position': c.job.title if c.job else 'General Application',
            'current_stage': c.current_stage or 'applied',
            'created_at': c.created_at.strftime('%Y-%m-%d') if c.created_at else None
        } for c in candidates]
    })

@bp.route('/candidate/<int:candidate_id>/journey')
@login_required
def get_candidate_journey(candidate_id):
    """Get complete journey timeline for a candidate"""
    candidate = Candidate.query.get_or_404(candidate_id)
    
    # Verify access - user must own the job this candidate applied to
    if candidate.job and candidate.job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    journey_stages = CandidateJourney.query.filter_by(candidate_id=candidate_id).order_by(CandidateJourney.created_at).all()
    
    return jsonify({
        'candidate': {
            'id': candidate.id,
            'name': candidate.name,
            'position': candidate.job.title if candidate.job else 'General Application',
            'applied_at': candidate.created_at.isoformat() if candidate.created_at else None,
            'source': candidate.source or 'Manual Upload',
            'current_stage': candidate.current_stage or 'applied'
        },
        'journey': [{
            'stage': stage.stage,
            'notes': stage.notes,
            'score': stage.score,
            'interviewer': stage.interviewer,
            'created_at': stage.created_at.isoformat() if stage.created_at else None
        } for stage in journey_stages]
    })

@bp.route('/candidate/<int:candidate_id>/stage', methods=['POST'])
@login_required
def update_candidate_stage(candidate_id):
    """Update candidate stage and log journey"""
    candidate = Candidate.query.get_or_404(candidate_id)
    
    # Verify access
    if candidate.job and candidate.job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    new_stage = data.get('stage')
    notes = data.get('notes')
    
    if not new_stage:
        return jsonify({'error': 'Stage is required'}), 400
        
    # Update current stage
    candidate.current_stage = new_stage
    
    # Log journey
    journey = CandidateJourney(
        candidate_id=candidate.id,
        stage=new_stage,
        notes=notes,
        created_at=datetime.utcnow()
    )
    db.session.add(journey)
    db.session.commit()
    
    return jsonify({
        'message': 'Stage updated successfully',
        'current_stage': candidate.current_stage
    })

@bp.route('/candidate/<int:candidate_id>/review-analysis')
@login_required
def get_review_analysis(candidate_id):
    """Get candidate review analysis data for the modal"""
    candidate = Candidate.query.get_or_404(candidate_id)
    
    # Verify access
    if candidate.job and candidate.job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get analysis if exists
    analysis = Analysis.query.filter_by(candidate_id=candidate_id).first()
    
    analysis_data = None
    if analysis:
        analysis_data = {
            'final_score': analysis.final_score,
            'similarity': analysis.similarity,
            'skills_matched': analysis.skills_matched or [],
            'missing_skills': analysis.missing_skills or [],
            'phrasing_suggestions': analysis.phrasing_suggestions
        }
    
    return jsonify({
        'candidate': {
            'id': candidate.id,
            'name': candidate.name,
            'email': candidate.email,
            'position': candidate.job.title if candidate.job else 'General Application',
            'current_stage': 'In Screening' if candidate.processing_status == 'completed' else candidate.processing_status.replace('_', ' ').title(),
            'review_status': candidate.review_status
        },
        'analysis': analysis_data
    })


@bp.route('/candidate/<int:candidate_id>/generate-review', methods=['POST'])
@login_required
def generate_review(candidate_id):
    """
    Generate an LLM review email for a candidate.
    Request body: { "decision": "selected" | "rejected", "job_id": <int> }
    """
    try:
        candidate = Candidate.query.get_or_404(candidate_id)

        if candidate.job and candidate.job.recruiter_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        data     = request.get_json() or {}
        decision = data.get('decision', '').lower()
        job_id   = data.get('job_id') or candidate.job_id

        if decision not in ('selected', 'rejected'):
            return jsonify({'error': 'decision must be "selected" or "rejected"'}), 400
        if not job_id:
            return jsonify({'error': 'job_id is required — candidate may not be linked to a job'}), 400

        from ..pipeline import generate_review_email
        result = generate_review_email(
            candidate_id    = candidate_id,
            job_id          = int(job_id),
            decision        = decision,
            generated_by_id = current_user.id
        )

        if 'error' in result:
            return jsonify({'error': result['error']}), 500

        return jsonify(result), 200

    except Exception as e:
        import traceback
        print(f"[generate_review] Unhandled exception: {e}", flush=True)
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@bp.route('/candidate/<int:candidate_id>/email-history')
@login_required
def get_email_history(candidate_id):
    """Return all previously generated review emails for a candidate."""
    from ..models import ReviewEmail
    candidate = Candidate.query.get_or_404(candidate_id)

    if candidate.job and candidate.job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    emails = ReviewEmail.query.filter_by(
        candidate_id=candidate_id
    ).order_by(ReviewEmail.created_at.desc()).all()

    return jsonify({
        'emails': [{
            'id':       e.id,
            'subject':  e.email_subject,
            'body':     e.email_body,
            'decision': e.decision,
            'status':   e.status,
            'created_at': e.created_at.strftime('%d %b %Y, %H:%M') if e.created_at else None
        } for e in emails]
    })




@bp.route('/search', methods=['GET'])
@login_required
def search():
    query = request.args.get('q')
    job_id = request.args.get('job_id')
    limit = request.args.get('limit', 10, type=int)
    
    if not query or not job_id:
        return jsonify({'error': 'Missing query or job_id'}), 400
        
    job = Job.query.get(job_id)
    if not job or job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    query_embedding = generate_embedding(query)
    
    # PGVector similarity search
    candidates = db.session.scalars(
        select(Candidate)
        .filter_by(job_id=job_id)
        .order_by(Candidate.embedding.cosine_distance(query_embedding))
        .limit(limit)
    ).all()
    
    results = []
    for c in candidates:
        # Get analysis for this candidate/job
        analysis = Analysis.query.filter_by(candidate_id=c.id, job_id=job_id).first()
        match_score = analysis.final_score if analysis else 0 # Fallback
        
        results.append({
            'id': c.id,
            'name': c.name,
            'match_score': match_score,
        })
        
    return jsonify(results)

@bp.route('/score/<int:candidate_id>', methods=['GET'])
@login_required
def score(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    if candidate.job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    analysis = Analysis.query.filter_by(candidate_id=candidate.id).first()
    if not analysis:
        return jsonify({'error': 'Analysis not found'}), 404
        
    return jsonify({
        'candidate_id': candidate.id,
        'job_id': candidate.job_id,
        'final_score': analysis.final_score,
        'similarity': analysis.similarity,
        'missing_skills': analysis.missing_skills,
        'skills_matched': analysis.skills_matched,
        'phrasing_suggestions': analysis.phrasing_suggestions
    })

@bp.route('/embed', methods=['POST'])
@login_required
def embed():
    text = request.json.get('text')
    if not text:
        return jsonify({'error': 'Missing text'}), 400
        
    embedding = generate_embedding(text)
    return jsonify({
        'embedding': embedding,
        'dimensions': len(embedding)
    })

@bp.route('/seed', methods=['POST'])
@login_required
def seed_data():
    # Only allow if no candidates exist for the current user's jobs to prevent spamming
    # This is a bit of a hack for the user request "seed sample data" via API
    # In a real app, this might be an admin function or behind a special flag
    
    # Check if user owns the job provided
    job_id = request.json.get('job_id')
    if not job_id:
        return jsonify({'error': 'job_id required'}), 400
        
    job = Job.query.get(job_id)
    if not job or job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    # Seed dummy candidates
    dummy_candidates = [
        {
            "name": "Alice Python",
            "email": "alice@example.com",
            "resume_text": "Experienced Python Developer with Flask and PostgreSQL skills. Love working with AI.",
            "skills": ["python", "flask", "postgresql", "ai"]
        },
        {
            "name": "Bob Java",
            "email": "bob@example.com",
            "resume_text": "Java expert. Good at Spring Boot. Knowledge of SQL.",
            "skills": ["java", "spring boot", "sql"]
        }
    ]
    
    from ..pipeline import match_skills, compute_final_score
    import numpy as np
    
    seeded_ids = []
    
    for d in dummy_candidates:
        embedding = generate_embedding(d['resume_text'])
        
        # Scoring
        job_skills = job.required_skills or []
        matched, missing, skills_score = match_skills(d['skills'], job_skills)
        
        final_score, semantic_score = compute_final_score(
            job.embedding, 
            embedding, 
            skills_score
        )
        
        cand = Candidate(
            name=d['name'], 
            email=d['email'], 
            resume_text=d['resume_text'],
            skills=d['skills'],
            embedding=embedding,
            job_id=job.id
        )
        db.session.add(cand)
        db.session.flush()
        
        analysis = Analysis(
            candidate_id=cand.id,
            job_id=job.id,
            similarity=semantic_score,
            missing_skills=missing,
            skills_matched=matched,
            final_score=final_score,
            phrasing_suggestions={"suggestions": ["Auto-generated candidate"]}
        )
        db.session.add(analysis)
        seeded_ids.append(cand.id)
        
    db.session.commit()
    
@bp.route('/webhooks/google-form', methods=['POST'])
def google_form_webhook():
    """
    Webhook to receive candidate data from Google Forms via Google Apps Script.
    """
    # Security: Verify API Key
    # In production, use os.environ.get('WEBHOOK_SECRET')
    import os
    expected_key = os.environ.get('WEBHOOK_SECRET', 'skillvector_secret_key_2026')
    provided_key = request.headers.get('X-API-Key')
    
    if provided_key != expected_key:
        return jsonify({'error': 'Unauthorized: Invalid API Key'}), 401

    data = request.json
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    # Validation: Name is the only strictly required field for the DB (resume_text is also required but we can fallback)
    if 'name' not in data:
         # Try to be smart? No, just error or generic name
         return jsonify({'error': 'Missing field: name'}), 400
         
    # Fallback for resume_text if missing (e.g. file upload only)
    if 'resume_text' not in data or not data['resume_text']:
        if 'resume_url' in data:
            data['resume_text'] = f"Resume file uploaded at: {data['resume_url']}\n(Automatic text extraction from Drive link is not yet configured)"
        else:
            data['resume_text'] = "No resume text provided."

    # Optional: Logic to find a default job_id if not provided
    # For now, we accept job_id if sent, else it might be None
    job_id = data.get('job_id')
    
    # Create Candidate
    candidate = Candidate(
        name=data['name'],
        email=data.get('email'),
        resume_text=data['resume_text'],
        source='Google Forms',
        processing_status='pending',
        job_id=job_id,
        phone=data.get('phone'),
        linkedin_url=data.get('linkedin_url'),
        github_url=data.get('github_url')
    )
    
    # Store other known fields in extracted_data for reference
    extras = {}
    if 'college' in data: extras['college'] = data['college']
    if 'department' in data: extras['department'] = data['department']
    if 'job_title' in data: extras['job_title'] = data['job_title']
    if 'resume_url' in data: extras['resume_url'] = data['resume_url']
    
    if extras:
        candidate.extracted_data = extras
    
    db.session.add(candidate)
    db.session.commit()
    
    # Trigger background processing
    from .. import executor
    from ..services import process_candidate_background
    
    # We need a job_id for full processing (matching). If none, we might just analyze generic data.
    if job_id:
        executor.submit(process_candidate_background, candidate.id, job_id)
    else:
        # Try to find a default job or skip matching
        # For now, let's just log it or pick the first job as fallback
        job = Job.query.first()
        if job:
            candidate.job_id = job.id
            db.session.commit()
            executor.submit(process_candidate_background, candidate.id, job.id)
    
    return jsonify({'message': 'Candidate received', 'id': candidate.id}), 201
