"""
Data Extraction Module for Stage 10 ML Feature Engineering.
Safely extracts historical sales, inventory, products, categories, and promotions
from PostgreSQL using strict read-only transactions.
"""

import datetime
from typing import Dict, Any, Optional
import pandas as pd
from database.db_connection import get_connection


def extract_stage10_source_data(dbname: Optional[str] = None) -> Dict[str, pd.DataFrame]:
    """
    Extracts all required source data for Stage 10 in a strictly read-only transaction.
    Returns a dictionary of DataFrames:
      - 'sales': raw transaction records
      - 'products': product master metadata including category and stock_unit
      - 'categories': category reference data
      - 'inventory': daily historical stock snapshots
      - 'promotions': historical promotional campaign dates and discount percentages
    """
    conn = get_connection(dbname=dbname)
    # Enforce read-only transaction mode
    conn.read_only = True
    
    try:
        with conn.cursor() as cur:
            # 1. Sales transactions
            cur.execute("""
                SELECT 
                    sale_id,
                    date,
                    product_id,
                    customer_id,
                    quantity,
                    unit_price,
                    discount,
                    promotion_id,
                    revenue
                FROM sales
                ORDER BY date, product_id;
            """)
            sales_cols = [col[0] for col in cur.description]
            sales_rows = cur.fetchall()
            df_sales = pd.DataFrame(sales_rows, columns=sales_cols)
            if not df_sales.empty:
                df_sales["date"] = pd.to_datetime(df_sales["date"]).dt.date
                df_sales["quantity"] = pd.to_numeric(df_sales["quantity"], errors="coerce")

            # 2. Products
            cur.execute("""
                SELECT 
                    p.product_id,
                    p.product_name,
                    p.category_id,
                    c.category_name,
                    p.supplier_id,
                    p.stock_unit,
                    p.base_price,
                    p.cost_price,
                    p.popularity_class,
                    p.demand_pattern_class
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                ORDER BY p.product_id;
            """)
            prod_cols = [col[0] for col in cur.description]
            prod_rows = cur.fetchall()
            df_products = pd.DataFrame(prod_rows, columns=prod_cols)

            # 3. Categories
            cur.execute("SELECT category_id, category_name FROM categories ORDER BY category_id;")
            cat_cols = [col[0] for col in cur.description]
            cat_rows = cur.fetchall()
            df_categories = pd.DataFrame(cat_rows, columns=cat_cols)

            # 4. Inventory
            cur.execute("""
                SELECT 
                    inventory_id,
                    date,
                    product_id,
                    opening_stock,
                    units_received,
                    closing_stock,
                    stockout_flag
                FROM inventory
                ORDER BY date, product_id;
            """)
            inv_cols = [col[0] for col in cur.description]
            inv_rows = cur.fetchall()
            df_inventory = pd.DataFrame(inv_rows, columns=inv_cols)
            if not df_inventory.empty:
                df_inventory["date"] = pd.to_datetime(df_inventory["date"]).dt.date
                for col in ["opening_stock", "units_received", "closing_stock"]:
                    df_inventory[col] = pd.to_numeric(df_inventory[col], errors="coerce")

            # 5. Promotions
            cur.execute("""
                SELECT 
                    promotion_id,
                    promotion_name,
                    discount_percentage,
                    start_date,
                    end_date
                FROM promotions
                ORDER BY start_date;
            """)
            promo_cols = [col[0] for col in cur.description]
            promo_rows = cur.fetchall()
            df_promotions = pd.DataFrame(promo_rows, columns=promo_cols)
            if not df_promotions.empty:
                df_promotions["start_date"] = pd.to_datetime(df_promotions["start_date"]).dt.date
                df_promotions["end_date"] = pd.to_datetime(df_promotions["end_date"]).dt.date

            # Extract distinct promotional eligibility per product from sales transactions
            cur.execute("""
                SELECT DISTINCT 
                    promotion_id,
                    product_id
                FROM sales
                WHERE promotion_id IS NOT NULL;
            """)
            eligible_rows = cur.fetchall()
            df_promo_eligibility = pd.DataFrame(eligible_rows, columns=["promotion_id", "product_id"])

        return {
            "sales": df_sales,
            "products": df_products,
            "categories": df_categories,
            "inventory": df_inventory,
            "promotions": df_promotions,
            "promo_eligibility": df_promo_eligibility,
        }
    finally:
        conn.close()
