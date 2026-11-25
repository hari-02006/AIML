import datetime

def standardize_dates(data, date_columns):
    for row in data:
        for col in date_columns:
            if col in row and row[col]:
                try:
                    datetime.datetime.strptime(row[col], '%Y-%m-%d')
                except ValueError:
                    row[col] = None
            else:
                row[col] = None
    return data

def clean_dataframe(data):
    for row in data:
        for k, v in row.items():
            if isinstance(v, str):
                row[k] = v.strip()
                if row[k] == '':
                    row[k] = None
        
        if 'stockout_flag' in row:
            if row['stockout_flag'] is not None:
                sf = row['stockout_flag'].lower()
                if sf in ('true', '1'):
                    row['stockout_flag'] = True
                elif sf in ('false', '0'):
                    row['stockout_flag'] = False
                else:
                    row['stockout_flag'] = None
    return data
