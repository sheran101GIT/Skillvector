"""
cleanup_seed.py
---------------
Removes the demo seed data (John Doe / recruiter@example.com) that was inserted
by seed_db.py from the Render production database.

Run from the skillvector-hr directory:
    python scripts/cleanup_seed.py
"""

import sys
import os

# Allow running from scripts/ OR skillvector-hr/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

# ── Render external database URL ────────────────────────────────────────────
DATABASE_URL = (
    "postgresql://skillvector_db_q1s9_user:avZV1Qih58W8ucIvd3NaJlyyCaFikhnZ"
    "@dpg-d7q8oc9ugtpc73aqm8h0-a.singapore-postgres.render.com/skillvector_db_q1s9"
)

SEED_USERNAME = "recruiter"
SEED_EMAIL    = "recruiter@example.com"


def cleanup():
    print("Connecting to Render database…")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        cur = conn.cursor()

        # 1. Find the seed user
        cur.execute(
            "SELECT id, name, email FROM users WHERE username = %s AND email = %s",
            (SEED_USERNAME, SEED_EMAIL),
        )
        row = cur.fetchone()

        if not row:
            print("[OK]  Seed user not found - database is already clean.")
            cur.close()
            conn.close()
            return

        user_id, user_name, user_email = row
        print(f"Found seed user: id={user_id}, name='{user_name}', email='{user_email}'")

        # 2. Find jobs owned by the seed user
        cur.execute("SELECT id, title FROM jobs WHERE recruiter_id = %s", (user_id,))
        jobs = cur.fetchall()
        job_ids = [j[0] for j in jobs]
        print(f"Found {len(jobs)} seeded job(s): {[j[1] for j in jobs]}")

        if job_ids:
            # 3. Delete analyses linked to those jobs
            cur.execute(
                "DELETE FROM analyses WHERE job_id = ANY(%s)",
                (job_ids,),
            )
            print(f"  Deleted analyses for seeded jobs.")

            # 4. Delete review_emails linked to those jobs
            cur.execute(
                "DELETE FROM review_emails WHERE job_id = ANY(%s)",
                (job_ids,),
            )
            print(f"  Deleted review_emails for seeded jobs.")

            # 5. Find candidates linked to seeded jobs
            cur.execute(
                "SELECT id FROM candidates WHERE job_id = ANY(%s)",
                (job_ids,),
            )
            cand_ids = [r[0] for r in cur.fetchall()]

            if cand_ids:
                # Delete candidate journey stages
                cur.execute(
                    "DELETE FROM candidate_journeys WHERE candidate_id = ANY(%s)",
                    (cand_ids,),
                )
                # Delete the candidates themselves
                cur.execute(
                    "DELETE FROM candidates WHERE id = ANY(%s)",
                    (cand_ids,),
                )
                print(f"  Deleted {len(cand_ids)} candidate(s) linked to seeded jobs.")

            # 6. Delete notes linked to seeded jobs
            cur.execute(
                "DELETE FROM notes WHERE job_id = ANY(%s)",
                (job_ids,),
            )

            # 7. Delete Google Form connections for seeded jobs
            cur.execute(
                "DELETE FROM google_form_connections WHERE job_id = ANY(%s)",
                (job_ids,),
            )

            # 8. Delete job templates created by seed user
            cur.execute(
                "DELETE FROM job_templates WHERE created_by = %s",
                (user_id,),
            )

            # 9. Delete the seeded jobs
            cur.execute(
                "DELETE FROM jobs WHERE recruiter_id = %s",
                (user_id,),
            )
            print(f"  Deleted {len(jobs)} seeded job(s).")

        # 10. Finally delete the seed user
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        print(f"  Deleted seed user '{user_name}' (id={user_id}).")

        conn.commit()
        print("\n[DONE] Cleanup complete! The demo 'John Doe' data has been removed.")
        print("       You can now register and log in with your real account.")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Error during cleanup: {e}")
        raise
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    print("=" * 60)
    print("  SkillVector - Render Seed Cleanup")
    print("=" * 60)
    confirm = input(
        "\nThis will permanently delete the demo 'John Doe / recruiter' account\n"
        "and all data linked to it from the Render database.\n\n"
        "Type 'yes' to continue: "
    ).strip().lower()

    if confirm == "yes":
        cleanup()
    else:
        print("Aborted.")
