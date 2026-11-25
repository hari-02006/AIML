# Project Roadmap

## PHASE 0: Project foundation and research
- **Status**: COMPLETED
- **Objective**: Create the initial project scaffolding and foundation.
- **Main tasks**: Setup folder structure, documentation, and Git.
- **Inputs**: Requirements.
- **Outputs**: Project structure and docs.
- **Dependencies**: None.
- **Completion criteria**: Structure is validated.

## PHASE 1: Synthetic retail environment design
- **Status**: COMPLETED
- **Objective**: Design the synthetic e-commerce parameters.
- **Main tasks**: Define products, rules, and variations.
- **Inputs**: None.
- **Outputs**: Rule definitions.
- **Dependencies**: Phase 0.
- **Completion criteria**: Rules are fully defined.

## PHASE 2: Synthetic data generator
- **Status**: COMPLETED
- **Objective**: Write script to generate raw retail data.
- **Main tasks**: Implement Python script using Python standard library.
- **Inputs**: Phase 1 rules.
- **Outputs**: Raw CSV data and tests.
- **Dependencies**: Phase 1.
- **Completion criteria**: Script runs, produces expected data, and passes validation.

## PHASE 3: PostgreSQL database
- **Status**: COMPLETED
- **Objective**: Design and initialize the operational database.
- **Main tasks**: Schema creation, raw CSV loading, validation queries.
- **Inputs**: Phase 2 data and schema definitions.
- **Outputs**: Live PostgreSQL `smart_inventory` database, DB documentation.
- **Dependencies**: Phase 2, Local PostgreSQL installation.
- **Completion criteria**: DB is populated, foreign keys hold, and rows match.

## PHASE 4: ETL and data-quality pipeline
- **Status**: COMPLETED
- **Objective**: Move generated data to PostgreSQL cleanly and reproducibly.
- **Main tasks**: Extract, Transform (standardization, mapping), Validate (schema, duplicates, logic), Load (upsert).
- **Inputs**: Raw data (`data/raw/` or `data/incoming/`).
- **Outputs**: Populated database, processed/validated/rejected data folders, and JSON ETL run logs.
- **Dependencies**: Phase 2, 3.
- **Completion criteria**: Idempotent data loading, business-rule validation, incremental loading, and rejection of bad records properly functioning.

## PHASE 5: SQL analytics and exploratory analysis
- **Status**: COMPLETED
- **Objective**: Analyze the operational data to produce business insights without modifying the database.
- **Architecture**: 
  - `analytics/sql/`: Pure SQL logic using PostgreSQL aggregations.
  - `analytics/analysis.py`: Python script utilizing `psycopg` to extract SQL aggregations and output formatted CSVs/JSONs.
  - `analytics/reports/`: Static analytical summaries including `stage5-analytics-report.md`.
- **Metrics Calculated**: Revenue, units sold, true demand vs observed sales, stockout rates, weekday/weekend distribution, category performance, supplier delay tracking.
- **Charts**: Deferred to static markdown format and future dashboard phase due to visualization constraints; produced comprehensive analytical tables instead (Fallback strategy).
- **Tests**: Validated SQL parsing and demand mathematics in `tests/analytics/test_analytics.py`.
- **Limitations**: Time series based exclusively on 1-year simulated data. No real-world macro-trends modeled.
- **Completion criteria**: Insights produced, business questions answered, tests pass, database remains read-only.

## PHASE 6: Dashboard and Visualization
- **Status**: COMPLETED
- **Objective**: Build an interactive, user-friendly visualization layer presenting the SQL analytics.
- **Architecture**: Streamlit frontend leveraging Python and `psycopg` to query PostgreSQL directly.
- **Features**: Overview KPIs, Sales Trend, Category Revenue, Product Performance, True Demand vs Observed Sales, Promotion Metrics, Supplier Analytics, Customer Segmentation.
- **Inputs**: Stage 5 Analytics queries.
- **Outputs**: Local interactive dashboard.
- **Dependencies**: Phase 5.
- **Completion criteria**: Dashboard launches, displays data, filters work, and database remains read-only without implementing future ML.

