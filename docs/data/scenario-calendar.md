# Scenario Calendar

## Overview
This document outlines the hypothetical scenarios and events that will be simulated to evaluate the robustness of the ML forecasting and inventory engine.

## Future Experimental Scenarios
*(Note: These will be generated/tested in later stages. Stage 1 only designs them.)*

### SCENARIO A: Normal demand
- **Purpose**: Baseline performance.
- **Expected Change**: Standard operations.
- **Affected Parameters**: None (default multipliers).

### SCENARIO B: Promotion-heavy period
- **Purpose**: Test responsiveness to price drops.
- **Expected Change**: Sustained high discounts.
- **Affected Parameters**: `discount` = 15-20% for 2 weeks.

### SCENARIO C: Festival/seasonal demand
- **Purpose**: Test seasonal spikes.
- **Expected Change**: Massive short-term demand increase.
- **Affected Parameters**: `M_season` = 1.8 for 5 days across all categories.

### SCENARIO D: High-demand period (Macro trend)
- **Purpose**: Test structural shift in baseline demand.
- **Expected Change**: Long-term sustained higher demand.
- **Affected Parameters**: `D_base` increased by 30%.

### SCENARIO E: Low-demand period (Macro trend)
- **Purpose**: Test overstock risk and inventory cost.
- **Expected Change**: Sustained lower demand.
- **Affected Parameters**: `D_base` decreased by 30%.

### SCENARIO F: Stockout conditions
- **Purpose**: Test ML's ability to forecast true demand from censored observed sales.
- **Expected Change**: Inventory deliberately kept low.
- **Affected Parameters**: Initial inventory reduced; automated replenishment delayed.

### SCENARIO G: Long supplier lead time
- **Purpose**: Test safety stock buffers.
- **Expected Change**: Suppliers take longer than expected.
- **Affected Parameters**: Supplier lead time increased by 5-10 days globally.

### SCENARIO H: Higher price
- **Purpose**: Test price elasticity effects.
- **Expected Change**: Base price increases, causing demand drop.
- **Affected Parameters**: Base prices +25%.
