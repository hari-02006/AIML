"""
Stage 11 Forecasting Pipeline Orchestrator.
Coordinates:
1. Loading Stage 10 data and PostgreSQL stockout censoring mask.
2. Chronological splitting.
3. Expanding-window temporal CV strictly in Train.
4. Validation-based model selection.
5. Final Model Refitting on Train + Validation.
6. Single final evaluation on Test.
7. Atomic artifact generation (CSV, Parquet, Model Comparison Summary, Per-Product Metrics, JSON Metadata, Joblib Model).
"""

import datetime
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import joblib
import numpy as np
import pandas as pd

from ml.forecasting.data_loader import load_forecasting_dataset
from ml.forecasting.preprocessor import (
    split_chronological_partitions,
    TRAIN_START_DATE,
    TRAIN_END_DATE,
    VAL_START_DATE,
    VAL_END_DATE,
    TEST_START_DATE,
    TEST_END_DATE
)
from ml.forecasting.baseline_models import get_all_baseline_models
from ml.forecasting.classical_models import get_all_classical_pipelines
from ml.forecasting.model_trainer import (
    perform_temporal_cross_validation,
    evaluate_models_on_validation_set,
    execute_final_refitting_protocol
)
from ml.forecasting.model_evaluator import evaluate_per_product_metrics


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STAGE11_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "stage11"


