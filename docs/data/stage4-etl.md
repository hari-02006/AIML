# Stage 4 — ETL and Data Pipeline

## Purpose
The purpose of this stage is to construct a reusable, idempotent, and resilient ETL pipeline that safely transitions raw data (such as our Stage 2 CSV output or any incremental additions) into the operational `smart_inventory` PostgreSQL database without compromising integrity.

## Architecture

```mermaid
flowchart TD
    RAW[Raw CSV Files\ndata/raw/ or data/incoming/]
    EXTRACT[Extract Layer\n(csv_extractor.py)]
    TRANSFORM[Transform Layer\n(clean_data.py)]
    PROC[Processed Data\ndata/processed/]
    VALIDATE[Validate Layer\n(schema & business rules)]
    
    RAW --> EXTRACT
    EXTRACT --> TRANSFORM
    TRANSFORM --> PROC
    PROC --> VALIDATE
    
    VALIDATE -- Valid --> LOAD[Load Layer\n(postgres_loader.py)]
    VALIDATE -- Invalid --> REJ[Rejected Data\ndata/rejected/]
    
    LOAD -- INSERT ... ON CONFLICT --> DB[(PostgreSQL\nsmart_inventory)]
    
    DB --> AUDIT[ETL Run Log\nlogs/etl_quality_report.json]
    REJ --> AUDIT
```

## Modules
- **`etl/extract/`**: Safely extracts data from raw CSV files, enforcing existence and non-empty checks.
- **`etl/transform/`**: Standardizes string spaces, converts boolean values (e.g., `stockout_flag`), parses and normalizes dates (catching invalid dates like `2026-02-30`), and maps foreign keys (e.g., converting product `category` names to `category_id`).
- **`etl/validate/`**: Validates schema integrity (non-null constraints, numeric types), detects duplicate primary keys, and validates strict business rules (e.g., Inventory Equation: `opening + received - observed = closing`).
- **`etl/load/`**: Executes PostgreSQL inserts utilizing safe UPSERT logic (`ON CONFLICT DO NOTHING`) to ensure complete idempotency.

## Idempotency and Incremental Loading
The pipeline operates idempotently for immutable transactional records (such as historical sales):
- **New record** → inserted
- **Existing identical record** → skipped
- **Duplicate/conflicting primary key** → handled safely via PostgreSQL `ON CONFLICT DO NOTHING`

This implementation inserts new records and skips existing ones; it does *not* dynamically update changed records.

Running a `FULL` mode pipeline repeatedly over `data/raw/` results in exactly 0 database writes, properly logging rows as `Skipped`. Incremental loading is supported by pointing the pipeline to `data/incoming/`, appending new updates without destroying or resetting the baseline data.

## Rejection Handling
Invalid data causes the specific file batch to be redirected to `data/rejected/`.
For required dates, if an invalid date (e.g., `2026-02-30`) is provided:
- The transformation layer invalidates the date.
- The validation layer detects the missing required field.
- **The record is rejected and quarantined.** (It is *not* simply passed through as a valid record with a NULL date.)
- An audit report logs the failure.

## Testing & Validation
- Standard `data/raw` baseline executes perfectly into existing schema.
- Duplicate data is safely skipped via primary key conflict handling.
- Incremental test file (`test_incremental_sales.csv`) seamlessly loaded 2 new records.
- Bad data test file (`bad_sales.csv`) was caught during date and numeric transformation/validation and routed to `data/rejected/`, leaving the database clean.
- All Stage 2 constraints and raw file states are fully preserved.

## Limitations
- For this MVP, if a single file contains validation errors, the entire file block is rejected rather than filtering out individual bad rows and loading the rest. This preserves referential integrity at the batch level but can be optimized later.
- Implemented purely in Python Standard Library to bypass aggressive local Windows Application Control DLL blocks on `pandas`.
