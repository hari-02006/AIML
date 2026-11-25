# ml/inventory_decision/simulation/metrics.py

"""State‑based metric functions for the inventory experiment.

All functions accept plain Python ``list`` objects (as produced by the
engine) and return simple numeric values suitable for CSV storage.
"""

from __future__ import annotations

from typing import List

import numpy as np


def _as_array(series: List[int]) -> np.ndarray:
    return np.asarray(series, dtype=float)


def stockout_rate(closing_inventory: List[int]) -> float:
    """Proportion of days with zero on‑hand inventory."""
    arr = _as_array(closing_inventory)
    return float((arr == 0).mean())


def stockout_days(closing_inventory: List[int]) -> int:
    """Number of days where closing inventory is zero."""
    arr = _as_array(closing_inventory)
    return int((arr == 0).sum())


def stockout_product_days(closing_inventory: List[int]) -> int:
    """Total product‑days lost to stockout (sum of zero‑inventory days)."""
    # Equivalent to stockout_days * 1 unit (each day counts as one product‑day)
    return stockout_days(closing_inventory)


def lost_sales(
    demand_series: List[int],
    fulfilled_demand: List[int],
    backorder_fulfilled: List[int],
    policy: str = "backorder",
) -> int:
    """Total units never fulfilled.

    * ``policy == "backorder"`` – only the *final* backlog after the horizon
      counts as lost sales.
    * ``policy == "lost_sales"`` – every unmet demand is a lost sale.
    """
    demand = _as_array(demand_series)
    served = _as_array(fulfilled_demand) + _as_array(backorder_fulfilled)
    unmet = demand - served
    if policy == "lost_sales":
        return int(unmet[unmet > 0].sum())
    # backorder policy: lost sales = backlog remaining at the end
    return int(max(0.0, unmet[-1]))


def backorder_units(backorder_fulfilled: List[int]) -> int:
    """Total units that were backordered (i.e., fulfilled later)."""
    return int(sum(backorder_fulfilled))


def average_on_hand(closing_inventory: List[int]) -> float:
    """Mean on‑hand inventory across the horizon."""
    return float(_as_array(closing_inventory).mean())


def service_level(
    demand_series: List[int],
    fulfilled_demand: List[int],
    backorder_fulfilled: List[int],
    policy: str = "backorder",
) -> float:
    """Fraction of total demand that is eventually satisfied.

    For the backorder policy, the final backlog is excluded (treated as lost
    sales). For lost‑sales policy the denominator is the raw demand.
    """
    total_demand = _as_array(demand_series).sum()
    total_served = _as_array(fulfilled_demand).sum() + _as_array(
        backorder_fulfilled
    ).sum()
    if total_demand == 0:
        return 0.0
    return float(total_served / total_demand)


def replenishment_frequency(order_ledger: List) -> float:
    """Average number of orders placed per replication (per scenario)."""
    return float(len(order_ledger))


def inventory_turnover(
    closing_inventory: List[int],
    fulfilled_demand: List[int],
) -> float:
    """Turnover = total units sold / average on‑hand inventory."""
    avg_on_hand = average_on_hand(closing_inventory)
    total_sold = sum(fulfilled_demand)
    return float(total_sold / avg_on_hand) if avg_on_hand > 0 else 0.0
