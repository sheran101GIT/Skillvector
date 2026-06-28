"""
Backup Render PostgreSQL database to a local SQL file.
Works without pg_dump — uses pure Python (psycopg2/SQLAlchemy).

Usage:
    python scripts/backup_db.py
    python scripts/backup_db.py --output my_backup.sql
    python scripts/backup_db.py --url "postgresql://user:pass@host/db"
"""

import os
import sys
import argparse
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def get_db_url():
    """Get database URL from environment or .env file."""
    url = os.environ.get('DATABASE_URL')
    if url:
        return url
    
    # Try loading from .env
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('DATABASE_URL='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    return None


def backup_database(db_url, output_file):
    """
    Creates a logical backup by dumping all table data as INSERT statements.
    Also exports CREATE TABLE statements (DDL) via SQLAlchemy reflection.
    """
    from sqlalchemy import create_engine, inspect, text, MetaData
    
    # Fix Render's postgres:// vs postgresql:// issue
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    print(f"Connecting to database...")
    engine = create_engine(db_url)
    
    metadata = MetaData()
    metadata.reflect(bind=engine)
    
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    print(f"Found {len(table_names)} tables: {', '.join(table_names)}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"-- SkillVector Database Backup\n")
        f.write(f"-- Generated: {datetime.now().isoformat()}\n")
        f.write(f"-- Tables: {', '.join(table_names)}\n")
        f.write(f"--\n\n")
        
        with engine.connect() as conn:
            # ── 1. Export Schema (CREATE TABLE) ─────────────────────────
            f.write("-- =============================================\n")
            f.write("-- SCHEMA (DDL)\n")
            f.write("-- =============================================\n\n")
            
            # Check for pgvector extension
            try:
                result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                if result.fetchone():
                    f.write("CREATE EXTENSION IF NOT EXISTS vector;\n\n")
            except:
                pass
            
            for table_name in table_names:
                # Get CREATE TABLE statement via pg_dump-like query
                try:
                    # Get column definitions
                    columns = inspector.get_columns(table_name)
                    pk = inspector.get_pk_constraint(table_name)
                    fks = inspector.get_foreign_keys(table_name)
                    
                    f.write(f"-- Table: {table_name}\n")
                    f.write(f"DROP TABLE IF EXISTS {table_name} CASCADE;\n")
                    f.write(f"CREATE TABLE {table_name} (\n")
                    
                    col_defs = []
                    for col in columns:
                        col_type = str(col['type'])
                        nullable = "" if col.get('nullable', True) else " NOT NULL"
                        default = ""
                        if col.get('default') and 'nextval' not in str(col.get('default', '')):
                            default = f" DEFAULT {col['default']}"
                        col_defs.append(f"    {col['name']} {col_type}{nullable}{default}")
                    
                    # Primary key
                    if pk and pk.get('constrained_columns'):
                        pk_cols = ', '.join(pk['constrained_columns'])
                        col_defs.append(f"    PRIMARY KEY ({pk_cols})")
                    
                    f.write(',\n'.join(col_defs))
                    f.write("\n);\n")
                    
                    # Sequences for serial/identity columns
                    for col in columns:
                        if col.get('default') and 'nextval' in str(col.get('default', '')):
                            seq_name = f"{table_name}_{col['name']}_seq"
                            f.write(f"CREATE SEQUENCE IF NOT EXISTS {seq_name};\n")
                            f.write(f"ALTER TABLE {table_name} ALTER COLUMN {col['name']} SET DEFAULT nextval('{seq_name}');\n")
                    
                    # Foreign keys
                    for fk in fks:
                        fk_cols = ', '.join(fk['constrained_columns'])
                        ref_cols = ', '.join(fk['referred_columns'])
                        ref_table = fk['referred_table']
                        fk_name = fk.get('name', f"fk_{table_name}_{fk_cols}")
                        f.write(f"ALTER TABLE {table_name} ADD CONSTRAINT {fk_name} ")
                        f.write(f"FOREIGN KEY ({fk_cols}) REFERENCES {ref_table}({ref_cols});\n")
                    
                    f.write("\n")
                except Exception as e:
                    f.write(f"-- ERROR generating DDL for {table_name}: {e}\n\n")
            
            # ── 2. Export Data (INSERT statements) ──────────────────────
            f.write("\n-- =============================================\n")
            f.write("-- DATA (INSERT statements)\n")
            f.write("-- =============================================\n\n")
            
            total_rows = 0
            
            # Determine table order (respect foreign keys)
            # Simple approach: alembic_version first, then users, jobs, candidates, then rest
            priority_order = ['alembic_version', 'users', 'jobs', 'candidates', 
                            'analyses', 'notes', 'candidate_journeys', 
                            'job_templates', 'google_form_connections', 'review_emails']
            
            ordered_tables = []
            for t in priority_order:
                if t in table_names:
                    ordered_tables.append(t)
            for t in table_names:
                if t not in ordered_tables:
                    ordered_tables.append(t)
            
            for table_name in ordered_tables:
                try:
                    result = conn.execute(text(f'SELECT * FROM "{table_name}"'))
                    rows = result.fetchall()
                    columns = result.keys()
                    
                    if not rows:
                        f.write(f"-- Table {table_name}: 0 rows (empty)\n\n")
                        continue
                    
                    f.write(f"-- Table {table_name}: {len(rows)} rows\n")
                    col_names = ', '.join(columns)
                    
                    for row in rows:
                        values = []
                        for val in row:
                            if val is None:
                                values.append('NULL')
                            elif isinstance(val, bool):
                                values.append('TRUE' if val else 'FALSE')
                            elif isinstance(val, (int, float)):
                                values.append(str(val))
                            elif isinstance(val, datetime):
                                values.append(f"'{val.isoformat()}'")
                            elif isinstance(val, (list, dict)):
                                # JSON/JSONB or ARRAY data
                                json_str = json.dumps(val).replace("'", "''")
                                values.append(f"'{json_str}'")
                            elif isinstance(val, str):
                                escaped = val.replace("'", "''").replace("\n", "\\n").replace("\r", "\\r")
                                values.append(f"'{escaped}'")
                            else:
                                escaped = str(val).replace("'", "''")
                                values.append(f"'{escaped}'")
                        
                        values_str = ', '.join(values)
                        f.write(f"INSERT INTO {table_name} ({col_names}) VALUES ({values_str});\n")
                    
                    total_rows += len(rows)
                    f.write("\n")
                    
                except Exception as e:
                    f.write(f"-- ERROR exporting {table_name}: {e}\n\n")
            
            # ── 3. Reset sequences ──────────────────────────────────────
            f.write("\n-- =============================================\n")
            f.write("-- RESET SEQUENCES\n")
            f.write("-- =============================================\n\n")
            
            for table_name in table_names:
                try:
                    columns = inspector.get_columns(table_name)
                    for col in columns:
                        if col.get('default') and 'nextval' in str(col.get('default', '')):
                            seq_match = str(col['default'])
                            # Extract sequence name
                            if "'" in seq_match:
                                seq_name = seq_match.split("'")[1]
                            else:
                                seq_name = f"{table_name}_{col['name']}_seq"
                            
                            f.write(f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({col['name']}) FROM {table_name}), 1));\n")
                except:
                    pass
    
    file_size = os.path.getsize(output_file)
    print(f"\n[OK] Backup complete!")
    print(f"   File: {output_file}")
    print(f"   Size: {file_size / 1024:.1f} KB")
    print(f"   Tables: {len(table_names)}")
    print(f"   Total rows: {total_rows}")


def main():
    parser = argparse.ArgumentParser(description='Backup Render PostgreSQL database')
    parser.add_argument('--url', help='Database URL (overrides DATABASE_URL env var)')
    parser.add_argument('--output', '-o', default=None, help='Output SQL file path')
    args = parser.parse_args()
    
    db_url = args.url or get_db_url()
    if not db_url:
        print("[ERROR] No database URL found!")
        print("   Set DATABASE_URL env var, add it to .env, or pass --url")
        sys.exit(1)
    
    if args.output:
        output_file = args.output
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(os.path.dirname(__file__), '..', f'skillvector_backup_{timestamp}.sql')
    
    print(f"[BACKUP] Starting database backup...")
    print(f"   Output: {output_file}")
    backup_database(db_url, output_file)


if __name__ == '__main__':
    main()
