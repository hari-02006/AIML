
WITH product_sales AS (
    SELECT product_id, SUM(quantity) as units_sold, SUM(revenue) as revenue, COUNT(sale_id) as transaction_count
    FROM sales
    GROUP BY product_id
),
product_inventory AS (
    SELECT product_id, SUM(lost_sales_units) as lost_sales_units, SUM(CASE WHEN stockout_flag THEN 1 ELSE 0 END) as stockout_days
    FROM inventory
    GROUP BY product_id
)
SELECT 
    p.product_id,
    p.product_name,
    COALESCE(s.units_sold, 0) as units_sold,
    COALESCE(s.revenue, 0) as revenue,
    CASE WHEN s.units_sold > 0 THEN s.revenue / s.units_sold ELSE 0 END as avg_selling_price,
    COALESCE(s.transaction_count, 0) as transaction_count,
    COALESCE(i.lost_sales_units, 0) as lost_sales_units,
    COALESCE(i.stockout_days, 0) as stockout_days
FROM products p
LEFT JOIN product_sales s ON p.product_id = s.product_id
LEFT JOIN product_inventory i ON p.product_id = i.product_id
ORDER BY revenue DESC;
