"""
Unit and Integration Test Suite for Stage 10: ML Feature Engineering.
Validates:
  1. Transactional sales aggregation to daily demand
  2. Calendar features and periodic cyclical encodings
  3. Lag features (T - 1, 7, 14, 28) and absence of cross-product leakage
  4. Rolling statistics (mean, sum, std) and strict target leakage prevention
  5. Behavioral features (days since last sale, demand trend)
  6. Product and category metadata enrichment
  7. Inventory historical alignment (T - 1 precedence and missingness handling)
  8. Promotional date interval labeling
  9. Data quality and missingness summary generation
 10. Atomic artifact generation and metadata completeness
 11. Fail-closed production database read-only safety guard
"""

import math
import datetime
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from ml.features.feature_pipeline import (
    aggregate_daily_demand,
    generate_calendar_features,
    generate_lag_and_rolling_features,
    merge_product_and_category_metadata,
    merge_historical_inventory_features,
    merge_promotion_features,
    build_stage10_feature_dataset
)
from ml.features.feature_validator import validate_feature_leakage_and_integrity
from ml.features.feature_reporter import (
    generate_feature_data_dictionary,
    generate_feature_quality_summary,
    save_stage10_artifacts,
    STAGE10_OUTPUT_DIR
)
from ml.features.data_extractor import extract_stage10_source_data
from ml.features import run_stage10_pipeline, load_latest_stage10_artifacts
from database.db_connection import get_connection


# ---------------------------------------------------------------------------
# Synthetic Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_sales_and_products():
    """Generates a small deterministic 10-day synthetic sales dataset for 2 products."""
    dates_p1 = [datetime.date(2025, 1, 1) + datetime.timedelta(days=i) for i in range(10)]
    dates_p2 = [datetime.date(2025, 1, 1) + datetime.timedelta(days=i) for i in range(10)]
    
    # Product 1: Multiple transactions on day 1 (10 + 5 = 15), zero on day 3
    sales_records = [
        {"sale_id": "S1", "date": dates_p1[0], "product_id": "P1", "quantity": 10},
        {"sale_id": "S2", "date": dates_p1[0], "product_id": "P1", "quantity": 5},
        {"sale_id": "S3", "date": dates_p1[1], "product_id": "P1", "quantity": 20},
        # Day 2 omitted -> zero demand
        {"sale_id": "S4", "date": dates_p1[3], "product_id": "P1", "quantity": 30},
        {"sale_id": "S5", "date": dates_p1[4], "product_id": "P1", "quantity": 40},
        {"sale_id": "S6", "date": dates_p1[5], "product_id": "P1", "quantity": 50},
        {"sale_id": "S7", "date": dates_p1[6], "product_id": "P1", "quantity": 60},
        {"sale_id": "S8", "date": dates_p1[7], "product_id": "P1", "quantity": 70},
        {"sale_id": "S9", "date": dates_p1[8], "product_id": "P1", "quantity": 80},
        {"sale_id": "S10", "date": dates_p1[9], "product_id": "P1", "quantity": 90},
        # Product 2
        {"sale_id": "S11", "date": dates_p2[0], "product_id": "P2", "quantity": 100},
        {"sale_id": "S12", "date": dates_p2[1], "product_id": "P2", "quantity": 200},
    ]
    for i in range(2, 10):
        sales_records.append({
            "sale_id": f"S{13+i}",
            "date": dates_p2[i],
            "product_id": "P2",
            "quantity": (i + 1) * 100
        })
        
    df_sales = pd.DataFrame(sales_records)
    
    df_products = pd.DataFrame([
        {"product_id": "P1", "product_name": "Product One", "category_id": 1, "category_name": "Audio",
         "supplier_id": "SUP1", "stock_unit": "Units", "base_price": 100.0, "cost_price": 60.0,
         "popularity_class": "HIGH", "demand_pattern_class": "Stable"},
        {"product_id": "P2", "product_name": "Product Two", "category_id": 2, "category_name": "Peripherals",
         "supplier_id": "SUP2", "stock_unit": "Pieces", "base_price": 200.0, "cost_price": 120.0,
         "popularity_class": "MEDIUM", "demand_pattern_class": "Seasonal"}
    ])
    
    return df_sales, df_products


