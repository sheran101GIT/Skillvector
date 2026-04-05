
import sys
import os

print("Starting imports...", flush=True)
sys.path.append(os.getcwd())

print("Importing flask...", flush=True)
import flask
print("Flask imported.", flush=True)

print("Importing flask_migrate...", flush=True)
import flask_migrate
print("Flask-Migrate imported.", flush=True)

print("Importing sqlalchemy...", flush=True)
import sqlalchemy
print("SQLAlchemy imported.", flush=True)

print("Importing pgvector...", flush=True)
try:
    import pgvector
    print("pgvector imported.", flush=True)
except ImportError:
    print("pgvector import failed (not installed?).", flush=True)

print("Importing local app package...", flush=True)
try:
    import app
    print("app package imported.", flush=True)
except Exception as e:
    print(f"app import failed: {e}", flush=True)

print("Importing app.create_app...", flush=True)
try:
    from app import create_app
    print("create_app imported.", flush=True)
except Exception as e:
    print(f"create_app import failed: {e}", flush=True)

print("Done.", flush=True)
