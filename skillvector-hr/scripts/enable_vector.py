import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        print("Enabling vector extension...")
        db.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.session.commit()
        print("Vector extension enabled successfully.")
    except Exception as e:
        print(f"Failed to enable extension: {e}")
