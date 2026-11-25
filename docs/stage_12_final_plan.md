# Stage 12 – Final Consolidated Implementation‑Planning Report

**Project:** Smart Inventory & Demand Prediction System
**Stage:** 12 – Inventory Decision Engine (planning only)
**Author:** Antigravity (AGY) – generated on 2026‑11‑04

---

## A. VERIFIED DATA FRESHNESS

| Data source | Latest `date` observed | Age (days) as of 2026‑11‑04 | Notes |
|------------|-----------------------|----------------------------|-------|
| **Production `sales` table** (processed snapshot) | 2026‑01‑01 | 307 days | Only a single test row is present in `sales_processed.csv`. The full production table could not be queried; the snapshot is used as the best available source. |
| **Stage 10 feature set** (`daily_product_features.csv`) | 2025‑12‑31 | 339 days | Full feature set ends on 2025‑12‑31 (see `data/processed/stage10/daily_product_features.csv`). |
| **Inventory snapshots** (`inventory_processed.csv`) | 2026‑01‑07 (all 20 products) | 301 days | Tail of the file shows the most recent inventory date for every product. |
| **Stage 11 split periods** (metadata) | – | – | See **Stage 11 Chronological Partitions** below. |

> **Interpretation:** All source data are older than 300 days, well beyond any typical freshness threshold (e.g., 30 days). The decision‑engine must treat the forecasts as *stale* and flag the data‑staleness blocker (see Section F). No further DB reads were performed because the production database could not be accessed from this environment.

---

## B. STAGE 11 CHRONOLOGICAL PARTITIONS (VERIFIED)

From `data/processed/stage11/stage11_metadata.json`:

- **Training period:** 2025‑01‑29 → 2025‑09‑30 (4 900 rows)
- **Validation period:** 2025‑10‑01 → 2025‑11‑15 (920 rows)
- **Final‑test period:** 2025‑11‑16 → 2025‑12‑31 (920 rows)

The pipeline refit model on **Training + Validation** (2025‑01‑29 → 2025‑11‑15) and evaluated once on the final‑test window.

---

## C. FORECAST‑DATE ALIGNMENT (VERIFIED)

`ml/forecasting/forecast_pipeline.py` creates the prediction dataframe where the **`date` column corresponds to the *target* (one‑day‑ahead) date**. Features are taken from the *previous* day (`date‑1`). This alignment is documented in the pipeline’s `execute_final_refitting_protocol` function and is reflected in the `test_predictions.csv` where each row’s `date` is the day being forecasted.

---

## D. LEAD‑TIME POLICY

| Item | Status | Comment |
|------|--------|---------|
| Supplier‑lead‑time mapping | **MISSING** | No explicit mapping file exists in `config/`. The system currently falls back to a *default* of **7 days** (hard‑coded in the downstream decision script, but not persisted). |
| Supplier identifiers | **MISSING** | `supplier_id` appears in the feature set, but a lookup table linking to actual supplier contact information is not present. |

**Assumption:** For the planning document we assume a default lead‑time of 7 days for all suppliers unless a future configuration file (`config/lead_time.yaml`) is added.

---

## E. SAFETY‑STOCK POLICY

| Item | Status | Comment |
|------|--------|---------|
| Per‑product demand‑uncertainty (e.g., forecast‑error variance) | **MISSING** | `model_evaluator.py` reports only point‑estimate metrics (MAE, RMSE, etc.). No per‑product standard‑deviation is stored. |
| Safety‑stock factor | **MISSING** | No configuration (`config/safety_stock.yaml`) exists. The current prototype uses a *fixed 10 % of forecast* as a placeholder, which is undocumented. |

**Assumption:** The planner should require a `safety_stock.yaml` defining either a fixed factor (e.g., `0.10`) or per‑product standard‑deviation values before the engine can be run in production.

---

## F. STATUS‑PRIORITY RULES (VERIFIED)

| Status | Blocker Reason (highest priority) | Additional Reasons |
|--------|-----------------------------------|--------------------|
| **Stale Data** | Data freshness > 30 days (sales, inventory, Stage 10 features) | – |
| **Missing Lead‑Time** | No supplier lead‑time configuration | – |
| **Missing Safety‑Stock** | No safety‑stock configuration | – |
| **Ready** | All above blockers cleared | – |

The system will surface the *first* blocker in the list; however, the UI should also display the full set of applicable reasons.

---

## G. MISSING ARTIFACTS / CONFIGURATION FILES

- `config/lead_time.yaml` – mapping of `supplier_id → lead_time_days`.
- `config/safety_stock.yaml` – either a global factor or per‑product variance.
- `config/unit_mapping.yaml` – unit‑conversion table for diverse suppliers (currently absent).

---

## H. METRIC DISCREPANCY EXPLANATION (UNRESOLVED)

- **Observed test MAE (uncensored):** `1.9261050328227571` (computed from the CSV/Parquet predictions).
- **Previously recorded MAE in `model_comparison_summary.csv` / `stage11_metadata.json`:** `1.9263`.

Both files contain identical prediction values; the discrepancy is **not** caused by CSV rounding. The only plausible origin is a **post‑processing rounding step** that stored the metric rounded to **four decimal places** using Python’s `round(..., 4)`. However, rounding `1.926105...` to four decimals yields `1.9261`, not `1.9263`. The source of the `1.9263` value could therefore be a **different uncensored subset** (e.g., an earlier version of the censor‑filter) or a **manual edit**. Because the code path that writes the metric does not expose the intermediate value, we **cannot conclusively determine** the cause. The discrepancy is documented as *unexplained*.

---

## I. RISKS & MITIGATION

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stale source data | Forecasts may be inaccurate for current inventory decisions. | Refresh the ETL pipelines; schedule daily/weekly data loads before running Stage 12. |
| Missing lead‑time / safety‑stock config | Decision engine cannot compute reorder quantities. | Provide the required YAML files; enforce validation step before deployment. |
| Metric discrepancy ambiguity | Could erode stakeholder confidence. | Update the pipeline to log raw metric values before rounding and store them in audit logs. |

---

## J. NEXT STEPS (IMPLEMENTATION‑FREE)
1. **Create configuration files** (`lead_time.yaml`, `safety_stock.yaml`, `unit_mapping.yaml`) with placeholder values and mark them as required inputs.
2. **Schedule data‑refresh jobs** to update `sales`, `inventory`, and Stage 10 features at least weekly.
3. **Add audit logging** to `model_evaluator.py` to capture raw metric values (pre‑rounding) for future reproducibility.
4. **Update UI status panel** to list *all* applicable blocker reasons (as per Section F).
5. **Review and sign‑off** the finalized planning report.

---

## K. SIGN‑OFF

**Prepared by:** Antigravity (AGY) – autonomous coding assistant
**Reviewed by:** *[User to review and approve]*

*This document is a planning artefact only. No code, database, or infrastructure changes have been made.*
