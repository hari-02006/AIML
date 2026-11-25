# Data Pipeline Plan

## Planned Data Flow

```text
Synthetic Data Generator
        ↓
Raw Data
        ↓
Extract
        ↓
Transform
        ↓
Validate
        ↓
Load
        ↓
PostgreSQL
```

## Step Responsibilities
- **Synthetic Data Generator**: Emulates a real-world store and outputs CSV files representing the operational past.
- **Raw Data**: Stored in `data/raw/`.
- **Extract**: Read raw files safely.
- **Transform**: Clean and format types for database insertion.
- **Validate**: Ensure data quality constraints are met.
- **Load**: Bulk insert into PostgreSQL.

## Future Quality Checks
- Missing values
- Invalid dates
- Negative prices
- Negative quantities
- Duplicate IDs
- Invalid foreign keys
- Impossible inventory values
- Invalid discount values

*(Pipeline is not implemented in Stage 0.)*
