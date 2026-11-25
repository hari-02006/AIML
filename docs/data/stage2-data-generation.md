# Stage 2: Synthetic Data Generator
## Overview
The synthetic data generator translates the rules defined in Stage 1 into a robust Python application. The application models daily operations of a retail supply chain, decoupling true consumer demand from observed sales due to stockouts.

## Architecture
The generator is implemented entirely using the Python Standard Library (`csv`, `json`, `datetime`, `random`), sidestepping any dependency or DLL lock issues with external libraries like `pandas` and `numpy`.

The module is structured as follows:
- `data_generator/__main__.py`: CLI interface (`--seed`, `--start-date`, etc.).
- `data_generator/catalog.py`: Products and categories generation.
- `data_generator/customers.py`: Customer persona modeling.
- `data_generator/suppliers.py`: Supplier information.
- `data_generator/promotions.py`: Promotion modeling based on configuration.
- `data_generator/simulation.py`: The core daily loop.
- `data_generator/validation.py`: Data integrity constraints and reconciliation.
- `data_generator/utils.py`: PRNG and helper functions.
- `data_generator/config_loader.py`: YAML/JSON spec loader.

## Simulation Mechanics
1. **Initial Stock**: Products begin with an initial inventory range.
2. **True Demand**: Demand is a function of the base rate, weekend factors, promotional discounts, and a random noise variance (normal distribution).
3. **Observed Sales**: `min(True Demand, Available Stock)`.
4. **Replenishment**: Reorder point (ROP) is modeled dynamically. When `closing_stock < ROP`, a Purchase Order (PO) is generated. Lead times differ based on supplier reliability (`HIGH`, `MEDIUM`, `LOW`).

## Validation
A suite of validations runs on completion:
1. `Closing = Opening + Received - Observed`.
2. Sales records precisely aggregate to observed inventory sold.
3. Stockouts strictly align with lost sales records.

## Automated Testing
Tests are available in `tests/data/test_integrity.py` and run via `pytest`.

## Summary
The baseline generator (Seed 42) outputs ~7,300 product-day inventory records, 18,156 individual sales transactions, and over 150,000 units in true demand. It explicitly exposes 729 lost sales and 50 stockout product-days, providing our ML models a rich baseline for demand forecasting.
