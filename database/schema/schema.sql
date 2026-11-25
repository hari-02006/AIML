-- Smart Inventory & Demand Prediction System
-- PostgreSQL Initial Schema

CREATE TABLE categories (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE suppliers (
    supplier_id VARCHAR(50) PRIMARY KEY,
    supplier_name VARCHAR(255) NOT NULL,
    nominal_lead_time_days INTEGER CHECK (nominal_lead_time_days > 0),
    reliability_class VARCHAR(50)
);

CREATE TABLE products (
    product_id VARCHAR(50) PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    category_id INTEGER REFERENCES categories(category_id),
    base_price NUMERIC(10,2) CHECK (base_price > 0),
    cost_price NUMERIC(10,2) CHECK (cost_price > 0),
    popularity_class VARCHAR(50),
    demand_pattern_class VARCHAR(50),
    supplier_id VARCHAR(50) REFERENCES suppliers(supplier_id)
);

CREATE TABLE customers (
    customer_id VARCHAR(50) PRIMARY KEY,
    age_group VARCHAR(50),
    location VARCHAR(100),
    customer_segment VARCHAR(100)
);

CREATE TABLE promotions (
    promotion_id VARCHAR(50) PRIMARY KEY,
    promotion_name VARCHAR(255),
    discount_percentage NUMERIC(4,2) CHECK (discount_percentage >= 0 AND discount_percentage <= 1),
    start_date DATE,
    end_date DATE,
    CHECK (end_date >= start_date)
);

CREATE TABLE purchase_orders (
    purchase_order_id VARCHAR(50) PRIMARY KEY,
    product_id VARCHAR(50) REFERENCES products(product_id),
    supplier_id VARCHAR(50) REFERENCES suppliers(supplier_id),
    order_date DATE NOT NULL,
    quantity_ordered INTEGER CHECK (quantity_ordered > 0),
    expected_delivery_date DATE,
    actual_delivery_date DATE,
    status VARCHAR(50),
    CHECK (expected_delivery_date >= order_date),
    CHECK (actual_delivery_date IS NULL OR actual_delivery_date >= order_date)
);

CREATE TABLE inventory (
    inventory_id VARCHAR(100) PRIMARY KEY,
    date DATE NOT NULL,
    product_id VARCHAR(50) REFERENCES products(product_id),
    opening_stock INTEGER CHECK (opening_stock >= 0),
    units_received INTEGER CHECK (units_received >= 0),
    true_demand INTEGER CHECK (true_demand >= 0),
    observed_units_sold INTEGER CHECK (observed_units_sold >= 0),
    lost_sales_units INTEGER CHECK (lost_sales_units >= 0),
    closing_stock INTEGER CHECK (closing_stock >= 0),
    stockout_flag BOOLEAN,
    UNIQUE (date, product_id)
);

CREATE TABLE sales (
    sale_id VARCHAR(50) PRIMARY KEY,
    date DATE NOT NULL,
    product_id VARCHAR(50) REFERENCES products(product_id),
    customer_id VARCHAR(50) REFERENCES customers(customer_id),
    quantity INTEGER CHECK (quantity > 0),
    unit_price NUMERIC(10,2) CHECK (unit_price > 0),
    discount NUMERIC(4,2) CHECK (discount >= 0 AND discount <= 1),
    promotion_id VARCHAR(50) REFERENCES promotions(promotion_id),
    revenue NUMERIC(12,2) CHECK (revenue >= 0)
);

-- Indexes
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_supplier ON products(supplier_id);
CREATE INDEX idx_purchase_orders_date ON purchase_orders(order_date);
CREATE INDEX idx_purchase_orders_product ON purchase_orders(product_id);
CREATE INDEX idx_purchase_orders_supplier ON purchase_orders(supplier_id);
CREATE INDEX idx_inventory_date ON inventory(date);
CREATE INDEX idx_inventory_product ON inventory(product_id);
CREATE INDEX idx_sales_date ON sales(date);
CREATE INDEX idx_sales_product ON sales(product_id);
CREATE INDEX idx_sales_customer ON sales(customer_id);
CREATE INDEX idx_promotions_dates ON promotions(start_date, end_date);
