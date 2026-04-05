
import sys
import os
sys.path.append(os.getcwd())

from app import create_app, db
from sqlalchemy import text

print("Creating app...")
app = create_app()
print("App created.")

with app.app_context():
    print(f"DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    try:
        print("Testing DB connection...")
        db.session.execute(text("SELECT 1"))
        print("DB connection successful.")
    except Exception as e:
        print(f"DB connection failed: {e}")
