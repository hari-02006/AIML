
def generate_customers(num_customers, rng):
    segments = ["Budget", "Standard", "Premium", "Gaming/Tech Enthusiast"]
    segments_weights = [0.3, 0.4, 0.15, 0.15]
    locations = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Pune"]
    ages = ["18-24", "25-34", "35-44", "45+"]
    
    customers = []
    for i in range(1, num_customers + 1):
        customers.append({
            "customer_id": f"CUST_{i:04d}",
            "age_group": rng.choice(ages),
            "location": rng.choice(locations),
            "customer_segment": rng.choices(segments, weights=segments_weights, k=1)[0]
        })
    return customers
