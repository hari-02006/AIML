import os
import pandas as pd
import joblib
from pathlib import Path
from typing import Tuple, Dict

FEATURES_CSV = Path(__file__).resolve().parents[3] / "data" / "processed" / "stage10" / "daily_product_features.csv"
MODEL_PATH = Path(__file__).resolve().parents[3] / "data" / "processed" / "stage11" / "best_forecasting_model.joblib"

def load_features() -> pd.DataFrame:
    """Load the stage10 daily product features.
    Returns a DataFrame with at least columns:
    - product_id
    - date (feature date)
    - feature columns used by the model
    """
    return pd.read_csv(FEATURES_CSV)

def load_model() -> any:
    """Load the trained forecasting model.
    Returns the model object compatible with .predict().
    """
    return joblib.load(MODEL_PATH)

def generate_forecasts() -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Generate one‑day‑ahead forecasts for each product.
    Returns a tuple of (forecast_df, meta) where forecast_df has columns:
    - product_id
    - forecast_date (target date = feature_date + 1 day)
    - forecast_qty (predicted demand)
    The meta dict includes any notes about data windows.
    """
    features = load_features()
    model = load_model()
    # Ensure date column is datetime
    features = features.copy()
    features["date"] = pd.to_datetime(features["date"])
    # Predict using model (assumes model works directly on DataFrame without target column)
    # Drop non‑feature columns if present
    feature_cols = [c for c in features.columns if c not in ["product_id", "date"]]
    X = features[feature_cols]
    preds = model.predict(X)
    # Build forecast DataFrame
    forecast_df = pd.DataFrame({
        "product_id": features["product_id"],
        "forecast_date": features["date"] + pd.Timedelta(days=1),
        "forecast_qty": preds,
    })
    meta = {"generated_on": pd.Timestamp.now().isoformat(), "feature_rows": len(features)}
    return forecast_df, meta
