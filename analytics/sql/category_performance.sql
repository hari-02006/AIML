
SELECT 
    c.category_name,
    COALESCE(SUM(s.revenue), 0) as revenue,
    COALESCE(SUM(s.quantity), 0) as units_sold,
    COUNT(s.sale_id) as transaction_count,
    CASE WHEN SUM(s.quantity) > 0 THEN SUM(s.revenue) / SUM(s.quantity) ELSE 0 END as avg_selling_price
FROM categories c
LEFT JOIN products p ON c.category_id = p.category_id
LEFT JOIN sales s ON p.product_id = s.product_id
GROUP BY c.category_name
ORDER BY revenue DESC;