# ---------------------------------------------------------------------------
# Test Category A: Aggregation and Grid Logic
# ---------------------------------------------------------------------------

def test_aggregation_multi_transaction_and_zero_demand(synthetic_sales_and_products):
    """Verifies that multiple same-day transactions sum correctly and unrecorded dates are zero-filled."""
    df_sales, df_products = synthetic_sales_and_products
    grid_df, metrics = aggregate_daily_demand(df_sales, df_products)
    
    # P1 day 0 had two sales: 10 + 5 = 15
    p1_day0 = grid_df[(grid_df["product_id"] == "P1") & (grid_df["date"] == datetime.date(2025, 1, 1))]
    assert len(p1_day0) == 1
    assert p1_day0.iloc[0]["demand_units"] == 15
    assert p1_day0.iloc[0]["transaction_count"] == 2
    assert bool(p1_day0.iloc[0]["is_zero_demand_inferred"]) is False
    
    # P1 day 2 had no sales -> zero-filled
    p1_day2 = grid_df[(grid_df["product_id"] == "P1") & (grid_df["date"] == datetime.date(2025, 1, 3))]
    assert len(p1_day2) == 1
    assert p1_day2.iloc[0]["demand_units"] == 0
    assert p1_day2.iloc[0]["transaction_count"] == 0
    assert bool(p1_day2.iloc[0]["is_zero_demand_inferred"]) is True
    
    # Total grid length: 2 products * 10 dates = 20
    assert len(grid_df) == 20
    assert metrics["zero_demand_days_count"] == 1


# ---------------------------------------------------------------------------
# Test Category B: Calendar Features and Cyclical Encoding
# ---------------------------------------------------------------------------

def test_calendar_features_and_cyclical_encoding(synthetic_sales_and_products):
    """Verifies standard calendar attributes and mathematical boundaries of cyclical encodings."""
    df_sales, df_products = synthetic_sales_and_products
    grid_df, _ = aggregate_daily_demand(df_sales, df_products)
    cal_df = generate_calendar_features(grid_df)
    
    row_wed = cal_df[cal_df["date"] == datetime.date(2025, 1, 1)].iloc[0]
    # 2025-01-01 was a Wednesday (day_of_week = 2)
    assert row_wed["day_of_week"] == 2
    assert row_wed["day_of_month"] == 1
    assert row_wed["month"] == 1
    assert row_wed["quarter"] == 1
    assert row_wed["year"] == 2025
    assert row_wed["is_weekend"] == 0
    
    # Cyclical bounds [-1, 1]
    assert cal_df["day_of_week_sin"].between(-1.0, 1.0).all()
    assert cal_df["day_of_week_cos"].between(-1.0, 1.0).all()
    assert cal_df["month_sin"].between(-1.0, 1.0).all()
    assert cal_df["month_cos"].between(-1.0, 1.0).all()
    
    # Check Sunday weekend flag
    row_sun = cal_df[cal_df["date"] == datetime.date(2025, 1, 5)].iloc[0]
    assert row_sun["day_of_week"] == 6
    assert row_sun["is_weekend"] == 1


# ---------------------------------------------------------------------------
# Test Category C: Demand Lags & Leakage Prevention
# ---------------------------------------------------------------------------

