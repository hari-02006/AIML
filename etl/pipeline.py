import os
import csv
import json
import datetime
from .config import load_config
from .extract.csv_extractor import extract_file
from .transform.clean_data import clean_dataframe, standardize_dates
from .validate.schema_validation import validate_schema, check_duplicates
from .validate.business_rules import validate_inventory_rules
from .load.postgres_loader import load_table

def ensure_dirs(config):
    for d in [config['processed_dir'], config['validated_dir'], config['rejected_dir'], config['log_dir']]:
        os.makedirs(d, exist_ok=True)

def save_csv(path, data):
    if not data: return
    keys = list(data[0].keys())
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

def process_file(filepath, table_name, pk, date_cols, num_cols, not_nulls, config, run_id):
    print(f"Processing {filepath} for {table_name}...")
    try:
        data, file_hash = extract_file(filepath)
    except Exception as e:
        print(f"Failed to extract {filepath}: {e}")
        return {"extracted": 0, "processed": 0, "validated": 0, "rejected": 0, "eligible": 0, "attempted": 0, "inserted": 0, "skipped": 0, "errors": []}
        
    data = clean_dataframe(data)
    data = standardize_dates(data, date_cols)
    
    if table_name == 'products':
        from database.db_connection import get_connection
        conn = get_connection()
        cat_map = {}
        with conn.cursor() as cur:
            cur.execute("SELECT category_name, category_id FROM categories")
            for r in cur.fetchall():
                cat_map[r[0]] = r[1]
        conn.close()
        for row in data:
            row['category_id'] = cat_map.get(row.get('category'))
            if 'category' in row: del row['category']
            if 'id' in row:
                row['product_id'] = row['id']
                del row['id']
            if 'name' in row:
                row['product_name'] = row['name']
                del row['name']
                
    elif table_name == 'suppliers':
        for row in data:
            if 'id' in row:
                row['supplier_id'] = row['id']
                del row['id']
            if 'name' in row:
                row['supplier_name'] = row['name']
                del row['name']
    
    proc_path = os.path.join(config['processed_dir'], f"{table_name}_processed.csv")
    save_csv(proc_path, data)
    
    if not data:
        return {"extracted": 0, "processed": 0, "validated": 0, "rejected": 0, "eligible": 0, "attempted": 0, "inserted": 0, "skipped": 0, "errors": []}
        
    all_columns = list(data[0].keys())
    
    errors = validate_schema(data, all_columns, num_cols, not_nulls)
    errors += check_duplicates(data, pk)
    if table_name == 'inventory':
        errors += validate_inventory_rules(data)
        
    if errors:
        print(f"Validation errors in {table_name}: {errors}")
        rej_path = os.path.join(config['rejected_dir'], f"{table_name}_rejected.csv")
        save_csv(rej_path, data)
        return {"extracted": len(data), "processed": len(data), "validated": 0, "rejected": len(data), "eligible": 0, "attempted": 0, "inserted": 0, "skipped": 0, "errors": errors}
        
    val_path = os.path.join(config['validated_dir'], f"{table_name}_validated.csv")
    save_csv(val_path, data)
    
    if config.get('dry_run', False):
        print(f"Dry run: skipping database load for {table_name}")
        return {"extracted": len(data), "processed": len(data), "validated": len(data), "rejected": 0, "eligible": len(data), "attempted": 0, "inserted": 0, "skipped": 0, "errors": []}
    
    # Load to DB
    if table_name == 'categories':
        load_result = load_table(data, table_name, conflict_columns=['category_name'], columns=all_columns)
    else:
        load_result = load_table(data, table_name, conflict_columns=pk, columns=all_columns)
        
    return {
        "extracted": len(data),
        "processed": len(data),
        "validated": len(data),
        "rejected": 0,
        "eligible": len(data),
        "attempted": load_result["attempted"],
        "inserted": load_result["inserted"],
        "skipped": load_result["skipped"],
        "errors": []
    }

