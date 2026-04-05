import os
import io
import re
import json
import numpy as np

# Lazy loaded imports
# from pypdf import PdfReader
# from docx import Document
# from sentence_transformers import SentenceTransformer
# import spacy
# from rapidfuzz import process, fuzz
# from openai import OpenAI
# from sklearn.metrics.pairwise import cosine_similarity

# Load spaCy model lazily
nlp = None

# Initialize OpenAI client lazily
openai_client = None

# Initialize SBERT model lazily
sbert_model = None

# Load spaCy model lazily
nlp = None

# Initialize OpenAI client lazily
openai_client = None

# Initialize SBERT model lazily
sbert_model = None

# --- Text Extraction ---

def extract_text_from_pdf(file_stream):
    from pypdf import PdfReader
    reader = PdfReader(file_stream)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text.strip()

def extract_text_from_docx(file_stream):
    from docx import Document
    doc = Document(file_stream)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text.strip()

# --- Preprocessing ---

def preprocess_text(text):
    # Lowercase
    text = text.lower()
    # Normalize bullets
    text = re.sub(r'[•\-*]', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# --- Skill Extraction ---

COMMON_SKILLS_DB = [
    # Languages
    'python', 'java', 'c++', 'c', 'c#', 'javascript', 'typescript', 'html', 'css', 'php', 'ruby', 'go', 'golang', 'rust', 'swift', 'kotlin', 'scala', 'perl', 'bash', 'shell', 'sql',
    # Frontend
    'react', 'react.js', 'angular', 'angularjs', 'vue', 'vue.js', 'svelte', 'next.js', 'nuxt.js', 'ember.js', 'backbone.js', 'jquery', 'bootstrap', 'tailwind', 'material ui',
    # Backend
    'flask', 'django', 'fastapi', 'spring', 'spring boot', 'node.js', 'express', 'express.js', 'nest.js', 'asp.net', '.net', 'laravel', 'rails', 'ruby on rails',
    # Database
    'postgresql', 'mysql', 'sqlite', 'mongodb', 'redis', 'elasticsearch', 'dynamodb', 'cassandra', 'oracle', 'mssql', 'firebase', 'supabase',
    # DevOps/Cloud
    'docker', 'kubernetes', 'aws', 'amazon web services', 'azure', 'gcp', 'google cloud', 'git', 'gitlab', 'github', 'ci/cd', 'jenkins', 'circleci', 'travis ci', 'github actions', 'terraform', 'ansible',
    # AI/ML
    'machine learning', 'deep learning', 'nlp', 'computer vision', 'pytorch', 'tensorflow', 'keras', 'scikit-learn', 'pandas', 'numpy', 'matplotlib', 'seaborn', 'opencv', 'hugging face', 'transformers', 'llm', 'generative ai', 'openai', 'langchain',
    # Other
    'agile', 'scrum', 'kanban', 'jira', 'confluence', 'linux', 'unix', 'rest api', 'graphql', 'websockets', 'microservices', 'serverless', 'distributed systems', 'system design',
    # Soft Skills
    'communication', 'leadership', 'problem solving', 'teamwork', 'critical thinking', 'time management'
]

def extract_skills(text):
    """
    Extracts skills using spaCy for noun chunks and fuzzy matching against a DB.
    """
    global nlp
    if nlp is None:
        try:
             print("Loading SpaCy model...", flush=True)
             import spacy
             nlp = spacy.load("en_core_web_sm")
        except:
             print("Downloading SpaCy model...", flush=True)
             print("Downloading SpaCy model...", flush=True)
             from spacy.cli import download
             download("en_core_web_sm")
             import spacy
             nlp = spacy.load("en_core_web_sm")

    doc = nlp(text)
    found_skills = set()
    
    # 1. Regex match with word boundaries (avoids "java" in "javascript")
    text_lower = text.lower()
    for skill in COMMON_SKILLS_DB:
        # Escape special characters like +, ., #
        # Match word boundaries \b, but note that \b doesn't work well with C++ or C# or .NET
        # Manual boundary check or custom regex
        
        pattern = re.escape(skill)
        
        # Determine strictness based on skill chars
        # If skill contains non-word chars (like ., +, #), standard \b might fail if we are not careful
        # e.g. "c++" -> \bc\+\+\b works? \b matches between + and space.
        # But "node.js" -> \bnode\.js\b. . is not a word char properly separating.
        
        # Simplified robust approach:
        # Check if the skill is surrounded by non-word characters or start/end of string.
        # We replace non-alphanumeric chars in text with spaces for a simpler check? No, that breaks "c++".
        
        # Let's use specific regex for tricky ones, generic for others.
        
        if skill in ['c++', 'c#', '.net']:
             # Strict exact match with whitespace/punctuation boundaries
             p = r'(?:^|[\s,.\(\)\[\]])' + pattern + r'(?:$|[\s,.\(\)\[\]])'
             if re.search(p, text_lower):
                 found_skills.add(skill)
        elif skill == 'c':
             # Special case for C to avoid matching C++ or C#
             # Match 'c' with word boundaries, but NOT followed by + or #
             p = r'\bc\b(?![+#])'
             if re.search(p, text_lower):
                 found_skills.add(skill)
        else:
             # Standard word boundary
             # For "node.js", \b works if . is treated as boundary, usually it is. 
             # \b matches between \w and \W. "node" is \w, "." is \W. So \bnode\.js\b matches "node.js"
             if re.search(r'\b' + pattern + r'\b', text_lower):
                 found_skills.add(skill)

    return list(found_skills)

def extract_candidate_details(text):
    """
    Uses LLM (Gemini or OpenAI) to extract structured candidate details.
    Returns a dict with name, phone, email, location, education, etc.
    """
    prompt = f"""
    You are an expert HR data extractor. Extract the following details from the resume text below:
    1. Full Name (the candidate's name as appears on the resume)
    2. Phone Number
    3. Email Address
    4. Location (City, Country)
    5. Education History (List of degrees, universities, years)
    6. Work Experience (List of roles, companies, years, description)
    7. Projects (List of project titles, descriptions, technologies)
    8. Certificates (List of certificate names, issuers)
    9. LinkedIn/GitHub Links

    Resume Text:
    {text[:8000]}

    Return ONLY a valid JSON object with these keys:
    {{
        "name": "string - the candidate's full name or null if not found",
        "phone": "string or null",
        "email": "string or null",
        "location": "string or null",
        "linkedin_url": "string or null",
        "github_url": "string or null",
        "skills": ["string", "... list of technical skills extracted from resume ..."],
        "education": [ {{ "degree": "...", "institution": "...", "year": "..." }} ],
        "work_experience": [ {{ "role": "...", "company": "...", "duration": "...", "description": "..." }} ],
        "projects": [ {{ "title": "...", "description": "...", "tech_stack": "..." }} ],
        "certificates": [ {{ "name": "...", "issuer": "..." }} ]
    }}
    """
    
    # 1. Try Groq (Primary)
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are an expert HR data extractor. Output JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            msg = f"Groq Extraction Failed: {str(e)}"
            print(msg, flush=True)
            return {"error": msg}

    # 2. Try Google Gemini (Fallback or specific request)
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:
        import time
        import google.generativeai as genai
        genai.configure(api_key=google_key)
        # Using the standard stable model to avoid quota/rate limits
        model_name = 'gemini-1.5-flash'
        
        retries = 3
        base_delay = 2
        
        for attempt in range(retries):
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                return json.loads(response.text)
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Quota exceeded" in err_str:
                    if attempt < retries - 1:
                        sleep_time = base_delay * (2 ** attempt)
                        print(f"Gemini Rate Limit/Quota hit. Retrying in {sleep_time}s...", flush=True)
                        time.sleep(sleep_time)
                        continue
                
                # If it's not a quota error, or we ran out of retries
                msg = f"Gemini Extraction Failed: {err_str}"
                print(msg, flush=True)
                return {"error": msg}

    # 2. Try OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            global openai_client
            if openai_client is None:
                 from openai import OpenAI
                 openai_client = OpenAI(api_key=api_key)

            # Simple retry for OpenAI as well
            for attempt in range(3):
                try:
                    response = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0,
                        response_format={"type": "json_object"}
                    )
                    return json.loads(response.choices[0].message.content)
                except Exception as e:
                    if "429" in str(e) and attempt < 2:
                        time.sleep(2 * (attempt + 1))
                        continue
                    raise e
                    
        except Exception as e:
             msg = f"OpenAI Extraction Failed: {str(e)}"
             print(msg, flush=True)
             return {"error": msg}

    # Fallback
    return {"error": "No valid API keys or Quota Exceeded"}