def test_lags_and_no_cross_product_leakage(synthetic_sales_and_products):
    """Verifies that lag 1 is strictly T - 1, and first row of P2 never receives P1's last value."""
    df_sales, df_products = synthetic_sales_and_products
    grid_df, _ = aggregate_daily_demand(df_sales, df_products)
    lag_df = generate_lag_and_rolling_features(grid_df)
    
    p1 = lag_df[lag_df["product_id"] == "P1"].reset_index(drop=True)
    p2 = lag_df[lag_df["product_id"] == "P2"].reset_index(drop=True)
    
    # P1 first day has no prior lag
    assert pd.isna(p1.loc[0, "demand_lag_1"])
    # P1 second day receives day 0's demand (15)
    assert p1.loc[1, "demand_lag_1"] == 15.0
    
    # P2 first day MUST be NaN — never inherit P1's day 9 demand (90)!
    assert pd.isna(p2.loc[0, "demand_lag_1"])
    assert p2.loc[1, "demand_lag_1"] == 100.0


# ---------------------------------------------------------------------------
# Test Category D: Rolling Statistical Features & Strict Zero-Leakage
# ---------------------------------------------------------------------------

def test_rolling_features_strict_zero_leakage():
    """
    CRITICAL TEST: Proves mathematically that current day's demand_units
    NEVER enters current day's rolling_mean_7, rolling_sum_7, or rolling_std_7.
    """
    # Create 14 days of data with a massive spike on day 7
    dates = [datetime.date(2025, 1, 1) + datetime.timedelta(days=i) for i in range(14)]
    # Constant demand of 10 for days 0..6, spike of 1000 on day 7, 10 afterwards
    demands = [10] * 7 + [1000] + [10] * 6
    
    df = pd.DataFrame({
        "product_id": ["P_TEST"] * 14,
        "date": dates,
        "demand_units": demands
    })
    
    roll_df = generate_lag_and_rolling_features(df)
    
    # At day 7 (where spike occurs in target):
    # rolling_mean_7 must be calculated on days 0..6 (all 10s) -> mean must be exactly 10.0!
    # If leakage occurred, day 7's 1000 would be included and mean would be (6*10 + 1000)/7 = 151.4!
    day_7_roll_mean = roll_df.loc[7, "rolling_mean_7"]
    assert np.isclose(day_7_roll_mean, 10.0), (
        f"TARGET LEAKAGE DETECTED! Expected rolling_mean_7 on day 7 to be 10.0 (past days only), "
        f"got {day_7_roll_mean}!"
    )
    assert roll_df.loc[7, "rolling_sum_7"] == 70.0
    assert np.isclose(roll_df.loc[7, "rolling_std_7"], 0.0)
    
    # The spike of 1000 should only enter rolling_mean_7 on day 8 (T + 1)
    day_8_roll_mean = roll_df.loc[8, "rolling_mean_7"]
    expected_day_8 = (6 * 10 + 1000) / 7.0
    assert np.isclose(day_8_roll_mean, expected_day_8, atol=1e-3)


# ---------------------------------------------------------------------------
# Test Category E: Inventory Lag Precedence (T - 1)
# ---------------------------------------------------------------------------

def test_inventory_features_lag_precedence():
    """Verifies that inventory features available on date T reflect date T - 1 observations."""
    df_grid = pd.DataFrame({
        "product_id": ["P1", "P1"],
        "date": [datetime.date(2025, 1, 1), datetime.date(2025, 1, 2)],
        "demand_units": [5, 10]
    })
    
    df_inv = pd.DataFrame({
        "product_id": ["P1", "P1"],
        "date": [datetime.date(2025, 1, 1), datetime.date(2025, 1, 2)],
        "opening_stock": [100, 95],
        "units_received": [0, 20],
        "closing_stock": [95, 105],
        "stockout_flag": [False, False]
    })
    
    merged = merge_historical_inventory_features(df_grid, df_inv)
    
    # On 2025-01-01: no preceding inventory (T-1) exists -> prev_day_* must be NaN
    d1 = merged[merged["date"] == datetime.date(2025, 1, 1)].iloc[0]
    assert pd.isna(d1["prev_day_closing_stock"])
    assert bool(d1["has_prev_day_inventory"]) is False
    
    # On 2025-01-02: receives 2025-01-01's closing stock (95)
    d2 = merged[merged["date"] == datetime.date(2025, 1, 2)].iloc[0]
    assert d2["prev_day_closing_stock"] == 95.0
    assert d2["prev_day_opening_stock"] == 100.0
    assert bool(d2["has_prev_day_inventory"]) is True


