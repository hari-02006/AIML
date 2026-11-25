
SELECT 
    s.supplier_name,
    COUNT(po.purchase_order_id) as num_purchase_orders,
    SUM(po.quantity_ordered) as total_units_ordered,
    s.nominal_lead_time_days,
    AVG(po.actual_delivery_date - po.order_date) as avg_actual_lead_time,
    AVG(po.actual_delivery_date - po.expected_delivery_date) as avg_delay_days,
    MAX(po.actual_delivery_date - po.expected_delivery_date) as max_delay_days,
    COUNT(CASE WHEN po.actual_delivery_date <= po.expected_delivery_date THEN 1 END)::numeric / COUNT(po.purchase_order_id) as on_time_delivery_rate
FROM suppliers s
LEFT JOIN purchase_orders po ON s.supplier_id = po.supplier_id
GROUP BY s.supplier_name, s.nominal_lead_time_days
ORDER BY num_purchase_orders DESC;
