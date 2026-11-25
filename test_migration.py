import os, sys, uuid, datetime
import psycopg
from pathlib import Path

# Load env from project root .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]
env_path = PROJECT_ROOT / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

# Connection parameters (default trust)
host = os.getenv('DB_HOST', 'localhost')
port = os.getenv('DB_PORT', '5432')
user = os.getenv('DB_USER', 'postgres')
password = os.getenv('DB_PASSWORD', '')

# Create a unique disposable test DB name
test_db = f"smart_inventory_test_{uuid.uuid4().hex[:8]}_test"
print('Creating disposable DB:', test_db)

admin_conn = psycopg.connect(host=host, port=port, dbname='postgres', user=user, password=password)
admin_conn.autocommit = True
with admin_conn.cursor() as cur:
    cur.execute(f'CREATE DATABASE {test_db}')
admin_conn.close()

def run_sql_file(conn, file_path):
    with open(file_path, 'r') as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)

def apply_migrations():
    conn = psycopg.connect(host=host, port=port, dbname=test_db, user=user, password=password)
    # set env for guard
    os.environ['ENVIRONMENT'] = 'test'
    os.environ['TEST_DB_NAME'] = test_db
    # schema
    run_sql_file(conn, str(PROJECT_ROOT / 'database' / 'schema' / 'schema.sql'))
    # stage9
    run_sql_file(conn, str(PROJECT_ROOT / 'database' / 'migrations' / 'stage9_invoice_tables.sql'))
    # stage14 add missing
    run_sql_file(conn, str(PROJECT_ROOT / 'database' / 'migrations' / 'stage14_add_missing_tables.sql'))
    # stage14 extend twice
    for i in range(2):
        run_sql_file(conn, str(PROJECT_ROOT / 'database' / 'migrations' / 'stage14_extend_tables.sql'))
    conn.commit()
    conn.close()

apply_migrations()
print('Migrations applied successfully.')

# Cleanup
admin_conn = psycopg.connect(host=host, port=port, dbname='postgres', user=user, password=password)
admin_conn.autocommit = True
with admin_conn.cursor() as cur:
    cur.execute(f'DROP DATABASE IF EXISTS {test_db}')
admin_conn.close()
print('Disposed disposable DB.')
