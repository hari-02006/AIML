# STAGE 10: ML FEATURE ENGINEERING — COMPLETION REPORT
## Smart Inventory & Demand Prediction System

**Date**: November 4, 2026  
**Status**: COMPLETED  
**Scope**: Product-Level Daily Time-Series Feature Engineering with Strict Zero Target Leakage  

---

## 1. Executive Summary

Stage 10 has successfully engineered a structured, daily product-level machine learning feature dataset from the project's historical PostgreSQL database (`smart_inventory`). The resulting dataset provides clean, leakage-free time-series representations suitable for future demand forecasting models in **Stage 11: Demand Forecasting**.

All operations adhered strictly to safety constraints:
- **Zero writes to production PostgreSQL**: All extractions used read-only sessions (`conn.read_only = True`). Table row counts are 100% identical before and after.
- **Strict Zero Target Leakage**: All rolling statistical features (means, sums, standard deviations) and lag features are calculated strictly on preceding days ($T - 1$ and earlier). Current day demand is never observed in predictor columns.
- **Continuous Calendar Grid**: Built a complete 365-day grid for all 20 products ($20 \times 365 = 7,300$ rows) over the verified sales coverage window (2025-01-01 to 2025-12-31). Zero-demand days are explicitly tracked.
- **Precedence-Aware Inventory Alignment**: Historical inventory stock snapshots ($T - 1$) are merged with temporal precedence; same-day closing stock is never used as a demand predictor.
- **All 122 Repository Tests Passed** with 0 failures and 0 warnings.

---

## 2. Source Database & Feasibility Findings

Inspection of the production PostgreSQL database (`smart_inventory`) yielded the following schema and data coverage:

| Table | Relevant Columns | Verified Date Range | Total Rows | Target Viability |
|---|---|---|---:|---|
| **`sales`** | `sale_id`, `date`, `product_id`, `quantity`, `revenue`, `promotion_id` | 2025-01-01 to 2025-12-31 (365 days) | 18,156 | **Verified**: Ground-truth target `demand_units` = `SUM(quantity)` per product per date. 0 nulls, 0 negative values. |
| **`products`** | `product_id`, `product_name`, `category_id`, `supplier_id`, `stock_unit`, `base_price`, `cost_price`, `popularity_class`, `demand_pattern_class` | Static Catalog | 20 | Complete metadata for all 20 catalog products. |
| **`categories`** | `category_id`, `category_name` | Static Catalog | 5 | Audio (1), Displays (2), Peripherals (3), Storage (4), Accessories (5). |
| **`inventory`** | `inventory_id`, `date`, `product_id`, `opening_stock`, `units_received`, `closing_stock`, `stockout_flag` | 2025-01-01 to 2026-01-07 (372 days) | 7,440 | 0 nulls in stocks. Verified exact match: `inventory.observed_units_sold == daily_sales_units` on all 7,267 active days. |
| **`promotions`** | `promotion_id`, `promotion_name`, `discount_percentage`, `start_date`, `end_date` | 2025-06-14 to 2025-10-19 | 2 | `WEEKEND_SALE` (15% off, June 14–15) and `FESTIVAL_SALE` (20% off, Oct 15–19). |

### Key Data Invariants & Target Formulation
- **Target Definition**: `demand_units = sum of valid sold quantities for a product on a particular calendar date`.
- **Unit Consistency**: All catalog products have standard commercial piece/unit semantics (`stock_unit` default 'Units').
- **Missing Sales Coverage & Zero-Demand**: Out of 7,300 product-date combinations in 2025, exactly 7,267 had recorded sales transactions. The remaining 33 product-days had 0 transactions and were matched to `inventory.observed_units_sold = 0`. These 33 days are zero-filled and transparently flagged with `is_zero_demand_inferred = True`.

---

## 3. Features Engineered (48 Columns Total)

The engineered dataset `daily_product_features` contains 48 columns organized into 8 functional families:

### A. Keys & Target (3 columns)
1. `product_id` (string): Unique catalog product identifier.
2. `date` (date): Daily observation timestamp ($T$).
3. `demand_units` (integer): **Target variable**. Total units demanded/sold on date $T$. Kept strictly separate from input predictors.

### B. Calendar Features & Cyclical Encodings (11 columns)
4. `day_of_week` (integer): Day index (0=Monday, 6=Sunday).
5. `day_of_month` (integer): Day within month (1–31).
6. `week_of_year` (integer): ISO calendar week number (1–53).
7. `month` (integer): Month index (1–12).
8. `quarter` (integer): Calendar quarter (1–4).
9. `year` (integer): Calendar year (2025).
10. `is_weekend` (integer): Binary flag (1 for Saturday/Sunday, 0 otherwise).
11. `day_of_week_sin` (float): $\sin(2\pi \cdot \text{day\_of\_week} / 7)$
12. `day_of_week_cos` (float): $\cos(2\pi \cdot \text{day\_of\_week} / 7)$
13. `month_sin` (float): $\sin(2\pi \cdot (\text{month} - 1) / 12)$
14. `month_cos` (float): $\cos(2\pi \cdot (\text{month} - 1) / 12)$

