
SELECT 
    (SELECT COALESCE(SUM(revenue), 0) FROM sales) as total_revenue,
    (SELECT COALESCE(SUM(quantity), 0) FROM sales) as total_units_sold,
    (SELECT COUNT(*) FROM products) as total_products,
    (SELECT COUNT(*) FROM customers) as total_customers,
    (SELECT COUNT(*) FROM sales) as total_transactions,
    (SELECT COALESCE(SUM(closing_stock), 0) FROM inventory WHERE date = (SELECT MAX(date) FROM inventory)) as current_total_inventory,
    (SELECT COALESCE(SUM(lost_sales_units), 0) FROM inventory) as total_lost_sales,
    (SELECT COUNT(*) FROM inventory WHERE stockout_flag = TRUE) as stockout_product_days
;
