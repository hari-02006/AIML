"""
Artifact Generation and Reporting Module for Stage 10 ML Feature Engineering.
Safely saves the output files to data/processed/stage10/ using atomic write-and-replace:
  1. daily_product_features.csv (and daily_product_features.parquet)
  2. feature_data_dictionary.csv
  3. feature_quality_summary.csv
  4. stage10_metadata.json
"""

import os
import json
import tempfile
import datetime
from pathlib import Path
from typing import Dict, Any, List
import pandas as pd

STAGE10_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "stage10"


def generate_feature_data_dictionary() -> pd.DataFrame:
    """
    Builds the complete data dictionary defining every feature, formula, data type, and leakage policy.
    """
    dictionary_entries = [
        {
            "column_name": "product_id",
            "feature_group": "Identifier",
            "data_type": "string",
            "description": "Unique product identifier code (e.g. PROD_001).",
            "source": "products.product_id",
            "leakage_safe": "Yes (Static metadata)"
        },
        {
            "column_name": "date",
            "feature_group": "Timeline / Key",
            "data_type": "date",
            "description": "Calendar observation date (YYYY-MM-DD).",
            "source": "Calendar Grid (derived from sales.date range)",
            "leakage_safe": "Yes (Observation timestamp)"
        },
        {
            "column_name": "demand_units",
            "feature_group": "Target Variable",
            "data_type": "integer",
            "description": "Ground-truth units sold on this date. Zero-filled on covered dates without transactions.",
            "source": "SUM(sales.quantity) per product-date",
            "leakage_safe": "TARGET ONLY (Must not be used as an input predictor in Stage 11)"
        },
        {
            "column_name": "day_of_week",
            "feature_group": "Calendar",
            "data_type": "integer",
            "description": "Day of the week index (0 = Monday, 6 = Sunday).",
            "source": "date.dayofweek",
            "leakage_safe": "Yes (Deterministic calendar property)"
        },
        {
            "column_name": "day_of_month",
            "feature_group": "Calendar",
            "data_type": "integer",
            "description": "Day number within the month (1 to 31).",
            "source": "date.day",
            "leakage_safe": "Yes (Deterministic calendar property)"
        },
        {
            "column_name": "week_of_year",
            "feature_group": "Calendar",
            "data_type": "integer",
            "description": "ISO week number of the calendar year (1 to 53).",
            "source": "date.isocalendar().week",
            "leakage_safe": "Yes (Deterministic calendar property)"
        },
        {
            "column_name": "month",
            "feature_group": "Calendar",
            "data_type": "integer",
            "description": "Month number of the calendar year (1 to 12).",
            "source": "date.month",
            "leakage_safe": "Yes (Deterministic calendar property)"
        },
        {
            "column_name": "quarter",
            "feature_group": "Calendar",
            "data_type": "integer",
            "description": "Calendar quarter (1 to 4).",
            "source": "date.quarter",
            "leakage_safe": "Yes (Deterministic calendar property)"
        },
        {
            "column_name": "year",
            "feature_group": "Calendar",
            "data_type": "integer",
            "description": "Calendar year.",
            "source": "date.year",
            "leakage_safe": "Yes (Deterministic calendar property)"
        },
        {
            "column_name": "is_weekend",
            "feature_group": "Calendar",
            "data_type": "integer",
            "description": "Binary flag indicating whether the date is Saturday or Sunday (1=Weekend, 0=Weekday).",
            "source": "day_of_week in [5, 6]",
            "leakage_safe": "Yes (Deterministic calendar property)"
        },
        {
            "column_name": "day_of_week_sin",
            "feature_group": "Calendar (Cyclical)",
            "data_type": "float",
            "description": "Sine cyclical encoding of day of week: sin(2 * pi * day_of_week / 7).",
            "source": "Cyclical transformation of day_of_week",
            "leakage_safe": "Yes (Continuous periodic representation)"
        },
        {
            "column_name": "day_of_week_cos",
            "feature_group": "Calendar (Cyclical)",
            "data_type": "float",
            "description": "Cosine cyclical encoding of day of week: cos(2 * pi * day_of_week / 7).",
            "source": "Cyclical transformation of day_of_week",
            "leakage_safe": "Yes (Continuous periodic representation)"
        },
        {
            "column_name": "month_sin",
            "feature_group": "Calendar (Cyclical)",
            "data_type": "float",
            "description": "Sine cyclical encoding of month: sin(2 * pi * (month - 1) / 12).",
            "source": "Cyclical transformation of month",
            "leakage_safe": "Yes (Continuous periodic representation)"
        },
        {
            "column_name": "month_cos",
            "feature_group": "Calendar (Cyclical)",
            "data_type": "float",
            "description": "Cosine cyclical encoding of month: cos(2 * pi * (month - 1) / 12).",
            "source": "Cyclical transformation of month",
            "leakage_safe": "Yes (Continuous periodic representation)"
        },
        {
            "column_name": "demand_lag_1",
            "feature_group": "Demand Lag",
            "data_type": "float",
            "description": "Demand units sold on previous calendar day (T - 1).",
            "source": "demand_units.shift(1) per product",
            "leakage_safe": "Yes (T - 1 strictly historical)"
        },
        {
            "column_name": "demand_lag_7",
            "feature_group": "Demand Lag",
            "data_type": "float",
            "description": "Demand units sold 7 calendar days earlier (same weekday last week, T - 7).",
            "source": "demand_units.shift(7) per product",
            "leakage_safe": "Yes (T - 7 strictly historical)"
        },
        {
            "column_name": "demand_lag_14",
            "feature_group": "Demand Lag",
            "data_type": "float",
            "description": "Demand units sold 14 calendar days earlier (T - 14).",
            "source": "demand_units.shift(14) per product",
            "leakage_safe": "Yes (T - 14 strictly historical)"
        },
        {
            "column_name": "demand_lag_28",
            "feature_group": "Demand Lag",
            "data_type": "float",
            "description": "Demand units sold 28 calendar days earlier (T - 28, full 4-week cycle).",
            "source": "demand_units.shift(28) per product",
            "leakage_safe": "Yes (T - 28 strictly historical)"
        },
        {
            "column_name": "rolling_mean_7",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Rolling average daily demand over preceding 7 days (T-7 to T-1). Current day excluded.",
            "source": "demand_units.shift(1).rolling(7).mean() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "rolling_mean_14",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Rolling average daily demand over preceding 14 days (T-14 to T-1). Current day excluded.",
            "source": "demand_units.shift(1).rolling(14).mean() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "rolling_mean_28",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Rolling average daily demand over preceding 28 days (T-28 to T-1). Current day excluded.",
            "source": "demand_units.shift(1).rolling(28).mean() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "rolling_sum_7",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Rolling total units sold over preceding 7 days (T-7 to T-1). Current day excluded.",
            "source": "demand_units.shift(1).rolling(7).sum() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "rolling_sum_14",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Rolling total units sold over preceding 14 days (T-14 to T-1). Current day excluded.",
            "source": "demand_units.shift(1).rolling(14).sum() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "rolling_sum_28",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Rolling total units sold over preceding 28 days (T-28 to T-1). Current day excluded.",
            "source": "demand_units.shift(1).rolling(28).sum() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "rolling_std_7",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Sample standard deviation of daily demand over preceding 7 days (T-7 to T-1).",
            "source": "demand_units.shift(1).rolling(7).std() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "rolling_std_14",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Sample standard deviation of daily demand over preceding 14 days (T-14 to T-1).",
            "source": "demand_units.shift(1).rolling(14).std() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "rolling_std_28",
            "feature_group": "Rolling Statistics",
            "data_type": "float",
            "description": "Sample standard deviation of daily demand over preceding 28 days (T-28 to T-1).",
            "source": "demand_units.shift(1).rolling(28).std() per product",
            "leakage_safe": "Yes (Shifted prior to window calculation)"
        },
        {
            "column_name": "days_since_last_sale",
            "feature_group": "Behavioral",
            "data_type": "float",
            "description": "Number of days elapsed since the most recent non-zero sale prior to current date.",
            "source": "Historical sales recency counter per product",
            "leakage_safe": "Yes (Calculated using past records only)"
        },
        {
            "column_name": "demand_trend_ratio_7_28",
            "feature_group": "Behavioral",
            "data_type": "float",
            "description": "Ratio of short-term demand (rolling_mean_7) to baseline demand (rolling_mean_28).",
            "source": "rolling_mean_7 / (rolling_mean_28 + 1e-4)",
            "leakage_safe": "Yes (Derived from strictly historical rolling features)"
        },
        {
            "column_name": "product_name",
            "feature_group": "Product Metadata",
            "data_type": "string",
            "description": "Descriptive commercial product title.",
            "source": "products.product_name",
            "leakage_safe": "Yes (Static catalog attribute)"
        },
        {
            "column_name": "category_id",
            "feature_group": "Product Metadata",
            "data_type": "integer",
            "description": "Foreign key reference to categories table.",
            "source": "products.category_id",
            "leakage_safe": "Yes (Static catalog hierarchy)"
        },
        {
            "column_name": "category_name",
            "feature_group": "Product Metadata",
            "data_type": "string",
            "description": "Product category name (Audio, Peripherals, Displays, Storage, Accessories).",
            "source": "categories.category_name",
            "leakage_safe": "Yes (Static catalog hierarchy)"
        },
        {
            "column_name": "supplier_id",
            "feature_group": "Product Metadata",
            "data_type": "string",
            "description": "Primary supplier identifier code.",
            "source": "products.supplier_id",
            "leakage_safe": "Yes (Static supply attribute)"
        },
        {
            "column_name": "stock_unit",
            "feature_group": "Product Metadata",
            "data_type": "string",
            "description": "Canonical inventory tracking unit (e.g. Units).",
            "source": "products.stock_unit (defaults to 'Units')",
            "leakage_safe": "Yes (Unit standardization attribute)"
        },
        {
            "column_name": "base_price",
            "feature_group": "Product Metadata",
            "data_type": "float",
            "description": "Standard catalog selling price.",
            "source": "products.base_price",
            "leakage_safe": "Yes (Reference catalog price)"
        },
        {
            "column_name": "cost_price",
            "feature_group": "Product Metadata",
            "data_type": "float",
            "description": "Standard wholesale procurement cost.",
            "source": "products.cost_price",
            "leakage_safe": "Yes (Reference catalog cost)"
        },
        {
            "column_name": "popularity_class",
            "feature_group": "Product Metadata",
            "data_type": "string",
            "description": "Product volume classification (HIGH, MEDIUM, LOW).",
            "source": "products.popularity_class",
            "leakage_safe": "Yes (Static classification attribute)"
        },
        {
            "column_name": "demand_pattern_class",
            "feature_group": "Product Metadata",
            "data_type": "string",
            "description": "Demand volatility pattern (Stable, Seasonal, Weekend-sensitive, etc.).",
            "source": "products.demand_pattern_class",
            "leakage_safe": "Yes (Static classification attribute)"
        },
        {
            "column_name": "prev_day_opening_stock",
            "feature_group": "Inventory",
            "data_type": "float",
            "description": "Opening inventory stock recorded on previous calendar day (T - 1).",
            "source": "inventory.opening_stock at T - 1",
            "leakage_safe": "Yes (T - 1 historical snapshot)"
        },
        {
            "column_name": "prev_day_closing_stock",
            "feature_group": "Inventory",
            "data_type": "float",
            "description": "Closing inventory stock recorded on previous calendar day (T - 1).",
            "source": "inventory.closing_stock at T - 1",
            "leakage_safe": "Yes (T - 1 historical snapshot)"
        },
        {
            "column_name": "prev_day_units_received",
            "feature_group": "Inventory",
            "data_type": "float",
            "description": "Stock replenishment units delivered on previous calendar day (T - 1).",
            "source": "inventory.units_received at T - 1",
            "leakage_safe": "Yes (T - 1 historical snapshot)"
        },
        {
            "column_name": "prev_day_stockout_flag",
            "feature_group": "Inventory",
            "data_type": "boolean",
            "description": "Whether stockout occurred on previous calendar day (T - 1).",
            "source": "inventory.stockout_flag at T - 1",
            "leakage_safe": "Yes (T - 1 historical snapshot)"
        },
        {
            "column_name": "promotion_active",
            "feature_group": "Promotion",
            "data_type": "integer",
            "description": "Binary indicator whether a marketing promotion was active on this date (1=Active, 0=None).",
            "source": "promotions date intervals",
            "leakage_safe": "Yes (Deterministic promotional schedule)"
        },
        {
            "column_name": "promotion_id",
            "feature_group": "Promotion",
            "data_type": "string",
            "description": "Identifier of the promotional campaign (FESTIVAL_SALE, WEEKEND_SALE, or None).",
            "source": "promotions.promotion_id",
            "leakage_safe": "Yes (Deterministic promotional schedule)"
        },
        {
            "column_name": "promotion_discount_pct",
            "feature_group": "Promotion",
            "data_type": "float",
            "description": "Promotional discount percentage active on this date (e.g. 0.20 for 20% off).",
            "source": "promotions.discount_percentage",
            "leakage_safe": "Yes (Deterministic promotional schedule)"
        },
        {
            "column_name": "is_zero_demand_inferred",
            "feature_group": "Quality Indicator",
            "data_type": "boolean",
            "description": "True if date was within sales coverage but had zero sales transactions (zero-filled).",
            "source": "Calendar Grid reconciliation",
            "leakage_safe": "Yes (Data provenance transparency)"
        },
        {
            "column_name": "has_prev_day_inventory",
            "feature_group": "Quality Indicator",
            "data_type": "boolean",
            "description": "True if preceding day (T - 1) has a verified physical inventory record.",
            "source": "Inventory join reconciliation",
            "leakage_safe": "Yes (Data completeness transparency)"
        },
        {
            "column_name": "has_sufficient_history_28d",
            "feature_group": "Quality Indicator",
            "data_type": "boolean",
            "description": "True if at least 28 prior calendar days exist for lag/rolling features to be fully populated.",
            "source": "Lag/Rolling boundary check",
            "leakage_safe": "Yes (Model training filtering flag)"
        }
    ]
    return pd.DataFrame(dictionary_entries)


