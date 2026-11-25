-- Smart Inventory & Demand Prediction System
-- Basic Operational Queries

-- List all products with their categories
SELECT p.product_id, p.product_name, c.category_name, p.base_price
FROM products p
JOIN categories c ON p.category_id = c.category_id;

-- List products with suppliers
SELECT p.product_id, p.product_name, s.supplier_name, s.nominal_lead_time_days
FROM products p
JOIN suppliers s ON p.supplier_id = s.supplier_id;

-- Total sales quantity and revenue by product
SELECT 
    p.product_name,
    SUM(s.quantity) AS total_quantity_sold,
    SUM(s.revenue) AS total_revenue
FROM sales s
JOIN products p ON s.product_id = p.product_id
GROUP BY p.product_name
ORDER BY total_revenue DESC;

-- Low-stock records (e.g., closing stock < 10)
SELECT i.date, p.product_name, i.closing_stock
FROM inventory i
JOIN products p ON i.product_id = p.product_id
WHERE i.closing_stock < 10
ORDER BY i.date DESC
LIMIT 50;

-- Stockout records (days where true demand exceeded available stock)
SELECT i.date, p.product_name, i.true_demand, i.observed_units_sold, i.lost_sales_units
FROM inventory i
JOIN products p ON i.product_id = p.product_id
WHERE i.stockout_flag = TRUE
ORDER BY i.date DESC;

-- Sales by date
SELECT date, SUM(quantity) AS daily_units_sold, SUM(revenue) AS daily_revenue
FROM sales
GROUP BY date
ORDER BY date DESC
LIMIT 10;

-- Purchase orders by supplier
SELECT s.supplier_name, COUNT(po.purchase_order_id) AS total_pos, SUM(po.quantity_ordered) AS total_units_ordered
FROM purchase_orders po
JOIN suppliers s ON po.supplier_id = s.supplier_id
GROUP BY s.supplier_name;
