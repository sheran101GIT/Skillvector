from .db import db
from flask_login import UserMixin
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(128), unique=True, nullable=False)
    username = db.Column(db.String(64), unique=True, nullable=False) # Keeping for Flask-Login compat if needed, or map email to it
    name = db.Column(db.String(128))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), default="recruiter")
    
    jobs = db.relationship('Job', backref='recruiter', lazy=True)

class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, nullable=False)
    required_skills = db.Column(ARRAY(db.String))
    embedding = db.Column(Vector(384))
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    recruiter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # New Fields for Job Management
    location = db.Column(db.String(128))
    department = db.Column(db.String(128))
    experience_range = db.Column(db.String(64)) # e.g. "3-5 years"
    is_active = db.Column(db.Boolean, default=True)
    
    candidates = db.relationship('Candidate', backref='job', lazy=True) # This might change if many-to-many
    analyses = db.relationship('Analysis', backref='job', lazy=True, cascade="all, delete-orphan")

class Candidate(db.Model):
    __tablename__ = 'candidates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128))
    resume_text = db.Column(db.Text, nullable=False)
    skills = db.Column(ARRAY(db.String))
    github_url = db.Column(db.String(256))
    linkedin_url = db.Column(db.String(256))
    
    # New Fields for Detailed Analysis
    phone = db.Column(db.String(64))
    location = db.Column(db.String(128))
    education = db.Column(JSONB) # List of dicts
    work_experience = db.Column(JSONB) # List of dicts
    projects = db.Column(JSONB) # List of dicts
    certificates = db.Column(JSONB) # List of dicts
    extracted_data = db.Column(JSONB) # Full JSON dump for backup

    embedding = db.Column(Vector(384))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Async processing status
    processing_status = db.Column(db.String(32), default='pending') # pending, processing, completed, failed
    error_message = db.Column(db.Text)
    
    # Review/Email Status
    review_status = db.Column(db.String(32), default='pending') # pending, sent

    # Decision Status
    decision_status = db.Column(db.String(32), default='pending') # pending, approved, rejected
    experience_years = db.Column(db.Integer, default=0)
    
    # Journey tracking fields
    source = db.Column(db.String(64), default='Manual Upload')  # Google Forms, Manual Upload, LinkedIn, etc.
    current_stage = db.Column(db.String(64), default='applied')  # applied, screening, interview_scheduled, interview_completed, offer_extended, joined, rejected
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Optional: Link to job if 1:N, or use Analysis for M:N
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=True)

    analyses = db.relationship('Analysis', backref='candidate', lazy=True, cascade="all, delete-orphan")
    journey_stages = db.relationship('CandidateJourney', backref='candidate', lazy=True, order_by='CandidateJourney.created_at', cascade="all, delete-orphan")

    @property
    def analysis(self):
        """Helper to get the primary analysis (assuming 1 per candidate for now)"""
        if self.analyses:
            # Return the most recent one if multiple, or just the first
            return self.analyses[-1] 
        return None

class Analysis(db.Model):
    __tablename__ = 'analyses'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    similarity = db.Column(db.Float)
    missing_skills = db.Column(ARRAY(db.String))
    skills_matched = db.Column(ARRAY(db.String))
    phrasing_suggestions = db.Column(JSONB)
    final_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Note(db.Model):
    __tablename__ = 'notes'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    recruiter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    note_text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32)) # e.g., 'shortlisted', 'rejected'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class CandidateJourney(db.Model):
    """Tracks each stage transition in a candidate's application journey"""
    __tablename__ = 'candidate_journeys'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    stage = db.Column(db.String(64), nullable=False)  # applied, screening, interview_scheduled, interview_completed, offer_extended, joined, rejected
    notes = db.Column(db.Text)  # Description of what happened at this stage
    score = db.Column(db.Float)  # Optional score at this stage (e.g., 8/10)
    interviewer = db.Column(db.String(128))  # Optional interviewer name
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class JobTemplate(db.Model):
    __tablename__ = 'job_templates'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False) # Template Name
    job_title = db.Column(db.String(128)) 
    description = db.Column(db.Text)
    required_skills = db.Column(ARRAY(db.String))
    department = db.Column(db.String(128))
    experience_range = db.Column(db.String(64))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GoogleFormConnection(db.Model):
    __tablename__ = 'google_form_connections'
    id = db.Column(db.Integer, primary_key=True)
    recruiter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    form_url = db.Column(db.String(512), nullable=False)
    form_title = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_sync = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    job = db.relationship('Job', backref=db.backref('google_forms', lazy=True))


class ReviewEmail(db.Model):
    """Stores LLM-generated candidate review emails with their input snapshot."""
    __tablename__ = 'review_emails'
    id                   = db.Column(db.Integer, primary_key=True)
    candidate_id         = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    job_id               = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    generated_by         = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Snapshot of what was fed to the LLM (for audit/debug)
    stage_notes_snapshot = db.Column(db.Text)       # concatenated journey notes
    analysis_snapshot    = db.Column(JSONB)          # scores + skills at generation time

    # LLM Output
    email_subject        = db.Column(db.String(256))
    email_body           = db.Column(db.Text)
    decision             = db.Column(db.String(32))  # 'selected' or 'rejected'

    # Lifecycle tracking
    status               = db.Column(db.String(32), default='draft')  # draft, copied, sent
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    candidate = db.relationship('Candidate', backref=db.backref('review_emails', lazy=True))
    job       = db.relationship('Job',       backref=db.backref('review_emails', lazy=True))

