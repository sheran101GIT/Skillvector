import time
import sys
import os
import numpy as np

# Add project root to path
sys.path.append(os.getcwd())

from app import create_app
from app.pipeline import preprocess_text, extract_skills, compute_final_score

# Mock Embedding Helper (since we might not want to spend API credits or keys might be missing)
def mock_generate_embedding(text):
    time.sleep(0.4) # Simulate network call
    return np.random.rand(384).tolist()

def benchmark():
    app = create_app()
    
    print("--- Starting SkillVector HR Performance Benchmark ---")
    
    # Sample Data
    sample_resume = """
    EXPERIENCED PYTHON DEVELOPER
    John Doe
    New York, NY | (555) 123-4567 | john.doe@email.com
    
    SUMMARY
    Senior Software Engineer with 7 years of experience in Python, Flask, and Cloud Computing.
    
    SKILLS
    - Programming: Python, JavaScript, SQL, C++
    - Web: Flask, Django, React, HTML5, CSS3
    - Database: PostgreSQL, MongoDB, Redis
    - Cloud: AWS, Docker, Kubernetes
    
    EXPERIENCE
    Senior Backend Engineer | TechCorp | 2020 - Present
    - Built microservices using Flask and Docker
    - Optimized PostgreSQL queries reducing latency by 40%
    """
    
    sample_job_emb = np.random.rand(384).tolist()
    
    # 1. Preprocessing and OCR Simulation
    start = time.time()
    clean_text = preprocess_text(sample_resume)
    t_preprocess = time.time() - start
    print(f"[Metric] Preprocessing Time: {t_preprocess:.4f}s")
    
    # 2. Skill Extraction (Local NLP)
    start = time.time()
    skills = extract_skills(clean_text)
    t_extraction = time.time() - start
    print(f"[Metric] Skill Extraction Time: {t_extraction:.4f}s")
    print(f"   -> Extracted {len(skills)} skills")
    
    # 3. Embedding Generation (Simulated)
    start = time.time()
    # In real app we call generate_embedding(clean_text), here we mock to test system overhead
    # valid_embedding = generate_embedding(clean_text) 
    emb = mock_generate_embedding(clean_text) 
    t_embedding = time.time() - start
    print(f"[Metric] Embedding Generation (Simulated Network): {t_embedding:.4f}s")
    
    # 4. Scoring Computation
    start = time.time()
    final, semantic = compute_final_score(sample_job_emb, emb, 0.8)
    t_scoring = time.time() - start
    print(f"[Metric] Scoring Logic Time: {t_scoring:.4f}s")
    
    # Total End-to-End Estimate
    total = t_preprocess + t_extraction + t_embedding + t_scoring
    print(f"--- Total Pipeline Latency: {total:.4f}s ---")

if __name__ == "__main__":
    benchmark()
