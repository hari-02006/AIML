# PostgreSQL Database Design
## Smart Inventory & Demand Prediction System

This document outlines the final relational schema for the Stage 3 database `smart_inventory`, reflecting the structure of the synthetic raw data generated in Stage 2.

## Entity Relationship Diagram
```mermaid
erDiagram
    CATEGORIES ||--o{ PRODUCTS : contains
    SUPPLIERS ||--o{ PRODUCTS : supplies
    SUPPLIERS ||--o{ PURCHASE_ORDERS : fulfills
    PRODUCTS ||--o{ PURCHASE_ORDERS : requested_in
    PRODUCTS ||--o{ INVENTORY : tracked_in
    PRODUCTS ||--o{ SALES : sold_in
    CUSTOMERS ||--o{ SALES : makes
    PROMOTIONS ||--o{ SALES : applies_to

    CATEGORIES {
        int category_id PK
        varchar category_name UK
    }
    SUPPLIERS {
        varchar supplier_id PK
        varchar supplier_name
        int nominal_lead_time_days
        varchar reliability_class
    }
    PRODUCTS {
        varchar product_id PK
        varchar product_name
        int category_id FK
        varchar supplier_id FK
        numeric base_price
        numeric cost_price
        varchar popularity_class
        varchar demand_pattern_class
    }
    CUSTOMERS {
        varchar customer_id PK
        varchar age_group
        varchar location
        varchar customer_segment
    }
    PROMOTIONS {
        varchar promotion_id PK
        varchar promotion_name
        numeric discount_percentage
        date start_date
        date end_date
    }
    PURCHASE_ORDERS {
        varchar purchase_order_id PK
        varchar product_id FK
        varchar supplier_id FK
        date order_date
        int quantity_ordered
        date expected_delivery_date
        date actual_delivery_date
        varchar status
    }
    INVENTORY {
        varchar inventory_id PK
        date date
        varchar product_id FK
        int opening_stock
        int units_received
        int true_demand
        int observed_units_sold
        int lost_sales_units
        int closing_stock
        boolean stockout_flag
    }
    SALES {
        varchar sale_id PK
        date date
        varchar product_id FK
        varchar customer_id FK
        varchar promotion_id FK
        int quantity
        numeric unit_price
        numeric discount
        numeric revenue
    }
```

## Schema Details
The full schema can be found in `database/schema/schema.sql`.

Key considerations implemented:
- **Foreign Keys**: Strong relational enforcement ensures no orphan transactions.
- **Constraints**: 
  - Stock levels (opening, closing, true demand, sales) must be `>= 0`.
  - Financials (revenue, prices) must be `>= 0`.
  - Discounts are constrained between `0` and `1`.
  - Delivery dates and end dates strictly follow start dates.
- **Primary Keys**: We utilized the natural `id` attributes created by the Stage 2 generator (e.g. `sale_id`, `inventory_id`). A composite unique constraint was added to `inventory (date, product_id)`.
- **Data Types**: All prices are represented precisely as `NUMERIC(10,2)` or `NUMERIC(12,2)` rather than approximate floats.

## Mappings
The explicit translation of CSV columns to PostgreSQL columns, including surrogate additions like `category_id`, is defined in [csv-to-postgres-mapping.md](csv-to-postgres-mapping.md).

## Loading Order
To satisfy constraints, data is loaded in the following dependency order:
1. `categories`
2. `suppliers`
3. `products`
4. `customers`
5. `promotions`
6. `purchase_orders`
7. `inventory`
8. `sales`
