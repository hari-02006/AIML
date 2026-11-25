"""
Stage 11 Model Trainer Module.
Orchestrates:
1. Expanding-window temporal cross-validation STRICTLY inside the training window (2025-01-29 to 2025-09-30).
2. Model selection on the Validation window (2025-10-01 to 2025-11-15).
3. The Approved Final Refitting Protocol:
   - Freeze the winning model architecture and hyperparameters.
   - Refit the complete Pipeline (preprocessor + model) using Training + Validation data (2025-01-29 to 2025-11-15).
   - Evaluate the refitted model and deterministic baselines on the Final Test window (2025-11-16 to 2025-12-31) exactly once.
"""

import datetime
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone

from ml.forecasting.preprocessor import (
    split_chronological_partitions,
    extract_xy_and_censoring_mask,
    TRAIN_START_DATE,
    TRAIN_END_DATE,
    VAL_START_DATE,
    VAL_END_DATE,
    TEST_START_DATE,
    TEST_END_DATE
)
from ml.forecasting.baseline_models import get_all_baseline_models
from ml.forecasting.classical_models import get_all_classical_pipelines
from ml.forecasting.model_evaluator import calculate_metrics, evaluate_forecasts_with_censoring


def generate_expanding_window_cv_folds(
    df_train: pd.DataFrame,
    n_folds: int = 3
) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
    """
    Generates expanding-window temporal folds strictly inside the training period (2025-01-29 to 2025-09-30).
    Ensures all folds respect chronological sequence:
      Train fold: [start_date, cutoff_date]
      Eval fold:  (cutoff_date, cutoff_date + window]
    No validation or test dates are EVER touched.
    """
    dates = sorted(df_train["date"].unique())
    total_days = len(dates)
    
    # Require at least 100 days for minimal training
    min_train_days = 120
    remaining_days = total_days - min_train_days
    fold_step = remaining_days // n_folds
    
    folds = []
    for f in range(n_folds):
        train_end_idx = min_train_days + f * fold_step
        eval_end_idx = train_end_idx + fold_step if f < n_folds - 1 else total_days
        
        train_dates = set(dates[:train_end_idx])
        eval_dates = set(dates[train_end_idx:eval_end_idx])
        
        fold_train = df_train[df_train["date"].isin(train_dates)].copy()
        fold_eval = df_train[df_train["date"].isin(eval_dates)].copy()
        
        folds.append((fold_train, fold_eval))
        
    return folds


def perform_temporal_cross_validation(
    df_train: pd.DataFrame,
    candidate_pipelines: Dict[str, BaseEstimator],
    n_folds: int = 3
) -> Dict[str, Dict[str, Any]]:
    """
    Runs expanding-window cross validation on candidate models inside df_train.
    Trains only on uncensored observations; evaluates on uncensored evaluation fold observations.
    """
    folds = generate_expanding_window_cv_folds(df_train, n_folds=n_folds)
    cv_results = {}
    
    for name, pipeline in candidate_pipelines.items():
        fold_mae = []
        fold_wape = []
        fold_rmse = []
        
        for fold_idx, (f_train, f_eval) in enumerate(folds):
            # Extract features and censoring masks
            X_tr, y_tr, cens_tr, _ = extract_xy_and_censoring_mask(f_train)
            X_ev, y_ev, cens_ev, _ = extract_xy_and_censoring_mask(f_eval)
            
            # Train only on uncensored rows
            uncens_mask = ~cens_tr
            model_clone = clone(pipeline)
            model_clone.fit(X_tr[uncens_mask], y_tr[uncens_mask])
            
            # Predict evaluation fold
            preds = model_clone.predict(X_ev)
            
            # Evaluate on uncensored eval fold
            ev_uncens = ~cens_ev
            metrics = calculate_metrics(y_ev[ev_uncens], preds[ev_uncens])
            fold_mae.append(metrics["mae"])
            fold_rmse.append(metrics["rmse"])
            if not np.isnan(metrics["wape"]):
                fold_wape.append(metrics["wape"])
                
        cv_results[name] = {
            "mean_cv_mae": round(float(np.mean(fold_mae)), 4),
            "mean_cv_rmse": round(float(np.mean(fold_rmse)), 4),
            "mean_cv_wape": round(float(np.mean(fold_wape)), 4) if fold_wape else np.nan,
            "folds_evaluated": len(folds)
        }
        
    return cv_results


