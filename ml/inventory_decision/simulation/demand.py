# -*- coding: utf-8 -*-
"""Demand generation utilities for inventory simulation.

This module provides a deterministic demand generator based on a random seed.
It also computes a SHA‑256 hash of the generated demand series for verification
across sensitivity scenarios.
"""

from __future__ import annotations

import hashlib
import numpy as np
from typing import List, Tuple

def generate_demand(seed: int, length: int = 180) -> Tuple[List[int], str]:
    """Generate a synthetic daily demand series.

    Parameters
    ----------
    seed: int
        Random seed for reproducibility.
    length: int, default 180
        Number of days to generate.

    Returns
    -------
    demand_series: List[int]
        List of daily demand values.
    demand_hash: str
        Hexadecimal SHA‑256 hash of the demand series.
    """
    rng = np.random.default_rng(seed)
    # Simple Poisson‑like demand with lambda = 20
    demand_series = rng.poisson(lam=20, size=length).astype(int).tolist()
    # Compute hash based on the string representation
    hash_obj = hashlib.sha256()
    hash_obj.update(",".join(map(str, demand_series)).encode())
    demand_hash = hash_obj.hexdigest()
    return demand_series, demand_hash
