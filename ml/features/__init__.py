"""
Stage 10 Orchestrator and Facade Module.
Provides high-level APIs to execute feature extraction, validation, and generation.
"""

from typing import Dict, Any, Tuple
import pandas as pd
from ml.features.data_extractor import extract_stage10_source_data
from ml.features.feature_pipeline import build_stage10_feature_dataset
from ml.features.feature_validator import validate_feature_leakage_and_integrity
from ml.features.feature_reporter import save_stage10_artifacts, STAGE10_OUTPUT_DIR


def run_stage10_pipeline(dbname: str = None) -> Tuple[bool, pd.DataFrame, Dict[str, Any], Dict[str, str]]:
    """
    Executes the complete Stage 10 Feature Engineering pipeline:
      1. Extracts source tables using read-only transaction
      2. Generates calendar, lag, rolling, metadata, inventory, and promotion features
      3. Validates against target leakage and data integrity
      4. Saves all artifacts atomically under data/processed/stage10/
      
    Returns:
      (success, feature_df, audit_metrics, artifact_paths)
    """
    # 1. Extraction
    source_data = extract_stage10_source_data(dbname=dbname)
    
    # 2. Feature Building
    feat_df, audit_metrics = build_stage10_feature_dataset(source_data)
    
    # 3. Leakage & Integrity Validation
    is_valid, validation_errors = validate_feature_leakage_and_integrity(feat_df)
    if not is_valid:
        error_msg = "; ".join(validation_errors)
        raise ValueError(f"Stage 10 Validation Failed: {error_msg}")
        
    audit_metrics["leakage_validation_passed"] = True
    
    # 4. Save Artifacts Atomically
    saved_artifacts = save_stage10_artifacts(feat_df, audit_metrics)
    
    return True, feat_df, audit_metrics, saved_artifacts


def load_latest_stage10_artifacts() -> Dict[str, Any]:
    """
    Loads pre-generated Stage 10 artifacts if they exist on disk.
    """
    csv_path = STAGE10_OUTPUT_DIR / "daily_product_features.csv"
    meta_path = STAGE10_OUTPUT_DIR / "stage10_metadata.json"
    dict_path = STAGE10_OUTPUT_DIR / "feature_data_dictionary.csv"
    qual_path = STAGE10_OUTPUT_DIR / "feature_quality_summary.csv"
    
    if not csv_path.exists() or not meta_path.exists():
        return {"exists": False}
        
    import json
    with open(meta_path, "r") as f:
        metadata = json.load(f)
        
    df_preview = pd.read_csv(csv_path, nrows=50)
    df_dict = pd.read_csv(dict_path) if dict_path.exists() else pd.DataFrame()
    df_qual = pd.read_csv(qual_path) if qual_path.exists() else pd.DataFrame()
    
    return {
        "exists": True,
        "csv_path": str(csv_path),
        "parquet_path": str(STAGE10_OUTPUT_DIR / "daily_product_features.parquet"),
        "metadata": metadata,
        "preview_df": df_preview,
        "dictionary_df": df_dict,
        "quality_df": df_qual,
        "total_rows": metadata.get("metrics", {}).get("total_output_rows", 7300),
        "total_columns": metadata.get("metrics", {}).get("total_columns", 47)
    }
