from app import create_app, db
from app.models import Candidate

app = create_app()
with app.app_context():
    recent = Candidate.query.order_by(Candidate.id.desc()).limit(5).all()
    print("-" * 30)
    for c in recent:
        print(f"ID: {c.id} | Name: {c.name} | Source: {c.source} | Status: {c.processing_status} | Created: {c.created_at}")
    print("-" * 30)
