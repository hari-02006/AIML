import os

def create_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# SQL Scripts
create_file("analytics/sql/overall_metrics.sql", """
SELECT 
    (SELECT COALESCE(SUM(revenue), 0) FROM sales) as total_revenue,
    (SELECT COALESCE(SUM(quantity), 0) FROM sales) as total_units_sold,
    (SELECT COUNT(*) FROM products) as total_products,
    (SELECT COUNT(*) FROM customers) as total_customers,
    (SELECT COUNT(*) FROM sales) as total_transactions,
    (SELECT COALESCE(SUM(closing_stock), 0) FROM inventory WHERE date = (SELECT MAX(date) FROM inventory)) as current_total_inventory,
    (SELECT COALESCE(SUM(lost_sales_units), 0) FROM inventory) as total_lost_sales,
    (SELECT COUNT(*) FROM inventory WHERE stockout_flag = TRUE) as stockout_product_days
;
""")

create_file("analytics/sql/sales_analysis.sql", """
SELECT 
    date,
    SUM(quantity) as units_sold,
    SUM(revenue) as revenue,
    COUNT(sale_id) as number_of_transactions
FROM sales
GROUP BY date
ORDER BY date;
""")

create_file("analytics/sql/product_analysis.sql", """
WITH product_sales AS (
    SELECT product_id, SUM(quantity) as units_sold, SUM(revenue) as revenue, COUNT(sale_id) as transaction_count
    FROM sales
    GROUP BY product_id
),
product_inventory AS (
    SELECT product_id, SUM(lost_sales_units) as lost_sales_units, SUM(CASE WHEN stockout_flag THEN 1 ELSE 0 END) as stockout_days
    FROM inventory
    GROUP BY product_id
)
SELECT 
    p.product_id,
    p.product_name,
    COALESCE(s.units_sold, 0) as units_sold,
    COALESCE(s.revenue, 0) as revenue,
    CASE WHEN s.units_sold > 0 THEN s.revenue / s.units_sold ELSE 0 END as avg_selling_price,
    COALESCE(s.transaction_count, 0) as transaction_count,
    COALESCE(i.lost_sales_units, 0) as lost_sales_units,
    COALESCE(i.stockout_days, 0) as stockout_days
FROM products p
LEFT JOIN product_sales s ON p.product_id = s.product_id
LEFT JOIN product_inventory i ON p.product_id = i.product_id
ORDER BY revenue DESC;
""")

create_file("analytics/sql/category_performance.sql", """
SELECT 
    c.category_name,
    COALESCE(SUM(s.revenue), 0) as revenue,
    COALESCE(SUM(s.quantity), 0) as units_sold,
    COUNT(s.sale_id) as transaction_count,
    CASE WHEN SUM(s.quantity) > 0 THEN SUM(s.revenue) / SUM(s.quantity) ELSE 0 END as avg_selling_price
FROM categories c
LEFT JOIN products p ON c.category_id = p.category_id
LEFT JOIN sales s ON p.product_id = s.product_id
GROUP BY c.category_name
ORDER BY revenue DESC;
""")

create_file("analytics/sql/inventory_analysis.sql", """
SELECT 
    p.product_name,
    SUM(i.units_received) as total_received,
    SUM(i.observed_units_sold) as total_observed_sales,
    SUM(i.true_demand) as total_true_demand,
    SUM(i.lost_sales_units) as total_lost_sales,
    SUM(CASE WHEN i.stockout_flag THEN 1 ELSE 0 END) as total_stockout_days
FROM inventory i
JOIN products p ON i.product_id = p.product_id
GROUP BY p.product_name
ORDER BY total_stockout_days DESC;
""")

create_file("analytics/sql/demand_vs_observed.sql", """
SELECT 
    SUM(true_demand) as total_true_demand,
    SUM(observed_units_sold) as total_observed_sales,
    SUM(lost_sales_units) as total_lost_sales,
    CASE WHEN SUM(true_demand) > 0 THEN SUM(lost_sales_units)::numeric / SUM(true_demand) ELSE 0 END as lost_sales_rate
FROM inventory;
""")