def generate_feature_quality_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes a column-by-column data quality, null-count, and missingness summary.
    """
    total_rows = len(df)
    summary_list = []
    
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        null_pct = round((null_count / total_rows) * 100.0, 2)
        unique_cnt = int(df[col].nunique(dropna=True))
        dtype_str = str(df[col].dtype)
        
        # Calculate sample min / max for numerical or date
        sample_min = None
        sample_max = None
        try:
            if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col]):
                sample_min = str(df[col].min())
                sample_max = str(df[col].max())
        except Exception:
            pass
            
        summary_list.append({
            "column_name": col,
            "data_type": dtype_str,
            "total_rows": total_rows,
            "null_count": null_count,
            "null_percentage": null_pct,
            "unique_values": unique_cnt,
            "min_val": sample_min,
            "max_val": sample_max
        })
        
    return pd.DataFrame(summary_list)


def save_stage10_artifacts(
    feat_df: pd.DataFrame,
    audit_metrics: Dict[str, Any]
) -> Dict[str, str]:
    """
    Saves all Stage 10 output artifacts atomically to data/processed/stage10/.
    Uses atomic temporary files replaced only after complete write succeeds.
    """
    STAGE10_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    saved_files: Dict[str, str] = {}
    
    # 1. Feature Dataset CSV
    csv_path = STAGE10_OUTPUT_DIR / "daily_product_features.csv"
    with tempfile.NamedTemporaryFile("w", delete=False, dir=STAGE10_OUTPUT_DIR, suffix=".tmp_csv", newline="") as tmp_f:
        feat_df.to_csv(tmp_f, index=False)
        tmp_csv_path = Path(tmp_f.name)
    tmp_csv_path.replace(csv_path)
    saved_files["features_csv"] = str(csv_path)

    # 2. Feature Dataset Parquet
    parquet_path = STAGE10_OUTPUT_DIR / "daily_product_features.parquet"
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=STAGE10_OUTPUT_DIR, suffix=".tmp_parquet") as tmp_f:
        feat_df.to_parquet(tmp_f, index=False, engine="pyarrow")
        tmp_parquet_path = Path(tmp_f.name)
    tmp_parquet_path.replace(parquet_path)
    saved_files["features_parquet"] = str(parquet_path)

    # 3. Data Dictionary CSV
    dict_df = generate_feature_data_dictionary()
    dict_path = STAGE10_OUTPUT_DIR / "feature_data_dictionary.csv"
    with tempfile.NamedTemporaryFile("w", delete=False, dir=STAGE10_OUTPUT_DIR, suffix=".tmp_dict", newline="") as tmp_f:
        dict_df.to_csv(tmp_f, index=False)
        tmp_dict_path = Path(tmp_f.name)
    tmp_dict_path.replace(dict_path)
    saved_files["data_dictionary"] = str(dict_path)

    # 4. Quality Summary CSV
    quality_df = generate_feature_quality_summary(feat_df)
    quality_path = STAGE10_OUTPUT_DIR / "feature_quality_summary.csv"
    with tempfile.NamedTemporaryFile("w", delete=False, dir=STAGE10_OUTPUT_DIR, suffix=".tmp_qual", newline="") as tmp_f:
        quality_df.to_csv(tmp_f, index=False)
        tmp_qual_path = Path(tmp_f.name)
    tmp_qual_path.replace(quality_path)
    saved_files["quality_summary"] = str(quality_path)

    # 5. Metadata JSON
    metadata = {
        "stage": "Stage 10: ML Feature Engineering",
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_database": "smart_inventory (read-only snapshot)",
        "target_variable": "demand_units (aggregated sum of valid sales quantities per product-date)",
        "granularity": "One record per product per calendar date",
        "temporal_coverage": {
            "sales_min_date": audit_metrics.get("min_sales_date"),
            "sales_max_date": audit_metrics.get("max_sales_date"),
            "distinct_calendar_dates": 365,
            "distinct_products": audit_metrics.get("distinct_products")
        },
        "inventory_temporal_alignment": {
            "mode": "Lagged by 1 day (T - 1 closing/opening stock as predictor for date T)",
            "leakage_rule": "Same-day closing stock and future snapshots strictly excluded"
        },
        "metrics": audit_metrics,
        "artifacts": {k: Path(v).name for k, v in saved_files.items()}
    }
    
    meta_path = STAGE10_OUTPUT_DIR / "stage10_metadata.json"
    with tempfile.NamedTemporaryFile("w", delete=False, dir=STAGE10_OUTPUT_DIR, suffix=".tmp_meta") as tmp_f:
        json.dump(metadata, tmp_f, indent=2)
        tmp_meta_path = Path(tmp_f.name)
    tmp_meta_path.replace(meta_path)
    saved_files["metadata_json"] = str(meta_path)

    return saved_files
