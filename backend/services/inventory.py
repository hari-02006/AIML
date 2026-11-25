"""Inventory service utilities"""
import psycopg
from ..db_connection import get_connection
from .guard import ensure_test_db

def reconcile_inventory(date: str, product_id: str):
    """Placeholder for physical‑stock reconciliation.
    In a real system this would compare actual counted stock with the
    recorded `inventory` table and adjust discrepancies.
    Here we simply ensure the inventory record exists.
    """
    conn = get_connection()
    ensure_test_db(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT inventory_id FROM inventory WHERE date = %s AND product_id = %s",
            (date, product_id)
        )
        if not cur.fetchone():
            # create a zero‑stock entry if missing
            cur.execute(
                "INSERT INTO inventory (inventory_id, date, product_id, opening_stock, units_received, true_demand, observed_units_sold, lost_sales_units, closing_stock, stockout_flag) "
                "VALUES (gen_random_uuid()::text, %s, %s, 0, 0, 0, 0, 0, 0, FALSE)",
                (date, product_id)
            )
    conn.commit()
    conn.close()
