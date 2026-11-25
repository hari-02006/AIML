import json
import traceback
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from database.db_connection import get_connection

def main():
    result = {
        "evidence_tag": "DATABASE-VERIFIED",
        "status": "SUCCESS",
        "data": {}
    }
    try:
        # Open connection and start an explicit read‑only transaction
        conn = get_connection()
        try:
            # Begin a read‑only transaction (PostgreSQL syntax)
            conn.execute("BEGIN TRANSACTION READ ONLY")
            # Verify transaction is read‑only
            with conn.cursor() as cur:
                cur.execute("SHOW transaction_read_only;")
                trx_ro = cur.fetchone()[0]
                if trx_ro != "on":
                    raise RuntimeError(f"Transaction is not read‑only (transaction_read_only={trx_ro})")
                # Proceed with inspection queries within the read‑only transaction
                cur.execute("SELECT current_database();")
                result["data"]["current_database"] = cur.fetchone()[0]
                cur.execute("SELECT current_user;")
                result["data"]["current_user"] = cur.fetchone()[0]
                cur.execute("SELECT MAX(date) FROM sales;")
                result["data"]["max_sales_date"] = str(cur.fetchone()[0])
                cur.execute("SELECT product_id, MAX(date) FROM inventory GROUP BY product_id;")
                inventory_dates = {row[0]: str(row[1]) for row in cur.fetchall()}
                result["data"]["inventory_latest_dates"] = inventory_dates
            # Roll back (no changes will be committed)
            conn.rollback()
        finally:
            conn.close()
    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
        result["evidence_tag"] = "DATABASE-VERIFICATION-FAILED"
    finally:
        try:
            conn.close()
        except Exception:
            pass
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