def run_pipeline(mode="full", data_dir=None, dry_run=False):
    config = load_config()
    config['dry_run'] = dry_run
    input_dir = data_dir or (config['input_dir'] if mode == "full" else config['incoming_dir'])
    
    ensure_dirs(config)
    run_id = f"ETL_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Starting ETL Run: {run_id} (Mode: {mode}, Dry Run: {dry_run})")
    
    entities = [
        ('categories.csv', 'categories', ['category_name'], [], [], ['category_name']),
        ('suppliers.csv', 'suppliers', ['supplier_id'], [], ['nominal_lead_time_days'], ['supplier_id', 'supplier_name']),
        ('products.csv', 'products', ['product_id'], [], ['base_price', 'cost_price'], ['product_id', 'product_name', 'category_id', 'supplier_id']),
        ('customers.csv', 'customers', ['customer_id'], [], [], ['customer_id']),
        ('promotions.csv', 'promotions', ['promotion_id'], ['start_date', 'end_date'], ['discount_percentage'], ['promotion_id']),
        ('purchase_orders.csv', 'purchase_orders', ['purchase_order_id'], ['order_date', 'expected_delivery_date', 'actual_delivery_date'], ['quantity_ordered'], ['purchase_order_id', 'product_id', 'supplier_id']),
        ('inventory.csv', 'inventory', ['inventory_id'], ['date'], ['opening_stock', 'units_received', 'true_demand', 'observed_units_sold', 'lost_sales_units', 'closing_stock'], ['inventory_id', 'date', 'product_id']),
        ('sales.csv', 'sales', ['sale_id'], ['date'], ['quantity', 'unit_price', 'discount', 'revenue'], ['sale_id', 'date', 'product_id', 'customer_id'])
    ]
    
    report = {
        "run_id": run_id,
        "mode": mode,
        "dry_run": dry_run,
        "status": "IN_PROGRESS",
        "entities": {}
    }
    
    total_ext, total_proc, total_val, total_rej, total_eli, total_att, total_ins, total_skip = 0, 0, 0, 0, 0, 0, 0, 0
    
    import glob
    for filename, table, pk, date_cols, num_cols, not_nulls in entities:
        search_pattern = os.path.join(input_dir, f"*{filename}")
        matched_files = glob.glob(search_pattern)
        
        if not matched_files:
            print(f"Skipping {filename} - no matching files found in {input_dir}.")
            continue
            
        for filepath in matched_files:
            metrics = process_file(filepath, table, pk, date_cols, num_cols, not_nulls, config, run_id)
            if table not in report["entities"]:
                report["entities"][table] = {"extracted": 0, "processed": 0, "validated": 0, "rejected": 0, "eligible": 0, "attempted": 0, "inserted": 0, "skipped": 0, "errors": []}
            report["entities"][table]["extracted"] += metrics["extracted"]
            report["entities"][table]["processed"] += metrics["processed"]
            report["entities"][table]["validated"] += metrics["validated"]
            report["entities"][table]["rejected"] += metrics["rejected"]
            report["entities"][table]["eligible"] += metrics.get("eligible", 0)
            report["entities"][table]["attempted"] += metrics["attempted"]
            report["entities"][table]["inserted"] += metrics["inserted"]
            report["entities"][table]["skipped"] += metrics["skipped"]
            report["entities"][table]["errors"].extend(metrics["errors"])
            
            total_ext += metrics["extracted"]
            total_proc += metrics["processed"]
            total_val += metrics["validated"]
            total_rej += metrics["rejected"]
            total_eli += metrics.get("eligible", 0)
            total_att += metrics["attempted"]
            total_ins += metrics["inserted"]
            total_skip += metrics["skipped"]
        
    report["status"] = "SUCCESS" if total_rej == 0 else "PARTIAL_SUCCESS"
    
    rep_path = os.path.join(config['log_dir'], f"etl_quality_report_{run_id}.json")
    with open(rep_path, 'w') as f:
        json.dump(report, f, indent=4)
        
    print(f"\\nETL PIPELINE COMPLETE")
    print(f"Extracted: {total_ext}")
    print(f"Processed: {total_proc}")
    print(f"Validated: {total_val}")
    print(f"Rejected: {total_rej}")
    if config.get('dry_run'):
        print(f"Load Eligible: {total_eli}")
    print(f"Load Attempted: {total_att}")
    print(f"Inserted: {total_ins}")
    print(f"Skipped: {total_skip}")
    print(f"Status: {report['status']}")
    
    if config.get('dry_run'):
        print(f"\\nDry Run = TRUE")
        print(f"Database Writes = 0")