## IA 50% MILESTONE
**The IA milestone should eventually include:**
1. Project definition
2. Architecture
3. Synthetic data generator
4. PostgreSQL database
5. Data validation
6. ETL pipeline
7. SQL analytics
8. Basic dashboard

*Files merely existing do NOT mean the milestone is complete. A milestone is complete only when the actual component is implemented, tested, and demonstrable.*

## PHASE 7: Invoice scanning interface
- **Status**: COMPLETED
- **Objective**: Provide a mobile-friendly frontend interface for capturing or uploading invoice images.
- **Main tasks**: Add Streamlit Invoice Scanner page, camera capture, file upload (JPG/PNG), format validation, image preview, session-state staging.
- **Inputs**: Device camera or image files from local filesystem.
- **Outputs**: Validated invoice images held in Streamlit session state for downstream processing.
- **Dependencies**: Phase 6.
- **Completion criteria**: Interface captures/uploads images, validates types/formats, provides preview and discard controls without database modification.

## PHASE 8: OCR and invoice data extraction
- **Status**: COMPLETED
- **Objective**: Extract product names and purchased quantities across all pages of single or multi-page documents (PDF, TIFF, PNG, JPG).
- **Main tasks**: Fast automatic Windows Media OCR execution, complete multi-page document loop (`pypdfium2`, Pillow frames), two-tier SHA-256 caching (document and page-level), inventory-only extraction schema (`product_name`, `quantity`, `unit`, `source_page`), live multi-page progress bar, and editable `st.data_editor` UI table. PaddleOCR-VL 1.6 preserved for advanced multimodal extraction on port 8505.
- **Inputs**: Staged invoice images or PDFs from Phase 7.
- **Outputs**: Parsed product inventory table with verification status, source page references, and diagnostics.
- **Dependencies**: Phase 7.
- **Completion criteria**: Sub-second to 2-second extraction on real multi-page invoices (60 items in <2s), 100% extraction accuracy across tested GST and retail invoices, all unit tests passing, zero changes to raw data or PostgreSQL records.

## PHASE 9: Invoice review, item matching, and inventory reconciliation
- **Status**: COMPLETED
- **Objective**: Review parsed invoice data against product catalog, confirm purchase receipts, establish canonical stock units, reconcile stale stock, and update live PostgreSQL inventory transactionally.
- **Main tasks**:
  - Exact & normalized product matching with ambiguity detection against `products`.
  - Stale inventory reconciliation prompting physical count confirmation when gap exceeds `INVENTORY_STALE_DAYS` (30 days).
  - Safe daily UPSERT logic for same-day multiple invoice receipts preserving `opening_stock`.
  - Canonical stock unit validation and confirmed conversion factor calculation (`conversion_factor > 0`).
  - Managed document storage in `data/invoices/{pending,approved,rejected}/` using copy-and-commit workflow with SHA-256 byte verification.
  - Dedicated isolated test suite (25 tests) running strictly against `smart_inventory_test`.
  - Verified `pg_dump` backup created and verified prior to production migration.
  - Production migration applied to `smart_inventory`: `products.stock_unit`, `purchase_invoices`, and `purchase_invoice_items`.
  - Streamlit dashboard Section 5 (Reconciliation & Approval) and Section 6 (Invoice History & Audit) integrated.
- **Inputs**: Extracted invoice data from Phase 8.
- **Outputs**: Approved purchase invoices, verified invoice items, updated daily inventory rows, archived document files, and audit records.
- **Dependencies**: Phase 8.
- **Completion criteria**: All 25 Stage 9 tests passing, 100/100 project tests passing, zero baseline row changes in original 8 tables, zero raw CSV modifications, and live dashboard updating immediately upon invoice approval.

