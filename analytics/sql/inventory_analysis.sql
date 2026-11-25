
SELECT 
    p.product_name,
    SUM(i.units_received) as total_received,
    SUM(i.observed_units_sold) as total_observed_sales,
    SUM(i.true_demand) as total_true_demand,
    SUM(i.lost_sales_units) as total_lost_sales,
    SUM(CASE WHEN i.stockout_flag THEN 1 ELSE 0 END) as total_stockout_days
FROM inventory i
JOIN products p ON i.product_id = p.product_id
GROUP BY p.product_name
ORDER BY total_stockout_days DESC;
