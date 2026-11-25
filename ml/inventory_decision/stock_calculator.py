import pandas as pd
import os
from pathlib import Path
from typing import Dict, Tuple, List

# -------------------
# Project root resolver
# -------------------

def _resolve_project_root() -> Path:
    """Return the project root directory.
    Walks up from this file until a marker file (README.md or .git) is found.
    Raises RuntimeError if not found.
    """
    cur = Path(__file__).resolve()
    for _ in range(5):  # reasonable depth
        if (cur / "README.md").is_file() or (cur / ".git").is_dir():
            return cur
        cur = cur.parent
    raise RuntimeError("Project root marker (README.md or .git) not found")

# Resolve project root once
PROJECT_ROOT = _resolve_project_root()

# Path to inventory processed CSV – use two parents up from this module (ml/inventory_decision -> ml -> project root)
INVENTORY_CSV = PROJECT_ROOT / "data" / "processed" / "inventory_processed.csv"

# -------------------
# CSV loading and validation
# -------------------

REQUIRED_COLUMNS = {"product_id", "date", "closing_stock"}
UNIT_COLUMNS = {"unit", "stock_unit"}


def load_inventory() -> pd.DataFrame:
    """Load and validate the processed inventory CSV.
    Returns a DataFrame with a proper datetime ``date`` column.
    Performs exhaustive validation and raises descriptive errors.
    """
    if not INVENTORY_CSV.is_file():
        raise FileNotFoundError(f"Inventory file not found at {INVENTORY_CSV}")

    df = pd.read_csv(INVENTORY_CSV)
    if df.empty:
        raise ValueError("Inventory CSV is empty")

    # Verify required columns
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Inventory CSV missing required columns: {sorted(missing)}")

    # Check for unit column – at least one of the accepted names must exist
    if not UNIT_COLUMNS.intersection(df.columns):
        raise ValueError("Inventory CSV missing unit column (expected 'unit' or 'stock_unit')")
    # Normalize unit column name to 'unit'
    if "stock_unit" in df.columns:
        df = df.rename(columns={"stock_unit": "unit"})

    # Convert date column
    try:
        df["date"] = pd.to_datetime(df["date"], errors="raise")
    except Exception as exc:
        raise ValueError(f"Invalid date values in inventory CSV: {exc}")

    # Validate closing_stock numeric
    if not pd.api.types.is_numeric_dtype(df["closing_stock"]):
        raise ValueError("closing_stock column must be numeric")
    if (df["closing_stock"] < 0).any():
        raise ValueError("closing_stock contains negative values")

    # Detect duplicate (product_id, date) entries
    dup = df.duplicated(subset=["product_id", "date"], keep=False)
    if dup.any():
        dup_rows = df[dup]
        raise ValueError(f"Duplicate product_id/date rows detected: {dup_rows}")

    # Check for inconsistent units per product
    unit_map = df.groupby("product_id")['unit'].nunique()
    inconsistent = unit_map[unit_map > 1]
    if not inconsistent.empty:
        raise ValueError(
            f"Inconsistent unit definitions for products: {list(inconsistent.index)}"
        )

    return df

# -------------------
# Freshness calculation
# -------------------

INVENTORY_STALE_DAYS = 30


def compute_freshness(df: pd.DataFrame, as_of_date: pd.Timestamp) -> Tuple[Dict[str, bool], pd.Timestamp]:
    """Calculate per‑product freshness.
    Returns a dict mapping product_id → is_fresh and the most recent inventory date.
    A product is fresh if 0 ≤ age_days ≤ INVENTORY_STALE_DAYS.
    Future dates and missing dates are treated as not fresh.
    """
    if df.empty:
        raise ValueError("Inventory DataFrame is empty – cannot compute freshness")

    as_of = pd.to_datetime(as_of_date)
    freshness: Dict[str, bool] = {}
    latest_date = df['date'].max()

    for pid, grp in df.groupby('product_id'):
        # Use the latest date for this product
        last_date = grp['date'].max()
        if pd.isna(last_date):
            is_fresh = False
        else:
            age_days = (as_of - last_date).days
            is_fresh = 0 <= age_days <= INVENTORY_STALE_DAYS
        freshness[pid] = is_fresh

    return freshness, latest_date

# -------------------
# Physical stock retrieval
# -------------------

def _validate_confirmed_qty(qty) -> float:
    """Validate a manually confirmed quantity.
    Returns the float value if valid, otherwise raises ValueError.
    """
    if isinstance(qty, (int, float)):
        val = float(qty)
    else:
        raise ValueError("Manual stock count must be a numeric type")
    if pd.isna(val):
        raise ValueError("Manual stock count cannot be NaN")
    if val < 0:
        raise ValueError("Manual stock count cannot be negative")
    if pd.isinf(val):
        raise ValueError("Manual stock count cannot be infinite")
    return val


def get_physical_stock(df: pd.DataFrame, product_id: str, confirmed_qty: float = None, as_of_date: pd.Timestamp = None) -> Tuple[float, str]:
    """Return on‑hand stock for a product.
    If ``confirmed_qty`` is provided, it is validated and returned (overrides CSV).
    Otherwise the latest valid inventory row is used *only if it is fresh*.
    Returns (stock_quantity, unit).
    Raises ValueError with a clear blocker message when data is unavailable.
    """
    if as_of_date is None:
        as_of_date = pd.Timestamp.now()

    rec = df[df['product_id'] == product_id]
    if rec.empty:
        raise ValueError(f"NEEDS STOCK RECONCILIATION: product {product_id} missing from inventory data")

    unit = rec.iloc[0]['unit']  # unit column already normalized during load_inventory
    if confirmed_qty is not None:
        qty = _validate_confirmed_qty(confirmed_qty)
        return qty, unit

    # No manual count – use latest record
    latest_row = rec.loc[rec['date'].idxmax()]
    latest_date = latest_row['date']
    age_days = (pd.to_datetime(as_of_date) - latest_date).days
    if not (0 <= age_days <= INVENTORY_STALE_DAYS):
        raise ValueError(
            f"NEEDS STOCK RECONCILIATION: inventory for product {product_id} is stale (last date {latest_date.date()})"
        )
    stock = latest_row['closing_stock']
    return stock, unit
