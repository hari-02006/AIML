import datetime
import math
from .utils import get_random_state, daterange

def run_simulation(config, products, suppliers, promotions, customers, start_date, end_date, seed):
    rng = get_random_state(seed)
    
    inventory_records = []
    sales_records = []
    purchase_orders = []
    
    current_inventory = {}
    for p in products:
        min_inv, max_inv = p['initial_inventory_range']
        current_inventory[p['id']] = rng.randint(min_inv, max_inv)
        
    po_counter = 1
    sale_counter = 1
    active_pos = []
    supplier_dict = {s['id']: s for s in suppliers}
    
    # helper for normal dist
    def normal_variate(mu, sigma):
        # using Box-Muller or rng.gauss
        return rng.gauss(mu, sigma)
    
    for current_date in daterange(start_date, end_date):
        dow = current_date.weekday() # 0=Mon, 6=Sun
        is_weekend = dow >= 5
        
        active_promo = None
        for promo in promotions:
            if promo['start_date'] <= current_date <= promo['end_date']:
                active_promo = promo
                break
                
        received_today = {p['id']: 0 for p in products}
        remaining_pos = []
        for po in active_pos:
            if po['actual_delivery_date'] == current_date.strftime('%Y-%m-%d'):
                received_today[po['product_id']] += po['quantity_ordered']
                po['status'] = 'Delivered'
            else:
                remaining_pos.append(po)
        active_pos = remaining_pos
                
        for product in products:
            pid = product['id']
            opening_stock = current_inventory[pid]
            units_received = received_today[pid]
            available_stock = opening_stock + units_received
            
            pop = product['popularity_class']
            if pop == 'HIGH': base_d = 30
            elif pop == 'MEDIUM': base_d = 15
            else: base_d = 5
            
            m_dow = 1.0
            if product['demand_pattern_class'] == 'Weekend-sensitive' and is_weekend:
                m_dow = rng.uniform(1.3, 1.5)
                
            m_season = 1.0
            discount = 0.0
            promo_id = ""
            if active_promo is not None:
                promo_conf = next((p for p in config['promotions'] if p['id'] == active_promo['promotion_id']), None)
                if promo_conf and product['category'] in promo_conf['affected_categories']:
                    m_season = promo_conf['intensity']
                    discount = active_promo['discount_percentage']
                    promo_id = active_promo['promotion_id']
                    
            m_promo = 1.0
            if discount > 0:
                m_promo = 1.0 + discount
                
            variance_factor = 0.4 if product['demand_pattern_class'] == 'Highly-variable' else 0.1
            mu = base_d * m_dow * m_season * m_promo
            sigma = mu * variance_factor
            noise = normal_variate(0, sigma)
            
            true_demand = max(0, int(round(mu + noise)))
            
            observed_sales = min(true_demand, available_stock)
            lost_sales = true_demand - observed_sales
            stockout_flag = true_demand > available_stock
            
            closing_stock = available_stock - observed_sales
            current_inventory[pid] = closing_stock
            
            inventory_records.append({
                "inventory_id": f"INV_{current_date.strftime('%Y%m%d')}_{pid}",
                "date": current_date.strftime('%Y-%m-%d'),
                "product_id": pid,
                "opening_stock": opening_stock,
                "units_received": units_received,
                "true_demand": true_demand,
                "observed_units_sold": observed_sales,
                "lost_sales_units": lost_sales,
                "closing_stock": closing_stock,
                "stockout_flag": str(stockout_flag)
            })
            
            if observed_sales > 0:
                num_tx = rng.randint(1, min(4, observed_sales)) if observed_sales > 1 else 1
                splits = [observed_sales // num_tx] * num_tx
                remainder = observed_sales % num_tx
                for i in range(remainder):
                    splits[i] += 1
                    
                for qty in splits:
                    if qty > 0:
                        cust = rng.choice(customers)
                        unit_price = product['base_price']
                        revenue = qty * unit_price * (1 - discount)
                        sales_records.append({
                            "sale_id": f"SALE_{sale_counter:06d}",
                            "date": current_date.strftime('%Y-%m-%d'),
                            "product_id": pid,
                            "customer_id": cust['customer_id'],
                            "quantity": qty,
                            "unit_price": unit_price,
                            "discount": discount,
                            "promotion_id": promo_id,
                            "revenue": round(revenue, 2)
                        })
                        sale_counter += 1
            
            rop = base_d * 10
            if closing_stock < rop:
                if not any(po['product_id'] == pid for po in active_pos):
                    sup_id = product['supplier_id']
                    sup = supplier_dict[sup_id]
                    nom_lt = sup['nominal_lead_time_days']
                    rel = sup['reliability_class']
                    
                    if rel == 'HIGH': var = 0
                    elif rel == 'MEDIUM': var = rng.randint(-1, 1)
                    else: var = rng.randint(-3, 3)
                    
                    actual_lt = max(1, nom_lt + var)
                    
                    po = {
                        "purchase_order_id": f"PO_{po_counter:05d}",
                        "product_id": pid,
                        "supplier_id": sup_id,
                        "order_date": current_date.strftime('%Y-%m-%d'),
                        "quantity_ordered": base_d * 30,
                        "expected_delivery_date": (current_date + datetime.timedelta(days=nom_lt)).strftime('%Y-%m-%d'),
                        "actual_delivery_date": (current_date + datetime.timedelta(days=actual_lt)).strftime('%Y-%m-%d'),
                        "status": "In Transit"
                    }
                    purchase_orders.append(po)
                    active_pos.append(po)
                    po_counter += 1

    return inventory_records, sales_records, purchase_orders
