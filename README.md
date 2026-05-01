<div align="center">
  <h1>🚀 SkillVector</h1>
  <p><b>An AI-Powered Applicant Tracking & Resume Screening System for Modern HR Teams</b></p>
  
  <a href="https://skillvector-app.onrender.com"><strong>Check out the Live Demo</strong></a>
  <br>
</div>

<hr>

## 📖 Overview

SkillVector is a next-generation HR application designed to modernize and streamline the recruitment workflow. By harmonizing **deterministic NLP** (for precise fact extraction) with **probabilistic Large Language Models (LLMs)** (for semantic reasoning), SkillVector significantly reduces the manual effort required in screening candidates. 

It automatically parses resumes, semantically matches candidates against job requirements, tracks their journey through the interview pipeline, and even generates personalized review emails using AI.

## ✨ Key Features

- **🧠 Smart Resume Parsing**: Effortlessly extracts structured candidate data (skills, education, work experience, projects) from uploaded PDFs and DOCX files.
- **🎯 Semantic Matching**: Uses vector embeddings (`sentence-transformers`) and PostgreSQL `pgvector` to move beyond simple keyword matching, understanding the true context of a candidate's skills against job descriptions.
- **📊 Detailed AI Analysis**: Generates deep insights including similarity scores, missing skills, matched skills, and tailored phrasing suggestions using advanced LLMs (OpenAI, Google Gemini, Groq).
- **🛤️ Candidate Journey Tracking**: Easily move candidates through customizable stages (Applied, Screening, Interview, Offer, Rejected) and maintain a central source of truth with stage-specific notes.
- **✉️ Automated Contextual Emails**: Automatically draft highly personalized selection or rejection emails based on the candidate's journey notes and AI analysis.
- **🔗 Google Forms Integration**: Connect your job postings directly to Google Forms for seamless candidate intake.

## 🛠️ Technology Stack

**Backend & Core:**
- **Framework:** Python, Flask, Flask-SQLAlchemy, Flask-Login
- **Database:** PostgreSQL with `pgvector` extension for high-performance similarity search
- **Asynchronous Processing:** Flask-Executor

**AI & Machine Learning:**
- **NLP & Parsing:** `spacy`, `pdfplumber`, `python-docx`
- **Embeddings:** `sentence-transformers` (384-dimensional vectors)
- **Generative AI Providers:** `openai`, `google-generativeai`, `groq`

**Deployment:**
- Hosted on **Render** using Gunicorn.

## 🚀 Local Setup & Installation

### Prerequisites
- Python 3.9+
- PostgreSQL database (with the `vector` extension installed)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/SkillVector.git
cd SkillVector/skillvector-hr
```

### 2. Set up the Python Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Database Configuration

Ensure PostgreSQL is running locally or accessible via a remote URI.
Create a database named `skillvector_hr` and enable the vector extension:

```sql
CREATE DATABASE skillvector_hr;
\c skillvector_hr
CREATE EXTENSION IF NOT EXISTS vector;
```

### 4. Environment Variables

Create a `.env` file in the `skillvector-hr` directory. You will need to configure your database URI and API keys for the LLM providers:

```env
SECRET_KEY=your_secret_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/skillvector_hr

# AI API Keys
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
```

### 5. Run Migrations

Initialize and migrate the database schema:

```bash
flask db upgrade
```

### 6. Run the Application

Start the Flask development server:

```bash
flask run
```

The application should now be accessible at `http://127.0.0.1:5000/`.

## 🧠 Architecture Overview

SkillVector leverages a **Hybrid AI Architecture**:
1. **Extraction Layer**: Tools like `pdfplumber` and `spaCy` deterministically extract raw text and entities.
2. **Embedding Layer**: Local transformer models convert text into dense vector representations.
3. **Database Layer**: `pgvector` performs highly efficient cosine-similarity searches to rank candidates.
4. **Generative Layer**: External LLMs synthesize the extracted facts and similarity scores into human-readable insights, summaries, and email drafts.

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](#) if you want to contribute.

## 📝 License

This project is open-source and available under the [MIT License](LICENSE).