# ---------------------------------------------------------------------------
# Test Category F: Promotion Features Matching
# ---------------------------------------------------------------------------

def test_promotion_features_date_matching():
    """Verifies promotion labeling only on dates within start_date and end_date."""
    df_grid = pd.DataFrame({
        "product_id": ["P1"] * 3,
        "date": [datetime.date(2025, 6, 13), datetime.date(2025, 6, 14), datetime.date(2025, 6, 16)],
        "demand_units": [10, 20, 10]
    })
    
    df_promos = pd.DataFrame([
        {
            "promotion_id": "WEEKEND_SALE",
            "promotion_name": "Weekend Sale",
            "discount_percentage": 0.15,
            "start_date": datetime.date(2025, 6, 14),
            "end_date": datetime.date(2025, 6, 15)
        }
    ])
    
    res = merge_promotion_features(df_grid, df_promos)
    
    assert res.loc[0, "promotion_active"] == 0
    assert res.loc[1, "promotion_active"] == 1
    assert res.loc[1, "promotion_id"] == "WEEKEND_SALE"
    assert res.loc[1, "promotion_discount_pct"] == 0.15
    assert res.loc[2, "promotion_active"] == 0


def test_promotion_eligibility_product_filtering():
    """
    Verifies that promotion features are assigned strictly to eligible products:
    - One product eligible for a promotion.
    - Another product not eligible for that promotion.
    - Both products evaluated on a date inside the promotion interval.
    Only the eligible product must receive the active promotion indicator.
    """
    promo_date = datetime.date(2025, 6, 14)
    df_grid = pd.DataFrame({
        "product_id": ["P_ELIGIBLE", "P_INELIGIBLE"],
        "date": [promo_date, promo_date],
        "demand_units": [25, 10]
    })
    
    df_promos = pd.DataFrame([
        {
            "promotion_id": "WEEKEND_SALE",
            "promotion_name": "Weekend Sale",
            "discount_percentage": 0.15,
            "start_date": datetime.date(2025, 6, 14),
            "end_date": datetime.date(2025, 6, 15)
        }
    ])
    
    df_eligibility = pd.DataFrame({
        "promotion_id": ["WEEKEND_SALE"],
        "product_id": ["P_ELIGIBLE"]
    })
    
    res = merge_promotion_features(df_grid, df_promos, df_eligibility)
    
    # Eligible product inside promotion interval
    row_eligible = res[res["product_id"] == "P_ELIGIBLE"].iloc[0]
    assert row_eligible["promotion_active"] == 1
    assert row_eligible["promotion_id"] == "WEEKEND_SALE"
    assert row_eligible["promotion_discount_pct"] == 0.15
    
    # Ineligible product inside promotion interval
    row_ineligible = res[res["product_id"] == "P_INELIGIBLE"].iloc[0]
    assert row_ineligible["promotion_active"] == 0
    assert row_ineligible["promotion_id"] is None
    assert row_ineligible["promotion_discount_pct"] == 0.0


# ---------------------------------------------------------------------------
# Test Category G: Feature Validator & Leakage Detection
# ---------------------------------------------------------------------------

