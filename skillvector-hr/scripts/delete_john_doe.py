"""
delete_john_doe.py
------------------
Finds and removes any candidate named 'John Doe' from the Render production database.
Run from the skillvector-hr directory:
    python scripts/delete_john_doe.py
"""

import psycopg2

DATABASE_URL = (
    "postgresql://skillvector_db_q1s9_user:avZV1Qih58W8ucIvd3NaJlyyCaFikhnZ"
    "@dpg-d7q8oc9ugtpc73aqm8h0-a.singapore-postgres.render.com/skillvector_db_q1s9"
)

def find_and_delete():
    print("Connecting to Render database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    # Find all candidates with 'john doe' in their name (case-insensitive)
    cur.execute(
        "SELECT id, name, email, processing_status, created_at FROM candidates WHERE LOWER(name) LIKE %s ORDER BY created_at",
        ('%john doe%',)
    )
    rows = cur.fetchall()

    if not rows:
        print("[OK] No 'John Doe' candidates found in the database. Nothing to delete.")
        cur.close()
        conn.close()
        return

    print(f"\nFound {len(rows)} 'John Doe' candidate(s):\n")
    print(f"{'ID':<6} {'Name':<20} {'Email':<30} {'Status':<15} {'Created At'}")
    print("-" * 90)
    for r in rows:
        print(f"{r[0]:<6} {(r[1] or ''):<20} {(r[2] or 'N/A'):<30} {(r[3] or ''):<15} {r[4]}")

    confirm = input("\nDelete all the above candidates and their related data? Type 'yes' to confirm: ").strip().lower()
    if confirm != 'yes':
        print("Aborted.")
        cur.close()
        conn.close()
        return

    cand_ids = [r[0] for r in rows]

    # Delete dependent records first (FK constraints)
    cur.execute("DELETE FROM analyses       WHERE candidate_id = ANY(%s)", (cand_ids,))
    cur.execute("DELETE FROM review_emails  WHERE candidate_id = ANY(%s)", (cand_ids,))
    cur.execute("DELETE FROM candidate_journeys WHERE candidate_id = ANY(%s)", (cand_ids,))
    cur.execute("DELETE FROM notes          WHERE candidate_id = ANY(%s)", (cand_ids,))
    cur.execute("DELETE FROM candidates     WHERE id = ANY(%s)", (cand_ids,))

    conn.commit()
    print(f"\n[DONE] Deleted {len(cand_ids)} 'John Doe' candidate(s) and all related data.")
    print("       Refresh your deployed app - the report should be gone.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("  SkillVector - Delete John Doe Candidate(s)")
    print("=" * 60)
    try:
        find_and_delete()
    except Exception as e:
        print(f"[ERROR] {e}")
        raise
