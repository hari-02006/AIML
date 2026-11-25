# Smart Inventory & Demand Prediction System

## Run locally

From this project directory, run these commands with Python 3.13 in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:INVENTORY_DEMO = "1"
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py
```

Open [the dashboard](http://localhost:8501). Demo mode loads bundled synthetic data in memory. It includes Overview, Sales, Product and Inventory analytics, plus invoice upload and OCR preview. OCR uses Windows Media OCR when available or a locally installed Tesseract executable.

For live analytics, invoice approval and stock updates, follow the [PostgreSQL setup guide](docs/database/database-setup.md). Remove `INVENTORY_DEMO` from your shell before starting Streamlit in PostgreSQL mode.

## Project Title
Smart Inventory & Demand Prediction System

## Project Purpose
To build an end-to-end Smart Inventory & Demand Prediction System for a simulated e-commerce electronics business.

## Business Problem
Inventory management. The system will help answer:
- What products are selling?
- What is the current inventory?
- Which products are at risk of stockout?
- What demand is expected in the future?
- When should the business consider reordering?
- Approximately how much should be reordered?
- Why does the system recommend a particular inventory action?

## Proposed Solution
A system combining Data Engineering, Data Analytics, Machine Learning, Inventory Decision Support, and Generative AI, operating in a controlled synthetic retail environment.

## Research Question
[Placeholder for future research question]

## Main Objectives
- Simulate an online retail store (electronics).
- Generate synthetic data.
- Build an ETL pipeline into a PostgreSQL database.
- Perform exploratory data analysis and basic dashboarding.
- Implement demand forecasting and inventory decision engines.
- Add an AI assistant to explain recommendations.

## Planned Architecture
See `docs/architecture/system-architecture.md`.

## Technology Stack
- **Dashboard**: Streamlit
- **Application and data processing**: Python
- **Database**: PostgreSQL
- **Data Generation**: Python, Pandas, NumPy
- **ETL**: Python, Pandas, SQL
- **Analytics**: PostgreSQL SQL, Pandas, Plotly
- **Machine Learning**: scikit-learn, XGBoost
- **AI**: Ollama / local open-source LLM
- **Version Control**: Git, GitHub

*(Future possibility: Airflow, Docker, Data Warehouse, Cloud deployment)*

## Development Phases
See `PROJECT_ROADMAP.md`.

## Stage 9: Purchase Invoice Intake & Inventory Stock Update
Stage 9 integrates invoice processing directly with the live PostgreSQL database (`smart_inventory`).
- **Product Reconciliation**: Extracted OCR items match against the existing product catalog with canonical unit checking (`products.stock_unit`).
- **Stale Stock Audit**: When a product's last recorded inventory date exceeds `INVENTORY_STALE_DAYS` (30 days), the shopkeeper is prompted to confirm physical stock before adding new deliveries.
- **Transactional Approval**: Safely locks inventory records, executes daily UPSERTs preserving `opening_stock`, moves document files via a verified copy-and-commit protocol, and archives invoices in `purchase_invoices` and `purchase_invoice_items`.
- **Duplicate Protection**: Dual-tier duplicate protection using SHA-256 binary hash matching and heuristic re-scan warnings based on supplier identity and invoice reference.
- **Live Dashboard**: Inventory Analytics reflects approved incoming quantities using the latest inventory record for each product.


## IA 50% Milestone
The mini-project must be at least 50% complete before the IA examination. See roadmap for details.

## Current Project Status
**This project is currently under development.** 
Stages 0 through 9 (Project Foundation, Synthetic Retail Environment Design, Synthetic Data Generator, PostgreSQL Database, ETL / Data Pipeline, Analytics, Dashboard, Invoice Scanning Interface, OCR & Invoice Data Extraction, and Invoice Approval & Inventory Stock Update) are fully **completed**.
See `PROJECT_STATUS.md` for exact tracking.

## Future Scope
Advanced engineering and cloud deployment (Docker, Airflow, Data Warehouse).
