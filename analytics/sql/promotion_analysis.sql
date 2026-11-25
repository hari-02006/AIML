
SELECT 
    CASE WHEN promotion_id IS NOT NULL THEN 'During Promotion' ELSE 'No Promotion' END as promo_status,
    SUM(revenue) as total_revenue,
    SUM(quantity) as total_units_sold,
    AVG(quantity) as avg_units_per_transaction
FROM sales
GROUP BY promo_status;
