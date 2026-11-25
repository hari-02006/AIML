# Inventory Simulation Rules

## Overview
This document specifies how inventory levels are tracked, decremented by sales, and replenished by purchase orders over time.

## Daily Inventory Balance
At the end of every day $t$, for each product $i$:

$Closing\_Inventory_{i, t} = Opening\_Inventory_{i, t} + Received\_Units_{i, t} - Observed\_Sales_{i, t}$

Where:
- $Opening\_Inventory_{i, t} = Closing\_Inventory_{i, t-1}$
- $Received\_Units_{i, t}$: The sum of quantities from Purchase Orders where `actual_delivery_date == t`.

## True Demand vs Observed Sales (Constraint)
The fundamental rule of this simulation:
$Observed\_Sales_{i, t} = \min(True\_Demand_{i, t}, Opening\_Inventory_{i, t} + Received\_Units_{i, t})$

$Lost\_Sales_{i, t} = True\_Demand_{i, t} - Observed\_Sales_{i, t}$

## Stockout Condition
A stockout occurs on day $t$ if $True\_Demand_{i, t} > (Opening\_Inventory_{i, t} + Received\_Units_{i, t})$.
In this event, `stockout_flag = True`.

## Replenishment (Supplier Lead Time)
When a Purchase Order is placed on day $t_{order}$ with a supplier:
1. Lookup supplier's `nominal_lead_time`.
2. Add random variance based on supplier's `reliability_class`.
   - HIGH: variance is $\pm 0$ days.
   - MEDIUM: variance is $\pm 1$ day.
   - LOW: variance is $\pm 3$ days.
3. Calculate `actual_delivery_date`.
4. On `actual_delivery_date`, $Received\_Units$ is updated.

*(Note: In the Stage 2 data generator, we will likely use a simplified automated replenishment policy, such as Reorder Point = Base, to generate the initial history, before the ML-driven inventory engine takes over in Stage 9).*
