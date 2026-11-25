"""
Feature Generation Pipeline for Stage 10 ML Feature Engineering.

Transforms extracted transactional sales and historical inventory into a clean,
daily product-level dataset with strictly zero target leakage.
"""

import math
import datetime
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


def aggregate_daily_demand(df_sales: pd.DataFrame, df_products: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Aggregates transactional sales records into daily product demand.
    Builds a complete calendar grid over the verified sales coverage date range.
    Zero-fills covered dates without recorded transactions (reflecting zero observed demand).
    
    Returns:
      (grid_df, audit_metrics)
    """
    total_sales_rows = len(df_sales)
    
    # 1. Validation of sales rows
    valid_mask = (
        df_sales["product_id"].notna() &
        df_sales["date"].notna() &
        df_sales["quantity"].notna() &
        (df_sales["quantity"] > 0)
    )
    valid_sales = df_sales[valid_mask].copy()
    invalid_sales_rows = total_sales_rows - len(valid_sales)
    
    # 2. Daily aggregation: SUM(quantity) as demand_units
    daily_agg = valid_sales.groupby(["product_id", "date"], as_index=False).agg(
        demand_units=("quantity", "sum"),
        transaction_count=("sale_id", "count")
    )
    
    # 3. Complete Calendar Grid construction
    min_date = valid_sales["date"].min()
    max_date = valid_sales["date"].max()
    all_dates = pd.date_range(start=min_date, end=max_date, freq="D").date
    all_products = df_products["product_id"].unique()
    
    grid_index = pd.MultiIndex.from_product(
        [all_products, all_dates],
        names=["product_id", "date"]
    )
    grid_df = pd.DataFrame(index=grid_index).reset_index()
    
    # Merge daily aggregation onto grid
    grid_df = pd.merge(grid_df, daily_agg, on=["product_id", "date"], how="left")
    
    # Track whether demand was recorded or zero-filled
    grid_df["is_zero_demand_inferred"] = grid_df["demand_units"].isna()
    grid_df["demand_units"] = grid_df["demand_units"].fillna(0).astype(int)
    grid_df["transaction_count"] = grid_df["transaction_count"].fillna(0).astype(int)
    
    # Sort deterministically
    grid_df = grid_df.sort_values(["product_id", "date"]).reset_index(drop=True)
    
    audit_metrics = {
        "total_source_sales_rows": total_sales_rows,
        "valid_sales_rows": len(valid_sales),
        "invalid_sales_rows": invalid_sales_rows,
        "distinct_products": len(all_products),
        "min_sales_date": str(min_date),
        "max_sales_date": str(max_date),
        "total_grid_rows": len(grid_df),
        "zero_demand_days_count": int(grid_df["is_zero_demand_inferred"].sum()),
        "active_sales_days_count": int((~grid_df["is_zero_demand_inferred"]).sum())
    }
    
    return grid_df, audit_metrics


def generate_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generates deterministic calendar features and cyclical encodings from the 'date' column.
    """
    res = df.copy()
    dates = pd.to_datetime(res["date"])
    
    # Standard calendar attributes
    res["day_of_week"] = dates.dt.dayofweek  # 0 = Monday, 6 = Sunday
    res["day_of_month"] = dates.dt.day
    res["week_of_year"] = dates.dt.isocalendar().week.astype(int)
    res["month"] = dates.dt.month
    res["quarter"] = dates.dt.quarter
    res["year"] = dates.dt.year
    res["is_weekend"] = res["day_of_week"].isin([5, 6]).astype(int)
    
    # Cyclical encodings
    # day_of_week in [0..6] -> period 7
    res["day_of_week_sin"] = np.round(np.sin(2 * np.pi * res["day_of_week"] / 7.0), 6)
    res["day_of_week_cos"] = np.round(np.cos(2 * np.pi * res["day_of_week"] / 7.0), 6)
    
    # month in [1..12] -> period 12
    res["month_sin"] = np.round(np.sin(2 * np.pi * (res["month"] - 1) / 12.0), 6)
    res["month_cos"] = np.round(np.cos(2 * np.pi * (res["month"] - 1) / 12.0), 6)
    
    return res


def generate_lag_and_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generates historical demand lag and rolling statistical features per product.
    CRITICAL: Strictly prevents target leakage by:
      1. Shifting target by 1 day first (previous_demand = demand_units.shift(1))
      2. Calculating rolling statistics strictly on previous_demand (closed='left' equivalent)
      3. Setting features to NaN when insufficient history exists
    """
    res = df.copy()
    res = res.sort_values(["product_id", "date"]).reset_index(drop=True)
    
    grouped = res.groupby("product_id", group_keys=False)
    
    # 1. Demand Lags: lag_1 is previous day, lag_7 is 7 days prior, etc.
    res["demand_lag_1"] = grouped["demand_units"].shift(1)
    res["demand_lag_7"] = grouped["demand_units"].shift(7)
    res["demand_lag_14"] = grouped["demand_units"].shift(14)
    res["demand_lag_28"] = grouped["demand_units"].shift(28)
    
    # 2. Rolling features based strictly on historical shifted demand (shift(1))
    # Using shift(1) guarantees that the current day's demand_units NEVER enters the window
    shifted_demand = grouped["demand_units"].shift(1)
    
    # We group the shifted series by product_id to compute rolling metrics
    shifted_grouped = shifted_demand.groupby(res["product_id"])
    
    for w in [7, 14, 28]:
        res[f"rolling_mean_{w}"] = np.round(
            shifted_grouped.rolling(window=w, min_periods=w).mean().reset_index(drop=True), 4
        )
        res[f"rolling_sum_{w}"] = (
            shifted_grouped.rolling(window=w, min_periods=w).sum().reset_index(drop=True)
        )
        res[f"rolling_std_{w}"] = np.round(
            shifted_grouped.rolling(window=w, min_periods=w).std().reset_index(drop=True), 4
        )
    
    # 3. Behavioral Features: days since last sale & demand trend
    days_list = []
    for _, group in res.groupby("product_id"):
        last_idx = None
        for i, val in enumerate(group["demand_units"]):
            if last_idx is None:
                days_list.append(np.nan)
            else:
                days_list.append(float(i - last_idx))
            if val > 0:
                last_idx = i
                
    res["days_since_last_sale"] = pd.Series(days_list, index=res.index)
    
    # Demand trend: ratio of short-term rolling mean (7d) to longer-term rolling mean (28d)
    # Using a small epsilon to prevent division by zero
    res["demand_trend_ratio_7_28"] = np.where(
        res["rolling_mean_28"].notna() & (res["rolling_mean_28"] > 0),
        np.round(res["rolling_mean_7"] / (res["rolling_mean_28"] + 1e-4), 4),
        np.nan
    )
    
    # History readiness flag: True when at least 28 days of history exist for the product
    res["has_sufficient_history_28d"] = res["rolling_mean_28"].notna()
    
    return res


def merge_product_and_category_metadata(df: pd.DataFrame, df_products: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches dataset with verified product and category metadata.
    """
    res = df.copy()
    meta_cols = [
        "product_id", "product_name", "category_id", "category_name",
        "supplier_id", "stock_unit", "base_price", "cost_price",
        "popularity_class", "demand_pattern_class"
    ]
    meta_df = df_products[meta_cols].copy()
    
    # Standardize stock_unit label if null
    meta_df["stock_unit"] = meta_df["stock_unit"].fillna("Units")
    
    res = pd.merge(res, meta_df, on="product_id", how="left")
    return res


def merge_historical_inventory_features(df: pd.DataFrame, df_inventory: pd.DataFrame) -> pd.DataFrame:
    """
    Merges historical inventory observations with strict alignment and no data leakage.
    Rules:
      1. Uses previous-day inventory metrics (lagged by 1 day) as predictors for today.
      2. Same-day closing stock is NEVER used as a predictor.
      3. Missing inventory observations are explicitly flagged, not indefinitely forward-filled.
    """
    res = df.copy()
    inv = df_inventory.copy()
    
    inv = inv.sort_values(["product_id", "date"]).reset_index(drop=True)
    
    # Prepare previous-day inventory attributes
    # The predictor for date T must use inventory recorded at date T - 1
    inv_lagged = inv[[
        "product_id", "date", "opening_stock", "closing_stock", "units_received", "stockout_flag"
    ]].copy()
    
    # Advance date by 1 day so that when merged with sales on date T, it represents T - 1 inventory
    inv_lagged["effective_target_date"] = inv_lagged["date"] + datetime.timedelta(days=1)
    
    inv_lagged = inv_lagged.rename(columns={
        "opening_stock": "prev_day_opening_stock",
        "closing_stock": "prev_day_closing_stock",
        "units_received": "prev_day_units_received",
        "stockout_flag": "prev_day_stockout_flag"
    })
    
    inv_lagged = inv_lagged[[
        "product_id", "effective_target_date", "prev_day_opening_stock",
        "prev_day_closing_stock", "prev_day_units_received", "prev_day_stockout_flag"
    ]]
    
    # Merge onto main dataframe
    res = pd.merge(
        res,
        inv_lagged,
        left_on=["product_id", "date"],
        right_on=["product_id", "effective_target_date"],
        how="left"
    )
    res = res.drop(columns=["effective_target_date"])
    
    # Quality indicator for inventory coverage
    res["has_prev_day_inventory"] = res["prev_day_closing_stock"].notna()
    res["prev_day_stockout_flag"] = res["prev_day_stockout_flag"].fillna(False).astype(bool)
    
    return res


def merge_promotion_features(
    df: pd.DataFrame,
    df_promotions: pd.DataFrame,
    df_eligibility: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Marks promotional periods based on verified date intervals in the promotions table
    and product-level eligibility.
    If df_eligibility is provided (columns: ['promotion_id', 'product_id']), only products
    specifically eligible for the given promotion receive the active promotion indicator.
    """
    res = df.copy()
    res["promotion_active"] = 0
    res["promotion_id"] = None
    res["promotion_discount_pct"] = 0.0
    
    if df_promotions is None or df_promotions.empty:
        return res
        
    for _, p in df_promotions.iterrows():
        p_id = p["promotion_id"]
        start_d = p["start_date"]
        end_d = p["end_date"]
        disc = float(p.get("discount_percentage", 0.0))
        
        date_mask = (res["date"] >= start_d) & (res["date"] <= end_d)
        
        if df_eligibility is not None and not df_eligibility.empty:
            eligible_products = df_eligibility[df_eligibility["promotion_id"] == p_id]["product_id"].unique()
            mask = date_mask & (res["product_id"].isin(eligible_products))
        else:
            mask = date_mask
            
        res.loc[mask, "promotion_active"] = 1
        res.loc[mask, "promotion_id"] = p_id
        res.loc[mask, "promotion_discount_pct"] = disc
        
    return res


def build_stage10_feature_dataset(
    source_data: Dict[str, pd.DataFrame]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Full end-to-end orchestration to generate the complete Stage 10 feature dataset.
    """
    df_sales = source_data["sales"]
    df_products = source_data["products"]
    df_inventory = source_data["inventory"]
    df_promotions = source_data["promotions"]
    df_promo_eligibility = source_data.get("promo_eligibility", None)
    
    # Step 1: Aggregate daily demand on complete grid
    grid_df, audit_metrics = aggregate_daily_demand(df_sales, df_products)
    
    # Step 2: Calendar features
    feat_df = generate_calendar_features(grid_df)
    
    # Step 3: Lag and rolling statistical features
    feat_df = generate_lag_and_rolling_features(feat_df)
    
    # Step 4: Product and category metadata
    feat_df = merge_product_and_category_metadata(feat_df, df_products)
    
    # Step 5: Historical inventory features
    feat_df = merge_historical_inventory_features(feat_df, df_inventory)
    
    # Step 6: Promotion features (with product eligibility enforcement)
    feat_df = merge_promotion_features(feat_df, df_promotions, df_promo_eligibility)
    
    # Column ordering: Keys -> Target -> Calendar -> Lags -> Rolling -> Metadata -> Inventory -> Promo -> Quality
    ordered_cols = [
        # Keys & Date
        "product_id",
        "date",
        # Target (separated conceptually)
        "demand_units",
        # Calendar features
        "day_of_week",
        "day_of_month",
        "week_of_year",
        "month",
        "quarter",
        "year",
        "is_weekend",
        "day_of_week_sin",
        "day_of_week_cos",
        "month_sin",
        "month_cos",
        # Demand Lag features
        "demand_lag_1",
        "demand_lag_7",
        "demand_lag_14",
        "demand_lag_28",
        # Rolling Statistical features
        "rolling_mean_7",
        "rolling_mean_14",
        "rolling_mean_28",
        "rolling_sum_7",
        "rolling_sum_14",
        "rolling_sum_28",
        "rolling_std_7",
        "rolling_std_14",
        "rolling_std_28",
        # Behavioral features
        "days_since_last_sale",
        "demand_trend_ratio_7_28",
        # Product & Category metadata
        "product_name",
        "category_id",
        "category_name",
        "supplier_id",
        "stock_unit",
        "base_price",
        "cost_price",
        "popularity_class",
        "demand_pattern_class",
        # Historical Inventory features
        "prev_day_opening_stock",
        "prev_day_closing_stock",
        "prev_day_units_received",
        "prev_day_stockout_flag",
        # Promotion features
        "promotion_active",
        "promotion_id",
        "promotion_discount_pct",
        # Quality & Readiness flags
        "is_zero_demand_inferred",
        "has_prev_day_inventory",
        "has_sufficient_history_28d"
    ]
    
    feat_df = feat_df[ordered_cols].sort_values(["product_id", "date"]).reset_index(drop=True)
    
    # Compute summary metrics
    audit_metrics["total_output_rows"] = len(feat_df)
    audit_metrics["total_columns"] = len(ordered_cols)
    audit_metrics["rows_with_sufficient_history_28d"] = int(feat_df["has_sufficient_history_28d"].sum())
    audit_metrics["rows_with_prev_day_inventory"] = int(feat_df["has_prev_day_inventory"].sum())
    audit_metrics["promoted_rows_count"] = int((feat_df["promotion_active"] == 1).sum())
    
    return feat_df, audit_metrics
