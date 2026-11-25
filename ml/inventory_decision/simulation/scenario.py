"""Scenario definitions for inventory simulation.

A ``Scenario`` encapsulates the configuration for a single experiment run.
It holds the demand series, lead‑time, safety‑stock and provides a ``run``
method that returns a dict with the computed ``reorder_point`` and
``target_stock`` using the functions from ``core``.
"""

from __future__ import annotations

from typing import List, Dict

from .core import reorder_point, target_stock

class Scenario:
    """Simple container for a simulation scenario.

    Parameters
    ----------
    demand_series:
        List of daily demand values (synthetic or historical).
    lead_time_days:
        Lead‑time in days.
    safety_stock_units:
        Safety‑stock quantity.
    """

    def __init__(self, demand_series: List[float], lead_time_days: int, safety_stock_units: float):
        self.demand_series = demand_series
        self.lead_time_days = lead_time_days
        self.safety_stock_units = safety_stock_units

    def run(self) -> Dict[str, float]:
        """Execute the scenario and return key inventory numbers.

        Returns
        -------
        dict
            ``{"reorder_point": ..., "target_stock": ...}``
        """
        rp = reorder_point(self.demand_series, self.lead_time_days, self.safety_stock_units)
        ts = target_stock(self.demand_series, self.lead_time_days, self.safety_stock_units)
        return {"reorder_point": rp, "target_stock": ts}
