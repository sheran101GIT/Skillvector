import sys
import os

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, Job
from werkzeug.security import generate_password_hash
from app.pipeline import generate_embedding

app = create_app()

def seed():
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Check if user exists
        if User.query.filter_by(username='recruiter').first():
            print("Database already seeded.")
            return

        # Create Recruiter
        user = User(
            username='recruiter', 
            email='recruiter@example.com',
            name='John Doe',
            password_hash=generate_password_hash('password')
        )
        db.session.add(user)
        db.session.commit()
        
        print("Created user 'recruiter' with password 'password'")
        
        # Create a sample Job
        desc = "We are looking for a Senior Python Developer with experience in Flask, PostgreSQL, and AI."
        job = Job(
            title="Senior Python Developer",
            description=desc,
            required_skills=['Python', 'Flask', 'PostgreSQL', 'AI'],
            embedding=generate_embedding(desc),
            recruiter_id=user.id
        )
        db.session.add(job)
        db.session.commit()
        
        print("Created sample job 'Senior Python Developer'")

if __name__ == '__main__':
    seed()
