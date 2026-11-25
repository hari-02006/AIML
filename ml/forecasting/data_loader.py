"""
Stage 11 Data Loader Module.
Loads the verified Stage 10 daily product feature dataset from disk and enriches it
with the target-date stockout censoring mask retrieved strictly read-only from PostgreSQL.

Safeguards:
1. Production database queries are strictly read-only (conn.read_only = True).
2. Joining the stockout mask requires matching both product_id and target_date.
3. Every forecasting observation is validated to have exactly one matching inventory record.
4. Missing or duplicate records trigger explicit errors; missing flags are NEVER silently filled as False.
5. Target censoring mask (is_target_censored) is kept strictly separate from predictor feature columns.
"""

import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import pandas as pd
from database.db_connection import get_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STAGE10_PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "stage10" / "daily_product_features.parquet"


def load_stage10_feature_dataset(
    parquet_path: Optional[Path] = None
) -> pd.DataFrame:
    """
    Loads the mature Stage 10 daily product features dataset from Parquet.
    Returns rows where has_sufficient_history_28d is True (6,740 rows, 2025-01-29 to 2025-12-31).
    """
    path = parquet_path or DEFAULT_STAGE10_PARQUET_PATH
    if not path.exists():
        raise FileNotFoundError(f"Stage 10 Parquet dataset not found at {path.resolve()}")
    
    df = pd.read_parquet(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        
    return df


def extract_target_date_stockout_mask(
    dbname: Optional[str] = None
) -> pd.DataFrame:
    """
    Extracts same-day stockout_flag for each product_id and date from the inventory table
    using a strictly read-only transaction against PostgreSQL.
    Returns DataFrame with columns: ['product_id', 'date', 'stockout_flag'].
    """
    conn = get_connection(dbname=dbname)
    conn.read_only = True
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    product_id,
                    date,
                    stockout_flag
                FROM inventory
                WHERE date <= '2025-12-31'
                ORDER BY date, product_id;
            """)
            rows = cur.fetchall()
            cols = [col[0] for col in cur.description]
            df_inv = pd.DataFrame(rows, columns=cols)
            df_inv["date"] = pd.to_datetime(df_inv["date"]).dt.date
            # Ensure boolean type without nulls
            if df_inv["stockout_flag"].isnull().any():
                raise ValueError("Encountered NULL stockout_flag in inventory table!")
            df_inv["stockout_flag"] = df_inv["stockout_flag"].astype(bool)
            return df_inv
    finally:
        conn.close()


def load_forecasting_dataset(
    parquet_path: Optional[Path] = None,
    dbname: Optional[str] = None,
    mature_only: bool = True
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Loads the Stage 10 features and joins the target-date stockout censoring mask.
    
    Integrity Safeguards:
    - Joins on (product_id, date).
    - Asserts that exactly 1 inventory record matches each forecasting row (1-to-1 cardinality).
    - Checks for missing or duplicate product-date pairs.
    - NEVER silently substitutes False for missing stockout flags.
    - Attaches 'is_target_censored' boolean mask.
    """
    df_features = load_stage10_feature_dataset(parquet_path=parquet_path)
    
    if mature_only:
        df_features = df_features[df_features["has_sufficient_history_28d"] == True].copy()
        
    df_features = df_features.sort_values(["product_id", "date"]).reset_index(drop=True)
    
    # Extract inventory stockout mask
    df_mask = extract_target_date_stockout_mask(dbname=dbname)
    
    # Check for duplicate keys in mask
    mask_dups = df_mask.duplicated(subset=["product_id", "date"])
    if mask_dups.any():
        dup_count = mask_dups.sum()
        raise ValueError(f"Integrity violation: {dup_count} duplicate (product_id, date) rows found in inventory mask!")
        
    # Check for duplicate keys in features
    feat_dups = df_features.duplicated(subset=["product_id", "date"])
    if feat_dups.any():
        dup_count = feat_dups.sum()
        raise ValueError(f"Integrity violation: {dup_count} duplicate (product_id, date) rows found in feature dataset!")
        
    # Perform strict inner merge and verify row count preservation
    merged = pd.merge(
        df_features,
        df_mask[["product_id", "date", "stockout_flag"]],
        on=["product_id", "date"],
        how="left"
    )
    
    # Validate completeness: every feature row MUST have a matched inventory flag
    missing_mask = merged["stockout_flag"].isnull()
    if missing_mask.any():
        missing_count = missing_mask.sum()
        missing_samples = merged[missing_mask][["product_id", "date"]].head(5).to_dict("records")
        raise ValueError(
            f"Integrity violation: {missing_count} forecasting observations lack matching inventory stockout flags! "
            f"Samples: {missing_samples}"
        )
        
    # Validate 1-to-1 cardinality: row count must be exactly preserved
    if len(merged) != len(df_features):
        raise ValueError(
            f"Integrity violation: Expected {len(df_features)} rows after mask merge, got {len(merged)}!"
        )
        
    # Rename stockout_flag to is_target_censored to distinguish from prev_day_stockout_flag
    merged = merged.rename(columns={"stockout_flag": "is_target_censored"})
    merged["is_target_censored"] = merged["is_target_censored"].astype(bool)
    
    # Audit summary
    total_rows = len(merged)
    censored_count = int(merged["is_target_censored"].sum())
    uncensored_count = total_rows - censored_count
    
    audit_metrics = {
        "total_forecasting_rows": total_rows,
        "mature_date_min": str(merged["date"].min()),
        "mature_date_max": str(merged["date"].max()),
        "distinct_products": int(merged["product_id"].nunique()),
        "censored_stockout_rows": censored_count,
        "uncensored_rows": uncensored_count,
        "censored_percentage": round((censored_count / total_rows) * 100, 2)
    }
    
    return merged, audit_metrics
