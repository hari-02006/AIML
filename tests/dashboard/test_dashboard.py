import pytest
import pandas as pd
from frontend.data.dashboard_queries import (
    get_overall_metrics, get_sales_trend, get_demand_vs_observed,
    get_category_revenue, get_top_products_revenue, get_lost_sales_by_product,
    get_stockout_overview
)

def test_overall_metrics_structure():
    df = get_overall_metrics()
    assert not df.empty
    assert 'total_revenue' in df.columns
    assert 'total_units_sold' in df.columns
    assert 'total_transactions' in df.columns
    assert 'current_inventory' in df.columns

def test_sales_trend():
    df = get_sales_trend()
    assert not df.empty
    assert 'date' in df.columns
    assert 'revenue' in df.columns

def test_product_query():
    df = get_top_products_revenue()
    assert not df.empty
    assert 'product_name' in df.columns
    assert 'revenue' in df.columns

def test_inventory_query():
    df = get_stockout_overview()
    assert not df.empty
    assert 'products_with_stockouts' in df.columns

def test_overall_metrics_date_filtering():
    df = get_overall_metrics('2025-01-01', '2025-12-31')
    assert not df.empty
    assert df.iloc[0]['total_lost_sales'] == 729
    assert df.iloc[0]['stockout_product_days'] == 50

