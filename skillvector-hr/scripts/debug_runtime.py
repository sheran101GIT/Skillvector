
import sys
import os

print("Starting checks...", flush=True)
sys.path.append(os.getcwd())

from app import create_app, db
from sqlalchemy import text

print("Calling create_app()...", flush=True)
app = create_app()
print("create_app() returned.", flush=True)

print("Checking DB URI...", flush=True)
with app.app_context():
    print(f"DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    print("Testing DB connection...", flush=True)
    try:
        db.session.execute(text("SELECT 1"))
        print("DB connection successful.", flush=True)
    except Exception as e:
        print(f"DB connection failed: {e}", flush=True)

print("Done.", flush=True)