def run_stage11_pipeline(
    dbname: Optional[str] = None,
    output_dir: Optional[Path] = None,
    random_state: int = 42
) -> Tuple[bool, Dict[str, Any], Dict[str, str]]:
    """
    Executes the complete Stage 11 Baseline & Classical ML Forecasting workflow.
    Returns:
      (success, summary_metrics, artifact_paths)
    """
    out_dir = output_dir or STAGE11_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Load Data & Stockout Mask
    df_forecasting, loader_metrics = load_forecasting_dataset(dbname=dbname, mature_only=True)
    
    # Step 2: Chronological Splitting
    splits = split_chronological_partitions(df_forecasting)
    df_train = splits["train"]
    df_val = splits["val"]
    df_test = splits["test"]
    
    # Step 3: Instantiate Baselines and Classical ML Pipelines
    baseline_models = get_all_baseline_models()
    classical_pipelines = get_all_classical_pipelines(random_state=random_state)
    all_candidate_models = {**baseline_models, **classical_pipelines}
    
    # Step 4: Temporal Cross-Validation strictly inside Training period
    cv_results = perform_temporal_cross_validation(
        df_train=df_train,
        candidate_pipelines=classical_pipelines,
        n_folds=3
    )
    
    # Step 5: Evaluate on Validation set & select winning model
    best_model_name, val_summary, _ = evaluate_models_on_validation_set(
        df_train=df_train,
        df_val=df_val,
        models=all_candidate_models
    )
    
    # Step 6: Final Refitting Protocol (Refit on Train + Val, Evaluate on Test)
    final_model, df_test_preds, test_summary = execute_final_refitting_protocol(
        df_train=df_train,
        df_val=df_val,
        df_test=df_test,
        selected_model_name=best_model_name,
        candidate_models=all_candidate_models
    )
    
    # Step 7: Calculate Per-Product Metrics on Test Set (Uncensored)
    df_per_product = evaluate_per_product_metrics(
        df_eval=df_test_preds,
        y_true_col="actual_demand",
        y_pred_col="predicted_demand",
        product_id_col="product_id",
        censored_col="is_target_censored",
        uncensored_only=True
    )
    
    # Step 8: Build Model Comparison Summary DataFrame
    summary_rows = []
    for model_name, eval_dict in test_summary.items():
        uncens = eval_dict["uncensored"]
        overall = eval_dict["overall"]
        val_uncens = val_summary["validation_metrics_all"].get(model_name, {}).get("uncensored", {})
        cv_res = cv_results.get(model_name, {})
        
        summary_rows.append({
            "model_name": model_name,
            "model_type": "classical_ml" if model_name in classical_pipelines else "deterministic_baseline",
            "is_selected_model": bool(model_name == best_model_name),
            "cv_mae": cv_res.get("mean_cv_mae", np.nan),
            "val_mae": val_uncens.get("mae", np.nan),
            "val_wape": val_uncens.get("wape", np.nan),
            "test_mae_uncensored": uncens.get("mae", np.nan),
            "test_rmse_uncensored": uncens.get("rmse", np.nan),
            "test_wape_uncensored": uncens.get("wape", np.nan),
            "test_bias_uncensored": uncens.get("mbe", np.nan),
            "test_mae_overall": overall.get("mae", np.nan),
            "test_sample_count": uncens.get("sample_count", 0)
        })
    df_model_comparison = pd.DataFrame(summary_rows).sort_values("test_mae_uncensored").reset_index(drop=True)
    
    # Step 9: Atomic Serialization of Artifacts
    csv_preds_path = out_dir / "test_predictions.csv"
    pq_preds_path = out_dir / "test_predictions.parquet"
    summary_csv_path = out_dir / "model_comparison_summary.csv"
    product_csv_path = out_dir / "per_product_metrics.csv"
    model_joblib_path = out_dir / "best_forecasting_model.joblib"
    meta_json_path = out_dir / "stage11_metadata.json"
    
    # Write Predictions
    df_test_preds.to_csv(csv_preds_path, index=False)
    df_test_preds.to_parquet(pq_preds_path, index=False)
    
    # Write Summaries
    df_model_comparison.to_csv(summary_csv_path, index=False)
    df_per_product.to_csv(product_csv_path, index=False)
    
    # Serialize winning model
    joblib.dump(final_model, model_joblib_path)
    
    # Serialize Metadata
    metadata = {
        "stage": "Stage 11: Baseline & Classical ML Demand Forecasting",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "loader_metrics": loader_metrics,
        "chronological_partitions": {
            "training_period": f"{TRAIN_START_DATE} to {TRAIN_END_DATE} ({len(df_train)} rows)",
            "validation_period": f"{VAL_START_DATE} to {VAL_END_DATE} ({len(df_val)} rows)",
            "final_test_period": f"{TEST_START_DATE} to {TEST_END_DATE} ({len(df_test)} rows)"
        },
        "selected_model": {
            "model_name": best_model_name,
            "validation_uncensored_mae": val_summary["best_val_uncensored_mae"],
            "test_uncensored_mae": float(df_model_comparison[df_model_comparison["is_selected_model"]]["test_mae_uncensored"].iloc[0]),
            "test_uncensored_wape": float(df_model_comparison[df_model_comparison["is_selected_model"]]["test_wape_uncensored"].iloc[0])
        },
        "refitting_protocol": (
            "Model selected via Validation period (2025-10-01 to 2025-11-15). "
            "Pipeline refitted on combined Training + Validation data (2025-01-29 to 2025-11-15). "
            "Evaluated on Final Test data (2025-11-16 to 2025-12-31) exactly once."
        ),
        "artifacts": {
            "test_predictions_csv": str(csv_preds_path.resolve()),
            "test_predictions_parquet": str(pq_preds_path.resolve()),
            "model_comparison_summary_csv": str(summary_csv_path.resolve()),
            "per_product_metrics_csv": str(product_csv_path.resolve()),
            "best_forecasting_model_joblib": str(model_joblib_path.resolve()),
            "metadata_json": str(meta_json_path.resolve())
        }
    }
    with open(meta_json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        
    artifacts = {
        "predictions_csv": str(csv_preds_path.resolve()),
        "predictions_parquet": str(pq_preds_path.resolve()),
        "model_comparison": str(summary_csv_path.resolve()),
        "per_product_metrics": str(product_csv_path.resolve()),
        "model_file": str(model_joblib_path.resolve()),
        "metadata_json": str(meta_json_path.resolve())
    }
    
    return True, metadata, artifacts
