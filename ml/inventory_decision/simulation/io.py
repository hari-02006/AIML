# ml/inventory_decision/simulation/io.py

"""CSV I/O utilities for the Stage 13 inventory experiment.

The CSV contains one row per *scenario run* (replication × scenario) with
the following columns (order matters for readability, extra columns are
ignored on read):

    replication_id
    scenario_name
    demand_seed
    demand_series_hash
    safety_stock_units
    review_period_demand
    lead_time_days
    policy
    order_ledger          # semicolon‑separated “order_id:placement:qty:receipt”
    demand_series         # semicolon‑separated daily demand integers
    opening_inventory     # semicolon‑separated daily opening levels
    receipts              # semicolon‑separated daily receipts
    fulfilled_demand      # semicolon‑separated daily fulfilled demand
    backorder_fulfilled   # semicolon‑separated daily backorder fulfilment
    closing_inventory     # semicolon‑separated daily closing levels
    stockout_rate
    stockout_days
    stockout_product_days
    lost_sales
    backorder_units
    avg_on_hand
    service_level
    replenishment_freq
    inventory_turnover
"""

import csv
from pathlib import Path
from typing import List, Mapping

OUTPUT_PATH = Path(__file__).parent / "output" / "experiment_records.csv"
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

BASE_COLUMNS = [
    "replication_id",
    "scenario_name",
    "demand_seed",
    "demand_series_hash",
    "safety_stock_units",
    "review_period_demand",
    "lead_time_days",
    "policy",
    "order_ledger",
    "demand_series",
    "opening_inventory",
    "receipts",
    "fulfilled_demand",
    "backorder_fulfilled",
    "closing_inventory",
    "stockout_rate",
    "stockout_days",
    "stockout_product_days",
    "lost_sales",
    "backorder_units",
    "avg_on_hand",
    "service_level",
    "replenishment_freq",
    "inventory_turnover",
]


def _series_to_str(series: List[int]) -> str:
    """Semicolon‑separated representation for CSV storage."""
    return ";".join(map(str, series))


def write_record(record: Mapping[str, object]) -> None:
    """Append a single experiment record to the CSV.

    The ``record`` mapping must contain at least the keys in ``BASE_COLUMNS``.
    Missing keys are written as empty strings.
    """
    row = [record.get(col, "") for col in BASE_COLUMNS]

    # If the file does not exist yet, write the header first.
    write_header = not OUTPUT_PATH.is_file()
    with OUTPUT_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(BASE_COLUMNS)
        writer.writerow(row)
