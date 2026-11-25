import pytest
from ml.inventory_decision.simulation.demand import generate_demand

def test_demand_hash_consistency_across_replications():
    base_seed = 100
    # Generate 30 replications
    hashes = []
    for i in range(30):
        seed = base_seed + i
        _, demand_hash = generate_demand(seed)
        hashes.append(demand_hash)
    # All hashes should be unique
    assert len(set(hashes)) == 30

def test_demand_hash_repeat_same_seed():
    seed = 12345
    series1, hash1 = generate_demand(seed)
    series2, hash2 = generate_demand(seed)
    assert series1 == series2
    assert hash1 == hash2
