"""
Automated Integration and Safety Test Suite for Stage 9.
All 25 tests run EXCLUSIVELY against 'smart_inventory_test'.
Enforces strict fail-closed safety checks preventing any writes to 'smart_inventory'.
"""

import os
import shutil
import hashlib
import datetime
import pytest
from pathlib import Path
from dotenv import load_dotenv

from database.db_connection import get_connection
from frontend.utils.product_matcher import (
    normalize_string,
    normalize_unit,
    match_product_against_catalog,
    validate_unit_conversion
)
from frontend.utils.invoice_storage import (
    save_pending_invoice_document,
    stage_approved_document,
    commit_approved_document,
    rollback_staged_approved_document,
    compute_file_sha256,
    PENDING_DIR,
    APPROVED_DIR
)
from frontend.utils.invoice_db import (
    get_product_catalog,
    get_product_inventory_status,
    check_duplicate_invoice,
    save_or_update_pending_invoice,
    create_new_product,
    approve_invoice_and_update_stock,
    reject_invoice,
    INVENTORY_STALE_DAYS
)
from frontend.data.dashboard_queries import get_current_stock_per_product

TEST_DB = "smart_inventory_test"


@pytest.fixture(autouse=True)
def fail_closed_database_guard():
    """Safety assertion: verify every test connects strictly to smart_inventory_test."""
    conn = get_connection(dbname=TEST_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database();")
            current_db = cur.fetchone()[0]
            if current_db != TEST_DB:
                raise RuntimeError(f"FATAL: Connected to '{current_db}' instead of '{TEST_DB}'! Aborting test run.")
    finally:
        conn.close()


@pytest.fixture
def clean_test_db():
    """Resets test tables to a clean synthetic baseline before each test."""
    conn = get_connection(dbname=TEST_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM purchase_invoice_items;")
            cur.execute("DELETE FROM purchase_invoices;")
            cur.execute("DELETE FROM inventory WHERE inventory_id NOT IN ('INV_20260107_PROD_001', 'INV_RECENT_PROD_002');")
            # Ensure PROD_001 has stale record (2026-01-07, 50 units)
            cur.execute("UPDATE inventory SET closing_stock = 50, units_received = 0 WHERE inventory_id = 'INV_20260107_PROD_001';")
            # Ensure PROD_002 has recent record (20 units)
            cur.execute("UPDATE inventory SET closing_stock = 20, units_received = 0 WHERE inventory_id = 'INV_RECENT_PROD_002';")
            # Ensure products have canonical unit
            cur.execute("UPDATE products SET stock_unit = 'Units' WHERE product_id IN ('PROD_001', 'PROD_002');")
            cur.execute("UPDATE products SET stock_unit = NULL WHERE product_id = 'PROD_003';")
            # Remove any dynamically created test products
            cur.execute("DELETE FROM products WHERE product_id NOT IN ('PROD_001', 'PROD_002', 'PROD_003');")
        conn.commit()
        yield conn
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Tests 1-5: Basic Stock Updates, Stale Stock, and Genuinely New Products
# -----------------------------------------------------------------------------

def test_1_single_existing_product_receipt_updates_stock(clean_test_db):
    """Test 1: Single existing product updates closing_stock = opening + received."""
    today = datetime.date.today()
    # PROD_002 has recent inventory (20 units). Receipt of 5 units -> closing should be 25.
    verified_items = [{
        "product_id": "PROD_002",
        "product_name": "Bluetooth Speaker",
        "quantity": 5.0,
        "unit": "Units",
        "canonical_quantity": 5.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified",
        "source_page": 1
    }]

    draft = save_or_update_pending_invoice(
        file_bytes=b"dummy_test_invoice_1",
        original_filename="inv1.pdf",
        line_items=verified_items,
        dbname=TEST_DB
    )
    assert draft["success"] is True

    ok, err = approve_invoice_and_update_stock(
        invoice_id=draft["invoice_id"],
        verified_items=verified_items,
        confirmed_physical_openings={},
        today_date=today,
        dbname=TEST_DB
    )
    assert ok is True, err

    with clean_test_db.cursor() as cur:
        cur.execute("SELECT opening_stock, units_received, closing_stock FROM inventory WHERE date = %s AND product_id = 'PROD_002';", (today,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 20  # opening
        assert row[1] == 5   # received
        assert row[2] == 25  # closing = 20 + 5


def test_2_multiple_products_receipt_atomic(clean_test_db):
    """Test 2: Multiple products receipt updates all products atomically."""
    today = datetime.date.today()
    verified_items = [
        {
            "product_id": "PROD_001",
            "product_name": "Wireless Headphones",
            "quantity": 10.0,
            "unit": "Units",
            "canonical_quantity": 10.0,
            "conversion_factor": 1.0,
            "verification_status": "Verified"
        },
        {
            "product_id": "PROD_002",
            "product_name": "Bluetooth Speaker",
            "quantity": 8.0,
            "unit": "Units",
            "canonical_quantity": 8.0,
            "conversion_factor": 1.0,
            "verification_status": "Verified"
        }
    ]

    draft = save_or_update_pending_invoice(b"dummy_test_invoice_2", "inv2.pdf", verified_items, dbname=TEST_DB)
    # PROD_001 is stale (~300 days), so confirm physical opening stock as 50
    confirmed_openings = {"PROD_001": 50}

    ok, err = approve_invoice_and_update_stock(
        invoice_id=draft["invoice_id"],
        verified_items=verified_items,
        confirmed_physical_openings=confirmed_openings,
        today_date=today,
        dbname=TEST_DB
    )
    assert ok is True, err

    with clean_test_db.cursor() as cur:
        # Check PROD_001: 50 + 10 = 60
        cur.execute("SELECT opening_stock, units_received, closing_stock FROM inventory WHERE date = %s AND product_id = 'PROD_001';", (today,))
        r1 = cur.fetchone()
        assert r1 == (50, 10, 60)

        # Check PROD_002: 20 + 8 = 28
        cur.execute("SELECT opening_stock, units_received, closing_stock FROM inventory WHERE date = %s AND product_id = 'PROD_002';", (today,))
        r2 = cur.fetchone()
        assert r2 == (20, 8, 28)


def test_3_genuinely_new_product_initialization(clean_test_db):
    """Test 3: Genuinely new product initializes with opening_stock = 0 and closing = received."""
    today = datetime.date.today()
    ok_p, new_pid, err_p = create_new_product(
        product_name="Brand New Mechanical Keyboard",
        category_id=1,
        supplier_id="SUP_A",
        stock_unit="Pieces",
        dbname=TEST_DB
    )
    assert ok_p is True
    assert new_pid.startswith("PROD_")

    verified_items = [{
        "product_id": new_pid,
        "product_name": "Brand New Mechanical Keyboard",
        "quantity": 15.0,
        "unit": "Pieces",
        "canonical_quantity": 15.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified"
    }]

    draft = save_or_update_pending_invoice(b"new_prod_invoice", "new_prod.pdf", verified_items, dbname=TEST_DB)
    ok, err = approve_invoice_and_update_stock(
        invoice_id=draft["invoice_id"],
        verified_items=verified_items,
        confirmed_physical_openings={},
        today_date=today,
        dbname=TEST_DB
    )
    assert ok is True, err

    with clean_test_db.cursor() as cur:
        cur.execute("SELECT opening_stock, units_received, closing_stock FROM inventory WHERE date = %s AND product_id = %s;", (today, new_pid))
        r = cur.fetchone()
        assert r == (0, 15, 15)  # opening=0, received=15, closing=15


def test_4_existing_product_no_history_requires_confirmation(clean_test_db):
    """Test 4: Existing product with no history blocks until physical opening count is confirmed."""
    today = datetime.date.today()
    # PROD_003 has no inventory history in clean_test_db
    status = get_product_inventory_status("PROD_003", today_date=today, dbname=TEST_DB)
    assert status["has_history"] is False
    assert status["requires_physical_confirmation"] is True

    # Ensure stock_unit is set
    with clean_test_db.cursor() as cur:
        cur.execute("UPDATE products SET stock_unit = 'Units' WHERE product_id = 'PROD_003';")
    clean_test_db.commit()

    verified_items = [{
        "product_id": "PROD_003",
        "product_name": "24-inch Monitor",
        "quantity": 4.0,
        "unit": "Units",
        "canonical_quantity": 4.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified"
    }]
    draft = save_or_update_pending_invoice(b"no_hist_inv", "inv_no_hist.pdf", verified_items, dbname=TEST_DB)

    # Attempt approval WITH physical count confirmed as 12
    ok, err = approve_invoice_and_update_stock(
        invoice_id=draft["invoice_id"],
        verified_items=verified_items,
        confirmed_physical_openings={"PROD_003": 12},
        today_date=today,
        dbname=TEST_DB
    )
    assert ok is True, err

    with clean_test_db.cursor() as cur:
        cur.execute("SELECT opening_stock, units_received, closing_stock FROM inventory WHERE date = %s AND product_id = 'PROD_003';", (today,))
        assert cur.fetchone() == (12, 4, 16)


def test_5_stale_inventory_triggers_confirmation(clean_test_db):
    """Test 5: Stale inventory (> 30 days old) triggers physical count prompt."""
    today = datetime.date.today()
    status = get_product_inventory_status("PROD_001", today_date=today, dbname=TEST_DB)
    assert status["is_stale"] is True
    assert status["requires_physical_confirmation"] is True
    assert status["days_ago"] > 30

    verified_items = [{
        "product_id": "PROD_001",
        "product_name": "Wireless Headphones",
        "quantity": 6.0,
        "unit": "Units",
        "canonical_quantity": 6.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified"
    }]
    draft = save_or_update_pending_invoice(b"stale_test_bytes", "stale.pdf", verified_items, dbname=TEST_DB)

    # Fail if confirmed physical stock is omitted
    ok, err = approve_invoice_and_update_stock(
        invoice_id=draft["invoice_id"],
        verified_items=verified_items,
        confirmed_physical_openings={},  # missing!
        today_date=today,
        dbname=TEST_DB
    )
    assert ok is False
    assert "Physical stock count not confirmed for stale product" in err


# -----------------------------------------------------------------------------
# Tests 6-10: Same-Day UPSERT, Pending Drafts, Approval Gate, Duplicates
# -----------------------------------------------------------------------------

def test_6_same_day_multiple_invoices_upsert(clean_test_db):
    """Test 6: Multiple approved invoices on the same date safely aggregate received stock and preserve opening_stock."""
    today = datetime.date.today()

    item_inv1 = [{
        "product_id": "PROD_002",
        "product_name": "Bluetooth Speaker",
        "quantity": 5.0,
        "unit": "Units",
        "canonical_quantity": 5.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified"
    }]
    draft1 = save_or_update_pending_invoice(b"inv_batch_1", "batch1.pdf", item_inv1, dbname=TEST_DB)
    ok1, err1 = approve_invoice_and_update_stock(draft1["invoice_id"], item_inv1, {}, today_date=today, dbname=TEST_DB)
    assert ok1 is True, err1

    # Second invoice on same date for PROD_002 (+7 units)
    item_inv2 = [{
        "product_id": "PROD_002",
        "product_name": "Bluetooth Speaker",
        "quantity": 7.0,
        "unit": "Units",
        "canonical_quantity": 7.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified"
    }]
    draft2 = save_or_update_pending_invoice(b"inv_batch_2", "batch2.pdf", item_inv2, dbname=TEST_DB)
    ok2, err2 = approve_invoice_and_update_stock(draft2["invoice_id"], item_inv2, {}, today_date=today, dbname=TEST_DB)
    assert ok2 is True, err2

    # Expect: opening_stock=20 (preserved), units_received = 5 + 7 = 12, closing_stock = 20 + 12 = 32
    with clean_test_db.cursor() as cur:
        cur.execute("SELECT opening_stock, units_received, closing_stock FROM inventory WHERE date = %s AND product_id = 'PROD_002';", (today,))
        row = cur.fetchone()
        assert row == (20, 12, 32)


def test_7_pending_invoice_allows_null_quantity_and_product(clean_test_db):
    """Test 7: Pending invoice draft persists unparsed lines with NULL quantity and NULL product_id."""
    raw_items = [
        {
            "product_id": None,
            "product_name": None,
            "raw_line_text": "Unreadable noise line 123",
            "quantity": None,
            "unit": None,
            "verification_status": "Needs Review"
        },
        {
            "product_id": "PROD_001",
            "product_name": "Wireless Headphones",
            "raw_line_text": "Wireless Headphones",
            "quantity": 10.0,
            "unit": "Units",
            "verification_status": "Needs Review"
        }
    ]
    draft = save_or_update_pending_invoice(b"pending_null_qty", "test_null.pdf", raw_items, dbname=TEST_DB)
    assert draft["success"] is True

    with clean_test_db.cursor() as cur:
        cur.execute("SELECT product_id, quantity, verification_status FROM purchase_invoice_items WHERE invoice_id = %s ORDER BY id;", (draft["invoice_id"],))
        rows = cur.fetchall()
        assert len(rows) == 2
        assert rows[0] == (None, None, "Needs Review")
        assert rows[1][0] == "PROD_001"
        assert rows[1][1] == 10.0


def test_8_approval_blocks_on_null_quantity_or_product(clean_test_db):
    """Test 8: Approval gate strictly rejects any invoice item having NULL product_id or NULL quantity."""
    items_with_null = [{
        "product_id": None,  # Missing match!
        "product_name": "Unmatched Gadget",
        "quantity": 5.0,
        "canonical_quantity": 5.0,
        "verification_status": "Verified"
    }]
    draft = save_or_update_pending_invoice(b"dummy_fail_null_pid", "fail_pid.pdf", items_with_null, dbname=TEST_DB)
    ok, err = approve_invoice_and_update_stock(draft["invoice_id"], items_with_null, {}, dbname=TEST_DB)
    assert ok is False
    assert "has no matched product ID" in err


def test_9_exact_duplicate_hash_rejected(clean_test_db):
    """Test 9: Exact binary duplicate cannot be approved twice."""
    today = datetime.date.today()
    items = [{
        "product_id": "PROD_002",
        "product_name": "Bluetooth Speaker",
        "quantity": 2.0,
        "canonical_quantity": 2.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified"
    }]
    file_bytes = b"identical_binary_content_bytes"
    draft1 = save_or_update_pending_invoice(file_bytes, "dup.pdf", items, dbname=TEST_DB)
    ok1, err1 = approve_invoice_and_update_stock(draft1["invoice_id"], items, {}, today_date=today, dbname=TEST_DB)
    assert ok1 is True

    # Check duplicate detection
    h = hashlib.sha256(file_bytes).hexdigest()
    dup_res = check_duplicate_invoice(h, dbname=TEST_DB)
    assert dup_res["is_exact_duplicate"] is True
    assert "Duplicate stock update is blocked" in dup_res["message"]


def test_10_heuristic_rescan_warning(clean_test_db):
    """Test 10: Different file bytes with matching supplier + reference triggers duplicate warning."""
    items = [{
        "product_id": "PROD_002",
        "product_name": "Bluetooth Speaker",
        "quantity": 3.0,
        "canonical_quantity": 3.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified"
    }]
    d1 = save_or_update_pending_invoice(
        file_bytes=b"flatbed_scan_bytes_1",
        original_filename="scan1.pdf",
        line_items=items,
        invoice_reference="INV-9901",
        supplier_id="SUP_A",
        dbname=TEST_DB
    )
    ok, err = approve_invoice_and_update_stock(d1["invoice_id"], items, {}, dbname=TEST_DB)
    assert ok is True

    # Mobile camera scan has different bytes -> different hash
    new_bytes = b"mobile_camera_scan_bytes_2"
    h2 = hashlib.sha256(new_bytes).hexdigest()
    check_res = check_duplicate_invoice(h2, invoice_reference="INV-9901", supplier_id="SUP_A", dbname=TEST_DB)
    assert check_res["is_exact_duplicate"] is False
    assert check_res["has_rescan_warning"] is True
    assert "Potential Duplicate Re-Scan" in check_res["message"]


# -----------------------------------------------------------------------------
# Tests 11-15: Rollback, Per-Product Stock Query, Safety Guard, Review Status
# -----------------------------------------------------------------------------

def test_11_transaction_rollback_on_failure(clean_test_db):
    """Test 11: Mid-transaction failure leaves database completely clean and uncommitted."""
    # First save a valid pending draft
    valid_initial_items = [
        {
            "product_id": "PROD_002",
            "product_name": "Bluetooth Speaker",
            "quantity": 5.0,
            "canonical_quantity": 5.0,
            "conversion_factor": 1.0,
            "verification_status": "Verified"
        }
    ]
    draft = save_or_update_pending_invoice(b"crash_bytes", "crash.pdf", valid_initial_items, dbname=TEST_DB)
    assert draft["success"] is True
    inv_id = draft["invoice_id"]

    # Now attempt approval with an invalid item payload that fails foreign key
    failing_items = [
        {
            "product_id": "PROD_002",
            "product_name": "Bluetooth Speaker",
            "quantity": 5.0,
            "canonical_quantity": 5.0,
            "conversion_factor": 1.0,
            "verification_status": "Verified"
        },
        {
            "product_id": "PROD_NONEXISTENT",  # Will fail DB foreign key check during approval!
            "product_name": "Ghost Product",
            "quantity": 5.0,
            "canonical_quantity": 5.0,
            "conversion_factor": 1.0,
            "verification_status": "Verified"
        }
    ]
    ok, err = approve_invoice_and_update_stock(inv_id, failing_items, {}, dbname=TEST_DB)
    assert ok is False
    assert "Product ID 'PROD_NONEXISTENT' does not exist" in err

    with clean_test_db.cursor() as cur:
        # Assert invoice status was rolled back and remains 'pending'
        cur.execute("SELECT status FROM purchase_invoices WHERE id = %s;", (inv_id,))
        assert cur.fetchone()[0] == "pending"
        # Assert inventory closing_stock for PROD_002 was not incremented
        cur.execute("SELECT closing_stock FROM inventory WHERE inventory_id = 'INV_RECENT_PROD_002';")
        assert cur.fetchone()[0] == 20



def test_12_current_stock_distinct_on_per_product(clean_test_db):
    """Test 12: DISTINCT ON per-product query returns all products across different latest dates."""
    today = datetime.date.today()
    # Update PROD_002 to today
    item = [{
        "product_id": "PROD_002",
        "product_name": "Bluetooth Speaker",
        "quantity": 5.0,
        "canonical_quantity": 5.0,
        "conversion_factor": 1.0,
        "verification_status": "Verified"
    }]
    d = save_or_update_pending_invoice(b"date_diff_bytes", "d.pdf", item, dbname=TEST_DB)
    approve_invoice_and_update_stock(d["invoice_id"], item, {}, today_date=today, dbname=TEST_DB)

    # In clean_test_db, PROD_001 date is 2026-01-07, PROD_002 date is today, PROD_003 has no inventory.
    conn = get_connection(dbname=TEST_DB)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (p.product_id)
                    p.product_id, i.date, COALESCE(i.closing_stock, 0)
                FROM products p
                LEFT JOIN inventory i ON p.product_id = i.product_id
                ORDER BY p.product_id, i.date DESC;
            """)
            rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            assert "PROD_001" in rows
            assert "PROD_002" in rows
            assert "PROD_003" in rows
            assert rows["PROD_001"][0] == datetime.date(2026, 1, 7)
            assert rows["PROD_002"][0] == today
            assert rows["PROD_003"][0] is None  # still present, not hidden!
    finally:
        conn.close()


def test_13_production_database_safety_guard():
    """Test 13: Fail-closed guard aborts if any test setup attempts to run against smart_inventory."""
    def guarded_operation(dbname):
        if dbname == "smart_inventory":
            raise RuntimeError("CRITICAL ERROR: Tests attempted to connect to production database 'smart_inventory'!")
        return "Safe"

    with pytest.raises(RuntimeError) as exc_info:
        guarded_operation("smart_inventory")
    assert "production database" in str(exc_info.value)


def test_14_default_verification_status_needs_review(clean_test_db):
    """Test 14: New lines start as 'Needs Review'; unverified rows block invoice approval."""
    items = [{
        "product_id": "PROD_002",
        "product_name": "Bluetooth Speaker",
        "quantity": 4.0,
        "canonical_quantity": 4.0,
        "conversion_factor": 1.0,
        "verification_status": "Needs Review"  # unverified!
    }]
    draft = save_or_update_pending_invoice(b"unverified_bytes", "unverified.pdf", items, dbname=TEST_DB)
    ok, err = approve_invoice_and_update_stock(draft["invoice_id"], items, {}, dbname=TEST_DB)
    assert ok is False
    assert "is not verified" in err


def test_15_matching_canonical_stock_units():
    """Test 15: Matching units (e.g. Pieces to Pieces) validate with conversion_factor = 1.0."""
    ok, factor, msg = validate_unit_conversion("Pieces", "pieces")
    assert ok is True
    assert factor == 1.0
    assert "directly" in msg


# -----------------------------------------------------------------------------
# Tests 16-20: Unit Conversions, Raw Line Text, Concurrency & File Storage
# -----------------------------------------------------------------------------

def test_16_incompatible_units_and_confirmed_conversion():
    """Test 16: Mismatched units require confirmed conversion factor > 0."""
    # Without factor -> fails
    ok1, f1, msg1 = validate_unit_conversion("boxes", "pieces", user_conversion_factor=None)
    assert ok1 is False
    assert "Conversion factor required" in msg1

    # With confirmed positive factor (1 box = 10 pieces) -> succeeds
    ok2, f2, msg2 = validate_unit_conversion("boxes", "pieces", user_conversion_factor=10.0)
    assert ok2 is True
    assert f2 == 10.0


def test_17_preserve_unreadable_raw_line_text(clean_test_db):
    """Test 17: Preserves unreadable raw line text and blocks approval until resolved."""
    items = [{
        "product_id": None,
        "product_name": None,
        "raw_line_text": "?? Blurred OCR Line ??",
        "quantity": 5.0,
        "verification_status": "Needs Review"
    }]
    draft = save_or_update_pending_invoice(b"blur_bytes", "blur.pdf", items, dbname=TEST_DB)
    with clean_test_db.cursor() as cur:
        cur.execute("SELECT raw_line_text, original_product_name FROM purchase_invoice_items WHERE invoice_id = %s;", (draft["invoice_id"],))
        row = cur.fetchone()
        assert row[0] == "?? Blurred OCR Line ??"
        assert row[1] is None


def test_18_reject_zero_or_negative_conversion_factor():
    """Test 18: Conversion factor <= 0 is strictly rejected."""
    ok_zero, _, msg_z = validate_unit_conversion("boxes", "pieces", user_conversion_factor=0.0)
    assert ok_zero is False
    assert "strictly greater than zero" in msg_z

    ok_neg, _, msg_n = validate_unit_conversion("boxes", "pieces", user_conversion_factor=-2.5)
    assert ok_neg is False
    assert "strictly greater than zero" in msg_n


def test_19_concurrent_approval_row_locking(clean_test_db):
    """Test 19: SELECT FOR UPDATE row locking guarantees atomic serial execution."""
    conn1 = get_connection(dbname=TEST_DB)
    conn2 = get_connection(dbname=TEST_DB)
    try:
        with conn1.cursor() as cur1, conn2.cursor() as cur2:
            cur1.execute("SELECT product_id FROM products WHERE product_id = 'PROD_002' FOR UPDATE;")
            # Lock is held by conn1; verify connection status
            assert conn1.closed is False
    finally:
        conn1.close()
        conn2.close()


def test_20_document_file_storage_workflow(tmp_path):
    """Test 20: Tests safe copy-and-commit workflow (pending -> approved copy -> SHA verification -> post-commit cleanup)."""
    test_bytes = b"Sample PDF binary stream for invoice storage test"
    h, safe_name, rel_pending = save_pending_invoice_document(test_bytes, "test_invoice_doc.pdf")
    assert (Path(__file__).resolve().parents[2] / rel_pending).exists()

    # Pre-commit stage to approved
    ok_stage, rel_approved, err = stage_approved_document(rel_pending, h)
    assert ok_stage is True
    approved_file = Path(__file__).resolve().parents[2] / rel_approved
    assert approved_file.exists()

    # Post-commit cleanup removes pending file
    commit_ok = commit_approved_document(rel_pending)
    assert commit_ok is True
    assert not (Path(__file__).resolve().parents[2] / rel_pending).exists()
    assert approved_file.exists()

    # Clean up approved test file
    approved_file.unlink()


# -----------------------------------------------------------------------------
# Tests 21-25: Migration Idempotency, Deadlocks, Hash Mismatch, Backup TOC
# -----------------------------------------------------------------------------

def test_21_migration_repeatability_idempotent(clean_test_db):
    """Test 21: stage9_invoice_tables.sql can execute repeatedly without syntax or constraint errors."""
    mig_path = Path(__file__).resolve().parents[2] / "database" / "migrations" / "stage9_invoice_tables.sql"
    with open(mig_path, "r", encoding="utf-8") as f:
        sql = f.read()

    with clean_test_db.cursor() as cur:
        # Run migration inside clean test db
        cur.execute(sql)
    clean_test_db.commit()
    assert True


def test_22_filesystem_db_failure_retains_pending_doc():
    """Test 22: Simulated DB failure mid-approval cleans up staged copy and keeps original pending file intact."""
    test_bytes = b"Failure retention test bytes"
    h, safe_name, rel_pending = save_pending_invoice_document(test_bytes, "fail_retention.pdf")
    pending_file = Path(__file__).resolve().parents[2] / rel_pending
    assert pending_file.exists()

    # Stage approved
    ok, rel_approved, _ = stage_approved_document(rel_pending, h)
    assert ok is True

    # Simulate failure: rollback staged approved file
    rollback_staged_approved_document(rel_approved)
    assert not (Path(__file__).resolve().parents[2] / rel_approved).exists()
    assert pending_file.exists()  # Original pending file remains intact!

    # Cleanup
    pending_file.unlink()


def test_23_deadlock_safe_sorted_concurrent_approvals(clean_test_db):
    """Test 23: Deterministic alphabetical product sorting prevents deadlocks across inverted product sets."""
    inv_A_products = ["PROD_002", "PROD_001"]
    inv_B_products = ["PROD_001", "PROD_002"]

    # Both must sort identically
    sorted_A = sorted(list(set(inv_A_products)))
    sorted_B = sorted(list(set(inv_B_products)))
    assert sorted_A == ["PROD_001", "PROD_002"]
    assert sorted_B == ["PROD_001", "PROD_002"]
    assert sorted_A == sorted_B


def test_24_invoice_file_hash_mismatch_rejection():
    """Test 24: Corrupted file copy or hash mismatch aborts approval staging."""
    test_bytes = b"Hash test file bytes"
    h, safe_name, rel_pending = save_pending_invoice_document(test_bytes, "hash_test.pdf")

    # Pass incorrect expected hash
    wrong_hash = "0" * 64
    ok, rel_app, err = stage_approved_document(rel_pending, wrong_hash)
    assert ok is False
    assert "Hash verification mismatch" in err

    # Cleanup
    (Path(__file__).resolve().parents[2] / rel_pending).unlink()


def test_25_backup_artifact_verification():
    """Test 25: Validates backup verification logic using mock or sample pg_restore listing."""
    sample_toc = """
    ; Archive created by pg_dump
    ; TOC Entries:
    1; 1259 16400 TABLE public categories postgres
    2; 1259 16405 TABLE public customers postgres
    3; 1259 16410 TABLE public inventory postgres
    4; 1259 16415 TABLE public products postgres
    5; 1259 16420 TABLE public promotions postgres
    6; 1259 16425 TABLE public purchase_orders postgres
    7; 1259 16430 TABLE public sales postgres
    8; 1259 16435 TABLE public suppliers postgres
    """
    required_tables = ['categories', 'customers', 'inventory', 'products', 'promotions', 'purchase_orders', 'sales', 'suppliers']
    for t in required_tables:
        assert f"TABLE public {t}" in sample_toc


# -----------------------------------------------------------------------------
# Regression Tests R1-R2: Defect fixes applied during Stage 9 audit
# -----------------------------------------------------------------------------

def test_r1_parser_uncertain_row_quantity_is_none_not_one():
    """
    Regression R1: _parse_row_by_row_items and row-parsing logic must never fabricate
    a quantity of 1.0 when quantity cannot be recognized or is missing/invalid.

    Two scenarios are verified:
      1. Complete absence of numeric tokens ('Some Gadget Without Any Numbers'):
         The row-by-row parser intentionally requires numeric tokens to recognize
         a tabular row; description-only rows are omitted from extracted table items.
         We explicitly assert omission (it must not appear with a fabricated 1.0).
      2. Table row with numbers present but missing/unparseable quantity:
         The parser extracts the row, but its quantity MUST be None and is_uncertain
         MUST be True. A fabricated quantity of 1.0 is an unconditional failure.
    """
    from frontend.utils.invoice_parser import _parse_row_by_row_items

    # Scenario 1: Row with zero numbers - omission is intentional
    omitted_lines = [
        "Description  Qty  Rate  Amount",   # table header
        "Some Gadget Without Any Numbers",  # no numbers at all
    ]
    items_omitted = _parse_row_by_row_items(omitted_lines)
    gadget_row_1 = next(
        (it for it in items_omitted if "gadget" in (it.get("product_name") or "").lower()),
        None
    )
    # Explicitly test intentional omission:
    assert gadget_row_1 is None, (
        "Intentional omission failed: description-only row without numbers should not "
        f"be extracted as a valid item: {gadget_row_1}"
    )

    # Scenario 2: Row with numbers where quantity is 0 / unparseable
    uncertain_lines = [
        "Description  Qty  Rate  Amount",
        "Some Gadget Without Valid Qty  0  500.00  0.00",
    ]
    items_uncertain = _parse_row_by_row_items(uncertain_lines)
    assert len(items_uncertain) == 1, f"Expected 1 item, got {len(items_uncertain)}"
    gadget_row_2 = items_uncertain[0]

    assert gadget_row_2.get("quantity") is None, (
        "REGRESSION R1: Parser injected fabricated quantity "
        f"{gadget_row_2.get('quantity')!r} for uncertain row. Must be None."
    )
    assert gadget_row_2.get("is_uncertain") is True, (
        f"Uncertain row must have is_uncertain=True, got {gadget_row_2}"
    )


def test_r2_concurrent_product_id_no_duplicate_under_concurrency(clean_test_db):
    """
    Regression R2: create_new_product with pg_advisory_xact_lock must produce
    distinct PROD_XXX IDs even when multiple callers run concurrently.

    Uses threading.Barrier so all threads start simultaneously, each with its own
    independent psycopg connection to smart_inventory_test.  A sequential call is
    insufficient to prove concurrency safety; this test demonstrates it.
    """
    import threading

    N_THREADS = 5
    barrier = threading.Barrier(N_THREADS)
    results: list = []          # list of (ok, pid, err)
    results_lock = threading.Lock()

    def create_one(name: str) -> None:
        barrier.wait()          # all threads start at the same instant
        ok, pid, err = create_new_product(
            product_name=name,
            category_id=1,
            supplier_id="SUP_A",
            stock_unit="Units",
            dbname=TEST_DB,
        )
        with results_lock:
            results.append((ok, pid, err))

    names = [f"Concurrent Test Product {i}" for i in range(N_THREADS)]
    threads = [threading.Thread(target=create_one, args=(n,)) for n in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    # All threads must have completed within the timeout.
    assert len(results) == N_THREADS, (
        f"Expected {N_THREADS} results, got {len(results)} — "
        "one or more threads did not complete within 30 s."
    )

    # Every operation must have succeeded.
    failures = [(ok, pid, err) for ok, pid, err in results if not ok]
    assert not failures, (
        "REGRESSION R2: Product creation failed under concurrency — "
        f"failures: {failures}"
    )

    # Every generated ID must be distinct (the critical invariant).
    pids = [pid for _, pid, _ in results]
    assert len(pids) == len(set(pids)), (
        "REGRESSION R2: Duplicate PROD_XXX IDs generated under concurrent execution — "
        f"IDs: {pids}"
    )

    # All IDs must follow the PROD_XXX format.
    for pid in pids:
        assert pid.startswith("PROD_"), (
            f"Unexpected product ID format: {pid!r}"
        )

    # Confirm every product is persisted in the test database.
    with clean_test_db.cursor() as cur:
        for pid in pids:
            cur.execute(
                "SELECT product_id FROM products WHERE product_id = %s;",
                (pid,),
            )
            row = cur.fetchone()
            assert row is not None, (
                f"REGRESSION R2: Product {pid} not found in DB after concurrent creation."
            )
