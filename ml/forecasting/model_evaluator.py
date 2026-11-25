"""
Stage 11 Model Evaluator Module.
Calculates standard and robust regression metrics:
1. MAE (Mean Absolute Error).
2. RMSE (Root Mean Squared Error).
3. WAPE (Weighted Absolute Percentage Error) with strict zero-denominator policy (returns np.nan).
4. MBE (Mean Bias Error).

Supports:
- Overall metrics.
- Subsetting by uncensored vs censored stockout observations.
- Per-product evaluations across all 20 products.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def calculate_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray
) -> Dict[str, Any]:
    """
    Computes MAE, RMSE, WAPE, and Mean Bias Error.
    
    WAPE Zero-Denominator Policy:
    If sum(y_true) == 0, returns np.nan instead of 0.0.
    """
    y_t = np.asarray(y_true, dtype=float)
    y_p = np.asarray(y_pred, dtype=float)
    
    n = len(y_t)
    if n == 0:
        return {
            "sample_count": 0,
            "mae": np.nan,
            "rmse": np.nan,
            "wape": np.nan,
            "mbe": np.nan
        }
        
    diff = y_p - y_t
    abs_diff = np.abs(diff)
    
    mae = float(np.mean(abs_diff))
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    mbe = float(np.mean(diff))
    
    sum_actual = float(np.sum(y_t))
    if sum_actual > 0.0:
        wape = float(np.sum(abs_diff) / sum_actual)
    else:
        # Zero-denominator policy: return NaN
        wape = np.nan
        
    return {
        "sample_count": n,
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wape": round(wape, 4) if not np.isnan(wape) else np.nan,
        "mbe": round(mbe, 4)
    }


def evaluate_forecasts_with_censoring(
    y_true: pd.Series,
    y_pred: np.ndarray,
    is_censored: pd.Series
) -> Dict[str, Dict[str, Any]]:
    """
    Evaluates predictions broken down by:
      - 'overall': all observations
      - 'uncensored': physical stock was available (primary benchmark)
      - 'censored': stock depleted to 0 during target date
    """
    y_t = y_true.to_numpy(dtype=float)
    y_p = np.asarray(y_pred, dtype=float)
    cens = is_censored.to_numpy(dtype=bool)
    
    overall_metrics = calculate_metrics(y_t, y_p)
    uncensored_metrics = calculate_metrics(y_t[~cens], y_p[~cens])
    censored_metrics = calculate_metrics(y_t[cens], y_p[cens])
    
    return {
        "overall": overall_metrics,
        "uncensored": uncensored_metrics,
        "censored": censored_metrics
    }


def evaluate_per_product_metrics(
    df_eval: pd.DataFrame,
    y_true_col: str = "actual_demand",
    y_pred_col: str = "predicted_demand",
    product_id_col: str = "product_id",
    censored_col: Optional[str] = "is_target_censored",
    uncensored_only: bool = True
) -> pd.DataFrame:
    """
    Calculates metrics for each product individually.
    Returns a DataFrame sorted by product_id.
    """
    df = df_eval.copy()
    if uncensored_only and censored_col and censored_col in df.columns:
        df = df[df[censored_col] == False].copy()
        
    records = []
    for pid, group in df.groupby(product_id_col):
        y_t = group[y_true_col].to_numpy(dtype=float)
        y_p = group[y_pred_col].to_numpy(dtype=float)
        m = calculate_metrics(y_t, y_p)
        records.append({
            "product_id": pid,
            "sample_count": m["sample_count"],
            "mae": m["mae"],
            "rmse": m["rmse"],
            "wape": m["wape"],
            "mbe": m["mbe"],
            "mean_actual": round(float(np.mean(y_t)), 2) if len(y_t) > 0 else 0.0,
            "mean_pred": round(float(np.mean(y_p)), 2) if len(y_p) > 0 else 0.0
        })
        
    return pd.DataFrame(records).sort_values("product_id").reset_index(drop=True)
