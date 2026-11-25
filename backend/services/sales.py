"""Sales service utilities"""
import psycopg
from database.db_connection import get_connection
from .guard import ensure_test_db
import uuid

def record_sale(sale_id: str, date: str, product_id: str, customer_id: str, quantity: int, unit_price: float, promotion_id: str = None):
    """Record a sale with row‑locking and idempotency.
    Raises RuntimeError if a duplicate sale_id is supplied.
    """
    conn = get_connection()
    ensure_test_db(conn)
    with conn.cursor() as cur:
        # Idempotency check
        cur.execute("SELECT 1 FROM sales WHERE sale_id = %s", (sale_id,))
        if cur.fetchone():
            raise RuntimeError(f"Duplicate sale_id {sale_id}")
        # Lock inventory row
        cur.execute(
            "SELECT inventory_id, closing_stock FROM inventory WHERE product_id = %s FOR UPDATE",
            (product_id,)
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"No inventory record for product {product_id}")
        inventory_id, closing_stock = row
        if closing_stock < quantity:
            raise RuntimeError("Insufficient stock for sale")
        # Insert sale
        cur.execute(
            "INSERT INTO sales (sale_id, date, product_id, customer_id, quantity, unit_price, discount, revenue) "
            "VALUES (%s, %s, %s, %s, %s, %s, 0, %s)",
            (sale_id, date, product_id, customer_id, quantity, unit_price, quantity * unit_price)
        )
        # Update inventory closing stock
        cur.execute(
            "UPDATE inventory SET closing_stock = closing_stock - %s, observed_units_sold = observed_units_sold + %s "
            "WHERE inventory_id = %s",
            (quantity, quantity, inventory_id)
        )
    conn.commit()
    conn.close()
