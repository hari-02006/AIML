"""
Configuration loader for inventory decision engine.
Loads YAML configuration files located in the project's `config/` directory.
If a file is missing, returns an empty dict and records a MISSING flag.
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Tuple

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

def _load_yaml(file_name: str) -> Tuple[Dict, bool]:
    """Load a YAML file.
    Returns a tuple of (data_dict, missing_flag).
    If the file does not exist, returns ({}, True).
    """
    path = CONFIG_DIR / file_name
    if not path.is_file():
        return {}, True
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data, False
    except Exception as exc:  # pragma: no cover
        # If parsing fails, treat as missing for safety.
        return {}, True

def load_product_supplier_map() -> Tuple[Dict, bool]:
    """Load `product_supplier_map.yaml`.
    Returns (mapping_dict, missing_flag).
    """
    return _load_yaml("product_supplier_map.yaml")

def load_supplier_lead_time() -> Tuple[Dict, bool]:
    """Load `supplier_lead_time.yaml`.
    Returns (lead_time_dict, missing_flag).
    """
    return _load_yaml("supplier_lead_time.yaml")

def load_safety_stock() -> Tuple[Dict, bool]:
    """Load `safety_stock.yaml`.
    Returns (safety_stock_dict, missing_flag).
    """
    return _load_yaml("safety_stock.yaml")
