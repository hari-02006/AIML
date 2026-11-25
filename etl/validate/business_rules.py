def validate_inventory_rules(data):
    errors = []
    
    invalid_eq = 0
    invalid_demand = 0
    invalid_lost = 0
    invalid_stockout = 0
    
    for row in data:
        try:
            opening = int(float(row['opening_stock']))
            rec = int(float(row['units_received']))
            obs = int(float(row['observed_units_sold']))
            close = int(float(row['closing_stock']))
            true_d = int(float(row['true_demand']))
            lost = int(float(row['lost_sales_units']))
            
            if opening + rec - obs != close:
                invalid_eq += 1
            if obs > true_d:
                invalid_demand += 1
            if lost != true_d - obs:
                invalid_lost += 1
            if row['stockout_flag'] is True and lost == 0:
                invalid_stockout += 1
        except Exception:
            pass
            
    if invalid_eq: errors.append(f"Inventory equation mismatch on {invalid_eq} rows")
    if invalid_demand: errors.append(f"Observed sales > True demand on {invalid_demand} rows")
    if invalid_lost: errors.append(f"Lost sales equation mismatch on {invalid_lost} rows")
    if invalid_stockout: errors.append(f"Stockout flag True but no lost sales on {invalid_stockout} rows")
        
    return errors