### C. Demand Lag Features (4 columns)
15. `demand_lag_1` (float): Units sold on previous day ($T - 1$). Strictly NaN for first product observation.
16. `demand_lag_7` (float): Units sold 7 calendar days prior ($T - 7$, same day of prior week).
17. `demand_lag_14` (float): Units sold 14 calendar days prior ($T - 14$).
18. `demand_lag_28` (float): Units sold 28 calendar days prior ($T - 28$).

### D. Rolling Statistical Features (9 columns)
*All rolling windows are computed on `demand_units.shift(1)` across preceding days $[T-W, T-1]$, strictly excluding day $T$.*
19. `rolling_mean_7` (float): 7-day trailing mean daily demand.
20. `rolling_mean_14` (float): 14-day trailing mean daily demand.
21. `rolling_mean_28` (float): 28-day trailing mean daily demand.
22. `rolling_sum_7` (float): 7-day trailing total demand.
23. `rolling_sum_14` (float): 14-day trailing total demand.
24. `rolling_sum_28` (float): 28-day trailing total demand.
25. `rolling_std_7` (float): 7-day trailing standard deviation of demand.
26. `rolling_std_14` (float): 14-day trailing standard deviation of demand.
27. `rolling_std_28` (float): 28-day trailing standard deviation of demand.

### E. Historical Behavioral Features (2 columns)
28. `days_since_last_sale` (float): Count of calendar days elapsed since preceding positive demand event.
29. `demand_trend_ratio_7_28` (float): Ratio $\text{rolling\_mean\_7} / (\text{rolling\_mean\_28} + 10^{-4})$ quantifying short-term vs baseline demand trend.

### F. Product & Category Metadata (9 columns)
30. `product_name` (string): Standard product title.
31. `category_id` (integer): Category foreign key.
32. `category_name` (string): Commercial category name.
33. `supplier_id` (string): Primary supplier identifier.
34. `stock_unit` (string): Standard inventory tracking unit ('Units').
35. `base_price` (float): Standard unit selling price.
36. `cost_price` (float): Wholesale procurement cost.
37. `popularity_class` (string): Product sales class ('HIGH', 'MEDIUM', 'LOW').
38. `demand_pattern_class` (string): Demand dynamics ('Stable', 'Seasonal', 'Weekend-sensitive', 'Promotion-sensitive', 'Highly-variable').

### G. Historical Inventory Features (4 columns)
*Precedence-enforced: features for date $T$ strictly reflect snapshot from date $T - 1$.*
39. `prev_day_opening_stock` (float): Opening stock recorded at $T - 1$.
40. `prev_day_closing_stock` (float): Closing stock recorded at $T - 1$.
41. `prev_day_units_received` (float): Replenishment units delivered at $T - 1$.
42. `prev_day_stockout_flag` (boolean): Whether stockout occurred on $T - 1$.

### H. Promotion Features (3 columns)
43. `promotion_active` (integer): 1 if date $T$ falls within active promotion window, 0 otherwise.
44. `promotion_id` (string): Active promotion identifier or None.
45. `promotion_discount_pct` (float): Active promotional discount rate (0.15 or 0.20).

### I. Quality & Readiness Flags (3 columns)
46. `is_zero_demand_inferred` (boolean): True for the 33 covered days where zero transactions were recorded.
47. `has_prev_day_inventory` (boolean): True if verified $T - 1$ inventory record exists.
48. `has_sufficient_history_28d` (boolean): True if at least 28 prior days exist (rows ready for full model training).

---

## 4. Leakage Prevention Defenses

| Vulnerability | Mitigation Implemented | Automated Verification Check |
|---|---|---|
| **Current Target in Rolling Stats** | `demand_units.shift(1)` executed before calling `.rolling(window=W, min_periods=W)` | Evaluated with a synthetic 1,000-unit spike on day 7: rolling mean on day 7 remained exactly 10.0 (past days only). |
| **Cross-Product Bleed** | Features grouped by `product_id`. Shift operations do not bleed across boundaries. | Evaluated that for every product's first chronological record, `demand_lag_1` is strictly `NaN`. |
| **Same-Day Closing Stock Leakage** | Inventory snapshots lagged by $+1$ day (`date + timedelta(days=1)`) before merging on `sales.date`. | Evaluated that first observation date lacks previous-day inventory (`has_prev_day_inventory=False`). |
| **Future Dates in Lags** | Only positive lags ($k \in [1, 7, 14, 28]$) computed. | Verified against expected analytical shifts. |

---

## 5. Output Artifacts Generated

All artifacts were saved atomically under `data/processed/stage10/`:

