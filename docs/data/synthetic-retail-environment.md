# Synthetic Retail Environment Specification

## 1. Overview
This project simulates an online electronics retailer. To study inventory optimization, demand forecasting, and machine learning, we will generate a controlled synthetic dataset representing realistic operational history. This document serves as the formal specification for the data generator (Stage 2). 

## 2. PROJECT ASSUMPTIONS
All business behaviors defined here are **PROJECT ASSUMPTIONS** for the purpose of simulation. They are not empirical facts from real-world datasets.
- **Popularity**: High-popularity products sell significantly more units than lower-popularity ones.
- **Weekend Effect**: Certain products (e.g., Gaming accessories) see a demand boost on weekends (Saturday/Sunday).
- **Discount Effect**: Higher discounts (e.g., 20%) generally increase demand, but the response varies by product.
- **Seasonal Effect**: Demand increases across specific categories during predefined seasonal/festival periods.
- **Supplier Lead Time**: Replenishment takes time, ranging from 3 to 10 nominal days depending on the supplier. Lead times have random variability.
- **Inventory Bounds**: Opening inventory is strictly greater than or equal to 0. 

## 3. Product Catalog
The simulated catalog will contain 20 initial products across 5 categories: Audio, Computer Accessories, Displays, Storage, and Mobile Accessories. Each product is assigned:
- A base price and cost price.
- An initial inventory range.
- A **Popularity Class** (HIGH, MEDIUM, LOW).
- A **Demand Pattern Class** (Stable, Weekend-sensitive, Promotion-sensitive, Seasonal, Highly-variable).
- A designated **Supplier** (A, B, C, D, or E).

See `config/simulation_spec.yaml` for exact product details.

## 4. Product Popularity Classes
- **HIGH**: Consistently high sales volume (e.g., Wireless Headphones).
- **MEDIUM**: Average sales volume (e.g., Monitor).
- **LOW**: Slower moving items (e.g., 2TB External HDD).

## 5. Demand Pattern Classes
- **Stable**: Demand is relatively consistent with moderate random variation.
- **Weekend-sensitive**: Demand tends to be higher on Saturday and Sunday.
- **Promotion-sensitive**: Demand reacts strongly to discount events.
- **Seasonal**: Demand changes heavily during selected seasonal/festival periods.
- **Highly-variable**: Demand has larger random variation compared to its mean.

## 6. Price & Discount Behavior
- **Base Price**: The standard selling price.
- **Cost Price**: What the retailer pays the supplier.
- **Discounts**: Can be 0%, 5%, 10%, 15%, or 20%. Higher discounts probabilistically yield higher demand.

## 7. Weekday / Weekend Effect
- Mondays to Fridays are typical weekdays.
- Saturdays and Sundays are weekends. Products flagged as "Weekend-sensitive" will have a positive multiplier applied to their base demand on these days.

## 8. Seasonal & Promotional Events
Defined events (e.g., Festival Sale, Weekend Sale) will apply multipliers to demand. See `scenario-calendar.md` for specific events.

## 9. Customer Segmentation
Basic customer segments are defined (Budget, Standard, Premium, Gaming/Tech Enthusiast) to add demographic structure. However, demand generation will focus primarily on product-level aggregation.

## 10. True Demand vs. Observed Sales
This is a critical distinction in the simulation:
- **TRUE DEMAND**: How many units customers want to buy.
- **OBSERVED SALES**: How many units the store actually sold, constrained by available stock.
- **LOST SALES**: The unmet demand.
`Observed Sales = min(True Demand, Available Inventory)`
`Lost Sales = max(True Demand - Available Inventory, 0)`

## 11. Inventory Behavior
- `Closing Inventory = Opening Inventory + Received Units - Observed Sales`
- When True Demand > Available Inventory, a **Stockout** occurs. 

## 12. Supplier & Purchase Order Design
- **Suppliers**: A, B, C, D, E. Each has a nominal lead time (e.g., 3, 5, 7, 10 days) and a reliability class (HIGH, MEDIUM, LOW) dictating lead time variability.
- **Purchase Orders**: Contain status (Pending, In Transit, Delivered), order date, expected delivery, and actual delivery.

## 13. Randomness & Reproducibility
- The generator will use a configurable random seed (e.g., `RANDOM_SEED=42`) so that experiments can be reproduced. 
- True demand is a function of deterministic multipliers applied to base demand, injected with statistical noise (e.g., Poisson or Normal distribution).

## 14. Master Blueprint for Demand Generation
1. Base Demand lookup.
2. Apply Popularity Multiplier.
3. Apply Day-of-Week Multiplier.
4. Apply Seasonal Multiplier.
5. Apply Discount Multiplier.
6. Apply Customer/Segment Influence (optional).
7. Apply Random Noise -> **TRUE DEMAND**.
8. Apply Inventory Constraint -> **OBSERVED SALES**, **LOST SALES**.
9. Update Inventory -> **CLOSING INVENTORY**.
