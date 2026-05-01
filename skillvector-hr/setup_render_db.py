import os
import psycopg2
from urllib.parse import urlparse

# Replace this with your Render Internal or External Database URL
# Example: "postgresql://user:password@host/dbname"
DATABASE_URL = "postgresql://skillvector_db_q1s9_user:avZV1Qih58W8ucIvd3NaJlyyCaFikhnZ@dpg-d7q8oc9ugtpc73aqm8h0-a.singapore-postgres.render.com/skillvector_db_q1s9"

def setup_db():
    if DATABASE_URL == "PASTE_YOUR_RENDER_EXTERNAL_DATABASE_URL_HERE":
        print("Please paste your Render External Database URL in the DATABASE_URL variable.")
        return

    try:
        print("Connecting to the database...")
        # Connect to the Render database
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True  # Required to run CREATE EXTENSION
        cur = conn.cursor()

        print("Executing CREATE EXTENSION vector...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        print("Success! The 'vector' extension has been created.")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    setup_db()
