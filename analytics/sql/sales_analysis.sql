
SELECT 
    date,
    SUM(quantity) as units_sold,
    SUM(revenue) as revenue,
    COUNT(sale_id) as number_of_transactions
FROM sales
GROUP BY date
ORDER BY date;
