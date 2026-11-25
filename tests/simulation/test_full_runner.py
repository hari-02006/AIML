# tests/simulation/test_full_runner.py

import csv
from pathlib import Path

import pytest

from ml.inventory_decision.simulation.run import (
    main,
    OUTPUT_PATH,
    SENSITIVITY_PATH,
)

@pytest.fixture(scope="module", autouse=True)
def execute_experiment():
    """Run the full experiment once for the whole test suite.

    The fixture deletes any existing CSV to guarantee a fresh run.
    """
    if OUTPUT_PATH.is_file():
        OUTPUT_PATH.unlink()
    main()
    yield
    # Keep the CSV for possible manual inspection.


def _read_csv():
    with open(OUTPUT_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_row_count():
    rows = _read_csv()
    assert len(rows) == 30 * 9, "Expected 270 rows (30 replications × 9 scenarios)"


def test_hash_consistency():
    rows = _read_csv()
    # group by replication_id
    by_rep = {}
    for r in rows:
        rep = int(r["replication_id"])
        by_rep.setdefault(rep, []).append(r)
    for rep, records in by_rep.items():
        hashes = {rec["demand_series_hash"] for rec in records}
        assert len(hashes) == 1, f"Replication {rep} hashes differ across scenarios"
    # distinct hashes across replications
    all_hashes = {r["demand_series_hash"] for r in rows}
    assert len(all_hashes) == 30, "Each replication should have a unique demand hash"


def test_carry_forward():
    rows = _read_csv()
    sample = rows[0]
    opening = list(map(int, sample["opening_inventory"].split(";")))
    receipts = list(map(int, sample["receipts"].split(";")))
    closing = list(map(int, sample["closing_inventory"].split(";")))
    for i in range(1, len(opening)):
        expected = closing[i - 1] + receipts[i]
        assert opening[i] == expected, f"Day {i} inventory carry‑forward mismatch"


def test_backorder_fulfilment():
    rows = _read_csv()
    any_backorder = any(int(r["backorder_units"]) > 0 for r in rows)
    assert any_backorder, "Expected at least one backordered unit in the dataset"
    for r in rows:
        bo_fulfilled = list(map(int, r["backorder_fulfilled"].split(";")))
        receipts = list(map(int, r["receipts"].split(";")))
        for day, f in enumerate(bo_fulfilled):
            assert f <= receipts[day], "Backorder fulfilment cannot exceed receipts on the same day"


def test_order_ledger_structure():
    rows = _read_csv()
    for r in rows:
        ledger = r["order_ledger"].strip()
        if not ledger:
            continue
        for entry in ledger.split(";"):
            parts = entry.split(":")
            assert len(parts) == 4, "Ledger entry must be id:place:qty:receipt"
            _, placement, qty, receipt = parts
            assert int(qty) > 0, "Order quantity must be positive"


def test_metric_ranges():
    rows = _read_csv()
    for r in rows:
        rate = float(r["stockout_rate"])
        assert 0.0 <= rate <= 1.0
        sl = float(r["service_level"])
        assert 0.0 <= sl <= 1.0
        turn = float(r["inventory_turnover"])
        assert turn >= 0.0
