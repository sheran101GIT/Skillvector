"""
Restore a SkillVector database backup into a new PostgreSQL instance.
Works without pg_restore -- uses pure Python (psycopg2).

Usage:
    python scripts/restore_db.py --url "postgresql://user:pass@host/db"
    python scripts/restore_db.py --url "postgresql://user:pass@host/db" --file skillvector_backup_20260528_234730.sql
    python scripts/restore_db.py --url "postgresql://user:pass@host/db" --dry-run
"""

import os
import sys
import re
import argparse
import glob
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def find_latest_backup():
    """Find the most recent backup file in the project root."""
    project_root = os.path.join(os.path.dirname(__file__), '..')
    pattern = os.path.join(project_root, 'skillvector_backup_*.sql')
    backups = sorted(glob.glob(pattern), reverse=True)
    if backups:
        return backups[0]
    return None


def parse_sql_statements(sql_content):
    """
    Parse SQL file into individual statements.
    Handles multi-line INSERT statements with embedded newlines in string values.
    """
    statements = []
    current = []
    in_string = False
    prev_char = ''

    for line in sql_content.split('\n'):
        stripped = line.strip()

        # Skip empty lines and comments (only when not in the middle of a statement)
        if not current and (not stripped or stripped.startswith('--')):
            continue

        current.append(line)
        joined = '\n'.join(current)

        # Simple heuristic: count unescaped single quotes to determine
        # if we're inside a string literal. A statement is complete when
        # it ends with ';' and all quotes are balanced.
        quote_count = 0
        i = 0
        text = joined
        while i < len(text):
            ch = text[i]
            if ch == "'" and (i == 0 or text[i-1] != "'"):
                # Check for escaped quotes ('')
                if i + 1 < len(text) and text[i+1] == "'":
                    i += 2  # Skip escaped quote
                    continue
                quote_count += 1
            i += 1

        # Statement is complete if quotes are balanced and line ends with ;
        if stripped.endswith(';') and quote_count % 2 == 0:
            stmt = joined.strip()
            if stmt and not stmt.startswith('--'):
                statements.append(stmt)
            current = []

    # Handle any remaining statement
    if current:
        stmt = '\n'.join(current).strip()
        if stmt and not stmt.startswith('--'):
            statements.append(stmt)

    return statements


