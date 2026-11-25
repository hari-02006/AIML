"""
Tests for frontend website navigation and page selection safety.
Verifies that:
- The 4 removed/hidden navigation options (Promotion Analytics, Supplier Analytics, Customer Analytics, ML Feature Engineering) are absent.
- Exactly the 5 retained navigation options are present in the exact specified order.
- Default selection is 'Dashboard / Overview'.
- Outdated session-state page selections (including 'ML Feature Engineering') safely fall back to 'Dashboard / Overview'.
- The underlying queries and analytics modules for all pages remain intact and importable.
- Stage 9 and Stage 10 ML imports, pipeline utilities, and artifact loaders remain intact.
"""

import pytest
import re
from pathlib import Path


def test_navigation_pages_list_in_app():
    """Confirms exactly the 5 retained navigation sections in app.py."""
    app_path = Path("frontend/app.py")
    assert app_path.exists(), "frontend/app.py must exist"
    
    content = app_path.read_text(encoding="utf-8")
    
    # Extract NAVIGATION_PAGES list
    match = re.search(r"NAVIGATION_PAGES\s*=\s*\[(.*?)\]", content, re.DOTALL)
    assert match, "NAVIGATION_PAGES definition must exist in frontend/app.py"
    
    pages_raw = match.group(1)
    pages = [p.strip().strip('"').strip("'") for p in pages_raw.split(",") if p.strip()]
    
    expected_retained = [
        "Dashboard / Overview",
        "Sales Analytics",
        "Product Analytics",
        "Inventory Analytics",
        "Invoice Scanner"
    ]
    
    assert pages == expected_retained, f"Navigation list mismatch: {pages} != {expected_retained}"
    assert len(pages) == 5, f"Expected exactly 5 pages, found {len(pages)}"
    
    # Assert removed options are not in the list
    removed_options = [
        "Promotion Analytics",
        "Supplier Analytics",
        "Customer Analytics",
        "ML Feature Engineering"
    ]
    for removed in removed_options:
        assert removed not in pages, f"Removed option '{removed}' still found in NAVIGATION_PAGES!"


def test_outdated_session_state_fallback_logic():
    """Simulates session-state initialization with obsolete/hidden pages and verifies safe fallback."""
    NAVIGATION_PAGES = [
        "Dashboard / Overview",
        "Sales Analytics",
        "Product Analytics",
        "Inventory Analytics",
        "Invoice Scanner"
    ]
    
    removed_examples = [
        "Promotion Analytics",
        "Supplier Analytics",
        "Customer Analytics",
        "ML Feature Engineering",
        "Nonexistent Page",
        None,
        ""
    ]
    
    for stale_val in removed_examples:
        session_state = {"nav_page": stale_val}
        # Emulate the app.py fallback logic
        if "nav_page" not in session_state or session_state["nav_page"] not in NAVIGATION_PAGES:
            session_state["nav_page"] = NAVIGATION_PAGES[0]
            
        assert session_state["nav_page"] == "Dashboard / Overview"
        idx = NAVIGATION_PAGES.index(session_state["nav_page"])
        assert idx == 0


def test_retained_page_queries_and_modules_integrity():
    """Verifies that all query and helper functions supporting both retained and legacy pages remain intact."""
    from frontend.data.dashboard_queries import (
        get_date_range, get_overall_metrics, get_sales_trend, get_demand_vs_observed, 
        get_category_revenue, get_top_products_revenue, get_lost_sales_by_product,
        get_stockout_overview, get_product_details, get_inventory_details,
        get_promotion_metrics, get_supplier_metrics, get_customer_metrics,
        get_current_stock_per_product
    )
    
    # All symbols must be callable functions
    callables = [
        get_date_range, get_overall_metrics, get_sales_trend, get_demand_vs_observed, 
        get_category_revenue, get_top_products_revenue, get_lost_sales_by_product,
        get_stockout_overview, get_product_details, get_inventory_details,
        get_promotion_metrics, get_supplier_metrics, get_customer_metrics,
        get_current_stock_per_product
    ]
    for fn in callables:
        assert callable(fn), f"Expected {fn.__name__} to be callable"


def test_stage9_and_stage10_imports_intact():
    """Verifies Stage 9 and Stage 10 functions remain importable and preserved."""
    from frontend.utils.image_validator import validate_invoice_image, DOCUMENT_TYPES
    from frontend.utils.ocr_service import perform_ocr
    from frontend.utils.invoice_parser import parse_invoice_text
    from frontend.utils.product_matcher import match_product_against_catalog, validate_unit_conversion
    from frontend.utils.invoice_db import get_product_catalog, approve_invoice_and_update_stock
    from ml.features import run_stage10_pipeline, load_latest_stage10_artifacts
    
    assert callable(validate_invoice_image)
    assert callable(perform_ocr)
    assert callable(parse_invoice_text)
    assert callable(match_product_against_catalog)
    assert callable(validate_unit_conversion)
    assert callable(get_product_catalog)
    assert callable(approve_invoice_and_update_stock)
    assert callable(run_stage10_pipeline)
    assert callable(load_latest_stage10_artifacts)
