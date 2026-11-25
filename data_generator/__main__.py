import argparse
import os
import json
import datetime
import csv
from .config_loader import load_config
from .catalog import generate_catalog
from .suppliers import generate_suppliers
from .customers import generate_customers
from .promotions import generate_promotions
from .simulation import run_simulation
from .validation import run_validations
from .utils import get_random_state

def save_csv(data, filename, fieldnames):
    with open(filename, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            # only write expected fieldnames, ignore extra
            filtered_row = {k: row[k] for k in fieldnames if k in row}
            writer.writerow(filtered_row)

def main():
    parser = argparse.ArgumentParser(description="Synthetic Data Generator")
    parser.add_argument('--seed', type=int, default=42, help="Random seed")
    parser.add_argument('--start-date', type=str, default="2025-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument('--end-date', type=str, default="2025-12-31", help="End date (YYYY-MM-DD)")
    parser.add_argument('--scenario', type=str, default="normal", help="Scenario to run")
    parser.add_argument('--output-dir', type=str, default="data/raw", help="Output directory")
    args = parser.parse_args()

    print(f"Loading configuration...")
    config = load_config()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    rng = get_random_state(args.seed)
    
    print("Generating master data...")
    products, categories = generate_catalog(config)
    suppliers = generate_suppliers(config)
    customers = generate_customers(500, rng)
    
    sd = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
    ed = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()
    promotions = generate_promotions(config, sd, ed)
    
    print(f"Running simulation from {args.start_date} to {args.end_date}...")
    inventory, sales, purchase_orders = run_simulation(
        config, products, suppliers, promotions, customers, 
        sd, ed, args.seed
    )
    
    print("Running validations...")
    errors = run_validations(products, customers, suppliers, promotions, sales, inventory, purchase_orders)
    if errors:
        print("VALIDATION FAILED:")
        for e in errors[:10]:
            print(f" - {e}")
        if len(errors) > 10:
            print(f"... and {len(errors) - 10} more errors.")
        return
    else:
        print("Validation PASSED.")
        
    print("Saving files...")
    # Map for saving with right keys
    save_csv(categories, os.path.join(args.output_dir, "categories.csv"), ["category_name"])
    save_csv(products, os.path.join(args.output_dir, "products.csv"), ["id", "name", "category", "base_price", "cost_price", "popularity_class", "demand_pattern_class", "supplier_id"])
    save_csv(suppliers, os.path.join(args.output_dir, "suppliers.csv"), ["id", "name", "nominal_lead_time_days", "reliability_class"])
    save_csv(customers, os.path.join(args.output_dir, "customers.csv"), ["customer_id", "age_group", "location", "customer_segment"])
    
    # Process promotions dates to strings
    for p in promotions:
        if isinstance(p['start_date'], datetime.date):
            p['start_date'] = p['start_date'].strftime("%Y-%m-%d")
        if isinstance(p['end_date'], datetime.date):
            p['end_date'] = p['end_date'].strftime("%Y-%m-%d")
    
    save_csv(promotions, os.path.join(args.output_dir, "promotions.csv"), ["promotion_id", "promotion_name", "discount_percentage", "start_date", "end_date"])
    save_csv(inventory, os.path.join(args.output_dir, "inventory.csv"), ["inventory_id", "date", "product_id", "opening_stock", "units_received", "true_demand", "observed_units_sold", "lost_sales_units", "closing_stock", "stockout_flag"])
    save_csv(sales, os.path.join(args.output_dir, "sales.csv"), ["sale_id", "date", "product_id", "customer_id", "quantity", "unit_price", "discount", "promotion_id", "revenue"])
    save_csv(purchase_orders, os.path.join(args.output_dir, "purchase_orders.csv"), ["purchase_order_id", "product_id", "supplier_id", "order_date", "quantity_ordered", "expected_delivery_date", "actual_delivery_date", "status"])
    
    # Save manifest
    manifest = {
        "generator_version": "1.0",
        "random_seed": args.seed,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "scenario": args.scenario,
        "product_count": len(products),
        "customer_count": len(customers),
        "supplier_count": len(suppliers),
        "promotion_count": len(promotions),
        "row_counts": {
            "categories": len(categories),
            "products": len(products),
            "suppliers": len(suppliers),
            "customers": len(customers),
            "promotions": len(promotions),
            "inventory": len(inventory),
            "sales": len(sales),
            "purchase_orders": len(purchase_orders)
        },
        "generation_timestamp": datetime.datetime.now().isoformat()
    }
    with open(os.path.join(args.output_dir, "generation_manifest.json"), 'w') as f:
        json.dump(manifest, f, indent=4)
        
    total_true_demand = sum(r['true_demand'] for r in inventory)
    total_observed_sales = sum(r['observed_units_sold'] for r in inventory)
    total_lost_sales = sum(r['lost_sales_units'] for r in inventory)
    stockout_days = sum(1 for r in inventory if r['stockout_flag'] == 'True')
    total_revenue = sum(r['revenue'] for r in sales)
        
    # Write report
    report = {
        "seed": args.seed,
        "date_range": f"{args.start_date} to {args.end_date}",
        "scenario": args.scenario,
        "products": len(products),
        "customers": len(customers),
        "suppliers": len(suppliers),
        "promotions": len(promotions),
        "sales_row_count": len(sales),
        "inventory_row_count": len(inventory),
        "purchase_order_count": len(purchase_orders),
        "total_true_demand": total_true_demand,
        "total_observed_sales": total_observed_sales,
        "total_lost_sales": total_lost_sales,
        "number_of_stockout_days": stockout_days,
        "total_revenue": total_revenue,
        "validation_checks_passed": True
    }
    with open(os.path.join(args.output_dir, "generation_report.json"), 'w') as f:
        json.dump(report, f, indent=4)
        
    print("\nSYNTHETIC DATA GENERATION COMPLETE\n")
    print(f"Scenario: {args.scenario}")
    print(f"Seed: {args.seed}")
    print(f"Date range: {args.start_date} to {args.end_date}")
    print(f"Products: {len(products)}")
    print(f"Customers: {len(customers)}")
    print(f"Sales rows: {len(sales)}")
    print(f"Inventory rows: {len(inventory)}")
    print(f"Purchase orders: {len(purchase_orders)}")
    print(f"Total true demand: {report['total_true_demand']}")
    print(f"Observed sales: {report['total_observed_sales']}")
    print(f"Lost sales: {report['total_lost_sales']}")
    print(f"Stockout product-days: {report['number_of_stockout_days']}")
    print(f"Revenue: {report['total_revenue']}")
    print("Validation: PASSED")

if __name__ == '__main__':
    main()
