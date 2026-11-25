import csv
from database.db_connection import get_connection

def load_table(data, table_name, conflict_columns=None, columns=None):
    if not data:
        return 0
        
    conn = get_connection()
    attempted = len(data)
    inserted_count = 0
    try:
        with conn.cursor() as cur:
            if not columns:
                columns = list(data[0].keys())
                
            if conflict_columns:
                conflict_clause = f"ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"
                query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(['%s']*len(columns))}) {conflict_clause}"
                
                rows_to_insert = [[row.get(c) for c in columns] for row in data]
                cur.executemany(query, rows_to_insert)
                inserted_count = cur.rowcount
            else:
                query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(['%s']*len(columns))})"
                rows_to_insert = [[row.get(c) for c in columns] for row in data]
                cur.executemany(query, rows_to_insert)
                inserted_count = cur.rowcount
                    
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
        
    return {
        "attempted": attempted,
        "inserted": inserted_count,
        "skipped": attempted - inserted_count
    }
