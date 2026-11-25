import pytest
from ml.inventory_decision.simulation.core import reorder_point, target_stock, recommended_order_quantity

@pytest.mark.parametrize(
    "lead_demand, safety, review, inventory_pos, exp_rp, exp_ts, exp_qty",
    [
        # Example A
        (10, 0, 0, 12, 10, 10, 0),
        # Example B
        (10, 5, 0, 12, 15, 15, 3),
        # Example C (review period demand = 10)
        (10, 5, 10, 12, 15, 25, 13),
    ],
)
def test_examples(lead_demand, safety, review, inventory_pos, exp_rp, exp_ts, exp_qty):
    # Simulate demand series with lead_demand as first day's demand and zeros afterwards
    demand_series = [lead_demand] + [0] * 9
    rp = reorder_point(demand_series, lead_time_days=1, safety_stock_units=safety)
    ts = target_stock(demand_series, lead_time_days=1, safety_stock_units=safety, review_period_demand=review)
    qty = recommended_order_quantity(inventory_pos, ts)
    assert rp == exp_rp
    assert ts == exp_ts
    assert qty == exp_qty
