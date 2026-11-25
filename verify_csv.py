import pandas as pd, sys
csv_path = r'C:\Users\kshir\.gemini\antigravity\scratch\SmartInventoryDemandPrediction\ml\inventory_decision\simulation\output\experiment_records.csv'

df = pd.read_csv(csv_path)
print('Rows (including header):', len(df) + 1)
print('Data rows:', len(df))
print('Unique replications:', df['replication_id'].nunique())
scen_counts = df.groupby('replication_id')['scenario_name'].nunique()
print('Scenarios per replication min/max:', scen_counts.min(), scen_counts.max())
print('Unique demand hash per replication max:', df.groupby('replication_id')['demand_series_hash'].nunique().max())
consistent = (df.groupby('replication_id')['demand_series'].nunique() == 1).all()
print('Demand series identical per replication?', consistent)
