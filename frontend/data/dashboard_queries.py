import datetime
import decimal
import os
import sqlite3
from contextlib import closing

import pandas as pd
from database.build_sqlite import demo_database_snapshot
from database.db_connection import get_connection


def using_demo_data():
    return os.getenv("INVENTORY_DEMO", "0") == "1"


def run_query(query, params=None):
    if using_demo_data():
        bindings = [
            value.isoformat()[:10] if isinstance(value, datetime.date) else value
            for value in (params or ())
        ]
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.deserialize(demo_database_snapshot())
            conn.execute("PRAGMA query_only = ON")
            return pd.read_sql_query(query.replace("%s", "?"), conn, params=bindings)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description is not None:
                columns = [col[0] for col in cur.description]
                rows = cur.fetchall()
                df = pd.DataFrame(rows, columns=columns)
                # Convert decimal.Decimal columns to float for Streamlit/Altair
                for col in df.columns:
                    if len(df) > 0 and isinstance(df[col].iloc[0], decimal.Decimal):
                        df[col] = df[col].astype(float)
                return df
            return pd.DataFrame()
    finally:
        conn.close()

def get_date_range():
    """Return the sales date range from the selected data source."""
    row = run_query("SELECT MIN(date) as min_date, MAX(date) as max_date FROM sales").iloc[0]
    return pd.to_datetime(row['min_date']), pd.to_datetime(row['max_date'])

def get_overall_metrics(start_date=None, end_date=None):
    sales_where = "WHERE 1=1"
    inv_where = "WHERE 1=1"
    sales_params = []
    inv_params = []
    if start_date:
        sales_where += " AND date >= %s"
        sales_params.append(start_date)
        inv_where += " AND date >= %s"
        inv_params.append(start_date)
    if end_date:
        sales_where += " AND date <= %s"
        sales_params.append(end_date)
        inv_where += " AND date <= %s"
        inv_params.append(end_date)
    query = f"""
    WITH filtered_sales AS (
        SELECT revenue, quantity, sale_id FROM sales {sales_where}
    ), filtered_inventory AS (
        SELECT lost_sales_units, stockout_flag FROM inventory {inv_where}
    ), ranked_inventory AS (
        SELECT closing_stock, ROW_NUMBER() OVER (
            PARTITION BY product_id ORDER BY date DESC, inventory_id DESC
        ) as stock_rank
        FROM inventory
    )
    SELECT 
        (SELECT COALESCE(SUM(revenue), 0) FROM filtered_sales) as total_revenue,
        (SELECT COALESCE(SUM(quantity), 0) FROM filtered_sales) as total_units_sold,
        (SELECT COUNT(*) FROM products) as total_products,
        (SELECT COUNT(*) FROM customers) as total_customers,
        (SELECT COUNT(*) FROM filtered_sales) as total_transactions,
        (SELECT COALESCE(SUM(closing_stock), 0) FROM ranked_inventory WHERE stock_rank = 1) as current_inventory,
        (SELECT COALESCE(SUM(lost_sales_units), 0) FROM filtered_inventory) as total_lost_sales,
        (SELECT COUNT(*) FROM filtered_inventory WHERE stockout_flag = TRUE) as stockout_product_days
    """
    params = sales_params + inv_params
    return run_query(query, params if params else None)

def get_sales_trend(start_date=None, end_date=None):
    query = """SELECT date, SUM(revenue) as revenue, SUM(quantity) as units_sold, COUNT(sale_id) as transactions FROM sales WHERE 1=1"""
    params = []
    if start_date:
        query += " AND date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND date <= %s"
        params.append(end_date)
    query += " GROUP BY date ORDER BY date"
    result = run_query(query, params)
    result["date"] = pd.to_datetime(result["date"])
    return result

