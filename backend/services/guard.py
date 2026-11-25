import psycopg
import os

def ensure_test_db(conn: psycopg.Connection):
    """Raise if the current database is not exactly the expected disposable DB.
    Supports test mode (TEST_DB_NAME) and development mode (DEV_DB_NAME).
    """
    expected_test = os.getenv('TEST_DB_NAME')
    expected_dev = os.getenv('DEV_DB_NAME')
    if expected_test:
        expected = expected_test
    elif expected_dev:
        expected = expected_dev
    else:
        raise RuntimeError('Neither TEST_DB_NAME nor DEV_DB_NAME is set; write operations are prohibited')
    with conn.cursor() as cur:
        cur.execute('SELECT current_database();')
        db_name = cur.fetchone()[0]
        if db_name != expected:
            raise RuntimeError(
                f"Write protection violation: connected to {db_name}, expected {expected}"
            )
    """Raise if the current database is not exactly the expected disposable DB.
    The expected name is taken from the environment variable TEST_DB_NAME set by the
    test fixture and the PowerShell script.
    """
    expected_name = os.getenv('TEST_DB_NAME')
    if not expected_name:
        raise RuntimeError('TEST_DB_NAME environment variable not set')
    with conn.cursor() as cur:
        cur.execute('SELECT current_database();')
        db_name = cur.fetchone()[0]
        if db_name != expected_name:
            raise RuntimeError(
                f"Write protection violation: connected to {db_name}, expected {expected_name}"
            )

