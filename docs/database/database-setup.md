# Database Setup Guide

## Requirements
- PostgreSQL 13 or higher running locally (usually port `5432`).
- Python 3 with `psycopg[binary]` installed.
- A bundled dataset such as `data/raw_42/`, or synthetic CSVs generated during Stage 2.

## Configuration
Before running any script, ensure your connection credentials are provided.
1. Copy `.env.example` to `.env`.
2. Edit `.env` with your actual local PostgreSQL user and password:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=smart_inventory
DB_USER=postgres
DB_PASSWORD=your_password
```

## Schema Creation & Data Loading
For a fresh database, run the loader from the project root in your virtual environment. It connects to the maintenance database `postgres` and creates the database named in `DB_NAME` if needed. Creating a database requires a role with the `CREATEDB` privilege.
```bash
python -m database.load.load_raw_data --data-dir data/raw_42
```
The loader creates the base tables and imports the CSVs in a transaction. Apply the invoice migration to the same database using `psql` or your PostgreSQL client:

```bash
psql -h localhost -p 5432 -U postgres -d smart_inventory -v ON_ERROR_STOP=1 -f database/migrations/stage9_invoice_tables.sql
```

Use the host, port, user and database settings from `.env`. Then start the app with `python -m streamlit run frontend/app.py` and `INVENTORY_DEMO` unset.

## Validation
After loading, it is critical to run the validation queries to verify data integrity (such as the inventory equation and relational consistency).
Run the queries within `database/queries/validation.sql` using `psql`, pgAdmin, or your preferred SQL client.

## Resetting the Database
The project does **not** provide destructive reset scripts. If you must rebuild from scratch, manually connect as an admin and drop the database, then re-run the loading script.
```sql
-- WARNING: Destructive! Do not run in production.
DROP DATABASE smart_inventory;
```
