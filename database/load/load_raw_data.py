import csv
import os
import sys
import argparse
from contextlib import closing

from psycopg import sql

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from database.db_connection import get_connection

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default='data/raw')
    args = parser.parse_args()
    
    db_name = os.getenv("DB_NAME", "smart_inventory")
    with closing(get_connection(dbname="postgres")) as admin:
        admin.autocommit = True
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))

    with get_connection(dbname=db_name) as conn, conn.cursor() as cur:
        # 1. Apply schema
        schema_path = os.path.join('database', 'schema', 'schema.sql')
        with open(schema_path, 'r') as f:
            cur.execute(f.read())
        print("Schema applied.")

        # Helper for copy
        def load_csv(table, filepath):
            with open(filepath, 'r') as f:
                with cur.copy(f"COPY {table} FROM STDIN WITH CSV HEADER") as copy:
                    while data := f.read(8192):
                        copy.write(data)
            print(f"Loaded {table}")
            
        # 2. Categories
        # Our CSV for categories just has category_name. We can load it manually to generate IDs.
        cat_file = os.path.join(args.data_dir, 'categories.csv')
        cat_map = {}
        with open(cat_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cur.execute("INSERT INTO categories (category_name) VALUES (%s) RETURNING category_id", (row['category_name'],))
                cat_id = cur.fetchone()[0]
                cat_map[row['category_name']] = cat_id
        print("Loaded categories")

        # 3. Suppliers
        load_csv('suppliers', os.path.join(args.data_dir, 'suppliers.csv'))
        
        # 4. Products (needs category mapping)
        prod_file = os.path.join(args.data_dir, 'products.csv')
        with open(prod_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cat_id = cat_map[row['category']]
                cur.execute("""
                    INSERT INTO products (product_id, product_name, category_id, base_price, cost_price, popularity_class, demand_pattern_class, supplier_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (row['id'], row['name'], cat_id, row['base_price'], row['cost_price'], row['popularity_class'], row['demand_pattern_class'], row['supplier_id']))
        print("Loaded products")

        # 5. Customers
        load_csv('customers', os.path.join(args.data_dir, 'customers.csv'))

        # 6. Promotions
        load_csv('promotions', os.path.join(args.data_dir, 'promotions.csv'))

        # 7. Purchase Orders
        # We need to map empty strings to None (NULL) for actual_delivery_date
        po_file = os.path.join(args.data_dir, 'purchase_orders.csv')
        with open(po_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                act = row['actual_delivery_date'] if row['actual_delivery_date'] else None
                cur.execute("""
                    INSERT INTO purchase_orders (purchase_order_id, product_id, supplier_id, order_date, quantity_ordered, expected_delivery_date, actual_delivery_date, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (row['purchase_order_id'], row['product_id'], row['supplier_id'], row['order_date'], row['quantity_ordered'], row['expected_delivery_date'], act, row['status']))
        print("Loaded purchase_orders")

        # 8. Inventory (has stockout_flag as text True/False)
        inv_file = os.path.join(args.data_dir, 'inventory.csv')
        with open(inv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stk = row['stockout_flag'] == 'True'
                cur.execute("""
                    INSERT INTO inventory (inventory_id, date, product_id, opening_stock, units_received, true_demand, observed_units_sold, lost_sales_units, closing_stock, stockout_flag)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (row['inventory_id'], row['date'], row['product_id'], row['opening_stock'], row['units_received'], row['true_demand'], row['observed_units_sold'], row['lost_sales_units'], row['closing_stock'], stk))
        print("Loaded inventory")

        # 9. Sales (promotion_id can be empty)
        sales_file = os.path.join(args.data_dir, 'sales.csv')
        with open(sales_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                promo = row['promotion_id'] if row['promotion_id'] else None
                cur.execute("""
                    INSERT INTO sales (sale_id, date, product_id, customer_id, quantity, unit_price, discount, promotion_id, revenue)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (row['sale_id'], row['date'], row['product_id'], row['customer_id'], row['quantity'], row['unit_price'], row['discount'], promo, row['revenue']))
        print("Loaded sales")
        
    print("Database loading complete.")

if __name__ == "__main__":
    main()
