"""Product service utilities"""
import psycopg
from ..db_connection import get_connection
from .guard import ensure_test_db
from . import guard

def validate_stock_unit(product_id: str, unit: str):
    """Validate that the given unit matches the product's configured stock unit.
    Raises RuntimeError if mismatched.
    """
    conn = get_connection()
    ensure_test_db(conn, guard.TEST_DB_NAME)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT stock_unit FROM products WHERE product_id = %s",
            (product_id,)
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Product {product_id} not found")
        expected = row[0]
        if expected != unit:
            raise RuntimeError(
                f"Unit mismatch for product {product_id}: expected {expected}, got {unit}"
            )
    conn.close()