def restore_database(db_url, backup_file, dry_run=False):
    """
    Restores the database from a backup SQL file.
    Executes statements in order: DDL (CREATE/DROP/ALTER), then DATA (INSERT), then SEQUENCES.
    """
    from sqlalchemy import create_engine, text

    # Fix Render's postgres:// vs postgresql:// issue
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    print(f"Reading backup file: {backup_file}")
    with open(backup_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    file_size = os.path.getsize(backup_file)
    print(f"Backup file size: {file_size / 1024:.1f} KB")

    # Parse statements
    statements = parse_sql_statements(sql_content)
    print(f"Parsed {len(statements)} SQL statements")

    # Categorize statements
    extensions = []
    drops = []
    creates = []
    sequences_create = []
    alters = []
    inserts = []
    sequence_resets = []

    for stmt in statements:
        upper = stmt.upper().lstrip()
        if upper.startswith('CREATE EXTENSION'):
            extensions.append(stmt)
        elif upper.startswith('DROP TABLE'):
            drops.append(stmt)
        elif upper.startswith('CREATE TABLE'):
            creates.append(stmt)
        elif upper.startswith('CREATE SEQUENCE'):
            sequences_create.append(stmt)
        elif upper.startswith('ALTER TABLE'):
            alters.append(stmt)
        elif upper.startswith('INSERT INTO'):
            inserts.append(stmt)
        elif upper.startswith('SELECT SETVAL'):
            sequence_resets.append(stmt)
        else:
            # Other statements (handle gracefully)
            inserts.append(stmt)

    print(f"\nStatement breakdown:")
    print(f"  Extensions:      {len(extensions)}")
    print(f"  DROP TABLE:      {len(drops)}")
    print(f"  CREATE TABLE:    {len(creates)}")
    print(f"  CREATE SEQUENCE: {len(sequences_create)}")
    print(f"  ALTER TABLE:     {len(alters)}")
    print(f"  INSERT INTO:     {len(inserts)}")
    print(f"  Sequence resets: {len(sequence_resets)}")

    if dry_run:
        print("\n[DRY RUN] No changes will be made to the database.")
        print("\nStatements that would be executed:")
        for i, stmt in enumerate(extensions + drops + creates + sequences_create + alters + inserts + sequence_resets):
            preview = stmt[:120].replace('\n', ' ')
            print(f"  {i+1}. {preview}...")
        return

    # Confirm before proceeding
    print(f"\n{'='*50}")
    print(f"WARNING: This will modify the database at:")
    print(f"  {db_url[:50]}...")
    print(f"{'='*50}")
    response = input("\nProceed with restore? (yes/no): ").strip().lower()
    if response not in ('yes', 'y'):
        print("Restore cancelled.")
        return

    print(f"\nConnecting to database...")
    engine = create_engine(db_url)

    total = len(extensions) + len(drops) + len(creates) + len(sequences_create) + len(alters) + len(inserts) + len(sequence_resets)
    executed = 0
    errors = 0

    with engine.connect() as conn:
        # Phase 1: Extensions
        if extensions:
            print("\n[Phase 1/7] Creating extensions...")
            for stmt in extensions:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                    executed += 1
                except Exception as e:
                    print(f"  [WARN] Extension: {e}")
                    conn.rollback()
                    errors += 1

        # Phase 2: Drop existing tables (reverse order to respect FK)
        if drops:
            print("[Phase 2/7] Dropping existing tables...")
            for stmt in drops:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                    executed += 1
                except Exception as e:
                    # Table might not exist, that's fine
                    conn.rollback()
                    executed += 1

        # Phase 3: Create tables
        if creates:
            print("[Phase 3/7] Creating tables...")
            for stmt in creates:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                    executed += 1
                    # Extract table name for logging
                    match = re.search(r'CREATE TABLE (\w+)', stmt, re.IGNORECASE)
                    tname = match.group(1) if match else '?'
                    print(f"  Created: {tname}")
                except Exception as e:
                    print(f"  [ERROR] Create table: {e}")
                    conn.rollback()
                    errors += 1

        # Phase 4: Create sequences
        if sequences_create:
            print("[Phase 4/7] Creating sequences...")
            for stmt in sequences_create:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                    executed += 1
                except Exception as e:
                    conn.rollback()
                    executed += 1  # Sequence might already exist

        # Phase 5: Alter tables (FK constraints, defaults)
        if alters:
            print("[Phase 5/7] Adding constraints...")
            for stmt in alters:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                    executed += 1
                except Exception as e:
                    print(f"  [WARN] Alter: {e}")
                    conn.rollback()
                    errors += 1

        # Phase 6: Insert data
        if inserts:
            print("[Phase 6/7] Inserting data...")
            table_counts = {}
            for stmt in inserts:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                    executed += 1
                    # Track per-table counts
                    match = re.search(r'INSERT INTO (\w+)', stmt, re.IGNORECASE)
                    if match:
                        tname = match.group(1)
                        table_counts[tname] = table_counts.get(tname, 0) + 1
                except Exception as e:
                    print(f"  [ERROR] Insert: {str(e)[:100]}")
                    conn.rollback()
                    errors += 1

            for tname, count in table_counts.items():
                print(f"  {tname}: {count} rows inserted")

        # Phase 7: Reset sequences
        if sequence_resets:
            print("[Phase 7/7] Resetting sequences...")
            for stmt in sequence_resets:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                    executed += 1
                except Exception as e:
                    conn.rollback()
                    executed += 1  # Non-critical

    print(f"\n{'='*50}")
    print(f"[OK] Restore complete!")
    print(f"  Executed: {executed}/{total} statements")
    if errors:
        print(f"  Errors:   {errors} (check warnings above)")
    else:
        print(f"  Errors:   0")
    print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description='Restore SkillVector database from backup')
    parser.add_argument('--url', required=True, help='New database URL (required)')
    parser.add_argument('--file', '-f', default=None, help='Backup SQL file (defaults to latest)')
    parser.add_argument('--dry-run', action='store_true', help='Preview without executing')
    args = parser.parse_args()

    backup_file = args.file
    if not backup_file:
        backup_file = find_latest_backup()
        if not backup_file:
            print("[ERROR] No backup file found!")
            print("   Specify one with --file or run backup_db.py first")
            sys.exit(1)
        print(f"Using latest backup: {os.path.basename(backup_file)}")

    if not os.path.exists(backup_file):
        print(f"[ERROR] Backup file not found: {backup_file}")
        sys.exit(1)

    restore_database(args.url, backup_file, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
