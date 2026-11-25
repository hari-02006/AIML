
SELECT 
    EXTRACT(DOW FROM date) as dow,
    TO_CHAR(date, 'Day') as day_of_week,
    CASE WHEN EXTRACT(DOW FROM date) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END as day_type,
    SUM(quantity) as total_units_sold,
    SUM(revenue) as total_revenue,
    COUNT(sale_id) as transaction_count,
    AVG(quantity) as avg_units_sold,
    AVG(revenue) as avg_revenue
FROM sales
GROUP BY dow, day_of_week, day_type
ORDER BY dow;
