# Current Phase
Stage 10 — ML Feature Engineering (Completed)

# Completed
- Stage 0 — Project Foundation
- Stage 1 — Synthetic Retail Environment Design
- Stage 2 — Synthetic Data Generator
- Stage 3 — PostgreSQL Database
- Stage 4 — ETL / Data Pipeline
- Stage 5 — Analytics
- Stage 6 — Dashboard & Date Filter KPI Alignment
- Stage 7 — Invoice Scanning Interface
- Stage 8 — OCR & Invoice Data Extraction
- Stage 9 — Complete PostgreSQL Integration, Invoice Approval & Inventory Stock Update System:
  - Database Schema & Evolution:
    - Production database: `smart_inventory` (PostgreSQL 18.6).
    - Added `products.stock_unit VARCHAR(50) NULL` for canonical unit tracking.
    - Created `purchase_invoices` with `invoice_date`, `supplier_id` (FK), `document_path`, status tracking (`pending`, `approved`, `rejected`), and conditional unique index on `document_hash` for approved records.
    - Created `purchase_invoice_items` with `raw_line_text`, nullable `product_id` and `quantity` for pending drafts, `canonical_quantity`, `conversion_factor` (strictly `> 0`), and default `verification_status = 'Needs Review'`.
  - Stale Inventory & Reconciliation:
    - Configured `INVENTORY_STALE_DAYS = 30`. Products with historical inventory exceeding this gap trigger mandatory physical stock confirmation.
    - Inventory Analytics displays `Last Recorded Stock — Needs Reconciliation` for unconfirmed stale stock.
  - Concurrency & Same-Day Daily UPSERT:
    - Deterministic alphabetical `SELECT ... FOR UPDATE` row locking prevents deadlocks on concurrent approvals.
    - Safe daily UPSERT aggregates `units_received` and `closing_stock` for multiple same-day receipts while strictly preserving `opening_stock`.
  - Managed Document File Storage:
    - Organized in `data/invoices/{pending,approved,rejected}/` separate from raw CSVs.
    - Safe copy-and-commit workflow with SHA-256 byte verification prior to database transaction.
  - Testing & Production Safety:
    - Full repository test suite passed with zero warnings.
    - Production database verified intact.
- Stage 10 — ML Feature Engineering:
  - Built deterministic product-level daily time-series feature engineering pipeline in `ml/features/`.
  - Continuous 365-day calendar grid across all 20 products (7,300 total rows) over verified sales coverage (2025-01-01 to 2025-12-31).
  - Ground-truth target `demand_units` (sum of valid sold units per product-date) separated from input predictors.
  - 48 engineered columns: Calendar & cyclical (sin/cos), Lags (1, 7, 14, 28), Rolling statistics (means, sums, stds for 7, 14, 28 days), Behavioral (days since last sale, trend ratio), Product & Category metadata, Historical inventory snapshots ($T - 1$ precedence), and Promotion features.
  - Strict zero target leakage enforced: all rolling features computed on `demand_units.shift(1)` (closed='left'). Current day demand is never observed in predictors.
  - Precedence-aware historical inventory features ($T - 1$ closing/opening stock); current-day closing stock strictly excluded.
  - Atomic artifact generation under `data/processed/stage10/`: CSV, Parquet, Feature Data Dictionary, Quality Summary, and Run Metadata.
  - Integrated into Streamlit (`http://localhost:8504`) with interactive metrics, pipeline run triggers, previews, downloads, and data dictionary.
  - 9 dedicated Stage 10 tests added; entire repository test suite: **122/122 passed in 20.56s (0 warnings, 0 failures)**.
  - Production database `smart_inventory` verified read-only with identical row counts; raw CSVs and backup intact.

# In Progress
None

# Not Started
- Stage 11 — Demand Forecasting
- Stage 12 — Inventory Decision Engine
- Stage 13 — Inventory Simulation & Research Experiments
- Stage 14 — Generative AI Assistant
- Stage 15 — Advanced Engineering/Deployment

# Blocked
None

# Next Step
Stage 11 — Demand Forecasting


