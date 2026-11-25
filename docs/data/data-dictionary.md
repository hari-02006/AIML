# Data Dictionary

## 1. PRODUCT
| Field | Type | Input/Output | Description | Constraints |
|---|---|---|---|---|
| `product_id` | String | Input | Unique identifier | Not null |
| `product_name` | String | Input | Name of the product | Not null |
| `category` | String | Input | Product grouping | Not null |
| `base_price` | Float | Input | Standard price | > 0 |
| `cost_price` | Float | Input | Supplier cost | > 0, < base_price |
| `popularity_class` | String | Input | HIGH, MEDIUM, LOW | Valid enum |
| `demand_pattern_class` | String | Input | Stable, Seasonal, etc. | Valid enum |
| `supplier_id` | String | Input | Primary vendor | Valid FK |

## 2. SALES
| Field | Type | Input/Output | Description | Constraints |
|---|---|---|---|---|
| `sale_id` | String | Output | Unique transaction ID | Not null |
| `date` | Date | Output | Transaction date | Valid Date |
| `product_id` | String | Output | Sold product | Valid FK |
| `customer_id` | String | Output | Purchaser | Valid FK |
| `quantity` | Int | Output | Units sold | > 0 |
| `unit_price` | Float | Output | Price paid per unit | > 0 |
| `discount` | Float | Output | Applied discount % | 0.0 to 1.0 |
| `promotion_id` | String | Output | Campaign identifier | Nullable |
| `revenue` | Float | Output | `quantity * unit_price` | >= 0 |

## 3. DEMAND (Analytical/Generated)
| Field | Type | Input/Output | Description | Constraints |
|---|---|---|---|---|
| `true_demand` | Int | Output | Unconstrained demand | >= 0 |
| `observed_units_sold` | Int | Output | Constrained sales | >= 0, <= true_demand |
| `lost_sales_units` | Int | Output | `true_demand - observed_units_sold` | >= 0 |

## 4. INVENTORY
| Field | Type | Input/Output | Description | Constraints |
|---|---|---|---|---|
| `opening_stock` | Int | Output | Stock at start of day | >= 0 |
| `units_received` | Int | Output | PO deliveries today | >= 0 |
| `closing_stock` | Int | Output | Stock at end of day | >= 0 |
| `stockout_flag` | Boolean | Output | True if true_demand > stock | Boolean |

## 5. CUSTOMER
| Field | Type | Input/Output | Description | Constraints |
|---|---|---|---|---|
| `customer_id` | String | Input | Unique identifier | Not null |
| `age_group` | String | Input | e.g. 18-24, 25-34 | |
| `location` | String | Input | City/Region | |
| `customer_segment` | String | Input | Budget, Premium, etc. | Valid enum |

## 6. SUPPLIER
| Field | Type | Input/Output | Description | Constraints |
|---|---|---|---|---|
| `supplier_id` | String | Input | Unique identifier | Not null |
| `supplier_name` | String | Input | Vendor name | Not null |
| `lead_time_days` | Int | Input | Nominal delivery time | > 0 |
| `reliability_class` | String | Input | HIGH, MEDIUM, LOW | Valid enum |

## 7. PROMOTION
| Field | Type | Input/Output | Description | Constraints |
|---|---|---|---|---|
| `promotion_id` | String | Input | Unique identifier | Not null |
| `promotion_name` | String | Input | Campaign name | Not null |
| `discount_percentage` | Float | Input | Default discount | 0.0 to 1.0 |
| `start_date` | Date | Input | Campaign start | <= end_date |
| `end_date` | Date | Input | Campaign end | >= start_date |

## 8. PURCHASE ORDER
| Field | Type | Input/Output | Description | Constraints |
|---|---|---|---|---|
| `purchase_order_id` | String | Output | Unique identifier | Not null |
| `product_id` | String | Output | Ordered product | Valid FK |
| `supplier_id` | String | Output | Vendor | Valid FK |
| `quantity_ordered` | Int | Output | Units requested | > 0 |
| `order_date` | Date | Output | Date placed | <= expected_delivery |
| `expected_delivery_date` | Date | Output | Planned arrival | >= order_date |
| `actual_delivery_date` | Date | Output | Real arrival | Nullable until arrived |
| `status` | String | Output | Pending, Delivered, etc. | Valid enum |