def extract_experience(text):
    """
    Extracts years of experience using simple regex.
    Returns integer years (max found) or 0.
    """
    # Patterns: "5+ years", "5 years", "10 yrs"
    # match 1-2 digits, optional +, optional space, "year" or "yr"
    matches = re.findall(r'(\d{1,2})\+?\s*(?:years?|yrs?)', text.lower())
    if not matches:
        return 0
    
    # Convert to ints and filter unreasonable numbers (e.g. > 60)
    years = []
    for m in matches:
        try:
            y = int(m)
            if 0 < y < 60:
                years.append(y)
        except:
            pass
            
    return max(years) if years else 0

def match_skills(candidate_skills, job_skills, resume_text=None):
    """
    Matches candidate skills against job skills using:
    1. Fuzzy matching against extracted skills
    2. Direct text search in the resume (if provided)
    Returns (matched_skills, missing_skills, score)
    """
    from rapidfuzz import process, fuzz
    matched = set()
    missing = set()
    
    # Prepare resume text for direct search
    resume_lower = (resume_text or '').lower()
    
    for job_skill in job_skills:
        job_skill_lower = job_skill.lower().strip()
        found = False
        
        # Method 1: Direct text search in resume (most reliable)
        if resume_lower and job_skill_lower in resume_lower:
            found = True
        
        # Method 2: Fuzzy matching against extracted skills
        if not found and candidate_skills:
            match = process.extractOne(job_skill_lower, [s.lower() for s in candidate_skills], scorer=fuzz.token_sort_ratio)
            if match and match[1] >= 80:  # Lowered threshold for better matching
                found = True
        
        # Method 3: Check for partial matches (e.g., "react" in "react.js")
        if not found and resume_lower:
            # Split job skill and check if all parts are in resume
            skill_parts = job_skill_lower.replace('.', ' ').replace('-', ' ').split()
            if all(part in resume_lower for part in skill_parts if len(part) > 2):
                found = True
        
        if found:
            matched.add(job_skill)
        else:
            missing.add(job_skill)
            
    score = len(matched) / len(job_skills) if job_skills else 1.0
    return list(matched), list(missing), score

