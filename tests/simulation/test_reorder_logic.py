import pytest
from ml.inventory_decision.simulation.core import reorder_point, target_stock

@pytest.mark.parametrize(
    "demand, lead_time, safety, expected_rp",
    [
        ([10, 12, 8, 9, 11], 2, 0, 22),  # lead-time demand = 10+12
        ([5, 7, 6, 4, 3], 3, 2, 5+7+6+2),
        ([], 1, 5, 5),  # empty demand -> lead-time demand 0
    ],
)
def test_reorder_point(demand, lead_time, safety, expected_rp):
    assert reorder_point(demand, lead_time, safety) == expected_rp

def test_target_stock_consistency():
    demand = [10, 15, 12]
    rp = reorder_point(demand, 2, 3)
    ts = target_stock(demand, 2, 3)
    assert ts == rp  # target stock should equal reorder point, no double count
