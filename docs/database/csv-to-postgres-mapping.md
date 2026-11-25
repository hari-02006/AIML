# CSV to PostgreSQL Schema Mapping

This document describes the exact mapping from the Stage 2 generated raw synthetic CSV data to the PostgreSQL relational tables. No silent transformations are made unless explicitly noted.

## `categories.csv`
- `category_name` (string) -> `categories.category_name` (VARCHAR, UNIQUE, NOT NULL)
*Note: A surrogate `category_id` (SERIAL PRIMARY KEY) is added to the table.*

## `suppliers.csv`
- `id` -> `suppliers.supplier_id` (VARCHAR PRIMARY KEY)
- `name` -> `suppliers.supplier_name` (VARCHAR NOT NULL)
- `nominal_lead_time_days` -> `suppliers.nominal_lead_time_days` (INTEGER)
- `reliability_class` -> `suppliers.reliability_class` (VARCHAR)

## `products.csv`
- `id` -> `products.product_id` (VARCHAR PRIMARY KEY)
- `name` -> `products.product_name` (VARCHAR NOT NULL)
- `category` -> (Mapped to `products.category_id` by joining with `categories` table during load)
- `base_price` -> `products.base_price` (NUMERIC(10,2))
- `cost_price` -> `products.cost_price` (NUMERIC(10,2))
- `popularity_class` -> `products.popularity_class` (VARCHAR)
- `demand_pattern_class` -> `products.demand_pattern_class` (VARCHAR)
- `supplier_id` -> `products.supplier_id` (VARCHAR FOREIGN KEY)

## `customers.csv`
- `customer_id` -> `customers.customer_id` (VARCHAR PRIMARY KEY)
- `age_group` -> `customers.age_group` (VARCHAR)
- `location` -> `customers.location` (VARCHAR)
- `customer_segment` -> `customers.customer_segment` (VARCHAR)

## `promotions.csv`
- `promotion_id` -> `promotions.promotion_id` (VARCHAR PRIMARY KEY)
- `promotion_name` -> `promotions.promotion_name` (VARCHAR)
- `discount_percentage` -> `promotions.discount_percentage` (NUMERIC(4,2))
- `start_date` -> `promotions.start_date` (DATE)
- `end_date` -> `promotions.end_date` (DATE)

## `purchase_orders.csv`
- `purchase_order_id` -> `purchase_orders.purchase_order_id` (VARCHAR PRIMARY KEY)
- `product_id` -> `purchase_orders.product_id` (VARCHAR FOREIGN KEY)
- `supplier_id` -> `purchase_orders.supplier_id` (VARCHAR FOREIGN KEY)
- `order_date` -> `purchase_orders.order_date` (DATE)
- `quantity_ordered` -> `purchase_orders.quantity_ordered` (INTEGER)
- `expected_delivery_date` -> `purchase_orders.expected_delivery_date` (DATE)
- `actual_delivery_date` -> `purchase_orders.actual_delivery_date` (DATE)
- `status` -> `purchase_orders.status` (VARCHAR)

## `inventory.csv`
- `inventory_id` -> `inventory.inventory_id` (VARCHAR PRIMARY KEY)
- `date` -> `inventory.date` (DATE)
- `product_id` -> `inventory.product_id` (VARCHAR FOREIGN KEY)
- `opening_stock` -> `inventory.opening_stock` (INTEGER)
- `units_received` -> `inventory.units_received` (INTEGER)
- `true_demand` -> `inventory.true_demand` (INTEGER)
- `observed_units_sold` -> `inventory.observed_units_sold` (INTEGER)
- `lost_sales_units` -> `inventory.lost_sales_units` (INTEGER)
- `closing_stock` -> `inventory.closing_stock` (INTEGER)
- `stockout_flag` -> `inventory.stockout_flag` (BOOLEAN) - *Note: Stored as 'True'/'False' string in CSV, converted to TRUE/FALSE boolean in Postgres.*

## `sales.csv`
- `sale_id` -> `sales.sale_id` (VARCHAR PRIMARY KEY)
- `date` -> `sales.date` (DATE)
- `product_id` -> `sales.product_id` (VARCHAR FOREIGN KEY)
- `customer_id` -> `sales.customer_id` (VARCHAR FOREIGN KEY)
- `quantity` -> `sales.quantity` (INTEGER)
- `unit_price` -> `sales.unit_price` (NUMERIC(10,2))
- `discount` -> `sales.discount` (NUMERIC(4,2))
- `promotion_id` -> `sales.promotion_id` (VARCHAR FOREIGN KEY, NULLABLE)
- `revenue` -> `sales.revenue` (NUMERIC(12,2))