# --- Embeddings ---

def generate_embedding(text):
    """
    Generates 384-dim embedding using Google Gemini, OpenAI, or Groq.
    """
    # 1. Try Groq
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
             from groq import Groq
             client = Groq(api_key=groq_key)
             completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are an expert HR consultant. Output JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                response_format={"type": "json_object"}
            )
             return json.loads(completion.choices[0].message.content)
        except Exception as e:
             print(f"Groq Phrasing Failed: {e}")

    # 2. Try Google Gemini
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_key)
            
            # Using text-embedding-004 with dimensionality reduction
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text[:9000], # Gemini has large context
                task_type="retrieval_document",
                output_dimensionality=384
            )
            return result['embedding']
        except Exception as e:
            print(f"Gemini Embedding Failed: {e}", flush=True)

    # 2. Try OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            global openai_client
            if openai_client is None:
                 from openai import OpenAI
                 openai_client = OpenAI(api_key=api_key)
                 
            response = openai_client.embeddings.create(
                input=text[:8000],
                model="text-embedding-3-small",
                dimensions=384
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"OpenAI Embedding Failed: {e}", flush=True)
            
    # 3. Fallback / Mock
    print("LOG: Using Mock Embedding", flush=True)
    return [0.0] * 384

# --- Scoring & Phrasing ---

