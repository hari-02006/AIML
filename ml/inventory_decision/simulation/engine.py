# ml/inventory_decision/simulation/engine.py

"""Core simulation engine for a single scenario run.

The engine tracks:

* opening inventory each day
* receipts (arriving after the configured lead time)
* order placement ledger (including actual receipt day and status)
* available inventory before demand
* backorder fulfilment and creation of new backorders
* lost‑sales (when policy is \"lost_sales\")
* fulfilled demand
* closing inventory and closing backorders
* stockout flag per day
* inventory position per day
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import List

import numpy as np
from .core import recommended_order_quantity, target_stock


@dataclass
class Order:
    """A single replenishment order.

    Attributes:
        order_id: Unique identifier.
        placement_day: Day the order was placed.
        quantity: Units ordered.
        receipt_day: Expected receipt day (based on lead time).
        actual_receipt_day: Day the order was actually received (set when receipt occurs).
        status: ``"pending"`` until received, then ``"received"``.
    """

    order_id: int
    placement_day: int
    quantity: int
    receipt_day: int | None = None
    actual_receipt_day: int | None = None
    status: str = "pending"


@dataclass
class SimulationResult:
    # Daily series (one entry per horizon day)
    opening_inventory: List[int] = field(default_factory=list)
    receipts: List[int] = field(default_factory=list)
    available_before_demand: List[int] = field(default_factory=list)
    backorder_fulfilled: List[int] = field(default_factory=list)
    new_backorders: List[int] = field(default_factory=list)
    lost_sales: List[int] = field(default_factory=list)
    fulfilled_demand: List[int] = field(default_factory=list)
    closing_inventory: List[int] = field(default_factory=list)
    closing_backorders: List[int] = field(default_factory=list)
    stockout_flag: List[int] = field(default_factory=list)
    inventory_position: List[int] = field(default_factory=list)
    order_ledger: List[Order] = field(default_factory=list)


def run_one_scenario(
    demand_series: List[int],
    lead_time_days: int,
    safety_stock_units: float,
    review_period_demand: float,
    policy: str = "backorder",
) -> SimulationResult:
    """Execute the inventory policy over the horizon.

    The function follows the exact daily accounting steps required for Stage 13.
    """
    horizon = len(demand_series)
    result = SimulationResult()

    # State variables
    on_hand = 0  # closing inventory of previous day
    backorder = 0
    next_order_id = itertools.count(1)

    # receipt_day → total quantity pending arrival (aggregate per day)
    pending_receipts: dict[int, int] = {}

    for day in range(horizon):
        # ------------------------------------------------------------
        # 1️⃣ Opening inventory = previous closing + any receipts arriving today
        receipt_today = pending_receipts.pop(day, 0)
        # Mark orders that arrive today as received
        for order in result.order_ledger:
            if order.receipt_day == day and order.status == "pending":
                order.actual_receipt_day = day
                order.status = "received"
        opening = on_hand + receipt_today
        result.opening_inventory.append(opening)
        result.receipts.append(receipt_today)
        # Record inventory available before any demand handling
        result.available_before_demand.append(opening)

        # ------------------------------------------------------------
        # 2️⃣ Fulfil backorders first (if any) using available inventory
        if backorder > 0 and opening > 0:
            fulfil = min(backorder, opening)
            backorder -= fulfil
            opening -= fulfil
            result.backorder_fulfilled.append(fulfil)
        else:
            result.backorder_fulfilled.append(0)

        # ------------------------------------------------------------
        # 3️⃣ Serve today's demand with remaining inventory
        demand = demand_series[day]
        served = min(opening, demand)
        result.fulfilled_demand.append(served)

        # ------------------------------------------------------------
        # 4️⃣ Handle unmet demand according to policy
        unmet = demand - served
        if policy == "backorder":
            # New backorders are created for any unmet demand
            result.new_backorders.append(unmet)
            result.lost_sales.append(0)
            backorder += unmet
        else:  # lost_sales policy
            result.new_backorders.append(0)
            result.lost_sales.append(unmet)
            # backorder unchanged (remains 0 for lost‑sales mode)

        # ------------------------------------------------------------
        # 5️⃣ Compute closing inventory after both fulfilments
        closing = opening - served
        on_hand = closing
        result.closing_inventory.append(closing)
        result.closing_backorders.append(backorder)

        # Stockout flag: true if any demand could not be met today
        result.stockout_flag.append(1 if unmet > 0 else 0)

        # ------------------------------------------------------------
        # 6️⃣ Reorder decision (review at the end of the day)
        # Inventory position = on‑hand + outstanding order qty - outstanding backorders
        outstanding_orders_qty = sum(pending_receipts.values())
        inventory_position = on_hand + outstanding_orders_qty - backorder
        result.inventory_position.append(inventory_position)

        target = target_stock(
            demand_series,
            lead_time_days,
            safety_stock_units,
            review_period_demand,
        )
        order_qty_raw = recommended_order_quantity(inventory_position, target)
        order_qty = int(np.ceil(order_qty_raw)) if order_qty_raw > 0 else 0

        if order_qty > 0:
            order_id = next(next_order_id)
            receipt_day = day + lead_time_days
            order = Order(
                order_id=order_id,
                placement_day=day,
                quantity=int(order_qty),
                receipt_day=receipt_day,
            )
            result.order_ledger.append(order)
            # Add to pending receipts map
            pending_receipts[receipt_day] = pending_receipts.get(receipt_day, 0) + int(order_qty)

    return result