def get_demand_vs_observed(start_date=None, end_date=None):
    where = "WHERE 1=1"
    params = []
    if start_date:
        where += " AND date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND date <= %s"
        params.append(end_date)
    query = f"""
    SELECT 
        SUM(true_demand) as total_true_demand,
        SUM(observed_units_sold) as total_observed_sales,
        SUM(lost_sales_units) as total_lost_sales,
        CASE WHEN SUM(true_demand) > 0 THEN 1.0 * SUM(lost_sales_units) / SUM(true_demand) ELSE 0 END as lost_sales_rate
    FROM inventory
    {where}
    """
    return run_query(query, params if params else None)

def get_category_units_sold():
    """Retrieve total units sold per category (quantity focus)."""
    query = """
    SELECT c.category_name, COALESCE(SUM(s.quantity), 0) as units_sold
    FROM categories c
    LEFT JOIN products p ON c.category_id = p.category_id
    LEFT JOIN sales s ON p.product_id = s.product_id
    GROUP BY c.category_name
    ORDER BY units_sold DESC
    """
    return run_query(query)


def get_category_revenue():
    """Retrieve total revenue per category (revenue focus)."""
    query = """
    SELECT c.category_name, COALESCE(SUM(s.revenue), 0) as revenue
    FROM categories c
    LEFT JOIN products p ON c.category_id = p.category_id
    LEFT JOIN sales s ON p.product_id = s.product_id
    GROUP BY c.category_name
    ORDER BY revenue DESC
    """
    return run_query(query)

    """Retrieve total units sold per category (quantity focus)."""
    query = """
    SELECT c.category_name, COALESCE(SUM(s.quantity), 0) as units_sold
    FROM categories c
    LEFT JOIN products p ON c.category_id = p.category_id
    LEFT JOIN sales s ON p.product_id = s.product_id
    GROUP BY c.category_name
    ORDER BY units_sold DESC
    """
    return run_query(query)

def get_top_products_units(limit=10):
    """Top products by units sold (quantity)."""
    query = """
    WITH product_sales AS (
        SELECT product_id, SUM(quantity) as units_sold, SUM(revenue) as revenue
        FROM sales
        GROUP BY product_id
    )
    SELECT p.product_name, COALESCE(s.units_sold, 0) as units_sold, COALESCE(s.revenue, 0) as revenue
    FROM products p
    LEFT JOIN product_sales s ON p.product_id = s.product_id
    ORDER BY units_sold DESC
    LIMIT %s
    """
    return run_query(query, [limit])


def get_top_products_revenue(limit=10):
    """Top products by revenue (revenue focus)."""
    query = """
    WITH product_sales AS (
        SELECT product_id, SUM(revenue) as revenue, SUM(quantity) as units_sold
        FROM sales
        GROUP BY product_id
    )
    SELECT p.product_name, COALESCE(s.revenue, 0) as revenue, COALESCE(s.units_sold, 0) as units_sold
    FROM products p
    LEFT JOIN product_sales s ON p.product_id = s.product_id
    ORDER BY revenue DESC
    LIMIT %s
    """
    return run_query(query, [limit])
    """Top products by units sold (quantity)."""
    query = """
    WITH product_sales AS (
        SELECT product_id, SUM(quantity) as units_sold, SUM(revenue) as revenue
        FROM sales
        GROUP BY product_id
    )
    SELECT p.product_name, COALESCE(s.units_sold, 0) as units_sold, COALESCE(s.revenue, 0) as revenue
    FROM products p
    LEFT JOIN product_sales s ON p.product_id = s.product_id
    ORDER BY units_sold DESC
    LIMIT %s
    """
    return run_query(query, [limit])

