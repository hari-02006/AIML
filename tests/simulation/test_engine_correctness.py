import pytest
import numpy as np
from ml.inventory_decision.simulation.engine import run_one_scenario

@pytest.mark.parametrize("lead_time, safety_stock, policy", [
    (2, 0, "backorder"),
    (0, 5, "backorder"),
    (1, 0, "lost_sales"),
])
def test_inventory_accounting_basic(lead_time, safety_stock, policy):
    # constant demand of 5 units per day for 10 days
    demand = [5] * 10
    # set review period demand high to avoid ordering (so we focus on accounting)
    result = run_one_scenario(
        demand_series=demand,
        lead_time_days=lead_time,
        safety_stock_units=safety_stock,
        review_period_demand=1000,
        policy=policy,
    )
    # opening inventory should equal previous closing inventory (+ receipts)
    for i in range(len(demand)):
        assert result.opening_inventory[i] == (result.closing_inventory[i-1] if i > 0 else 0) + result.receipts[i]
    # inventory should never go negative
    assert all(inv >= 0 for inv in result.closing_inventory)
    # backorders should never be negative
    assert all(bo >= 0 for bo in result.closing_backorders)
    # fulfilled demand cannot exceed opening inventory
    for i in range(len(demand)):
        assert result.fulfilled_demand[i] <= result.opening_inventory[i]
    # if policy is lost_sales, there should be no backorders created
    if policy == "lost_sales":
        assert all(b == 0 for b in result.closing_backorders)
    else:
        # backorders may exist when demand > inventory
        pass