create_file("analytics/sql/promotion_analysis.sql", """
SELECT 
    CASE WHEN promotion_id IS NOT NULL THEN 'During Promotion' ELSE 'No Promotion' END as promo_status,
    SUM(revenue) as total_revenue,
    SUM(quantity) as total_units_sold,
    AVG(quantity) as avg_units_per_transaction
FROM sales
GROUP BY promo_status;
""")

create_file("analytics/sql/discount_analysis.sql", """
SELECT 
    CASE 
        WHEN discount = 0 THEN '0%'
        WHEN discount > 0 AND discount <= 0.05 THEN '0-5%'
        WHEN discount > 0.05 AND discount <= 0.10 THEN '5-10%'
        WHEN discount > 0.10 AND discount <= 0.20 THEN '10-20%'
        ELSE '>20%'
    END as discount_band,
    SUM(quantity) as units_sold,
    SUM(revenue) as total_revenue
FROM sales
GROUP BY discount_band
ORDER BY MIN(discount);
""")

create_file("analytics/sql/weekday_analysis.sql", """
SELECT 
    EXTRACT(DOW FROM date) as dow,
    TO_CHAR(date, 'Day') as day_of_week,
    CASE WHEN EXTRACT(DOW FROM date) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END as day_type,
    SUM(quantity) as total_units_sold,
    SUM(revenue) as total_revenue,
    COUNT(sale_id) as transaction_count,
    AVG(quantity) as avg_units_sold,
    AVG(revenue) as avg_revenue
FROM sales
GROUP BY dow, day_of_week, day_type
ORDER BY dow;
""")

create_file("analytics/sql/supplier_analysis.sql", """
SELECT 
    s.supplier_name,
    COUNT(po.purchase_order_id) as num_purchase_orders,
    SUM(po.quantity_ordered) as total_units_ordered,
    s.nominal_lead_time_days,
    AVG(po.actual_delivery_date - po.order_date) as avg_actual_lead_time,
    AVG(po.actual_delivery_date - po.expected_delivery_date) as avg_delay_days,
    MAX(po.actual_delivery_date - po.expected_delivery_date) as max_delay_days,
    COUNT(CASE WHEN po.actual_delivery_date <= po.expected_delivery_date THEN 1 END)::numeric / COUNT(po.purchase_order_id) as on_time_delivery_rate
FROM suppliers s
LEFT JOIN purchase_orders po ON s.supplier_id = po.supplier_id
GROUP BY s.supplier_name, s.nominal_lead_time_days
ORDER BY num_purchase_orders DESC;
""")

create_file("analytics/sql/customer_analysis.sql", """
SELECT 
    c.customer_segment,
    COUNT(DISTINCT c.customer_id) as num_customers,
    COUNT(s.sale_id) as num_orders,
    SUM(s.revenue) as total_revenue,
    CASE WHEN COUNT(DISTINCT c.customer_id) > 0 THEN SUM(s.revenue) / COUNT(DISTINCT c.customer_id) ELSE 0 END as revenue_per_customer
FROM customers c
LEFT JOIN sales s ON c.customer_id = s.customer_id
GROUP BY c.customer_segment
ORDER BY total_revenue DESC;
""")

