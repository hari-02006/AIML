import os
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
    md = "# Stage 5 - Analytics Report\n\n"
    md += "## Executive Summary\n"
    md += f"- **Total Revenue:** ${format_number(metrics['overall'][0]['total_revenue'])}\n"
    md += f"- **Total Units Sold:** {format_number(metrics['overall'][0]['total_units_sold'])}\n"
    md += f"- **Total Products:** {format_number(metrics['overall'][0]['total_products'])}\n"
    md += f"- **Total Customers:** {format_number(metrics['overall'][0]['total_customers'])}\n"
    md += f"- **Total Transactions:** {format_number(metrics['overall'][0]['total_transactions'])}\n"
    md += f"- **Current Inventory:** {format_number(metrics['overall'][0]['current_total_inventory'])}\n"
    md += f"- **Total Lost Sales:** {format_number(metrics['overall'][0]['total_lost_sales'])}\n"
    md += f"- **Stockout Product-Days:** {format_number(metrics['overall'][0]['stockout_product_days'])}\n\n"
    
    md += "## Demand vs Observed Sales\n"
    dvo = metrics['demand_vs_observed'][0]
    md += f"- **Total True Demand:** {format_number(dvo['total_true_demand'])}\n"
    md += f"- **Total Observed Sales:** {format_number(dvo['total_observed_sales'])}\n"
    md += f"- **Total Lost Sales:** {format_number(dvo['total_lost_sales'])}\n"
    md += f"- **Lost Sales Rate:** {format_number(float(dvo['lost_sales_rate']) * 100)}%\n\n"
    
    md += "## Key Findings\n"
    # Products
    prods = sorted(metrics['product'], key=lambda x: x['revenue'], reverse=True)
    if prods:
        md += f"1. **Highest Revenue Product:** {prods[0]['product_name']} (${format_number(prods[0]['revenue'])})\n"
    prods_units = sorted(metrics['product'], key=lambda x: x['units_sold'], reverse=True)
    if prods_units:
        md += f"2. **Highest Units Sold Product:** {prods_units[0]['product_name']} ({format_number(prods_units[0]['units_sold'])} units)\n"
    prods_lost = sorted(metrics['product'], key=lambda x: x['lost_sales_units'], reverse=True)
    if prods_lost:
        md += f"3. **Highest Lost Sales Product:** {prods_lost[0]['product_name']} ({format_number(prods_lost[0]['lost_sales_units'])} units)\n"
    
    # Categories
    cats = sorted(metrics['category'], key=lambda x: x['revenue'], reverse=True)
    if cats:
        md += f"4. **Highest Revenue Category:** {cats[0]['category_name']} (${format_number(cats[0]['revenue'])})\n"
        
    # Weekday vs Weekend
    wkd = metrics['weekday']
    weekend_rev = sum(d['total_revenue'] for d in wkd if d['day_type'] == 'Weekend')
    weekday_rev = sum(d['total_revenue'] for d in wkd if d['day_type'] == 'Weekday')
    md += f"5. **Weekend vs Weekday:** Weekend revenue (${format_number(weekend_rev)}) vs Weekday revenue (${format_number(weekday_rev)}).\n"
    
    # Promotions
    promo = metrics['promotion']
    md += f"6. **Promotions:** "
    for p in promo:
        md += f"{p['promo_status']} generated ${format_number(p['total_revenue'])}. "
    md += "\n"
    
    # Suppliers
    sups = sorted(metrics['supplier'], key=lambda x: x['avg_delay_days'] if x['avg_delay_days'] is not None else 0, reverse=True)
    if sups:
        md += f"7. **Supplier Delays:** The simulated data showed an average delivery delay of {format_number(sups[0]['avg_delay_days'])} days for {sups[0]['supplier_name']}.\n\n"
        
    md += "## Limitations\n"
    md += "- Results are based on simulated business behavior.\n"
    md += "- Patterns demonstrate the analytical pipeline.\n"
    md += "- Results should not be interpreted as real market behavior.\n"
    md += "- Temporal trends (monthly) reflect the short simulated period, not multi-year macro trends.\n\n"
    
    md += "## Next Stage\n"
    md += "Stage 6 — Dashboard (NOT STARTED)\n"
    
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
