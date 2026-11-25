# ml/inventory_decision/simulation/run.py

"""Stage 13 experiment driver.

* Generates 30 deterministic demand series (seed = BASE + replication_id).
* For each replication, runs the nine sensitivity scenarios defined in
  ``sensitivity.yaml`` using the **exact same demand series**.
* Persists all daily series and derived metrics via ``io.write_record``.
"""

from __future__ import annotations

import yaml
from pathlib import Path

from .demand import generate_demand
from .engine import run_one_scenario
from .metrics import (
    stockout_rate,
    stockout_days,
    stockout_product_days,
    lost_sales,
    backorder_units,
    average_on_hand,
    service_level,
    replenishment_frequency,
    inventory_turnover,
)
from .io import write_record, OUTPUT_PATH

PROJECT_ROOT = Path(__file__).parent
SENSITIVITY_PATH = PROJECT_ROOT / "sensitivity.yaml"

BASE_DEMAND_SEED = 1_000_000
NUM_REPLICATIONS = 30
HORIZON_DAYS = 180  # matches default demand length


def load_scenarios() -> list[dict]:
    """Parse ``sensitivity.yaml`` and compute derived parameters.

    Returns a list of dictionaries containing the fields used by the engine.
    """
    with open(SENSITIVITY_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    base_safety = 5
    base_review = 5
    enriched: list[dict] = []
    for entry in raw:
        enriched.append(
            {
                "name": entry["name"],
                "lead_time_days": entry["lead_time_days"],
                "safety_stock_units": base_safety * entry["safety_stock_multiplier"],
                "review_period_demand": base_review * entry["review_period_multiplier"],
                "policy": entry.get("policy", "backorder"),
            }
        )
    return enriched


def main() -> None:
    scenarios = load_scenarios()

    for rep_id in range(1, NUM_REPLICATIONS + 1):
        demand_seed = BASE_DEMAND_SEED + rep_id
        demand_series, demand_hash = generate_demand(
            seed=demand_seed, length=HORIZON_DAYS
        )

        for scenario in scenarios:
            result = run_one_scenario(
                demand_series=demand_series,
                lead_time_days=scenario["lead_time_days"],
                safety_stock_units=scenario["safety_stock_units"],
                review_period_demand=scenario["review_period_demand"],
                policy=scenario["policy"],
            )

            # Build CSV record
            record = {
                "replication_id": rep_id,
                "scenario_name": scenario["name"],
                "demand_seed": demand_seed,
                "demand_series_hash": demand_hash,
                "safety_stock_units": scenario["safety_stock_units"],
                "review_period_demand": scenario["review_period_demand"],
                "lead_time_days": scenario["lead_time_days"],
                "policy": scenario["policy"],
                "order_ledger": ";".join(
                    f"{o.order_id}:{o.placement_day}:{o.quantity}:{o.receipt_day}"
                    for o in result.order_ledger
                ),
                "demand_series": ";".join(map(str, demand_series)),
                "opening_inventory": ";".join(map(str, result.opening_inventory)),
                "receipts": ";".join(map(str, result.receipts)),
                "fulfilled_demand": ";".join(map(str, result.fulfilled_demand)),
                "backorder_fulfilled": ";".join(map(str, result.backorder_fulfilled)),
                "closing_inventory": ";".join(map(str, result.closing_inventory)),
                # Metrics
                "stockout_rate": stockout_rate(result.closing_inventory),
                "stockout_days": stockout_days(result.closing_inventory),
                "stockout_product_days": stockout_product_days(
                    result.closing_inventory
                ),
                "lost_sales": lost_sales(
                    demand_series,
                    result.fulfilled_demand,
                    result.backorder_fulfilled,
                    policy=scenario["policy"],
                ),
                "backorder_units": backorder_units(result.backorder_fulfilled),
                "avg_on_hand": average_on_hand(result.closing_inventory),
                "service_level": service_level(
                    demand_series,
                    result.fulfilled_demand,
                    result.backorder_fulfilled,
                    policy=scenario["policy"],
                ),
                "replenishment_freq": replenishment_frequency(result.order_ledger),
                "inventory_turnover": inventory_turnover(
                    result.closing_inventory, result.fulfilled_demand
                ),
            }

            write_record(record)


if __name__ == "__main__":
    main()
