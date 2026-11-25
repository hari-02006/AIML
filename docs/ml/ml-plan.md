# Machine Learning Plan

## Strategy
Target: Next-day demand prediction.

## Potential Features
- price
- discount
- promotion
- day_of_week
- month
- weekend
- festival
- lag_1
- lag_7
- lag_14
- rolling_mean_7
- rolling_mean_30
- rolling_std_7

## Candidate Approaches
1. Previous-day baseline
2. 7-day average baseline
3. Random Forest Regressor
4. XGBoost Regressor

## Evaluation Metrics
- MAE (Mean Absolute Error)
- RMSE (Root Mean Squared Error)
- MAPE/WAPE where appropriate

## Evaluation Strategy
- Time-aware train/test split.
- Avoid future-data leakage (e.g., using day N+1 to predict day N).

*(No ML model will be trained in Stage 0.)*
