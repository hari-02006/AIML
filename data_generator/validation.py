
def run_validations(products, customers, suppliers, promotions, sales, inventory, purchase_orders):
    errors = []
    
    sales_agg = {}
    for s in sales:
        key = (s['date'], s['product_id'])
        sales_agg[key] = sales_agg.get(key, 0) + s['quantity']
    
    for row in inventory:
        calc_close = row['opening_stock'] + row['units_received'] - row['observed_units_sold']
        if calc_close != row['closing_stock']:
            errors.append(f"Inventory equation mismatch on {row['date']} for {row['product_id']}")
            
        if row['observed_units_sold'] > row['true_demand']:
            errors.append(f"Observed > True demand on {row['date']} for {row['product_id']}")
            
        if row['lost_sales_units'] != row['true_demand'] - row['observed_units_sold']:
            errors.append(f"Lost sales equation mismatch on {row['date']} for {row['product_id']}")
            
        # Parse stockout_flag as boolean
        stockout_flag = row['stockout_flag'] == 'True'
        if stockout_flag and row['lost_sales_units'] == 0:
            errors.append(f"Stockout flag True but no lost sales on {row['date']} for {row['product_id']}")
            
        if not stockout_flag and row['lost_sales_units'] > 0:
            errors.append(f"Stockout flag False but lost sales > 0 on {row['date']} for {row['product_id']}")
            
        # Check against sales aggregation
        key = (row['date'], row['product_id'])
        agg_qty = sales_agg.get(key, 0)
        if agg_qty != row['observed_units_sold']:
            errors.append(f"Sales aggregate {agg_qty} != observed_units_sold {row['observed_units_sold']} on {row['date']} for {row['product_id']}")
            
    return errors