# Python Analysis Engine
create_file("analytics/analysis.py", """import os
import json
import csv
from database.db_connection import get_connection

def run_sql_file(filepath):
    with open(filepath, 'r') as f:
        query = f.read()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            cols = [desc[0] for desc in cur.description]
            results = [dict(zip(cols, row)) for row in cur.fetchall()]
        return results
    finally:
        conn.close()

def save_csv(data, filename):
    if not data: return
    os.makedirs('analytics/reports', exist_ok=True)
    keys = data[0].keys()
    with open(f'analytics/reports/{filename}', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

def format_number(val):
    if val is None: return "N/A"
    if isinstance(val, (int, float)):
        return f"{val:,.2f}" if isinstance(val, float) else f"{val:,}"
    return str(val)

def generate_markdown_report(metrics):
    md = "# Stage 5 - Analytics Report\\n\\n"
    md += "## Executive Summary\\n"
    md += f"- **Total Revenue:** ${format_number(metrics['overall'][0]['total_revenue'])}\\n"
    md += f"- **Total Units Sold:** {format_number(metrics['overall'][0]['total_units_sold'])}\\n"
    md += f"- **Total Products:** {format_number(metrics['overall'][0]['total_products'])}\\n"
    md += f"- **Total Customers:** {format_number(metrics['overall'][0]['total_customers'])}\\n"
    md += f"- **Total Transactions:** {format_number(metrics['overall'][0]['total_transactions'])}\\n"
    md += f"- **Current Inventory:** {format_number(metrics['overall'][0]['current_total_inventory'])}\\n"
    md += f"- **Total Lost Sales:** {format_number(metrics['overall'][0]['total_lost_sales'])}\\n"
    md += f"- **Stockout Product-Days:** {format_number(metrics['overall'][0]['stockout_product_days'])}\\n\\n"
    
    md += "## Demand vs Observed Sales\\n"
    dvo = metrics['demand_vs_observed'][0]
    md += f"- **Total True Demand:** {format_number(dvo['total_true_demand'])}\\n"
    md += f"- **Total Observed Sales:** {format_number(dvo['total_observed_sales'])}\\n"
    md += f"- **Total Lost Sales:** {format_number(dvo['total_lost_sales'])}\\n"
    md += f"- **Lost Sales Rate:** {format_number(float(dvo['lost_sales_rate']) * 100)}%\\n\\n"
    
    md += "## Key Findings\\n"
    # Products
    prods = sorted(metrics['product'], key=lambda x: x['revenue'], reverse=True)
    if prods:
        md += f"1. **Highest Revenue Product:** {prods[0]['product_name']} (${format_number(prods[0]['revenue'])})\\n"
    prods_units = sorted(metrics['product'], key=lambda x: x['units_sold'], reverse=True)
    if prods_units:
        md += f"2. **Highest Units Sold Product:** {prods_units[0]['product_name']} ({format_number(prods_units[0]['units_sold'])} units)\\n"
    prods_lost = sorted(metrics['product'], key=lambda x: x['lost_sales_units'], reverse=True)
    if prods_lost:
        md += f"3. **Highest Lost Sales Product:** {prods_lost[0]['product_name']} ({format_number(prods_lost[0]['lost_sales_units'])} units)\\n"
    
    # Categories
    cats = sorted(metrics['category'], key=lambda x: x['revenue'], reverse=True)
    if cats:
        md += f"4. **Highest Revenue Category:** {cats[0]['category_name']} (${format_number(cats[0]['revenue'])})\\n"
        
    # Weekday vs Weekend
    wkd = metrics['weekday']
    weekend_rev = sum(d['total_revenue'] for d in wkd if d['day_type'] == 'Weekend')
    weekday_rev = sum(d['total_revenue'] for d in wkd if d['day_type'] == 'Weekday')
    md += f"5. **Weekend vs Weekday:** Weekend revenue (${format_number(weekend_rev)}) vs Weekday revenue (${format_number(weekday_rev)}).\\n"
    
    # Promotions
    promo = metrics['promotion']
    md += f"6. **Promotions:** "
    for p in promo:
        md += f"{p['promo_status']} generated ${format_number(p['total_revenue'])}. "
    md += "\\n"
    
    # Suppliers
    sups = sorted(metrics['supplier'], key=lambda x: x['avg_delay_days'] if x['avg_delay_days'] is not None else 0, reverse=True)
    if sups:
        md += f"7. **Supplier Delays:** The simulated data showed an average delivery delay of {format_number(sups[0]['avg_delay_days'])} days for {sups[0]['supplier_name']}.\\n\\n"
        
    md += "## Limitations\\n"
    md += "- Results are based on simulated business behavior.\\n"
    md += "- Patterns demonstrate the analytical pipeline.\\n"
    md += "- Results should not be interpreted as real market behavior.\\n"
    md += "- Temporal trends (monthly) reflect the short simulated period, not multi-year macro trends.\\n\\n"
    
    md += "## Next Stage\\n"
    md += "Stage 6 — Dashboard (NOT STARTED)\\n"
    
    with open('analytics/reports/stage5-analytics-report.md', 'w') as f:
        f.write(md)

def main():
    print("Starting Analytics Extraction...")
    queries = {
        'overall': 'analytics/sql/overall_metrics.sql',
        'sales': 'analytics/sql/sales_analysis.sql',
        'product': 'analytics/sql/product_analysis.sql',
        'category': 'analytics/sql/category_performance.sql',
        'inventory': 'analytics/sql/inventory_analysis.sql',
        'demand_vs_observed': 'analytics/sql/demand_vs_observed.sql',
        'promotion': 'analytics/sql/promotion_analysis.sql',
        'discount': 'analytics/sql/discount_analysis.sql',
        'weekday': 'analytics/sql/weekday_analysis.sql',
        'supplier': 'analytics/sql/supplier_analysis.sql',
        'customer': 'analytics/sql/customer_analysis.sql'
    }
    
    metrics = {}
    for key, filepath in queries.items():
        print(f"Running {key} analysis...")
        data = run_sql_file(filepath)
        metrics[key] = data
        save_csv(data, f"{key}_analysis.csv")
    
    with open('analytics/reports/summary_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=4, default=str)
        
    generate_markdown_report(metrics)
    print("Analytics generation complete! Check analytics/reports/")

if __name__ == "__main__":
    main()
""")

