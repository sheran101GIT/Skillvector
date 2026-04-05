import logging
import traceback
from app import db
from app.models import Candidate, Analysis, Job
from app.pipeline import preprocess_text, generate_embedding, extract_skills, match_skills, compute_final_score, get_phrasing_suggestions, extract_experience, extract_candidate_details

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_candidate_background(candidate_id, job_id, upload_request_context_app=None):
    """
    Background task to process a candidate.
    Must be called within an application context if relying on Flask extensions like SQLAlchemy.
    Flask-Executor handles context automatically if configured correctly, but we ensure it here.
    """
    logger.info(f"Starting background processing for Candidate {candidate_id}")
    
    try:
        # Re-query objects to ensure they are attached to the current session
        candidate = Candidate.query.get(candidate_id)
        job = Job.query.get(job_id)
        
        if not candidate or not job:
            logger.error("Candidate or Job not found in background task.")
            return

        candidate.processing_status = 'processing'
        db.session.commit()

        # --- 1. Preprocess ---
        # The text is already stored in resume_text (raw) on upload, 
        # or we might want to store raw and clean separately. 
        # For now, let's assume what's in resume_text needs cleaning if not done yet.
        # But looking at the synchronous code, it cleaned BEFORE creating the candidate.
        # So we can just use candidate.resume_text if it was already cleaned, 
        # OR we refactor the upload to save RAW text and clean here.
        # Let's assume we save RAW text now in the route, so we clean here.
        
        clean_text = preprocess_text(candidate.resume_text)
        
        # --- 2. AI Analysis (Heavy) ---
        embedding = generate_embedding(clean_text)
        extracted_skills = extract_skills(clean_text)
        experience_years = extract_experience(clean_text)
        extracted_skills = extract_skills(clean_text)
        experience_years = extract_experience(clean_text)
        candidate.experience_years = experience_years
        
        # --- 2.5 Extract Detailed Info (New) ---
        details = extract_candidate_details(clean_text)
        
        if 'error' in details:
            logger.warning(f"Candidate details extraction failed: {details['error']}")
            # We don't fail the whole process, just note it.
            # Append to error message if it exists, or create new
            current_err = candidate.error_message or ""
            candidate.error_message = f"{current_err} [Detail Extraction: {details['error']}]".strip()
        else:
            # Update name if extracted and different from filename-based name
            extracted_name = details.get('name')
            if extracted_name and extracted_name.strip():
                candidate.name = extracted_name.strip()
            
            candidate.phone = details.get('phone')
            candidate.location = details.get('location')
            if details.get('email'): 
                 candidate.email = details.get('email')
            if details.get('linkedin_url'):
                 candidate.linkedin_url = details.get('linkedin_url')
            if details.get('github_url'):
                 candidate.github_url = details.get('github_url')
                 
            candidate.education = details.get('education')
            candidate.work_experience = details.get('work_experience')
            candidate.projects = details.get('projects')
            candidate.certificates = details.get('certificates')
            
        candidate.extracted_data = details
        
        # --- 3. Matching - pass resume text for direct skill search ---
        job_skills = job.required_skills or []
        matched, missing, skills_score = match_skills(extracted_skills, job_skills, candidate.resume_text)
        
        # --- 4. Phrasing (Optional & Slow) ---
        phrasing_data = get_phrasing_suggestions(clean_text, job.description)
        phrasing_score = phrasing_data.get('score', 0.5)  # Default to 0.5, not 0.8
        phrasing_suggestions = phrasing_data.get('suggestions', [])

        
        # --- 5. Scoring ---
        final_score, semantic_score = compute_final_score(
            job.embedding, 
            embedding, 
            skills_score, 
            phrasing_score
        )
        
        # --- 6. Update Candidate & Create Analysis ---
        # --- 6. Update Candidate & Create Analysis ---
        candidate.embedding = embedding
        
        # Merge skills from Regex (extracted_skills) and LLM (details.get('skills'))
        llm_skills = details.get('skills', []) if isinstance(details.get('skills'), list) else []
        # Normalize and deduplicate
        all_skills = set()
        for s in extracted_skills:
            all_skills.add(s.lower())
        for s in llm_skills:
            if isinstance(s, str):
                all_skills.add(s.lower())
                
        candidate.skills = list(all_skills)
        # If we want to store the cleaned text back:
        candidate.resume_text = clean_text 
        
        analysis = Analysis(
            candidate_id=candidate.id,
            job_id=job.id,
            similarity=semantic_score,
            missing_skills=missing,
            skills_matched=matched,
            final_score=final_score,
            phrasing_suggestions=phrasing_suggestions
        )
        db.session.add(analysis)
        
        candidate.processing_status = 'completed'
        db.session.commit()
        
        logger.info(f"Successfully processed Candidate {candidate_id}")

    except Exception as e:
        logger.error(f"Error processing candidate {candidate_id}: {str(e)}")
        logger.error(traceback.format_exc())
        
        # We need to rollback to be safe, then update status
        db.session.rollback()
        
        # Re-fetch to update status safely
        candidate = Candidate.query.get(candidate_id)
        if candidate:
            candidate.processing_status = 'failed'
            candidate.error_message = str(e)
            db.session.commit()
