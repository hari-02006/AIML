import pytest
import os
import csv
from etl.pipeline import run_pipeline
from database.db_connection import get_connection

def test_dry_run():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM sales")
    before = cur.fetchone()[0]
    conn.close()
    
    run_pipeline(mode="incremental", dry_run=True)
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM sales")
    after = cur.fetchone()[0]
    conn.close()
    
    assert before == after

def test_incremental_insertion_and_idempotency(tmp_path):
    # Setup temporary incoming dir
    incoming_dir = tmp_path / "incoming"
    incoming_dir.mkdir()
    
    test_file = incoming_dir / "test_sales.csv"
    
    data = [
        {"sale_id": "TEST_IDEMP_001", "date": "2026-01-01", "product_id": "PROD_001", "customer_id": "CUST_0001", "quantity": "1", "unit_price": "10.0", "discount": "0", "promotion_id": "", "revenue": "10.0"}
    ]
    
    keys = data[0].keys()
    with open(test_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)
        
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM sales WHERE sale_id = 'TEST_IDEMP_001'")
    conn.commit()
    
    cur.execute("SELECT count(*) FROM sales")
    before_count = cur.fetchone()[0]
    
    # First run
    run_pipeline(mode="incremental", data_dir=str(incoming_dir))
    
    cur.execute("SELECT count(*) FROM sales")
    after_first_count = cur.fetchone()[0]
    assert after_first_count == before_count + 1
    
    # Second run (Idempotency check)
    run_pipeline(mode="incremental", data_dir=str(incoming_dir))
    
    cur.execute("SELECT count(*) FROM sales")
    after_second_count = cur.fetchone()[0]
    assert after_second_count == after_first_count
    
    # Clean up
    cur.execute("DELETE FROM sales WHERE sale_id = 'TEST_IDEMP_001'")
    conn.commit()
    conn.close()
