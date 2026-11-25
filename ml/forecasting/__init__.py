"""
Stage 11 Forecasting Package Root.
Exposes:
- run_stage11_pipeline: end-to-end forecasting pipeline runner.
- load_best_forecasting_model: helper to load serialized joblib model.
"""

from pathlib import Path
from typing import Any, Tuple, Dict, Optional
import joblib
from ml.forecasting.forecast_pipeline import run_stage11_pipeline, STAGE11_OUTPUT_DIR


def load_best_forecasting_model(model_path: Optional[Path] = None) -> Any:
    """Loads the serialized winning Stage 11 forecasting model."""
    path = model_path or (STAGE11_OUTPUT_DIR / "best_forecasting_model.joblib")
    if not path.exists():
        raise FileNotFoundError(f"Best forecasting model not found at {path.resolve()}")
    return joblib.load(path)


__all__ = [
    "run_stage11_pipeline",
    "load_best_forecasting_model",
    "STAGE11_OUTPUT_DIR"
]
