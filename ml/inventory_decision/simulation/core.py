# Core simulation logic for inventory replenishment
"""Utility functions that implement the replenishment policy.

The project requires a *consistent* policy:

* **Reorder Point (ROP)** = Lead‑time demand + Safety stock
* **Target Stock** should *not* double‑count safety stock. In the synthetic
  demonstration scenario we keep it simple and set ``Target Stock = ROP``.

Both functions accept a ``demand_series`` (list or numpy array) representing
daily demand forecasts and the ``lead_time_days`` configuration.
"""

from __future__ import annotations

import numpy as np
from typing import Iterable


def lead_time_demand(demand_series: Iterable[float], lead_time_days: int) -> float:
    """Return the total expected demand over the lead‑time horizon.

    Parameters
    ----------
    demand_series:
        Iterable of daily demand values (historical or synthetic).
    lead_time_days:
        Number of days between order placement and receipt.
    """
    demand = np.asarray(list(demand_series), dtype=float)
    return float(demand[:lead_time_days].sum())


def reorder_point(demand_series: Iterable[float], lead_time_days: int, safety_stock_units: float) -> float:
    """Calculate the reorder point using the policy described above.

    ``ROP = Lead‑time demand + Safety stock``
    """
    lt_demand = lead_time_demand(demand_series, lead_time_days)
    return lt_demand + safety_stock_units


def target_stock(demand_series: Iterable[float], lead_time_days: int, safety_stock_units: float, review_period_demand: float = 0.0) -> float:
    """Return the target inventory level.

    The intended formula is:
    Target Stock = Lead‑time demand + Review‑period demand + Safety stock.

    In the synthetic demonstration the review period is defined as zero,
    which is documented here. When omitted, review_period_demand defaults to 0.0,
    yielding Target Stock = Reorder Point.
    """
    rp = reorder_point(demand_series, lead_time_days, safety_stock_units)
    return rp + review_period_demand

def recommended_order_quantity(inventory_position: float, target_stock: float) -> float:
    """Calculate the recommended order quantity.

    Order Quantity = max(0, Target Stock - Inventory Position).
    """
    return max(0.0, target_stock - inventory_position)
