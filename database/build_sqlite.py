import csv
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "demo_generated"
DB_PATH = PROJECT_ROOT / "data" / "smart_inventory.db"


def load_demo_data(conn):
    cur = conn.cursor()

    # Schema
    cur.executescript("""
    CREATE TABLE categories (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE suppliers (
        supplier_id TEXT PRIMARY KEY,
        supplier_name TEXT NOT NULL,
        nominal_lead_time_days INTEGER,
        reliability_class TEXT
    );

    CREATE TABLE products (
        product_id TEXT PRIMARY KEY,
        product_name TEXT NOT NULL,
        category_id INTEGER,
        base_price REAL,
        cost_price REAL,
        popularity_class TEXT,
        demand_pattern_class TEXT,
        supplier_id TEXT,
        stock_unit TEXT DEFAULT 'pcs',
        FOREIGN KEY (category_id) REFERENCES categories(category_id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
    );

    CREATE TABLE customers (
        customer_id TEXT PRIMARY KEY,
        age_group TEXT,
        location TEXT,
        customer_segment TEXT
    );

    CREATE TABLE promotions (
        promotion_id TEXT PRIMARY KEY,
        promotion_name TEXT,
        discount_percentage REAL,
        start_date TEXT,
        end_date TEXT
    );

    CREATE TABLE purchase_orders (
        purchase_order_id TEXT PRIMARY KEY,
        product_id TEXT,
        supplier_id TEXT,
        order_date TEXT NOT NULL,
        quantity_ordered INTEGER,
        expected_delivery_date TEXT,
        actual_delivery_date TEXT,
        status TEXT,
        FOREIGN KEY (product_id) REFERENCES products(product_id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
    );

    CREATE TABLE inventory (
        inventory_id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        product_id TEXT,
        opening_stock INTEGER,
        units_received INTEGER,
        true_demand INTEGER,
        observed_units_sold INTEGER,
        lost_sales_units INTEGER,
        closing_stock INTEGER,
        stockout_flag BOOLEAN,
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );

    CREATE TABLE sales (
        sale_id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        product_id TEXT,
        customer_id TEXT,
        quantity INTEGER,
        unit_price REAL,
        discount REAL,
        promotion_id TEXT,
        revenue REAL,
        FOREIGN KEY (product_id) REFERENCES products(product_id),
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
    );

    CREATE TABLE purchase_invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_reference TEXT,
        invoice_date TEXT,
        supplier_id TEXT,
        raw_supplier_name TEXT,
        document_hash TEXT NOT NULL,
        document_filename TEXT NOT NULL,
        document_path TEXT NOT NULL,
        document_type TEXT DEFAULT 'Supplier Invoice',
        total_pages INTEGER DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        approved_at TEXT,
        notes TEXT
    );

    CREATE TABLE purchase_invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL,
        product_id TEXT,
        raw_line_text TEXT,
        original_product_name TEXT,
        normalized_product_name TEXT,
        quantity REAL,
        unit TEXT,
        canonical_quantity REAL,
        conversion_factor REAL DEFAULT 1.0,
        verification_status TEXT DEFAULT 'Needs Review',
        source_page INTEGER DEFAULT 1,
        FOREIGN KEY (invoice_id) REFERENCES purchase_invoices(id),
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );

    CREATE INDEX idx_products_category ON products(category_id);
    CREATE INDEX idx_products_supplier ON products(supplier_id);
    CREATE INDEX idx_purchase_orders_date ON purchase_orders(order_date);
    CREATE INDEX idx_inventory_date ON inventory(date);
    CREATE INDEX idx_inventory_product ON inventory(product_id);
    CREATE INDEX idx_sales_date ON sales(date);
    CREATE INDEX idx_sales_product ON sales(product_id);
    """)

    # 1. Categories
    cat_map = {}
    with open(DATA_DIR / "categories.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute("INSERT INTO categories (category_name) VALUES (?)", (row["category_name"],))
            cat_map[row["category_name"]] = cur.lastrowid

    # 2. Suppliers
    with open(DATA_DIR / "suppliers.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            s_id = row.get("supplier_id") or row.get("id")
            s_name = row.get("supplier_name") or row.get("name")
            cur.execute(
                "INSERT INTO suppliers (supplier_id, supplier_name, nominal_lead_time_days, reliability_class) VALUES (?, ?, ?, ?)",
                (s_id, s_name, int(row["nominal_lead_time_days"]), row["reliability_class"])
            )

    # 3. Products
    with open(DATA_DIR / "products.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat_id = cat_map[row["category"]]
            cur.execute(
                """INSERT INTO products 
                   (product_id, product_name, category_id, base_price, cost_price, popularity_class, demand_pattern_class, supplier_id, stock_unit) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pcs')""",
                (row["id"], row["name"], cat_id, float(row["base_price"]), float(row["cost_price"]),
                 row["popularity_class"], row["demand_pattern_class"], row["supplier_id"])
            )

    # 4. Customers
    with open(DATA_DIR / "customers.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                "INSERT INTO customers (customer_id, age_group, location, customer_segment) VALUES (?, ?, ?, ?)",
                (row["customer_id"], row["age_group"], row["location"], row["customer_segment"])
            )

    # 5. Promotions
    with open(DATA_DIR / "promotions.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                "INSERT INTO promotions (promotion_id, promotion_name, discount_percentage, start_date, end_date) VALUES (?, ?, ?, ?, ?)",
                (row["promotion_id"], row["promotion_name"], float(row["discount_percentage"]), row["start_date"], row["end_date"])
            )

    # 6. Purchase Orders
    with open(DATA_DIR / "purchase_orders.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            act = row["actual_delivery_date"] if row["actual_delivery_date"] else None
            cur.execute(
                """INSERT INTO purchase_orders 
                   (purchase_order_id, product_id, supplier_id, order_date, quantity_ordered, expected_delivery_date, actual_delivery_date, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["purchase_order_id"], row["product_id"], row["supplier_id"], row["order_date"],
                 int(row["quantity_ordered"]), row["expected_delivery_date"], act, row["status"])
            )

    # 7. Inventory
    with open(DATA_DIR / "inventory.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        batch = []
        for row in reader:
            stk = 1 if row["stockout_flag"].lower() == "true" else 0
            batch.append((
                row["inventory_id"], row["date"], row["product_id"],
                int(row["opening_stock"]), int(row["units_received"]),
                int(row["true_demand"]), int(row["observed_units_sold"]),
                int(row["lost_sales_units"]), int(row["closing_stock"]), stk
            ))
            if len(batch) >= 1000:
                cur.executemany(
                    """INSERT INTO inventory 
                       (inventory_id, date, product_id, opening_stock, units_received, true_demand, observed_units_sold, lost_sales_units, closing_stock, stockout_flag)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    batch
                )
                batch = []
        if batch:
            cur.executemany(
                """INSERT INTO inventory 
                   (inventory_id, date, product_id, opening_stock, units_received, true_demand, observed_units_sold, lost_sales_units, closing_stock, stockout_flag)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                batch
            )

    # 8. Sales
    with open(DATA_DIR / "sales.csv", mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        batch = []
        for row in reader:
            promo = row["promotion_id"] if row["promotion_id"] else None
            batch.append((
                row["sale_id"], row["date"], row["product_id"], row["customer_id"],
                int(row["quantity"]), float(row["unit_price"]), float(row["discount"]),
                promo, float(row["revenue"])
            ))
            if len(batch) >= 1000:
                cur.executemany(
                    """INSERT INTO sales 
                       (sale_id, date, product_id, customer_id, quantity, unit_price, discount, promotion_id, revenue)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    batch
                )
                batch = []
        if batch:
            cur.executemany(
                """INSERT INTO sales 
                   (sale_id, date, product_id, customer_id, quantity, unit_price, discount, promotion_id, revenue)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                batch
            )

    conn.commit()


@lru_cache(maxsize=1)
def demo_database_snapshot():
    with closing(sqlite3.connect(":memory:")) as conn:
        load_demo_data(conn)
        return conn.serialize()


def build_database():
    snapshot = demo_database_snapshot()
    with DB_PATH.open("xb") as output:
        output.write(snapshot)
    print("SQLite database built successfully at", DB_PATH)

if __name__ == "__main__":
    build_database()
