import sys
import pathlib
import os
import uuid
import pytest
import psycopg

# Add the project root to sys.path so that tests can import top-level packages like `ml`, `frontend`, `database`, `etl`
project_root = pathlib.Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

@pytest.fixture(scope='session')
def disposable_pg_db():
    """Create a temporary PostgreSQL test database and ensure it is dropped after the session.
    The database name ends with `_test` to satisfy production-write guards.
    """
    # Generate a unique DB name
    unique_suffix = uuid.uuid4().hex[:8]
    db_name = f"smart_inventory_{unique_suffix}_test"
    # expose exact disposable DB name globally for guard checks
    os.environ["TEST_DB_NAME"] = db_name
    # expose exact disposable DB name globally for guard checks
    global TEST_DB_NAME
    TEST_DB_NAME = db_name
    # Connect to the default 'postgres' database to issue CREATE/DROP commands
    conn = psycopg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        dbname='postgres',
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
    )
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE DATABASE {db_name}")
    except Exception as e:
        conn.close()
        pytest.fail(f"Failed to create disposable test database '{db_name}': {e}")
    finally:
        cur.close()
        conn.close()

    # Override DB_NAME env var for the duration of the tests
    original_db_name = os.getenv('DB_NAME')
    os.environ['DB_NAME'] = db_name
    try:
        yield db_name
    finally:
        # Restore original DB_NAME
        if original_db_name is not None:
            os.environ['DB_NAME'] = original_db_name
        else:
            os.environ.pop('DB_NAME', None)
        # Drop the temporary database
        drop_conn = psycopg.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            dbname='postgres',
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
        )
        drop_conn.autocommit = True
        drop_cur = drop_conn.cursor()
        try:
            # Terminate any remaining connections to the DB before dropping
            drop_cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,)
            )
            drop_cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
        finally:
            drop_cur.close()
            drop_conn.close()

@pytest.fixture(scope='function')
def db_conn(disposable_pg_db):
    """Provide a live connection to the temporary PostgreSQL test database for a test function.
    The fixture ensures that the connection is to the exact database created by `disposable_pg_db`.
    """
    db_name = disposable_pg_db
    conn = psycopg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        dbname=db_name,
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
    )
    try:
        # Verify we are connected to the expected DB
        cur = conn.cursor()
        cur.execute('SELECT current_database()')
        current = cur.fetchone()[0]
        assert current == db_name, f"Connected to unexpected database: {current}"
        cur.close()
        yield conn
    finally:
        conn.close()
