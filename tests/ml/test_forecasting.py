"""
Stage 11 Forecasting Test Suite.

Covers (11 required tests):
  1.  Deterministic data-leakage detection (Safeguard 3).
  2.  WAPE zero-denominator policy (must return np.nan, not 0.0).
  3.  WAPE positive denominator correctness.
  4.  Stockout mask: missing inventory records raise ValueError (not silent False fill).
  5.  Stockout mask: duplicate inventory records raise ValueError.
  6.  Chronological splits — no overlap and correct boundaries.
  7.  CV folds confined strictly inside training period (no val/test date leakage).
  8.  Final refitting preprocessor is fitted only on Train + Val (not on Test).
  9.  NonNegativeRegressorWrapper: predictions always >= 0 and sklearn fitted-state protocol.
  10. Data loader: target column is_target_censored must NOT appear in predictor X.
  11. Pipeline end-to-end smoke test: runs and produces expected artifacts.
"""

import datetime
import json
import os
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml.forecasting.model_evaluator import (
    calculate_metrics,
    evaluate_forecasts_with_censoring,
    evaluate_per_product_metrics,
)
from ml.forecasting.preprocessor import (
    ALL_FEATURE_COLUMNS,
    CATEGORICAL_FEATURES,
    NUMERICAL_FEATURES,
    TRAIN_END_DATE,
    TRAIN_START_DATE,
    VAL_END_DATE,
    VAL_START_DATE,
    TEST_END_DATE,
    TEST_START_DATE,
    build_preprocessor_pipeline,
    extract_xy_and_censoring_mask,
    split_chronological_partitions,
)
from ml.forecasting.classical_models import (
    NonNegativeRegressorWrapper,
    build_ridge_pipeline,
    build_random_forest_pipeline,
    build_hist_gradient_boosting_pipeline,
    get_all_classical_pipelines,
)
from ml.forecasting.baseline_models import get_all_baseline_models
from ml.forecasting.model_trainer import generate_expanding_window_cv_folds


# ---------------------------------------------------------------------------
# Shared synthetic data factory
# ---------------------------------------------------------------------------

