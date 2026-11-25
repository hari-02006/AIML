import json
import traceback
import sys, os
from contextlib import contextmanager

# Ensure project root is on sys.path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from database.db_connection import get_connection

@contextmanager
def readonly_connection(expected_db: str = "smart_inventory"):
    """Yield a psycopg connection that is guaranteed read‑only.

    Steps:
    1. Open a connection.
    2. Begin an explicit READ ONLY transaction.
    3. Verify ``SHOW transaction_read_only`` returns ``on``.
    4. Verify ``SELECT current_database()`` matches *expected_db*.
    5. Yield the connection.
    6. Roll back and close the connection.
    """
    conn = None
    try:
        conn = get_connection()
        # Begin read‑only transaction (PostgreSQL syntax)
        conn.execute("BEGIN TRANSACTION READ ONLY")
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only;")
            tx_ro = cur.fetchone()[0]
            if tx_ro != "on":
                raise RuntimeError(f"Transaction is not read‑only (transaction_read_only={tx_ro})")
            cur.execute("SELECT current_database();")
            cur_db = cur.fetchone()[0]
            if cur_db != expected_db:
                raise RuntimeError(
                    f"Connected to unexpected database '{cur_db}' (expected '{expected_db}')"
                )
        yield conn
    finally:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()

def verify_database():
    """Run the verification steps and return a JSON‑serialisable dict.
    Used by the stand‑alone db_verification script.
    """
    result = {
        "status": "SUCCESS",
        "evidence_tag": "DATABASE-VERIFIED",
        "data": {},
    }
    try:
        with readonly_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database();")
                result["data"]["current_database"] = cur.fetchone()[0]
                cur.execute("SELECT current_user;")
                result["data"]["current_user"] = cur.fetchone()[0]
                cur.execute("SHOW transaction_read_only;")
                result["data"]["transaction_read_only"] = cur.fetchone()[0]
                cur.execute("SELECT MAX(date) FROM sales;")
                result["data"]["max_sales_date"] = str(cur.fetchone()[0])
                cur.execute(
                    "SELECT product_id, MAX(date) FROM inventory GROUP BY product_id;"
                )
                inv = {row[0]: str(row[1]) for row in cur.fetchall()}
                result["data"]["inventory_latest_dates"] = inv
    except Exception as e:
        result["status"] = "FAIL"
        result["evidence_tag"] = "DATABASE-VERIFICATION-FAILED"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
    return result

if __name__ == "__main__":
    print(json.dumps(verify_database(), indent=2))