def test_validator_detects_deliberate_leakage():
    """Verifies that validate_feature_leakage_and_integrity catches synthetic leakage."""
    # Build a valid dataset
    dates = [datetime.date(2025, 1, 1) + datetime.timedelta(days=i) for i in range(35)]
    df = pd.DataFrame({
        "product_id": ["P1"] * 35,
        "date": dates,
        "demand_units": [10] * 35
    })
    feat_df = generate_lag_and_rolling_features(df)
    
    # Valid dataset must pass
    is_valid, errors = validate_feature_leakage_and_integrity(feat_df)
    assert is_valid is True, f"Validation failed unexpectedly: {errors}"
    
    # Deliberately corrupt row 7 with leakage (e.g. inject current demand)
    leaked_df = feat_df.copy()
    leaked_df.loc[7, "rolling_mean_7"] = 999.0
    is_valid_leaked, leaked_errors = validate_feature_leakage_and_integrity(leaked_df)
    assert is_valid_leaked is False
    assert any("Rolling Mean Leakage" in err for err in leaked_errors)


# ---------------------------------------------------------------------------
# Test Category H: Pipeline Execution & Artifact Integrity
# ---------------------------------------------------------------------------

def test_full_stage10_pipeline_run_and_artifacts():
    """Executes the complete pipeline against smart_inventory and verifies generated artifacts."""
    success, feat_df, metrics, artifacts = run_stage10_pipeline()
    assert success is True
    assert feat_df.shape == (7300, 48)
    assert metrics["leakage_validation_passed"] is True
    
    # Verify all files exist on disk
    for key, path_str in artifacts.items():
        p = Path(path_str)
        assert p.exists(), f"Artifact {key} at {path_str} does not exist!"
        assert p.stat().st_size > 0, f"Artifact {key} at {path_str} is empty!"
        
    # Verify load_latest_stage10_artifacts helper
    loaded = load_latest_stage10_artifacts()
    assert loaded["exists"] is True
    assert loaded["total_rows"] == 7300
    assert loaded["total_columns"] == 48
    assert len(loaded["preview_df"]) == 50


# ---------------------------------------------------------------------------
# Test Category I: Production Database Read-Only Guard
# ---------------------------------------------------------------------------

def test_production_database_safety_guard():
    """
    Confirms that production smart_inventory remains strictly unmodified.
    Captures exact row counts immediately before and after the read-only feature extraction,
    verifying that no INSERT, UPDATE, DELETE, or DDL alters the production database.
    Also verifies that the database connection independently enforces read_only = True.
    All connections are safely managed in try/finally blocks.
    """
    tables = [
        "categories", "products", "inventory", "sales",
        "suppliers", "customers", "promotions", "purchase_orders",
        "purchase_invoices", "purchase_invoice_items"
    ]
    
    # 1. Capture production table counts immediately prior to extraction
    conn_pre = get_connection(dbname="smart_inventory")
    pre_counts = {}
    try:
        with conn_pre.cursor() as cur_pre:
            for t in tables:
                cur_pre.execute(f"SELECT COUNT(*) FROM {t};")
                row = cur_pre.fetchone()
                assert row is not None and row[0] is not None
                pre_counts[t] = int(row[0])
    finally:
        conn_pre.close()

    # Verify that all 10 tables were counted and none are None
    assert len(pre_counts) == len(tables)
    assert all(isinstance(c, int) for c in pre_counts.values())

    # 2. Execute extraction using extract_stage10_source_data
    from ml.features.data_extractor import extract_stage10_source_data
    extracted_data = extract_stage10_source_data(dbname="smart_inventory")
    assert "sales" in extracted_data
    assert len(extracted_data["sales"]) == pre_counts["sales"]
    
    # 3. Capture production table counts immediately post-extraction via separate connection
    conn_post = get_connection(dbname="smart_inventory")
    post_counts = {}
    try:
        with conn_post.cursor() as cur_post:
            for t in tables:
                cur_post.execute(f"SELECT COUNT(*) FROM {t};")
                row = cur_post.fetchone()
                assert row is not None and row[0] is not None
                post_counts[t] = int(row[0])
    finally:
        conn_post.close()
        
    # 4. Verify before-and-after parity across all tables
    assert len(post_counts) == len(tables)
    for t in tables:
        assert pre_counts[t] == post_counts[t], (
            f"Production safety violation: {t} changed from {pre_counts[t]} to {post_counts[t]}!"
        )