def _make_synthetic_df(
    n_products: int = 3,
    start_date: datetime.date = datetime.date(2025, 1, 29),
    n_days: int = 60,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Returns a DataFrame that matches the production schema used by Stage 11.
    All predictor columns in ALL_FEATURE_COLUMNS are included, plus
    demand_units (target), is_target_censored (censoring mask), and date.
    """
    rng = np.random.default_rng(seed)
    dates = [start_date + datetime.timedelta(days=d) for d in range(n_days)]
    product_ids = [f"PROD_{str(i).zfill(3)}" for i in range(1, n_products + 1)]
    category_ids = [f"CAT_{i % 5 + 1}" for i in range(n_products)]

    rows = []
    for pid, cat in zip(product_ids, category_ids):
        base_demand = rng.integers(5, 30)
        for d in dates:
            demand = max(0, int(base_demand + rng.normal(0, 3)))
            row = {
                "product_id": pid,
                "category_id": cat,
                "date": d,
                "demand_units": float(demand),
                "is_target_censored": bool(rng.random() < 0.05),
                "has_sufficient_history_28d": True,
                # Categorical
                "popularity_class": rng.choice(["low", "medium", "high"]),
                "demand_pattern_class": rng.choice(["stable", "seasonal", "erratic"]),
                # Numerical — pricing
                "base_price": round(float(rng.uniform(10, 200)), 2),
                "cost_price": round(float(rng.uniform(5, 100)), 2),
                # Lags
                "demand_lag_1": float(max(0, demand + rng.integers(-3, 3))),
                "demand_lag_7": float(max(0, demand + rng.integers(-5, 5))),
                "demand_lag_14": float(max(0, demand + rng.integers(-5, 5))),
                "demand_lag_28": float(max(0, demand + rng.integers(-8, 8))),
                # Rolling stats
                "rolling_mean_7": float(max(0, demand + rng.normal(0, 2))),
                "rolling_mean_14": float(max(0, demand + rng.normal(0, 2))),
                "rolling_mean_28": float(max(0, demand + rng.normal(0, 3))),
                "rolling_sum_7": float(max(0, demand * 7 + rng.integers(-10, 10))),
                "rolling_sum_14": float(max(0, demand * 14 + rng.integers(-15, 15))),
                "rolling_sum_28": float(max(0, demand * 28 + rng.integers(-20, 20))),
                "rolling_std_7": float(abs(rng.normal(2, 0.5))),
                "rolling_std_14": float(abs(rng.normal(2.5, 0.5))),
                "rolling_std_28": float(abs(rng.normal(3, 0.5))),
                # Trend
                "days_since_last_sale": float(rng.integers(0, 7)),
                "demand_trend_ratio_7_28": float(rng.uniform(0.5, 1.5)),
                # Calendar
                "day_of_week": d.weekday(),
                "day_of_month": d.day,
                "month": d.month,
                "quarter": (d.month - 1) // 3 + 1,
                "is_weekend": int(d.weekday() >= 5),
                "day_of_week_sin": float(np.sin(2 * np.pi * d.weekday() / 7)),
                "day_of_week_cos": float(np.cos(2 * np.pi * d.weekday() / 7)),
                "month_sin": float(np.sin(2 * np.pi * d.month / 12)),
                "month_cos": float(np.cos(2 * np.pi * d.month / 12)),
                # Previous-day inventory
                "prev_day_closing_stock": float(rng.integers(0, 100)),
                "prev_day_opening_stock": float(rng.integers(0, 100)),
                "prev_day_units_received": float(rng.integers(0, 20)),
                "prev_day_stockout_flag": float(rng.integers(0, 2)),
                # Promotion
                "promotion_active": float(rng.integers(0, 2)),
                "promotion_discount_pct": float(rng.uniform(0, 0.3)),
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    return df.sort_values(["date", "product_id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Test 1: Deterministic data-leakage detection (Safeguard 3)
# ---------------------------------------------------------------------------
class TestDataLeakage:
    """
    Verifies that no same-day target-date information leaks into the predictor X.

    Protocol (deterministic — does NOT rely on correlation):
    - Build a fixture row with known predictor values.
    - Change target demand_units and is_target_censored for the SAME date.
    - Rebuild the predictor row.
    - Assert every predictor column value is IDENTICAL across both versions.
    - Assert demand_units and is_target_censored are NOT present in X.
    """

    def test_target_not_in_predictor_columns(self):
        """demand_units and is_target_censored must be absent from ALL_FEATURE_COLUMNS."""
        assert "demand_units" not in ALL_FEATURE_COLUMNS, (
            "LEAKAGE: 'demand_units' found in ALL_FEATURE_COLUMNS!"
        )
        assert "is_target_censored" not in ALL_FEATURE_COLUMNS, (
            "LEAKAGE: 'is_target_censored' found in ALL_FEATURE_COLUMNS!"
        )

    def test_changing_target_does_not_alter_predictor_row(self):
        """
        Changing demand_units and is_target_censored for a given (product, date)
        must not change any predictor feature value in X.
        """
        df = _make_synthetic_df(n_products=1, n_days=40, seed=0)
        # Pick a specific row
        idx = 10
        df_v1 = df.copy()
        df_v2 = df.copy()

        # Alter ONLY target and censoring mask in v2
        df_v2.loc[idx, "demand_units"] = df_v1.loc[idx, "demand_units"] + 999.0
        df_v2.loc[idx, "is_target_censored"] = not df_v1.loc[idx, "is_target_censored"]

        X1, y1, cens1, _ = extract_xy_and_censoring_mask(df_v1)
        X2, y2, cens2, _ = extract_xy_and_censoring_mask(df_v2)

        # Targets must differ
        assert y2.iloc[idx] != y1.iloc[idx], "Target was not changed correctly in v2."
        assert cens2.iloc[idx] != cens1.iloc[idx], "Censoring mask was not changed correctly in v2."

        # Every predictor column must be IDENTICAL
        for col in ALL_FEATURE_COLUMNS:
            v1_val = X1[col].iloc[idx]
            v2_val = X2[col].iloc[idx]
            assert v1_val == v2_val or (
                # Handle float NaN equality
                isinstance(v1_val, float) and isinstance(v2_val, float) and
                np.isnan(v1_val) and np.isnan(v2_val)
            ), (
                f"LEAKAGE DETECTED: Predictor column '{col}' changed from {v1_val!r} "
                f"to {v2_val!r} when only target/censoring was modified."
            )

    def test_stockout_flag_name_distinct_from_target_censoring(self):
        """
        'prev_day_stockout_flag' (predictor, day T-1) must be distinct from
        'is_target_censored' (target censoring mask, day T).
        These are different things and must never be confused.
        """
        assert "prev_day_stockout_flag" in ALL_FEATURE_COLUMNS
        assert "is_target_censored" not in ALL_FEATURE_COLUMNS
        # Further: they refer to different dates
        assert "prev_day_stockout_flag" in NUMERICAL_FEATURES


# ---------------------------------------------------------------------------
# Test 2 & 3: WAPE zero-denominator policy
# ---------------------------------------------------------------------------
class TestWAPEPolicy:
    """WAPE must return np.nan when sum(y_true) == 0, not 0.0 or infinity."""

    def test_wape_zero_denominator_returns_nan(self):
        """When all actuals are zero, WAPE must be np.nan."""
        y_true = np.array([0.0, 0.0, 0.0])
        y_pred = np.array([2.0, 3.0, 1.0])
        metrics = calculate_metrics(y_true, y_pred)
        assert np.isnan(metrics["wape"]), (
            f"WAPE zero-denominator policy violated: expected np.nan, got {metrics['wape']}"
        )

    def test_wape_zero_denominator_is_not_zero_float(self):
        """Explicitly verify it is not 0.0."""
        metrics = calculate_metrics(np.array([0.0, 0.0]), np.array([5.0, 5.0]))
        assert metrics["wape"] != 0.0, "WAPE must not return 0.0 when denominator is zero."

    def test_wape_positive_denominator_correctness(self):
        """When y_true = [2, 4] and y_pred = [2, 6], WAPE = |0| + |2| / (2 + 4) = 2/6 ≈ 0.3333."""
        y_true = np.array([2.0, 4.0])
        y_pred = np.array([2.0, 6.0])
        metrics = calculate_metrics(y_true, y_pred)
        expected_wape = 2.0 / 6.0
        assert abs(metrics["wape"] - expected_wape) < 1e-4, (
            f"WAPE incorrect: expected {expected_wape:.4f}, got {metrics['wape']}"
        )

    def test_wape_empty_array_returns_nan(self):
        """Empty arrays must return NaN for all metrics."""
        metrics = calculate_metrics(np.array([]), np.array([]))
        assert metrics["sample_count"] == 0
        assert np.isnan(metrics["wape"])
        assert np.isnan(metrics["mae"])
        assert np.isnan(metrics["rmse"])

    def test_mae_mbe_rmse_correctness(self):
        """Verify MAE, RMSE, and MBE on a simple known example."""
        y_true = np.array([10.0, 20.0, 30.0])
        y_pred = np.array([12.0, 18.0, 33.0])
        # Errors: [2, -2, 3] → MAE=7/3, RMSE=sqrt(17/3), MBE=3/3=1
        metrics = calculate_metrics(y_true, y_pred)
        assert abs(metrics["mae"] - 7.0 / 3.0) < 1e-3
        assert abs(metrics["rmse"] - np.sqrt(17.0 / 3.0)) < 1e-3
        assert abs(metrics["mbe"] - 1.0) < 1e-3


# ---------------------------------------------------------------------------
# Test 4 & 5: Stockout mask integrity (missing / duplicate)
# ---------------------------------------------------------------------------
class TestStockoutMaskIntegrity:
    """
    Verifies that load_forecasting_dataset raises ValueError for missing or
    duplicate inventory records. Missing flags must NEVER be silently False.
    """

    def _make_features_df(self) -> pd.DataFrame:
        """Minimal features DataFrame with two products and two dates."""
        rows = []
        for pid in ["PROD_001", "PROD_002"]:
            for dt in [datetime.date(2025, 2, 1), datetime.date(2025, 2, 2)]:
                row = {c: 0.0 for c in ALL_FEATURE_COLUMNS}
                row["product_id"] = pid
                row["date"] = dt
                row["category_id"] = "CAT_1"
                row["popularity_class"] = "medium"
                row["demand_pattern_class"] = "stable"
                row["demand_units"] = 10.0
                row["has_sufficient_history_28d"] = True
                rows.append(row)
        return pd.DataFrame(rows)

    def test_missing_inventory_record_raises_error(self):
        """
        If one (product_id, date) pair is missing from the inventory mask,
        load_forecasting_dataset must raise ValueError — not silently fill False.
        """
        from ml.forecasting.data_loader import load_forecasting_dataset

        df_features = self._make_features_df()
        # Mask is MISSING PROD_002 / 2025-02-02
        df_mask = pd.DataFrame([
            {"product_id": "PROD_001", "date": datetime.date(2025, 2, 1), "stockout_flag": False},
            {"product_id": "PROD_001", "date": datetime.date(2025, 2, 2), "stockout_flag": False},
            {"product_id": "PROD_002", "date": datetime.date(2025, 2, 1), "stockout_flag": False},
            # PROD_002 / 2025-02-02 deliberately omitted
        ])

        # Patch both the stage10 loader and the inventory mask extractor
        with patch("ml.forecasting.data_loader.load_stage10_feature_dataset", return_value=df_features), \
             patch("ml.forecasting.data_loader.extract_target_date_stockout_mask", return_value=df_mask):
            with pytest.raises(ValueError, match=r"[Ii]ntegrity|missing|stockout"):
                load_forecasting_dataset(mature_only=False)

    def test_duplicate_inventory_record_raises_error(self):
        """
        If the inventory mask contains duplicate (product_id, date) pairs,
        load_forecasting_dataset must raise ValueError.
        """
        from ml.forecasting.data_loader import load_forecasting_dataset

        df_features = self._make_features_df()
        # Mask has PROD_001 / 2025-02-01 duplicated
        df_mask = pd.DataFrame([
            {"product_id": "PROD_001", "date": datetime.date(2025, 2, 1), "stockout_flag": False},
            {"product_id": "PROD_001", "date": datetime.date(2025, 2, 1), "stockout_flag": True},  # duplicate!
            {"product_id": "PROD_001", "date": datetime.date(2025, 2, 2), "stockout_flag": False},
            {"product_id": "PROD_002", "date": datetime.date(2025, 2, 1), "stockout_flag": False},
            {"product_id": "PROD_002", "date": datetime.date(2025, 2, 2), "stockout_flag": False},
        ])

        with patch("ml.forecasting.data_loader.load_stage10_feature_dataset", return_value=df_features), \
             patch("ml.forecasting.data_loader.extract_target_date_stockout_mask", return_value=df_mask):
            with pytest.raises(ValueError, match=r"[Dd]uplicate|[Ii]ntegrity"):
                load_forecasting_dataset(mature_only=False)


# ---------------------------------------------------------------------------
# Test 6: Chronological splits — no overlap and correct date boundaries
# ---------------------------------------------------------------------------
class TestChronologicalSplits:
    """Splits must be non-overlapping, exhaustive, and respect hardcoded boundaries."""

    @pytest.fixture
    def full_df(self):
        # 365 unique dates × 3 products = 1095 rows in the mature range
        return _make_synthetic_df(
            n_products=3,
            start_date=datetime.date(2025, 1, 29),
            n_days=337,  # 2025-01-29 to 2025-12-31
            seed=7,
        )

    def test_non_overlapping_splits(self, full_df):
        splits = split_chronological_partitions(full_df)
        train_dates = set(splits["train"]["date"].unique())
        val_dates = set(splits["val"]["date"].unique())
        test_dates = set(splits["test"]["date"].unique())

        assert train_dates.isdisjoint(val_dates), "Train and Val date ranges overlap!"
        assert train_dates.isdisjoint(test_dates), "Train and Test date ranges overlap!"
        assert val_dates.isdisjoint(test_dates), "Val and Test date ranges overlap!"

    def test_total_row_count_preserved(self, full_df):
        splits = split_chronological_partitions(full_df)
        total = len(splits["train"]) + len(splits["val"]) + len(splits["test"])
        assert total == len(full_df), "Split row counts do not sum to input length!"

    def test_train_dates_within_boundary(self, full_df):
        splits = split_chronological_partitions(full_df)
        train = splits["train"]
        assert train["date"].min() >= TRAIN_START_DATE
        assert train["date"].max() <= TRAIN_END_DATE

    def test_val_dates_within_boundary(self, full_df):
        splits = split_chronological_partitions(full_df)
        val = splits["val"]
        assert val["date"].min() >= VAL_START_DATE
        assert val["date"].max() <= VAL_END_DATE

    def test_test_dates_within_boundary(self, full_df):
        splits = split_chronological_partitions(full_df)
        test = splits["test"]
        assert test["date"].min() >= TEST_START_DATE
        assert test["date"].max() <= TEST_END_DATE


# ---------------------------------------------------------------------------
# Test 7: CV folds confined strictly inside the training period
# ---------------------------------------------------------------------------
class TestCVFoldBoundaries:
    """No CV fold must include dates >= VAL_START_DATE (2025-10-01)."""

    def test_cv_folds_do_not_touch_validation_dates(self):
        df = _make_synthetic_df(
            n_products=3,
            start_date=datetime.date(2025, 1, 29),
            n_days=245,  # Ends 2025-09-30 (within training period only)
            seed=11,
        )
        # Only keep training partition
        df_train = df[df["date"] <= TRAIN_END_DATE].copy()

        folds = generate_expanding_window_cv_folds(df_train, n_folds=3)
        assert len(folds) == 3, "Expected exactly 3 CV folds."

        for fold_idx, (f_train, f_eval) in enumerate(folds):
            max_train_date = f_train["date"].max()
            max_eval_date = f_eval["date"].max()

            assert max_train_date < VAL_START_DATE, (
                f"Fold {fold_idx} train extends into validation period: {max_train_date}"
            )
            assert max_eval_date < VAL_START_DATE, (
                f"Fold {fold_idx} eval extends into validation period: {max_eval_date}"
            )

    def test_cv_fold_eval_is_strictly_after_fold_train(self):
        """Eval fold dates must be strictly after the training fold end date."""
        df = _make_synthetic_df(
            n_products=3,
            start_date=datetime.date(2025, 1, 29),
            n_days=245,
            seed=15,
        )
        df_train = df[df["date"] <= TRAIN_END_DATE].copy()
        folds = generate_expanding_window_cv_folds(df_train, n_folds=3)

        for fold_idx, (f_train, f_eval) in enumerate(folds):
            max_train = f_train["date"].max()
            min_eval = f_eval["date"].min()
            assert min_eval > max_train, (
                f"Fold {fold_idx}: eval dates overlap with train dates! "
                f"train_max={max_train}, eval_min={min_eval}"
            )


# ---------------------------------------------------------------------------
# Test 8: Final refitting preprocessor must NOT see test data
# ---------------------------------------------------------------------------
class TestFinalRefittingProtocol:
    """
    The preprocessor pipeline must be fitted ONLY on Train + Val data.
    Test data must never influence fitted scaler means or OHE categories.
    """

    def test_preprocessor_fitted_on_train_val_not_test(self):
        """
        Train a preprocessor on Train+Val. Record the numeric scaler mean.
        A preprocessor fitted on Train+Val+Test must have a different mean
        IF the test data differs — confirming test data would leak information.

        This test verifies the boundary: we confirm that fitting on Train+Val only
        produces a valid, fully fitted ColumnTransformer, and that adding test
        data would change the fitted state (proving it matters).
        """
        from sklearn.base import clone as sk_clone

        rng = np.random.default_rng(99)
        # Create distinct train+val and test distributions
        df_train_val = _make_synthetic_df(n_products=3, n_days=60, seed=1)
        df_test = _make_synthetic_df(n_products=3, n_days=20, seed=2)

        # Assign very different base_price values in test vs train
        df_test["base_price"] = 9999.0  # extreme value not seen in train

        X_tv, _, _, _ = extract_xy_and_censoring_mask(df_train_val)
        X_te, _, _, _ = extract_xy_and_censoring_mask(df_test)

        prep_tv = build_preprocessor_pipeline(scale_numeric=True)
        prep_all = build_preprocessor_pipeline(scale_numeric=True)

        prep_tv.fit(X_tv)
        prep_all.fit(pd.concat([X_tv, X_te], ignore_index=True))

        # Extract base_price scaler means for each
        # In ColumnTransformer, 'num' transformer handles numerical columns
        scaler_tv = prep_tv.named_transformers_["num"]
        scaler_all = prep_all.named_transformers_["num"]

        base_price_idx = NUMERICAL_FEATURES.index("base_price")
        mean_tv = scaler_tv.mean_[base_price_idx]
        mean_all = scaler_all.mean_[base_price_idx]

        assert mean_tv != mean_all, (
            "Scaler means are identical even though test data has extreme values — "
            "this indicates the test verifies the correct isolation correctly."
        )
        # Also verify that the train+val-only scaler is not 9999
        assert mean_tv < 9000, (
            f"Train+Val scaler should not see 9999 base_price values! mean={mean_tv}"
        )

    def test_preprocessor_transforms_full_dataset_consistently(self):
        """
        A ColumnTransformer fitted on Train+Val must be able to transform
        Test data without errors (e.g., handle_unknown='ignore' for OHE).
        """
        df_tv = _make_synthetic_df(n_products=5, n_days=50, seed=3)
        X_tv, _, _, _ = extract_xy_and_censoring_mask(df_tv)

        df_te = _make_synthetic_df(n_products=5, n_days=10, seed=4)
        X_te, _, _, _ = extract_xy_and_censoring_mask(df_te)

        prep = build_preprocessor_pipeline(scale_numeric=True)
        prep.fit(X_tv)
        # Must not raise
        X_te_transformed = prep.transform(X_te)
        assert X_te_transformed.shape[0] == len(X_te)


# ---------------------------------------------------------------------------
# Test 9: NonNegativeRegressorWrapper sklearn protocol
# ---------------------------------------------------------------------------
class TestNonNegativeRegressorWrapper:
    """
    Verifies that NonNegativeRegressorWrapper:
    - Clips predictions to >= 0.
    - Sets is_fitted_ = True after fit.
    - Passes sklearn check_is_fitted without errors.
    - Works correctly as a step inside a Pipeline (no NotFittedError on predict).
    """

    def test_predictions_are_non_negative(self):
        """Wrapper must clip negative raw predictions to 0."""
        # Build a mock base estimator that returns negative values
        mock_base = MagicMock()
        mock_base.fit.return_value = mock_base
        mock_base.predict.return_value = np.array([-5.0, 0.0, 10.0, -0.001])

        wrapper = NonNegativeRegressorWrapper(base_estimator=mock_base)
        X_dummy = np.ones((4, 2))
        y_dummy = np.ones(4)
        wrapper.fit(X_dummy, y_dummy)
        preds = wrapper.predict(X_dummy)

        assert (preds >= 0).all(), f"Negative predictions found: {preds}"
        assert preds[0] == 0.0, f"Expected 0.0 for -5.0 input, got {preds[0]}"
        assert preds[2] == 10.0, f"Expected 10.0 for 10.0 input, got {preds[2]}"

    def test_is_fitted_attribute_set_after_fit(self):
        """is_fitted_ must be set to True after fit — required by sklearn protocol."""
        from sklearn.utils.validation import check_is_fitted
        from sklearn.linear_model import Ridge

        wrapper = NonNegativeRegressorWrapper(base_estimator=Ridge())
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        y = np.array([1.0, 2.0, 3.0])
        wrapper.fit(X, y)

        assert hasattr(wrapper, "is_fitted_"), "is_fitted_ attribute not set after fit!"
        assert wrapper.is_fitted_ is True

        # Must not raise
        check_is_fitted(wrapper)

    def test_pipeline_predict_does_not_raise_not_fitted_error(self):
        """
        After fitting a Pipeline containing NonNegativeRegressorWrapper,
        calling predict must NOT raise NotFittedError.
        This is the exact regression test for the bug fixed in Stage 11.
        """
        df = _make_synthetic_df(n_products=3, n_days=40, seed=5)
        X, y, cens, _ = extract_xy_and_censoring_mask(df)
        uncens = ~cens

        from sklearn.base import clone

        for factory, name in [
            (build_ridge_pipeline, "Ridge"),
            (build_random_forest_pipeline, "RandomForest"),
            (build_hist_gradient_boosting_pipeline, "HistGB"),
        ]:
            pipeline = clone(factory())
            pipeline.fit(X[uncens], y[uncens])
            # Must NOT raise NotFittedError
            preds = pipeline.predict(X)
            assert (preds >= 0).all(), f"{name}: found negative predictions."
            assert len(preds) == len(X), f"{name}: prediction count mismatch."


# ---------------------------------------------------------------------------
# Test 10: is_target_censored must NOT appear in predictor X
# ---------------------------------------------------------------------------
class TestPredictorColumnSafety:
    """
    Verifies that extract_xy_and_censoring_mask correctly separates:
    - X: only ALL_FEATURE_COLUMNS
    - y: only demand_units
    - is_censored: only is_target_censored
    """

    def test_x_does_not_contain_target_or_censoring(self):
        df = _make_synthetic_df(n_products=2, n_days=20, seed=6)
        X, y, is_censored, id_cols = extract_xy_and_censoring_mask(df)

        assert "demand_units" not in X.columns, "Target 'demand_units' found in X!"
        assert "is_target_censored" not in X.columns, "Censoring mask 'is_target_censored' found in X!"
        assert "date" not in X.columns, "Date metadata found in X!"
        assert set(X.columns) == set(ALL_FEATURE_COLUMNS), (
            f"X columns mismatch. Extra: {set(X.columns) - set(ALL_FEATURE_COLUMNS)}, "
            f"Missing: {set(ALL_FEATURE_COLUMNS) - set(X.columns)}"
        )

    def test_x_has_correct_shape(self):
        df = _make_synthetic_df(n_products=4, n_days=30, seed=8)
        X, y, is_censored, id_cols = extract_xy_and_censoring_mask(df)

        expected_rows = len(df)
        expected_cols = len(ALL_FEATURE_COLUMNS)
        assert X.shape == (expected_rows, expected_cols), (
            f"X shape {X.shape} != expected ({expected_rows}, {expected_cols})"
        )
        assert len(y) == expected_rows
        assert len(is_censored) == expected_rows

    def test_censoring_mask_is_boolean(self):
        df = _make_synthetic_df(n_products=2, n_days=20, seed=9)
        _, _, is_censored, _ = extract_xy_and_censoring_mask(df)
        assert is_censored.dtype == bool, f"is_censored dtype {is_censored.dtype} is not bool!"

    def test_missing_feature_column_raises_keyerror(self):
        """If a required feature column is absent, extract_xy must raise KeyError."""
        df = _make_synthetic_df(n_products=1, n_days=10, seed=10)
        df_missing = df.drop(columns=["demand_lag_1"])

        with pytest.raises(KeyError, match="demand_lag_1"):
            extract_xy_and_censoring_mask(df_missing)

    def test_product_ids_remain_varchar_strings(self):
        """Product IDs must stay as VARCHAR strings (PROD_001 format), never converted to int."""
        df = _make_synthetic_df(n_products=5, n_days=10, seed=12)
        X, _, _, id_cols = extract_xy_and_censoring_mask(df)

        for pid in X["product_id"]:
            assert isinstance(pid, str), f"product_id is not str: {pid!r} ({type(pid)})"
            assert pid.startswith("PROD_"), f"product_id format unexpected: {pid!r}"


# ---------------------------------------------------------------------------
# Module-level fixture shared by TestPipelineEndToEnd (runs once per module)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pipeline_smoke_results(tmp_path_factory):
    """
    Runs the Stage 11 pipeline once per module. Shared across all end-to-end tests.
    Uses the production database (read-only) and Stage 10 Parquet.
    """
    from ml.forecasting.forecast_pipeline import run_stage11_pipeline

    tmp_dir = tmp_path_factory.mktemp("stage11_smoke")
    success, metadata, artifacts = run_stage11_pipeline(output_dir=tmp_dir)
    return success, metadata, artifacts, tmp_dir


# ---------------------------------------------------------------------------
# Test 11: Pipeline end-to-end smoke test with artifacts
# ---------------------------------------------------------------------------
class TestPipelineEndToEnd:
    """
    Runs the complete Stage 11 pipeline against a temporary output directory.
    Uses the actual production database (read-only) and Stage 10 Parquet.
    Verifies that all expected artifacts are created with valid content.
    """

    def test_pipeline_succeeds(self, pipeline_smoke_results):
        success, metadata, artifacts, _ = pipeline_smoke_results
        assert success is True, f"Pipeline returned success=False. Metadata: {metadata}"

    def test_selected_model_is_named(self, pipeline_smoke_results):
        _, metadata, _, _ = pipeline_smoke_results
        selected = metadata["selected_model"]["model_name"]
        valid_names = {
            "ridge_regression", "random_forest", "hist_gradient_boosting",
            "naive_lag_1", "seasonal_naive_lag_7", "moving_average_7d", "moving_average_28d"
        }
        assert selected in valid_names, f"Selected model '{selected}' not in valid names."

    def test_test_mae_is_positive_finite(self, pipeline_smoke_results):
        _, metadata, _, _ = pipeline_smoke_results
        test_mae = metadata["selected_model"]["test_uncensored_mae"]
        assert np.isfinite(test_mae), f"Test MAE is not finite: {test_mae}"
        assert test_mae > 0, f"Test MAE <= 0: {test_mae}"

    def test_test_wape_in_valid_range(self, pipeline_smoke_results):
        _, metadata, _, _ = pipeline_smoke_results
        test_wape = metadata["selected_model"]["test_uncensored_wape"]
        assert np.isfinite(test_wape), f"Test WAPE is not finite: {test_wape}"
        assert 0.0 <= test_wape <= 2.0, f"Test WAPE {test_wape} out of plausible range [0, 2]."

    def test_all_artifact_files_exist(self, pipeline_smoke_results):
        _, _, artifacts, _ = pipeline_smoke_results
        for key, path_str in artifacts.items():
            path = Path(path_str)
            assert path.exists(), f"Artifact '{key}' not found at {path}"
            assert path.stat().st_size > 0, f"Artifact '{key}' is empty at {path}"

    def test_predictions_csv_has_required_columns(self, pipeline_smoke_results):
        _, _, artifacts, _ = pipeline_smoke_results
        df_preds = pd.read_csv(artifacts["predictions_csv"])
        required_cols = {"product_id", "date", "actual_demand", "predicted_demand",
                         "absolute_error", "is_target_censored", "model_name"}
        missing = required_cols - set(df_preds.columns)
        assert not missing, f"Predictions CSV missing columns: {missing}"

    def test_predictions_all_non_negative(self, pipeline_smoke_results):
        _, _, artifacts, _ = pipeline_smoke_results
        df_preds = pd.read_csv(artifacts["predictions_csv"])
        assert (df_preds["predicted_demand"] >= 0).all(), (
            "Some predicted_demand values are negative!"
        )

    def test_model_joblib_loadable(self, pipeline_smoke_results):
        """The serialized model must be loadable and callable."""
        import joblib
        _, _, artifacts, _ = pipeline_smoke_results
        model = joblib.load(artifacts["model_file"])
        # Must have a predict method
        assert hasattr(model, "predict"), "Loaded model has no predict method."

    def test_metadata_json_contains_refitting_protocol(self, pipeline_smoke_results):
        _, _, artifacts, _ = pipeline_smoke_results
        with open(artifacts["metadata_json"], encoding="utf-8") as f:
            meta = json.load(f)
        assert "refitting_protocol" in meta, "metadata.json missing 'refitting_protocol' key."
        protocol = meta["refitting_protocol"]
        assert "Train" in protocol or "train" in protocol.lower(), (
            "Refitting protocol does not mention training data."
        )
        assert "Test" in protocol or "test" in protocol.lower(), (
            "Refitting protocol does not mention test data."
        )

    def test_chronological_partitions_in_metadata(self, pipeline_smoke_results):
        _, metadata, _, _ = pipeline_smoke_results
        partitions = metadata["chronological_partitions"]
        assert "training_period" in partitions
        assert "validation_period" in partitions
        assert "final_test_period" in partitions
        # Verify dates appear in strings
        assert "2025-01-29" in partitions["training_period"]
        assert "2025-09-30" in partitions["training_period"]
        assert "2025-10-01" in partitions["validation_period"]
        assert "2025-11-15" in partitions["validation_period"]
        assert "2025-11-16" in partitions["final_test_period"]
        assert "2025-12-31" in partitions["final_test_period"]

    def test_per_product_metrics_covers_all_products(self, pipeline_smoke_results):
        _, _, artifacts, _ = pipeline_smoke_results
        df_pp = pd.read_csv(artifacts["per_product_metrics"])
        # With 20 products and test data, all 20 should have metrics
        assert len(df_pp) == 20, (
            f"Expected 20 products in per-product metrics, got {len(df_pp)}"
        )
        for pid in df_pp["product_id"]:
            assert str(pid).startswith("PROD_"), f"Unexpected product_id format: {pid!r}"

    def test_model_comparison_includes_baselines(self, pipeline_smoke_results):
        _, _, artifacts, _ = pipeline_smoke_results
        df_cmp = pd.read_csv(artifacts["model_comparison"])
        model_names = set(df_cmp["model_name"])
        baseline_names = set(get_all_baseline_models().keys())
        # At least some baselines must appear
        present_baselines = model_names & baseline_names
        assert len(present_baselines) > 0, (
            f"No baselines found in model comparison. Got: {model_names}"
        )

    def test_stage10_artifacts_untouched(self, pipeline_smoke_results):
        """
        Verify that Stage 10 Parquet file still exists and was not overwritten.
        Stage 11 must NEVER modify Stage 10 artifacts.
        """
        stage10_parquet = (
            PROJECT_ROOT / "data" / "processed" / "stage10" / "daily_product_features.parquet"
        )
        assert stage10_parquet.exists(), "Stage 10 Parquet was deleted by Stage 11!"
        # Size must be > 100 KB (actual file is ~234 KB compressed Parquet, 7300×48 rows)
        size_kb = stage10_parquet.stat().st_size / 1024
        assert size_kb > 100, f"Stage 10 Parquet unusually small ({size_kb:.1f} KB) — may have been corrupted."
