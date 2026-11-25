
SELECT 
    CASE 
        WHEN discount = 0 THEN '0%'
        WHEN discount > 0 AND discount <= 0.05 THEN '0-5%'
        WHEN discount > 0.05 AND discount <= 0.10 THEN '5-10%'
        WHEN discount > 0.10 AND discount <= 0.20 THEN '10-20%'
        ELSE '>20%'
    END as discount_band,
    SUM(quantity) as units_sold,
    SUM(revenue) as total_revenue
FROM sales
GROUP BY discount_band
ORDER BY MIN(discount);