# Analytics Tests
create_file("tests/analytics/test_analytics.py", """import pytest
import os
from database.db_connection import get_connection

def test_overall_metrics():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/overall_metrics.sql', 'r') as f:
                cur.execute(f.read())
                row = cur.fetchone()
                assert row is not None
                assert len(row) == 8
    finally:
        conn.close()

def test_demand_vs_observed():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/demand_vs_observed.sql', 'r') as f:
                cur.execute(f.read())
                row = cur.fetchone()
                assert row is not None
                # Check lost sales rate math logic
                # true_demand, observed_sales, lost_sales, rate
                true_demand, obs_sales, lost_sales, rate = row
                if true_demand > 0:
                    assert abs((float(lost_sales) / float(true_demand)) - float(rate)) < 0.01
    finally:
        conn.close()

def test_product_aggregation():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/product_analysis.sql', 'r') as f:
                cur.execute(f.read())
                rows = cur.fetchall()
                assert len(rows) > 0, "Product aggregation should return rows"
                assert len(rows[0]) == 8, "Product query should return exactly 8 columns"
    finally:
        conn.close()

def test_category_aggregation():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/category_performance.sql', 'r') as f:
                cur.execute(f.read())
                rows = cur.fetchall()
                assert len(rows) > 0, "Category aggregation should return rows"
                assert len(rows[0]) == 5, "Category query should return exactly 5 columns"
    finally:
        conn.close()

def test_inventory_aggregation():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/inventory_analysis.sql', 'r') as f:
                cur.execute(f.read())
                rows = cur.fetchall()
                assert len(rows) > 0, "Inventory aggregation should return rows"
                assert len(rows[0]) == 6, "Inventory query should return exactly 6 columns"
    finally:
        conn.close()

def test_sales_aggregation():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/sales_analysis.sql', 'r') as f:
                cur.execute(f.read())
                rows = cur.fetchall()
                assert len(rows) > 0, "Sales aggregation should return rows"
                assert len(rows[0]) == 4, "Sales query should return exactly 4 columns"
    finally:
        conn.close()
""")
