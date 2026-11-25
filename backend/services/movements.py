"""Movement service utilities"""
import psycopg
from database.db_connection import get_connection
from .guard import ensure_test_db
import uuid

def log_movement(
    movement_id: str,
    product_id: str,
    quantity: int,
    unit: str,
    movement_type: str,
    movement_date: str,
    operator: str,
    reference_id: str = None,
    reference_type: str = "UNKNOWN",
):
    """Record an inventory movement.
    `movement_type` must be 'IN', 'OUT', or 'ADJUSTMENT'.
    `reference_type` can be 'RECEIPT', 'SALE', 'ADJUSTMENT' etc.
    Idempotency is enforced via the primary key `movement_id`.
    """
    conn = get_connection()
    ensure_test_db(conn)
    with conn.cursor() as cur:
        # Idempotency check – primary key will raise if duplicate, but we check explicitly
        cur.execute("SELECT 1 FROM inventory_movements WHERE movement_id = %s", (movement_id,))
        if cur.fetchone():
            raise RuntimeError(f"Duplicate movement_id {movement_id}")
        # Insert movement record
        cur.execute(
            "INSERT INTO inventory_movements (movement_id, product_id, quantity, unit, movement_type, movement_date, operator, reference_id, movement_reference_type) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                movement_id,
                product_id,
                quantity,
                unit,
                movement_type,
                movement_date,
                operator,
                reference_id,
                reference_type,
            ),
        )
        # Adjust inventory closing_stock accordingly
        cur.execute(
            "SELECT inventory_id, closing_stock FROM inventory WHERE product_id = %s FOR UPDATE",
            (product_id,)
        )
        inv = cur.fetchone()
        if not inv:
            raise RuntimeError(f"No inventory record for product {product_id}")
        inventory_id, closing_stock = inv
        if movement_type == "IN":
            new_stock = closing_stock + quantity
        elif movement_type == "OUT":
            if closing_stock < quantity:
                raise RuntimeError("Insufficient stock for outbound movement")
            new_stock = closing_stock - quantity
        else:  # ADJUSTMENT
            new_stock = quantity  # quantity represents the corrected absolute stock
        cur.execute(
            "UPDATE inventory SET closing_stock = %s WHERE inventory_id = %s",
            (new_stock, inventory_id),
        )
    conn.commit()
    conn.close()