## PHASE 10: ML Feature Engineering
- **Status**: COMPLETED
- **Objective**: Engineer time-series and demand features from historical inventory and sales data for machine learning with strict zero target leakage.
- **Main tasks**:
  - Safe read-only extraction of historical sales, products, categories, inventory, and promotions.
  - Aggregation of transactional sales to daily product-level ground-truth target (`demand_units`).
  - Construction of complete 365-day calendar grid across all 20 products (7,300 total rows).
  - Generation of calendar attributes and cyclical periodic encodings (`sin` / `cos` for day of week and month).
  - Computation of demand lag features (lags 1, 7, 14, 28) isolated per product.
  - Computation of rolling statistics (mean, sum, std over 7, 14, 28 days) strictly shifted on previous days (closed='left') to eliminate target leakage.
  - Behavioral feature engineering: `days_since_last_sale` and short-vs-long term demand trend ratios.
  - Precedence-aware historical inventory features ($T - 1$ closing/opening stock); same-day closing stock strictly excluded.
  - Promotion date interval labeling and discount rates.
  - Data quality indicators and 28-day history readiness flags.
  - Atomic artifact generation under `data/processed/stage10/`: CSV, Parquet, Feature Data Dictionary, Quality Summary, and Run Metadata.
  - Streamlit UI integration on port 8504: interactive metrics, run triggers, preview table, downloads, and documentation.
- **Inputs**: Phase 9 historical sales, inventory, products, categories, and promotions.
- **Outputs**: `data/processed/stage10/daily_product_features.{csv,parquet}`, `feature_data_dictionary.csv`, `feature_quality_summary.csv`, and `stage10_metadata.json`.
- **Dependencies**: Phase 9.
- **Completion criteria**: Feature pipeline runs deterministically and reproducibly; zero target leakage verified; 9 dedicated Stage 10 tests passing; 122/122 repository tests passing (0 failures, 0 warnings); zero writes to production PostgreSQL.

## PHASE 11: Demand Forecasting
- **Status**: NOT STARTED
- **Objective**: Train and evaluate demand forecasting models per product.
- **Main tasks**: Baseline models (ARIMA/ETS), ML models (XGBoost, LightGBM), cross-validation, evaluation metrics.
- **Inputs**: Phase 10 feature datasets.
- **Outputs**: Trained forecasting models and forecast reports.
- **Dependencies**: Phase 10.
- **Completion criteria**: Forecast accuracy meets defined targets; models are versioned and documented.

## PHASE 12: Inventory Decision Engine
- **Status**: NOT STARTED
- **Objective**: Convert demand forecasts into actionable reorder decisions.
- **Main tasks**: Safety-stock calculation, reorder point, economic order quantity, decision rules.
- **Inputs**: Phase 11 forecasts and Phase 9 inventory data.
- **Outputs**: Reorder recommendations per product.
- **Dependencies**: Phase 11.
- **Completion criteria**: Decision engine produces explainable, validated reorder recommendations.

## PHASE 13: Inventory Simulation and Research Experiments
- **Status**: NOT STARTED
- **Objective**: Simulate inventory over time and run controlled experiments to measure stockout reduction.
- **Main tasks**: Discrete-event simulation, scenario comparison, sensitivity analysis.
- **Inputs**: Phase 12 decision engine outputs.
- **Outputs**: Simulation results and research experiment logs.
- **Dependencies**: Phase 12.
- **Completion criteria**: Experiments documented with reproducible results.

## PHASE 14: Generative AI Assistant
- **Status**: NOT STARTED
- **Objective**: Add an AI assistant to explain inventory decisions in natural language.
- **Main tasks**: Integrate local LLM (Ollama), prompt engineering for decision explanation, UI integration.
- **Inputs**: Inventory decisions from Phase 12.
- **Outputs**: AI-generated explanations displayed in the dashboard.
- **Dependencies**: Phase 12.
- **Completion criteria**: Assistant accurately explains inventory recommendations in plain language.

## PHASE 15: Advanced Engineering and Deployment
- **Status**: NOT STARTED
- **Objective**: Prepare the complete system for production-grade deployment.
- **Main tasks**: Dockerize all components, optionally add Airflow scheduling, cloud deployment (optional).
- **Inputs**: Entire completed system.
- **Outputs**: Deployed, containerised system.
- **Dependencies**: Phase 14.
- **Completion criteria**: System runs reliably in a production or staging environment.
