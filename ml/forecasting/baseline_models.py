"""
Stage 11 Baseline Models Module.
Deterministic, heuristic benchmarks for daily product demand forecasting:
1. Naive Baseline (predicts yesterday's demand using demand_lag_1).
2. Seasonal Naive Baseline (predicts same day of preceding week using demand_lag_7).
3. Moving Average 7-Day Baseline (predicts rolling_mean_7).
4. Moving Average 28-Day Baseline (predicts rolling_mean_28).

All models follow standard scikit-learn estimator interface (fit/predict).
Predictions are guaranteed non-negative.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin


class NaiveForecast(BaseEstimator, RegressorMixin):
    """
    Naive baseline forecasting model.
    Predicts demand at T+1 using the most recent available demand (demand_lag_1 from row T+1).
    """
    def __init__(self, lag_col: str = "demand_lag_1"):
        self.lag_col = lag_col
        self.name = "Naive (Lag 1)"

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None):
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.lag_col not in X.columns:
            raise KeyError(f"Required lag column '{self.lag_col}' not found in X!")
        preds = X[self.lag_col].fillna(0.0).to_numpy(dtype=float)
        return np.maximum(0.0, preds)


class SeasonalNaiveForecast(BaseEstimator, RegressorMixin):
    """
    Seasonal Naive baseline forecasting model.
    Predicts demand at T+1 using demand from the same weekday in the previous week (demand_lag_7).
    """
    def __init__(self, lag_col: str = "demand_lag_7"):
        self.lag_col = lag_col
        self.name = "Seasonal Naive (Lag 7)"

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None):
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.lag_col not in X.columns:
            raise KeyError(f"Required lag column '{self.lag_col}' not found in X!")
        preds = X[self.lag_col].fillna(0.0).to_numpy(dtype=float)
        return np.maximum(0.0, preds)


class MovingAverage7Forecast(BaseEstimator, RegressorMixin):
    """
    7-Day Moving Average baseline model.
    Predicts demand at T+1 using the 7-day trailing moving average (rolling_mean_7).
    """
    def __init__(self, rolling_col: str = "rolling_mean_7"):
        self.rolling_col = rolling_col
        self.name = "Moving Average (7-Day)"

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None):
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.rolling_col not in X.columns:
            raise KeyError(f"Required rolling column '{self.rolling_col}' not found in X!")
        preds = X[self.rolling_col].fillna(0.0).to_numpy(dtype=float)
        return np.maximum(0.0, preds)


class MovingAverage28Forecast(BaseEstimator, RegressorMixin):
    """
    28-Day Moving Average baseline model.
    Predicts demand at T+1 using the 28-day trailing moving average (rolling_mean_28).
    """
    def __init__(self, rolling_col: str = "rolling_mean_28"):
        self.rolling_col = rolling_col
        self.name = "Moving Average (28-Day)"

    def fit(self, X: pd.DataFrame, y: Optional[pd.Series] = None):
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.rolling_col not in X.columns:
            raise KeyError(f"Required rolling column '{self.rolling_col}' not found in X!")
        preds = X[self.rolling_col].fillna(0.0).to_numpy(dtype=float)
        return np.maximum(0.0, preds)


def get_all_baseline_models() -> Dict[str, BaseEstimator]:
    """Returns a dictionary of all standard baseline models."""
    return {
        "naive_lag_1": NaiveForecast(),
        "seasonal_naive_lag_7": SeasonalNaiveForecast(),
        "moving_average_7d": MovingAverage7Forecast(),
        "moving_average_28d": MovingAverage28Forecast()
    }