def evaluate_models_on_validation_set(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    models: Dict[str, BaseEstimator]
) -> Tuple[str, Dict[str, Any], Dict[str, BaseEstimator]]:
    """
    Fits models on uncensored training data (2025-01-29 to 2025-09-30).
    Evaluates on Validation data (2025-10-01 to 2025-11-15).
    Selects the best performing model according to uncensored Validation MAE.
    """
    X_tr, y_tr, cens_tr, _ = extract_xy_and_censoring_mask(df_train)
    X_va, y_va, cens_va, _ = extract_xy_and_censoring_mask(df_val)
    
    uncens_tr = ~cens_tr
    val_results = {}
    fitted_models = {}
    
    best_model_name = None
    lowest_val_mae = float("inf")
    
    for name, model in models.items():
        fitted = clone(model)
        # Train on uncensored training set
        fitted.fit(X_tr[uncens_tr], y_tr[uncens_tr])
        fitted_models[name] = fitted
        
        # Predict validation set
        preds = fitted.predict(X_va)
        
        # Comprehensive evaluation with censoring breakdown
        eval_metrics = evaluate_forecasts_with_censoring(y_va, preds, cens_va)
        val_results[name] = eval_metrics
        
        # Selection criterion: lowest uncensored MAE on validation set
        uncens_mae = eval_metrics["uncensored"]["mae"]
        if uncens_mae < lowest_val_mae:
            lowest_val_mae = uncens_mae
            best_model_name = name
            
    selection_summary = {
        "best_model_name": best_model_name,
        "best_val_uncensored_mae": lowest_val_mae,
        "validation_metrics_all": val_results
    }
    
    return best_model_name, selection_summary, fitted_models


def execute_final_refitting_protocol(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    df_test: pd.DataFrame,
    selected_model_name: str,
    candidate_models: Dict[str, BaseEstimator]
) -> Tuple[BaseEstimator, pd.DataFrame, Dict[str, Any]]:
    """
    Executes the Approved Final Model Refitting Protocol:
      1. Freezes selected model architecture.
      2. Refits complete preprocessing & model pipeline on Training + Validation data (2025-01-29 to 2025-11-15).
      3. Evaluates finalized refitted model and deterministic baselines on the Final Test set exactly once.
      4. Compiles final test predictions DataFrame with product_id, date, actual, predicted, and censoring flags.
    """
    # Combine Train and Validation
    df_train_val = pd.concat([df_train, df_val], ignore_index=True).sort_values(["date", "product_id"]).reset_index(drop=True)
    
    X_tr_val, y_tr_val, cens_tr_val, _ = extract_xy_and_censoring_mask(df_train_val)
    X_te, y_te, cens_te, id_te = extract_xy_and_censoring_mask(df_test)
    
    uncens_tr_val = ~cens_tr_val
    
    # 1. Refit finalized winning model
    winning_blueprint = candidate_models[selected_model_name]
    final_model = clone(winning_blueprint)
    final_model.fit(X_tr_val[uncens_tr_val], y_tr_val[uncens_tr_val])
    
    # 2. Generate final test predictions
    final_test_preds = final_model.predict(X_te)
    
    # 3. Compile predictions dataframe
    df_preds = id_te.copy()
    df_preds["actual_demand"] = y_te.to_numpy(dtype=float)
    df_preds["predicted_demand"] = np.round(final_test_preds, 2)
    df_preds["absolute_error"] = np.round(np.abs(df_preds["actual_demand"] - df_preds["predicted_demand"]), 2)
    df_preds["is_target_censored"] = cens_te.to_numpy(dtype=bool)
    df_preds["model_name"] = selected_model_name
    
    # 4. Evaluate finalized model on test set
    test_eval_summary = {}
    test_eval_summary[selected_model_name] = evaluate_forecasts_with_censoring(y_te, final_test_preds, cens_te)
    
    # 5. Also evaluate deterministic baselines on test set under the exact same policy
    baselines = get_all_baseline_models()
    for b_name, b_model in baselines.items():
        b_preds = b_model.predict(X_te)
        test_eval_summary[b_name] = evaluate_forecasts_with_censoring(y_te, b_preds, cens_te)
        
    return final_model, df_preds, test_eval_summary
