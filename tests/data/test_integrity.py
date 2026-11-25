import csv
import os

def test_inventory_equation():
    inventory_file = "data/raw/inventory.csv"
    assert os.path.exists(inventory_file)
    
    with open(inventory_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            open_st = int(row['opening_stock'])
            rec = int(row['units_received'])
            obs = int(row['observed_units_sold'])
            close = int(row['closing_stock'])
            assert open_st + rec - obs == close

def test_demand_sales_relationship():
    inventory_file = "data/raw/inventory.csv"
    with open(inventory_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            true_d = int(row['true_demand'])
            obs = int(row['observed_units_sold'])
            lost = int(row['lost_sales_units'])
            assert obs <= true_d
            assert lost == true_d - obs
            
            # Stockout test
            stockout = row['stockout_flag'] == 'True'
            if stockout:
                assert lost > 0
            if lost > 0:
                assert stockout

def test_sales_aggregation():
    inventory_file = "data/raw/inventory.csv"
    sales_file = "data/raw/sales.csv"
    
    inv_map = {}
    with open(inventory_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            inv_map[(row['date'], row['product_id'])] = int(row['observed_units_sold'])
            
    sales_agg = {}
    with open(sales_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['date'], row['product_id'])
            sales_agg[key] = sales_agg.get(key, 0) + int(row['quantity'])
            
    for key, agg_qty in sales_agg.items():
        assert inv_map[key] == agg_qty
        
    for key, obs in inv_map.items():
        if obs > 0:
            assert sales_agg.get(key, 0) == obs
        else:
            assert key not in sales_agg