def get_lost_sales_by_product(limit=10, start_date=None, end_date=None):
    where = "WHERE 1=1"
    params = []
    if start_date:
        where += " AND date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND date <= %s"
        params.append(end_date)
    query = f"""
    WITH product_inventory AS (
        SELECT product_id, SUM(lost_sales_units) as lost_sales_units
        FROM inventory
        {where}
        GROUP BY product_id
    )
    SELECT p.product_name, COALESCE(i.lost_sales_units, 0) as lost_sales_units
    FROM products p
    LEFT JOIN product_inventory i ON p.product_id = i.product_id
    WHERE i.lost_sales_units > 0
    ORDER BY lost_sales_units DESC
    LIMIT %s
    """
    params.append(limit)
    return run_query(query, params)

def get_stockout_overview(start_date=None, end_date=None):
    where = "WHERE 1=1"
    params = []
    if start_date:
        where += " AND date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND date <= %s"
        params.append(end_date)
    query = f"""
    SELECT 
        COUNT(DISTINCT product_id) as products_with_stockouts,
        SUM(CASE WHEN stockout_flag THEN 1 ELSE 0 END) as total_stockout_days,
        SUM(lost_sales_units) as total_lost_sales
    FROM inventory
    {where} AND (stockout_flag = TRUE OR lost_sales_units > 0)
    """
    return run_query(query, params if params else None)

def get_product_details(category=None):
    query = """
    WITH product_sales AS (
        SELECT product_id, SUM(quantity) as units_sold FROM sales GROUP BY product_id
    ), product_inventory AS (
        SELECT product_id, SUM(lost_sales_units) as lost_sales_units, SUM(CASE WHEN stockout_flag THEN 1 ELSE 0 END) as stockout_days FROM inventory GROUP BY product_id
    )
    SELECT p.product_name, c.category_name, COALESCE(s.units_sold, 0) as units_sold, COALESCE(i.lost_sales_units, 0) as lost_sales_units, COALESCE(i.stockout_days, 0) as stockout_days
    FROM products p
    LEFT JOIN categories c ON p.category_id = c.category_id
    LEFT JOIN product_sales s ON p.product_id = s.product_id
    LEFT JOIN product_inventory i ON p.product_id = i.product_id
    WHERE 1=1
    """
    params = []
    if category and category != 'All':
        query += " AND c.category_name = %s"
        params.append(category)
    query += " ORDER BY units_sold DESC"
    return run_query(query, params)

def get_inventory_details(start_date=None, end_date=None):
    where = "WHERE 1=1"
    params = []
    if start_date:
        where += " AND i.date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND i.date <= %s"
        params.append(end_date)
    query = f"""
    SELECT p.product_name,
        SUM(i.units_received) as total_received,
        SUM(i.observed_units_sold) as total_observed_sales,
        SUM(i.true_demand) as total_true_demand,
        SUM(i.lost_sales_units) as total_lost_sales,
        SUM(CASE WHEN i.stockout_flag THEN 1 ELSE 0 END) as total_stockout_days
    FROM inventory i
    JOIN products p ON i.product_id = p.product_id
    {where}
    GROUP BY p.product_name
    ORDER BY total_stockout_days DESC
    """
    return run_query(query, params if params else None)

def get_promotion_metrics():
    query = """
    SELECT CASE WHEN promotion_id IS NOT NULL THEN 'During Promotion' ELSE 'No Promotion' END as promo_status,
        SUM(revenue) as total_revenue,
        SUM(quantity) as total_units_sold,
        AVG(quantity) as avg_units_per_transaction,
        COUNT(sale_id) as transaction_count
    FROM sales
    GROUP BY promo_status
    """
    return run_query(query)

