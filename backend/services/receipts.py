"""Receipt service utilities"""
import psycopg
from database.db_connection import get_connection
from backend.services.guard import ensure_test_db
import uuid

def process_receipt(
    receipt_id: str,
    receipt_reference: str,
    purchase_order_id: str,
    product_id: str,
    quantity_received: int,
    unit_price: float,
    receipt_date: str,
    operator: str,
):
    """Process a purchase receipt.
    - `receipt_reference` must be unique; duplicate receipts are ignored (idempotent).
    - Updates `purchase_receipts` and increments inventory `units_received`.
    - Updates the related purchase_order status to 'RECEIVED' when fully received.
    """
    conn = get_connection()
    ensure_test_db(conn)
    with conn.cursor() as cur:
        # Idempotency: if receipt_reference already exists, do nothing
        cur.execute(
            "SELECT receipt_id FROM purchase_receipts WHERE receipt_reference = %s",
            (receipt_reference,)
        )
        existing = cur.fetchone()
        if existing:
            # Receipt already processed – nothing to do
            conn.commit()
            conn.close()
            return
        # Insert receipt
        cur.execute(
            "INSERT INTO purchase_receipts (receipt_id, receipt_reference, purchase_order_id, product_id, quantity_received, unit_price, receipt_date, operator) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                receipt_id,
                receipt_reference,
                purchase_order_id,
                product_id,
                quantity_received,
                unit_price,
                receipt_date,
                operator,
            ),
        )
        # Update inventory (incoming stock)
        cur.execute(
            "SELECT inventory_id, closing_stock FROM inventory WHERE product_id = %s FOR UPDATE",
            (product_id,)
        )
        inv = cur.fetchone()
        if inv:
            inventory_id, closing_stock = inv
            cur.execute(
                "UPDATE inventory SET units_received = units_received + %s, closing_stock = closing_stock + %s "
                "WHERE inventory_id = %s",
                (quantity_received, quantity_received, inventory_id),
            )
        else:
            # create inventory record if missing
            cur.execute(
                "INSERT INTO inventory (inventory_id, date, product_id, opening_stock, units_received, true_demand, observed_units_sold, lost_sales_units, closing_stock, stockout_flag) "
                "VALUES (gen_random_uuid()::text, %s, %s, 0, %s, 0, 0, 0, %s, FALSE)",
                (receipt_date, product_id, quantity_received, quantity_received),
            )
        # Update purchase order status (simple logic: mark RECEIVED)
        cur.execute(
            "UPDATE purchase_orders SET status = 'RECEIVED' WHERE purchase_order_id = %s",
            (purchase_order_id,)
        )
    conn.commit()
    conn.close()
