# Demand Generation Rules

## Overview
This document specifies the step-by-step logic to calculate daily demand for a given product. This logic will be implemented in Stage 2.

## The Demand Formula
Demand generation follows a multiplicative/additive model with stochastic noise.

### 1. Base Demand ($D_{base}$)
Each product has a baseline daily demand defined by its popularity:
- HIGH: ~30 units/day
- MEDIUM: ~15 units/day
- LOW: ~5 units/day

### 2. Day of Week Multiplier ($M_{dow}$)
If a product is `Weekend-sensitive`:
- Saturday/Sunday: $M_{dow}$ = 1.3 to 1.5
- Monday-Friday: $M_{dow}$ = 1.0

If `Stable` or other:
- All days: $M_{dow}$ = 1.0

### 3. Seasonality Multiplier ($M_{season}$)
If the current date falls within a seasonal event (e.g., Festival Sale) and the product's category is affected:
- $M_{season}$ = 1.2 to 2.0 (depending on event intensity)
- Otherwise: $M_{season}$ = 1.0

### 4. Discount / Promotion Multiplier ($M_{promo}$)
If a discount is active:
- 0%: $M_{promo}$ = 1.0
- 5%: $M_{promo}$ = 1.1
- 10%: $M_{promo}$ = 1.25
- 15%: $M_{promo}$ = 1.4
- 20%: $M_{promo}$ = 1.6
*Note: If the product is `Promotion-sensitive`, these multipliers are amplified (e.g., +0.2).*

### 5. Random Noise ($\epsilon$)
A random variable sampled to represent natural volatility. 
- `Stable`: Low variance ($\sigma \approx 0.1 \cdot \mu$)
- `Highly-variable`: High variance ($\sigma \approx 0.4 \cdot \mu$)

### 6. Final True Demand Calculation
$True \ Demand = \text{max}(0, \text{Round}(D_{base} \times M_{dow} \times M_{season} \times M_{promo} + \epsilon))$

## Driver Priority
1. **Primary Drivers**: Popularity, Day-of-week, Promotions, Seasons.
2. **Secondary Drivers**: Base Price, Customer segment, Random noise.