def compute_final_score(job_embedding, cand_embedding, skills_score, phrasing_score=0.5):
    from sklearn.metrics.pairwise import cosine_similarity
    
    # Handle mock embeddings (all zeros) - semantic score should be 0 in this case
    job_emb = np.array(job_embedding).reshape(1, -1)
    cand_emb = np.array(cand_embedding).reshape(1, -1)
    
    # Check if embeddings are valid (not all zeros)
    job_norm = np.linalg.norm(job_emb)
    cand_norm = np.linalg.norm(cand_emb)
    
    if job_norm < 0.01 or cand_norm < 0.01:
        # Mock/invalid embeddings - rely more on skills
        semantic_score = 0.0
    else:
        semantic_score = float(cosine_similarity(job_emb, cand_emb)[0][0])
        # Clamp to reasonable range
        semantic_score = max(0.0, min(1.0, semantic_score))
    
    # Adjusted Weighted Formula - Skills matter more
    # F = 0.40 * Semantic + 0.50 * Skills + 0.10 * Phrasing
    final_score = (0.40 * semantic_score) + (0.50 * skills_score) + (0.10 * phrasing_score)
    
    return final_score, semantic_score


def get_phrasing_suggestions(resume_text, job_description):
    """
    Uses Gemini or OpenAI to generate phrasing suggestions.
    """
    prompt = f"""
    You are an expert HR consultant. Analyze the resume text below against the job description.
    Identify 3 key areas where the candidate phrases their skills poorly.
    Resume: {resume_text[:2000]}
    Job: {job_description[:1000]}
    
    Return JSON format: {{ "score": 0.8, "suggestions": ["suggestion1", "suggestion2"] }}
    """
    
    # 1. Try Groq (Primary)
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are an expert HR consultant. Output JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                response_format={"type": "json_object"}
            )
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            print(f"Groq Phrasing Failed: {e}")

    # 2. Try Google Gemini (Secondary)
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            
            # Clean response (remove markdown backticks)
            text = response.text.strip()
            if text.startswith('```json'):
                text = text[7:-3]
            elif text.startswith('```'):
                text = text[3:-3]
            return json.loads(text)
        except Exception as e:
            err_str = str(e)
            print(f"Gemini Phrasing Failed: {err_str}")
            if "429" in err_str or "Quota exceeded" in err_str:
                return {"score": 0.5, "suggestions": ["AI suggestions temporarily unavailable due to usage limits. Please check back later."]}
            return {"score": 0.5, "suggestions": [f"AI Analysis Failed: {err_str}"]}

    # 2. Try OpenAI
    if not os.environ.get("OPENAI_API_KEY"):
         return {"score": 0.5, "suggestions": []} # Silent fail if no keys

    try:
        global openai_client
        if openai_client is None:
             from openai import OpenAI
             openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            response_format={"type": "json_object"},
            timeout=10.0
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Phrasing Error: {e}")
        return {"score": 0.5, "suggestions": []}


