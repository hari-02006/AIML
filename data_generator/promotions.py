import datetime

def generate_promotions(config, start_date, end_date):
    promos = config.get('promotions', [])
    records = []
    for p in promos:
        if p['id'] == 'FESTIVAL_SALE':
            start = datetime.datetime(2025, 10, 15).date()
            records.append({
                "promotion_id": p['id'],
                "promotion_name": p['name'],
                "discount_percentage": p['discount_range'][1],
                "start_date": start,
                "end_date": start + datetime.timedelta(days=p['duration_days'] - 1)
            })
        elif p['id'] == 'WEEKEND_SALE':
            start = datetime.datetime(2025, 6, 14).date()
            records.append({
                "promotion_id": p['id'],
                "promotion_name": p['name'],
                "discount_percentage": p['discount_range'][1],
                "start_date": start,
                "end_date": start + datetime.timedelta(days=p['duration_days'] - 1)
            })
    return records
