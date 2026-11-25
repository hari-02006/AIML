"""
Stage 11 Preprocessor Module.
Handles:
1. Strict chronological dataset splitting (Train, Validation, Final Test).
2. Feature column separation into Categorical, Numerical, and strictly Excluded.
3. Preprocessing ColumnTransformer (OneHotEncoder + StandardScaler / Passthrough).
4. Strict fit boundaries: transformations are fitted ONLY on training partitions.
5. Extraction of clean predictor matrices X, targets y, and censoring masks M.
"""

import datetime
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler


# Exact chronological boundaries agreed in the approved plan
TRAIN_START_DATE = datetime.date(2025, 1, 29)
TRAIN_END_DATE = datetime.date(2025, 9, 30)

VAL_START_DATE = datetime.date(2025, 10, 1)
VAL_END_DATE = datetime.date(2025, 11, 15)

TEST_START_DATE = datetime.date(2025, 11, 16)
TEST_END_DATE = datetime.date(2025, 12, 31)

# Categorical columns to be encoded via OneHotEncoder
CATEGORICAL_FEATURES = [
    "product_id",
    "category_id",
    "popularity_class",
    "demand_pattern_class"
]

# Numerical predictors: pricing, autoregressive lags, rolling statistics, calendar, and prior inventory
NUMERICAL_FEATURES = [
    # Catalog Pricing
    "base_price",
    "cost_price",
    # Autoregressive Lags
    "demand_lag_1",
    "demand_lag_7",
    "demand_lag_14",
    "demand_lag_28",
    # Shifted Rolling Statistics
    "rolling_mean_7",
    "rolling_mean_14",
    "rolling_mean_28",
    "rolling_sum_7",
    "rolling_sum_14",
    "rolling_sum_28",
    "rolling_std_7",
    "rolling_std_14",
    "rolling_std_28",
    # Trend Dynamics
    "days_since_last_sale",
    "demand_trend_ratio_7_28",
    # Calendar & Cyclical
    "day_of_week",
    "day_of_month",
    "month",
    "quarter",
    "is_weekend",
    "day_of_week_sin",
    "day_of_week_cos",
    "month_sin",
    "month_cos",
    # Previous-Day Inventory (T - 1)
    "prev_day_closing_stock",
    "prev_day_opening_stock",
    "prev_day_units_received",
    "prev_day_stockout_flag",
    # Promotion Status
    "promotion_active",
    "promotion_discount_pct"
]

ALL_FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERICAL_FEATURES


def split_chronological_partitions(
    df: pd.DataFrame
) -> Dict[str, pd.DataFrame]:
    """
    Partitions the dataset chronologically into:
      - 'train': 2025-01-29 to 2025-09-30 (4,900 rows)
      - 'val':   2025-10-01 to 2025-11-15 (920 rows)
      - 'test':  2025-11-16 to 2025-12-31 (920 rows)
    """
    train_mask = (df["date"] >= TRAIN_START_DATE) & (df["date"] <= TRAIN_END_DATE)
    val_mask = (df["date"] >= VAL_START_DATE) & (df["date"] <= VAL_END_DATE)
    test_mask = (df["date"] >= TEST_START_DATE) & (df["date"] <= TEST_END_DATE)
    
    df_train = df[train_mask].copy().sort_values(["date", "product_id"]).reset_index(drop=True)
    df_val = df[val_mask].copy().sort_values(["date", "product_id"]).reset_index(drop=True)
    df_test = df[test_mask].copy().sort_values(["date", "product_id"]).reset_index(drop=True)
    
    # Assert exhaustive, non-overlapping coverage
    total_split = len(df_train) + len(df_val) + len(df_test)
    if total_split != len(df):
        raise ValueError(
            f"Chronological split mismatch! Input rows: {len(df)}, Sum of splits: {total_split}"
        )
        
    return {
        "train": df_train,
        "val": df_val,
        "test": df_test
    }


def extract_xy_and_censoring_mask(
    df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.Series, pd.Series, pd.DataFrame]:
    """
    Separates a partitioned DataFrame into:
      - X: predictor features only (ALL_FEATURE_COLUMNS)
      - y: target demand_units
      - is_censored: boolean stockout indicator
      - id_cols: metadata keys (product_id, date) for alignment tracking
    """
    for col in ALL_FEATURE_COLUMNS:
        if col not in df.columns:
            raise KeyError(f"Required predictor feature '{col}' missing from DataFrame!")
            
    if "demand_units" not in df.columns:
        raise KeyError("Target column 'demand_units' missing from DataFrame!")
        
    if "is_target_censored" not in df.columns:
        raise KeyError("Censoring indicator 'is_target_censored' missing from DataFrame!")
        
    X = df[ALL_FEATURE_COLUMNS].copy()
    y = df["demand_units"].copy().astype(float)
    is_censored = df["is_target_censored"].copy().astype(bool)
    id_cols = df[["product_id", "date"]].copy()
    
    return X, y, is_censored, id_cols


def build_preprocessor_pipeline(
    scale_numeric: bool = True
) -> ColumnTransformer:
    """
    Constructs a ColumnTransformer that:
      - Encodes CATEGORICAL_FEATURES using OneHotEncoder(handle_unknown='ignore', sparse_output=False).
      - Applies StandardScaler to NUMERICAL_FEATURES if scale_numeric is True, else passthrough.
    """
    transformers = [
        (
            "cat",
            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            CATEGORICAL_FEATURES
        )
    ]
    
    if scale_numeric:
        transformers.append((
            "num",
            StandardScaler(),
            NUMERICAL_FEATURES
        ))
    else:
        transformers.append((
            "num",
            "passthrough",
            NUMERICAL_FEATURES
        ))
        
    preprocessor = ColumnTransformer(
        transformers=transformers,
        remainder="drop"
    )
    return preprocessor