def generate_review_email(candidate_id, job_id, decision, generated_by_id=None):
    """
    Generates a professional HR review email using the candidate's journey notes and
    AI analysis data. Saves the result to the review_emails table.

    Args:
        candidate_id (int): The candidate's DB id.
        job_id (int): The job's DB id.
        decision (str): 'selected' or 'rejected'.
        generated_by_id (int): The recruiter's user id (optional).

    Returns:
        dict: { 'email_id', 'subject', 'body' } or { 'error': '...' }
    """
    # Avoid circular import — import models inside function
    from .models import Candidate, Analysis, CandidateJourney, Note, ReviewEmail, Job
    from .db import db

    # ── 1. Load Candidate & Job ──────────────────────────────────────────────
    candidate = Candidate.query.get(candidate_id)
    job       = Job.query.get(job_id)

    if not candidate or not job:
        return {"error": "Candidate or Job not found."}

    # ── 2. Collect Stage Journey Notes ──────────────────────────────────────
    journey_stages = CandidateJourney.query.filter_by(
        candidate_id=candidate_id
    ).order_by(CandidateJourney.created_at).all()

    recruiter_notes = Note.query.filter_by(
        candidate_id=candidate_id, job_id=job_id
    ).order_by(Note.timestamp).all()

    # Build a readable timeline string
    notes_lines = []
    for stage in journey_stages:
        ts = stage.created_at.strftime('%d %b %Y') if stage.created_at else ''
        note_text = stage.notes or '(no note)'
        score_str = f" | Score: {stage.score}/10" if stage.score else ''
        interviewer_str = f" | Interviewer: {stage.interviewer}" if stage.interviewer else ''
        notes_lines.append(f"[{ts}] Stage: {stage.stage}{score_str}{interviewer_str} — {note_text}")

    for n in recruiter_notes:
        ts = n.timestamp.strftime('%d %b %Y') if n.timestamp else ''
        notes_lines.append(f"[{ts}] Recruiter Note: {n.note_text}")

    stage_notes_text = "\n".join(notes_lines) if notes_lines else "No recruiter notes recorded."

    # ── 3. Collect Analysis Snapshot ────────────────────────────────────────
    analysis = Analysis.query.filter_by(
        candidate_id=candidate_id, job_id=job_id
    ).order_by(Analysis.created_at.desc()).first()

    analysis_snapshot = {}
    if analysis:
        analysis_snapshot = {
            "final_score":          round((analysis.final_score or 0) * 100, 1),
            "similarity":           round((analysis.similarity or 0) * 100, 1),
            "skills_matched":       analysis.skills_matched or [],
            "missing_skills":       analysis.missing_skills or [],
            "phrasing_suggestions": analysis.phrasing_suggestions or []
        }

    score_str      = f"{analysis_snapshot.get('final_score', 'N/A')}%" if analysis_snapshot else "Not analysed"
    skills_matched = ", ".join(analysis_snapshot.get("skills_matched", [])) or "None recorded"
    missing_skills = ", ".join(analysis_snapshot.get("missing_skills", [])) or "None"
    ai_suggestions = ""
    raw_suggestions = analysis_snapshot.get("phrasing_suggestions") or []
    if raw_suggestions:
        # Handle both list format [{original, suggestion}] and dict format {suggestions: [...]}
        if isinstance(raw_suggestions, list):
            # Each item may be a string or a dict with 'suggestion' key
            lines = []
            for item in raw_suggestions[:3]:
                if isinstance(item, dict):
                    lines.append(item.get('suggestion') or item.get('original') or str(item))
                else:
                    lines.append(str(item))
            ai_suggestions = "\n".join(f"- {s}" for s in lines if s)
        elif isinstance(raw_suggestions, dict):
            suggestions = raw_suggestions.get("suggestions", [])
            ai_suggestions = "\n".join(f"- {s}" for s in suggestions[:3]) if suggestions else ""


    # ── 4. Collect Candidate Profile ────────────────────────────────────────
    experience_years = candidate.experience_years or 0

    education_str = ""
    if candidate.education:
        education_str = "; ".join(
            f"{e.get('degree','?')} from {e.get('institution','?')} ({e.get('year','')})"
            for e in (candidate.education or [])[:2]
        )

    latest_role = ""
    if candidate.work_experience:
        we = candidate.work_experience
        if isinstance(we, list) and len(we) > 0:
            r = we[0]
            latest_role = f"{r.get('role','?')} at {r.get('company','?')} ({r.get('duration','')})"

    decision_label = "selected for the next stage / offer" if decision == "selected" else "not moving forward at this time"

    # ── 5. Build Gemini Prompt ───────────────────────────────────────────────
    prompt = f"""You are a professional HR manager writing a formal candidate review email.

CANDIDATE: {candidate.name}
EMAIL: {candidate.email or 'N/A'}
APPLIED FOR: {job.title}
DECISION: {decision.upper()} — {decision_label}
EXPERIENCE: {experience_years} years
EDUCATION: {education_str or 'Not extracted'}
MOST RECENT ROLE: {latest_role or 'Not extracted'}

CANDIDATE JOURNEY NOTES (recruiter observations across all interview stages):
{stage_notes_text}
(CRITICAL: Ensure you explicitly include and highlight the keywords, specific feedback, and points mentioned in these recruiter notes in the email.)

AI MATCH ANALYSIS:
- Overall Match Score: {score_str}
- Matched Skills: {skills_matched}
- Missing Skills: {missing_skills}
- AI Observations:
{ai_suggestions or '  None available'}

INSTRUCTIONS:
Write a professional, warm HR review email addressed to the HR team or hiring manager (internal use).
The email should:
1. Have a clear, specific subject line referencing the candidate name and role
2. Briefly introduce the candidate and the role they applied for
3. Summarise their key strengths based on journey notes and matched skills (3-4 bullet points)
4. Mention any gaps or concerns (based on missing skills or journey notes) if relevant
5. Clearly state the decision ({decision}) with a brief professional rationale
6. Suggest concrete next steps based on the decision
7. Be concise (under 300 words for the body)

Return ONLY a valid JSON object with exactly this format:
{{"subject": "...", "body": "..."}}
Do NOT include markdown or code fences. Return raw JSON only. The `body` MUST be a single plain text string formatted with newlines. Do NOT make `body` a nested dictionary or object."""

    # ── 6. Call LLM (Groq → Gemini → OpenAI) ───────────────────────────────
    email_subject = None
    email_body    = None
    llm_error     = None

    # Try Groq first
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key and not email_subject:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are an HR professional. Output JSON only."},
                    {"role": "user",   "content": prompt}
                ],
                temperature=0.5,
                response_format={"type": "json_object"},
                timeout=30.0
            )
            result = json.loads(completion.choices[0].message.content)
            email_subject = result.get("subject")
            email_body    = result.get("body")
        except Exception as e:
            llm_error = str(e)
            print(f"[ReviewEmail] Groq failed: {e}", flush=True)

    # Fallback: Gemini
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key and not email_subject:
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            result = json.loads(response.text)
            email_subject = result.get("subject")
            email_body    = result.get("body")
        except Exception as e:
            llm_error = str(e)
            print(f"[ReviewEmail] Gemini failed: {e}", flush=True)

    # Fallback: OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key and not email_subject:
        try:
            global openai_client
            if openai_client is None:
                from openai import OpenAI
                openai_client = OpenAI(api_key=openai_key)
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            email_subject = result.get("subject")
            email_body    = result.get("body")
        except Exception as e:
            llm_error = str(e)
            print(f"[ReviewEmail] OpenAI failed: {e}", flush=True)

    if not email_subject or not email_body:
        return {"error": llm_error or "All LLM providers failed or no API keys configured."}

    # Ensure email_body is a string, LLM sometimes outputs dictionaries
    if isinstance(email_body, dict):
        lines = []
        for k, v in email_body.items():
            if isinstance(v, list):
                lines.append(f"{str(k).title()}:\n" + "\n".join(f"- {item}" for item in v))
            else:
                lines.append(f"{str(v)}")
        email_body = "\n\n".join(lines)
    elif isinstance(email_body, list):
        email_body = "\n\n".join(str(i) for i in email_body)

    if not isinstance(email_subject, str):
        email_subject = str(email_subject)

    # ── 7. Save to review_emails table ──────────────────────────────────────
    try:
        review_email = ReviewEmail(
            candidate_id         = candidate_id,
            job_id               = job_id,
            generated_by         = generated_by_id,
            stage_notes_snapshot = stage_notes_text,
            analysis_snapshot    = analysis_snapshot,
            email_subject        = email_subject,
            email_body           = email_body,
            decision             = decision,
            status               = 'draft'
        )
        db.session.add(review_email)
        db.session.commit()

        return {
            "email_id": review_email.id,
            "subject":  email_subject,
            "body":     email_body
        }
    except Exception as e:
        db.session.rollback()
        print(f"[ReviewEmail] DB save failed: {e}", flush=True)
        return {"error": f"DB save failed: {str(e)}"}
