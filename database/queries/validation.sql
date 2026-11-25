-- Smart Inventory & Demand Prediction System
-- Validation Queries

-- 1. Row counts
SELECT 'categories' AS table_name, COUNT(*) AS count FROM categories
UNION ALL
SELECT 'suppliers', COUNT(*) FROM suppliers
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'customers', COUNT(*) FROM customers
UNION ALL
SELECT 'promotions', COUNT(*) FROM promotions
UNION ALL
SELECT 'sales', COUNT(*) FROM sales
UNION ALL
SELECT 'inventory', COUNT(*) FROM inventory
UNION ALL
SELECT 'purchase_orders', COUNT(*) FROM purchase_orders;

-- 2. Inventory equation validation
-- opening_stock + units_received - observed_units_sold = closing_stock
SELECT COUNT(*) AS inventory_equation_failures
FROM inventory
WHERE opening_stock + units_received - observed_units_sold <> closing_stock;

-- 3. True demand validation
SELECT COUNT(*) AS true_demand_failures
FROM inventory
WHERE observed_units_sold > true_demand
   OR lost_sales_units <> true_demand - observed_units_sold
   OR lost_sales_units < 0;

-- 4. Sales-to-inventory reconciliation
SELECT 
    i.date, 
    i.product_id, 
    i.observed_units_sold, 
    COALESCE(SUM(s.quantity), 0) AS sales_quantity
FROM inventory i
LEFT JOIN sales s ON i.date = s.date AND i.product_id = s.product_id
GROUP BY i.date, i.product_id, i.observed_units_sold
HAVING i.observed_units_sold <> COALESCE(SUM(s.quantity), 0);

-- 5. Revenue validation
-- Tolerate small floating point differences by checking absolute difference < 0.05
SELECT COUNT(*) AS revenue_failures
FROM sales
WHERE ABS(quantity * unit_price * (1 - discount) - revenue) > 0.05;

-- 6. Stockout validation
SELECT COUNT(*) AS stockout_logic_failures
FROM inventory
WHERE (stockout_flag = TRUE AND lost_sales_units = 0)
   OR (stockout_flag = FALSE AND lost_sales_units > 0);

-- 7. Orphan foreign keys (Example on Sales)
SELECT COUNT(*) AS orphan_sales_product
FROM sales s
LEFT JOIN products p ON s.product_id = p.product_id
WHERE p.product_id IS NULL;

SELECT COUNT(*) AS orphan_sales_customer
FROM sales s
LEFT JOIN customers c ON s.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
