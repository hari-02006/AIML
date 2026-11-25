
SELECT 
    SUM(true_demand) as total_true_demand,
    SUM(observed_units_sold) as total_observed_sales,
    SUM(lost_sales_units) as total_lost_sales,
    CASE WHEN SUM(true_demand) > 0 THEN SUM(lost_sales_units)::numeric / SUM(true_demand) ELSE 0 END as lost_sales_rate
FROM inventory;
