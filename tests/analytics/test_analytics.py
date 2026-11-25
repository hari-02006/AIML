import pytest
import os
from database.db_connection import get_connection

def test_overall_metrics():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/overall_metrics.sql', 'r') as f:
                cur.execute(f.read())
                row = cur.fetchone()
                assert row is not None
                assert len(row) == 8
    finally:
        conn.close()

def test_demand_vs_observed():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/demand_vs_observed.sql', 'r') as f:
                cur.execute(f.read())
                row = cur.fetchone()
                assert row is not None
                # Check lost sales rate math logic
                # true_demand, observed_sales, lost_sales, rate
                true_demand, obs_sales, lost_sales, rate = row
                if true_demand > 0:
                    assert abs((float(lost_sales) / float(true_demand)) - float(rate)) < 0.01
    finally:
        conn.close()

def test_product_aggregation():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/product_analysis.sql', 'r') as f:
                cur.execute(f.read())
                rows = cur.fetchall()
                assert len(rows) > 0, "Product aggregation should return rows"
                assert len(rows[0]) == 8, "Product query should return exactly 8 columns"
    finally:
        conn.close()

def test_category_aggregation():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/category_performance.sql', 'r') as f:
                cur.execute(f.read())
                rows = cur.fetchall()
                assert len(rows) > 0, "Category aggregation should return rows"
                assert len(rows[0]) == 5, "Category query should return exactly 5 columns"
    finally:
        conn.close()

def test_inventory_aggregation():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/inventory_analysis.sql', 'r') as f:
                cur.execute(f.read())
                rows = cur.fetchall()
                assert len(rows) > 0, "Inventory aggregation should return rows"
                assert len(rows[0]) == 6, "Inventory query should return exactly 6 columns"
    finally:
        conn.close()

def test_sales_aggregation():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            with open('analytics/sql/sales_analysis.sql', 'r') as f:
                cur.execute(f.read())
                rows = cur.fetchall()
                assert len(rows) > 0, "Sales aggregation should return rows"
                assert len(rows[0]) == 4, "Sales query should return exactly 4 columns"
    finally:
        conn.close()