1. **`daily_product_features.csv`** (2,014,259 bytes)  
   Complete 7,300-row $\times$ 48-column CSV dataset.
2. **`daily_product_features.parquet`** (239,794 bytes)  
   High-efficiency binary Parquet dataset compressed via `pyarrow`.
3. **`feature_data_dictionary.csv`** (8,383 bytes)  
   Exhaustive dictionary defining each column, data type, formula, source, and leakage safety rationale.
4. **`feature_quality_summary.csv`** (2,291 bytes)  
   Column-by-column missingness, null counts, null percentages, min/max values, and unique counts.
5. **`stage10_metadata.json`** (1,511 bytes)  
   Machine-readable run metadata, execution timestamp, source database information, date boundaries, and artifact registry.

---

## 6. Streamlit Website Integration

Integrated a dedicated **ML Feature Engineering** navigation section into `frontend/app.py` (`http://localhost:8504`):
- **Navigation**: Added `"ML Feature Engineering"` option to the sidebar radio list.
- **KPI Metrics**: Displays total records (7,300), feature columns (48), products (20), date range, and 28-day ready rows (6,740).
- **Interactive Execution**: Added a `Run / Regenerate Feature Pipeline` button that triggers extraction, generation, and validation on demand without unneeded refreshes.
- **Dataset Previews & Downloads**: One-click download buttons for both CSV and Parquet files.
- **Documentation Tabs**: Interactive Data Dictionary and Quality Summary tables.
- **Preservation of Existing Pages**: All Stage 1–9 pages (Dashboard, Sales, Products, Inventory, Promotions, Suppliers, Customers, Invoice Scanner) continue functioning without error.

---

## 7. Automated Test Suite Results

```text
============================ 122 passed in 20.56s =============================
```
- **Tests Analytics**: 6 passed
- **Tests Dashboard**: 64 passed
- **Tests Data Integrity**: 3 passed
- **Tests ETL**: 2 passed
- **Tests Stage 9 (Invoice Integration & Safety)**: 27 passed
- **Tests Stage 9 Smoke E2E**: 11 passed
- **Tests Stage 10 (Feature Engineering & Leakage)**: 9 passed
  1. `test_aggregation_multi_transaction_and_zero_demand`: PASSED
  2. `test_calendar_features_and_cyclical_encoding`: PASSED
  3. `test_lags_and_no_cross_product_leakage`: PASSED
  4. `test_rolling_features_strict_zero_leakage`: PASSED
  5. `test_inventory_features_lag_precedence`: PASSED
  6. `test_promotion_features_date_matching`: PASSED
  7. `test_validator_detects_deliberate_leakage`: PASSED
  8. `test_full_stage10_pipeline_run_and_artifacts`: PASSED
  9. `test_production_database_safety_guard`: PASSED

---

## 8. Production Safety Verification

| Database / Artifact | Initial State | Post-Stage 10 State | Verification Result |
|---|---:|---:|---|
| `categories` | 5 | 5 | ✅ Unchanged |
| `products` | 20 | 20 | ✅ Unchanged |
| `inventory` | 7,440 | 7,440 | ✅ Unchanged |
| `sales` | 18,156 | 18,156 | ✅ Unchanged |
| `suppliers` | 4 | 4 | ✅ Unchanged |
| `customers` | 500 | 500 | ✅ Unchanged |
| `promotions` | 2 | 2 | ✅ Unchanged |
| `purchase_orders` | 260 | 260 | ✅ Unchanged |
| `purchase_invoices` | 0 | 0 | ✅ Unchanged |
| `purchase_invoice_items` | 0 | 0 | ✅ Unchanged |
| `data/raw/*.csv` | 8 files (2026-09-26 14:38:30) | 8 files (2026-09-26 14:38:30) | ✅ Unchanged |
| `database/backups/smart_inventory_pre_stage9.dump` | 276,891 bytes | 276,891 bytes | ✅ Unchanged |

---

## 9. Remaining Known Limitations

1. **Sales History Horizon**: Ground-truth sales coverage spans 365 calendar days (calendar year 2025). Models in Stage 11 will have 1 full annual seasonality cycle.
2. **First 28 Calendar Days**: Due to 28-day lag and rolling requirements, the first 28 days of 2025 ($28 \times 20 = 560$ rows) contain `NaN` in 28-day rolling columns. The flag `has_sufficient_history_28d = True` identifies the 6,740 fully populated training instances.
3. **Promotions Breadth**: Only 2 promotional campaigns exist in the database (totaling 140 promoted product-days).
4. **Historical Inventory Scope**: Daily inventory records end on January 7, 2026. This data is strictly used as historical observations and is never projected forward.

---

## 10. Roadmap & Status Alignment

- **Stage 9 (PostgreSQL Integration & Invoice Approval)**: COMPLETED
- **Stage 10 (ML Feature Engineering)**: **COMPLETED**
- **Stage 11 (Demand Forecasting)**: **NOT STARTED** (Next Stage)
