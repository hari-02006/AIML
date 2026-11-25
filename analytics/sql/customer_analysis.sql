
SELECT 
    c.customer_segment,
    COUNT(DISTINCT c.customer_id) as num_customers,
    COUNT(s.sale_id) as num_orders,
    SUM(s.revenue) as total_revenue,
    CASE WHEN COUNT(DISTINCT c.customer_id) > 0 THEN SUM(s.revenue) / COUNT(DISTINCT c.customer_id) ELSE 0 END as revenue_per_customer
FROM customers c
LEFT JOIN sales s ON c.customer_id = s.customer_id
GROUP BY c.customer_segment
ORDER BY total_revenue DESC;