def get_supplier_metrics():
    if using_demo_data():
        lead_time = "julianday(po.actual_delivery_date) - julianday(po.order_date)"
        delay = "julianday(po.actual_delivery_date) - julianday(po.expected_delivery_date)"
    else:
        lead_time = "po.actual_delivery_date - po.order_date"
        delay = "po.actual_delivery_date - po.expected_delivery_date"
    query = f"""
    SELECT s.supplier_name,
        COUNT(po.purchase_order_id) as num_purchase_orders,
        SUM(po.quantity_ordered) as total_units_ordered,
        s.nominal_lead_time_days,
        AVG({lead_time}) as avg_actual_lead_time,
        AVG({delay}) as avg_delay_days,
        1.0 * COUNT(CASE WHEN po.actual_delivery_date <= po.expected_delivery_date THEN 1 END) / NULLIF(COUNT(po.purchase_order_id), 0) as on_time_delivery_rate
    FROM suppliers s
    LEFT JOIN purchase_orders po ON s.supplier_id = po.supplier_id
    GROUP BY s.supplier_name, s.nominal_lead_time_days
    ORDER BY num_purchase_orders DESC
    """
    return run_query(query)

def get_customer_metrics():
    query = """
    SELECT c.customer_segment,
        COUNT(DISTINCT c.customer_id) as num_customers,
        COUNT(s.sale_id) as num_orders,
        SUM(s.revenue) as total_revenue
    FROM customers c
    LEFT JOIN sales s ON c.customer_id = s.customer_id
    GROUP BY c.customer_segment
    ORDER BY total_revenue DESC
    """
    return run_query(query)

def get_current_stock_per_product(stale_days: int = 30):
    """Latest inventory per product, flagging stale records."""
    days_since = "CAST(julianday(CURRENT_DATE) - julianday(i.date) AS INTEGER)" if using_demo_data() else "CURRENT_DATE - i.date"
    query = f"""
    WITH ranked_inventory AS (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY product_id ORDER BY date DESC, inventory_id DESC
        ) as stock_rank
        FROM inventory
    )
    SELECT
        p.product_id,
        p.product_name,
        c.category_name,
        COALESCE(p.stock_unit, 'Units') as stock_unit,
        i.date as latest_inventory_date,
        COALESCE(i.closing_stock, 0) as current_stock,
        COALESCE(i.opening_stock, 0) as opening_stock,
        COALESCE(i.units_received, 0) as units_received,
        COALESCE(i.stockout_flag, false) as stockout_flag,
        CASE WHEN i.date IS NULL THEN 'No Inventory History'
             WHEN ({days_since}) > %s THEN 'Needs Reconciliation'
             ELSE 'Up to Date' END as stock_status,
        ({days_since}) as days_since_last_record
    FROM products p
    LEFT JOIN categories c ON p.category_id = c.category_id
    LEFT JOIN ranked_inventory i ON p.product_id = i.product_id AND i.stock_rank = 1
    ORDER BY p.product_id;
    """
    result = run_query(query, [stale_days])
    result["latest_inventory_date"] = pd.to_datetime(result["latest_inventory_date"])
    result["stockout_flag"] = result["stockout_flag"].astype(bool)
    return result

def get_stockout_by_product(limit=10, start_date=None, end_date=None):
    """Product stockout days within optional date range."""
    where = "WHERE 1=1"
    params = []
    if start_date:
        where += " AND i.date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND i.date <= %s"
        params.append(end_date)
    query = f"""
    SELECT p.product_name, SUM(CASE WHEN i.stockout_flag THEN 1 ELSE 0 END) as stockout_days
    FROM inventory i
    JOIN products p ON i.product_id = p.product_id
    {where}
    GROUP BY p.product_name
    ORDER BY stockout_days DESC
    LIMIT %s
    """
    params.append(limit)
    return run_query(query, params)

def get_product_units_sold(limit=10, start_date=None, end_date=None):
    """Product units sold within optional date range."""
    where = "WHERE 1=1"
    params = []
    if start_date:
        where += " AND s.date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND s.date <= %s"
        params.append(end_date)
    query = f"""
    SELECT p.product_name, COALESCE(SUM(s.quantity), 0) as units_sold
    FROM sales s
    JOIN products p ON s.product_id = p.product_id
    {where}
    GROUP BY p.product_name
    ORDER BY units_sold DESC
    LIMIT %s
    """
    params.append(limit)
    return run_query(query, params)
