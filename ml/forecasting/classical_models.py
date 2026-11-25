"""
Stage 11 Classical Machine Learning Models Module.
Builds full scikit-learn Pipeline factories for:
1. Ridge Regression (L2 linear model with standardized features).
2. Random Forest Regressor (ensemble of decision trees).
3. HistGradientBoosting Regressor (histogram-based gradient boosting).

Safeguards:
- Complete end-to-end Pipeline encapsulation (Preprocessor + Estimator).
- All predictions clipped to non-negative floats (np.maximum(0.0, preds)).
- Reproducible random_state everywhere.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.pipeline import Pipeline
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from ml.forecasting.preprocessor import build_preprocessor_pipeline


class NonNegativeRegressorWrapper(BaseEstimator, RegressorMixin):
    """
    Wraps any base regressor to guarantee that predictions are clipped at 0 (non-negative).
    """
    def __init__(self, base_estimator: BaseEstimator):
        self.base_estimator = base_estimator

    def fit(self, X, y, **fit_params):
        self.base_estimator.fit(X, y, **fit_params)
        # Required by sklearn check_is_fitted: marks this wrapper as fitted.
        self.is_fitted_ = True
        return self

    def predict(self, X) -> np.ndarray:
        raw_preds = self.base_estimator.predict(X)
        return np.maximum(0.0, np.asarray(raw_preds, dtype=float))


def build_ridge_pipeline(
    alpha: float = 10.0,
    random_state: int = 42
) -> Pipeline:
    """
    Constructs a Pipeline with ColumnTransformer (OneHotEncoder + StandardScaler)
    and L2 regularized Ridge regression.
    """
    preprocessor = build_preprocessor_pipeline(scale_numeric=True)
    ridge = Ridge(alpha=alpha, random_state=random_state)
    wrapped = NonNegativeRegressorWrapper(base_estimator=ridge)
    
    return Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("regressor", wrapped)
    ])


def build_random_forest_pipeline(
    n_estimators: int = 100,
    max_depth: Optional[int] = 12,
    min_samples_leaf: int = 5,
    random_state: int = 42
) -> Pipeline:
    """
    Constructs a Pipeline with ColumnTransformer (OneHotEncoder + Passthrough)
    and RandomForestRegressor.
    """
    preprocessor = build_preprocessor_pipeline(scale_numeric=False)
    rf = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        n_jobs=-1,
        random_state=random_state
    )
    wrapped = NonNegativeRegressorWrapper(base_estimator=rf)
    
    return Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("regressor", wrapped)
    ])


def build_hist_gradient_boosting_pipeline(
    max_iter: int = 150,
    max_depth: Optional[int] = 8,
    learning_rate: float = 0.05,
    min_samples_leaf: int = 20,
    l2_regularization: float = 1.0,
    random_state: int = 42
) -> Pipeline:
    """
    Constructs a Pipeline with ColumnTransformer (OneHotEncoder + Passthrough)
    and HistGradientBoostingRegressor.
    """
    preprocessor = build_preprocessor_pipeline(scale_numeric=False)
    hgb = HistGradientBoostingRegressor(
        max_iter=max_iter,
        max_depth=max_depth,
        learning_rate=learning_rate,
        min_samples_leaf=min_samples_leaf,
        l2_regularization=l2_regularization,
        random_state=random_state
    )
    wrapped = NonNegativeRegressorWrapper(base_estimator=hgb)
    
    return Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("regressor", wrapped)
    ])


def get_all_classical_pipelines(random_state: int = 42) -> Dict[str, Pipeline]:
    """Returns candidate classical ML regression pipelines."""
    return {
        "ridge_regression": build_ridge_pipeline(alpha=10.0, random_state=random_state),
        "random_forest": build_random_forest_pipeline(n_estimators=100, max_depth=12, random_state=random_state),
        "hist_gradient_boosting": build_hist_gradient_boosting_pipeline(max_iter=150, random_state=random_state)
    }
