def validate_schema(data, required_columns, numeric_columns, not_null_columns):
    errors = []
    if not data:
        return errors
        
    first_row = data[0]
    missing_cols = [c for c in required_columns if c not in first_row]
    if missing_cols:
        errors.append(f"Missing columns: {missing_cols}")
        
    for col in not_null_columns:
        nulls = sum(1 for row in data if row.get(col) is None)
        if nulls > 0:
            errors.append(f"Column {col} has {nulls} null values")
                
    for col in numeric_columns:
        non_numeric = 0
        for row in data:
            if row.get(col) is not None:
                try:
                    float(row[col])
                except ValueError:
                    non_numeric += 1
        if non_numeric > 0:
            errors.append(f"Column {col} has {non_numeric} non-numeric values")
                
    return errors

def check_duplicates(data, primary_keys):
    if not primary_keys:
        return []
    
    seen = set()
    dupes = 0
    for row in data:
        key = tuple(row.get(k) for k in primary_keys)
        if key in seen:
            dupes += 1
        seen.add(key)
        
    if dupes > 0:
        return [f"Found {dupes} duplicate rows based on keys {primary_keys}"]
    return []
