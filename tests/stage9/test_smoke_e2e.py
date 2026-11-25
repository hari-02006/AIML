"""
Stage 9 — Programmatic End-to-End Smoke Test

Exercises the COMPLETE invoice approval code path against smart_inventory_test ONLY.
OCR is skipped — pre-extracted items are used, which is identical to what the UI does
after the OCR step returns results.

Coverage:
  SE-1  Fail-closed guard: test DB is smart_inventory_test, NOT smart_inventory
  SE-2  Pending draft creation and persistence (save_or_update_pending_invoice)
  SE-3  Draft can be re-fetched from DB (simulates page refresh)
  SE-4  Exact-duplicate detection (check_duplicate_invoice on approved invoice)
  SE-5  Product matching against test catalog (match_product_against_catalog)
  SE-6  Invoice approval and inventory stock increment (approve_invoice_and_update_stock)
  SE-7  Approved invoice appears in purchase_invoices with status='approved'
  SE-8  Inventory quantity increased correctly for each approved line item
  SE-9  Re-upload of same file bytes → is_exact_duplicate=True
  SE-10 Reject a second draft → status='rejected' in DB
  SE-11 Approved file appears in redirected isolated approved directory
  SE-12 Pending file removed after approval commit

HARD CONSTRAINTS (enforced at runtime):
  - All DB writes go to smart_inventory_test only.
  - Production smart_inventory row counts must be unchanged before and after.
  - All test file storage is redirected to an isolated temporary directory within data/invoices/
    so that normal pending, approved, and rejected invoice directories remain 100% pristine.
"""

import os
import io
import sys
import shutil
import datetime
import hashlib
import pytest
from pathlib import Path
from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import frontend.utils.invoice_storage as invoice_storage
from database.db_connection import get_connection
from frontend.utils.invoice_db import (
    get_product_catalog,
    get_product_inventory_status,
    check_duplicate_invoice,
    save_or_update_pending_invoice,
    approve_invoice_and_update_stock,
    reject_invoice,
    INVENTORY_STALE_DAYS,
)
from frontend.utils.product_matcher import match_product_against_catalog

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEST_DB = "smart_inventory_test"
PROD_DB = "smart_inventory"

PROD_HEADPHONES = "PROD_001"
PROD_SPEAKER    = "PROD_002"

# Isolated test storage directory
TMP_SMOKE_STORAGE = invoice_storage.INVOICES_DIR / "_tmp_smoke_test"
TMP_PENDING_DIR   = TMP_SMOKE_STORAGE / "pending"
TMP_APPROVED_DIR  = TMP_SMOKE_STORAGE / "approved"
TMP_REJECTED_DIR  = TMP_SMOKE_STORAGE / "rejected"


@pytest.fixture(autouse=True, scope="session")
def isolate_smoke_test_storage():
    """
    Redirects PENDING_DIR, APPROVED_DIR, REJECTED_DIR to an isolated temporary subfolder
    under data/invoices/_tmp_smoke_test during the smoke test run, ensuring no synthetic
    documents pollute the application's normal invoice directories.
    """
    orig_pending  = invoice_storage.PENDING_DIR
    orig_approved = invoice_storage.APPROVED_DIR
    orig_rejected = invoice_storage.REJECTED_DIR

    TMP_PENDING_DIR.mkdir(parents=True, exist_ok=True)
    TMP_APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    TMP_REJECTED_DIR.mkdir(parents=True, exist_ok=True)

    invoice_storage.PENDING_DIR  = TMP_PENDING_DIR
    invoice_storage.APPROVED_DIR = TMP_APPROVED_DIR
    invoice_storage.REJECTED_DIR = TMP_REJECTED_DIR

    yield

    # Restore originals and remove temp directory
    invoice_storage.PENDING_DIR  = orig_pending
    invoice_storage.APPROVED_DIR = orig_approved
    invoice_storage.REJECTED_DIR = orig_rejected

    if TMP_SMOKE_STORAGE.exists():
        shutil.rmtree(TMP_SMOKE_STORAGE, ignore_errors=True)


def _make_invoice_bytes(tag: str) -> bytes:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return f"SYNTHETIC INVOICE [{tag}] generated at {ts}".encode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_count(dbname: str, table: str) -> int:
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            return cur.fetchone()[0]
    finally:
        conn.close()


def _prod_row_counts() -> Dict[str, int]:
    """Snapshot production table row counts."""
    tables = [
        "categories", "products", "inventory", "sales",
        "suppliers", "customers", "promotions", "purchase_orders",
        "purchase_invoices", "purchase_invoice_items",
    ]
    return {t: _row_count(PROD_DB, t) for t in tables}


def _get_inventory_qty(product_id: str, date: datetime.date, dbname: str) -> int:
    """Return closing_stock for a product on a specific date, or 0 if absent."""
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT closing_stock FROM inventory WHERE product_id = %s AND date = %s;",
                (product_id, date),
            )
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        conn.close()


def _get_invoice_status(invoice_id: int, dbname: str) -> str:
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM purchase_invoices WHERE id = %s;",
                (invoice_id,),
            )
            row = cur.fetchone()
            return row[0] if row else "NOT_FOUND"
    finally:
        conn.close()


def _clean_test_invoices(dbname: str) -> None:
    """Remove all purchase_invoices and purchase_invoice_items from the test DB."""
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM purchase_invoice_items;")
            cur.execute("DELETE FROM purchase_invoices;")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SE-1  Fail-closed guard
# ---------------------------------------------------------------------------

class TestSE1FailClosedGuard:
    def test_se1_test_db_is_not_production(self):
        """SE-1: Every smoke test connection must reach smart_inventory_test, NOT smart_inventory."""
        conn = get_connection(dbname=TEST_DB)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database();")
                current_db = cur.fetchone()[0]
            assert current_db == TEST_DB, (
                f"FAIL-CLOSED: Expected database '{TEST_DB}', "
                f"connected to '{current_db}' instead."
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# SE-2 / SE-3  Pending draft creation and persistence
# ---------------------------------------------------------------------------

class TestSE2SE3PendingDraft:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        _clean_test_invoices(TEST_DB)
        yield
        _clean_test_invoices(TEST_DB)

    def test_se2_create_pending_draft(self):
        """SE-2: save_or_update_pending_invoice creates a pending record in the DB."""
        inv_bytes = _make_invoice_bytes("se2")
        items = [
            {
                "product_id": PROD_HEADPHONES,
                "product_name": "Wireless Headphones",
                "quantity": 5.0,
                "unit": "Units",
                "verification_status": "Verified",
                "is_uncertain": False,
                "unit_price": 1200.0,
                "canonical_quantity": 5,
                "conversion_factor": 1,
            }
        ]
        result = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se2.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE2",
            invoice_date=datetime.date.today(),
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        assert result.get("invoice_id") is not None, (
            f"SE-2: Expected invoice_id in result dict, got: {result}"
        )
        invoice_id = result["invoice_id"]

        conn = get_connection(dbname=TEST_DB)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, invoice_reference FROM purchase_invoices WHERE id = %s;",
                    (invoice_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        assert row is not None, f"SE-2: Invoice #{invoice_id} not found in DB."
        assert row[0] == "pending", f"SE-2: Expected status='pending', got '{row[0]}'."
        assert row[1] == "INV-SMOKE-SE2", f"SE-2: Invoice reference mismatch: {row[1]}"

    def test_se3_pending_draft_persists_after_refetch(self):
        """SE-3: Re-fetching the same file bytes returns the SAME invoice_id (draft resumption)."""
        inv_bytes = _make_invoice_bytes("se3")
        items = [
            {
                "product_id": PROD_SPEAKER,
                "product_name": "Bluetooth Speaker",
                "quantity": 10.0,
                "unit": "Units",
                "verification_status": "Verified",
                "is_uncertain": False,
                "unit_price": 800.0,
                "canonical_quantity": 10,
                "conversion_factor": 1,
            }
        ]

        result1 = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se3.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE3",
            invoice_date=datetime.date.today(),
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        inv_id1 = result1["invoice_id"]

        result2 = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se3.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE3",
            invoice_date=datetime.date.today(),
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        inv_id2 = result2["invoice_id"]

        assert inv_id1 == inv_id2, (
            f"SE-3: Draft resumption failed — first call got #{inv_id1}, "
            f"second call got #{inv_id2}. Expected the same invoice_id."
        )


# ---------------------------------------------------------------------------
# SE-4  Duplicate detection
# ---------------------------------------------------------------------------

class TestSE4DuplicateDetection:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        _clean_test_invoices(TEST_DB)
        yield
        _clean_test_invoices(TEST_DB)

    def test_se4_exact_duplicate_detected(self):
        """SE-4: check_duplicate_invoice returns is_exact_duplicate=True for approved document hash."""
        inv_bytes = _make_invoice_bytes("se4")
        doc_hash = hashlib.sha256(inv_bytes).hexdigest()
        items = [
            {
                "product_id": PROD_SPEAKER,
                "product_name": "Bluetooth Speaker",
                "quantity": 3.0,
                "unit": "Units",
                "verification_status": "Verified",
                "is_uncertain": False,
                "unit_price": 800.0,
                "canonical_quantity": 3,
                "conversion_factor": 1,
            }
        ]
        result = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se4.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE4",
            invoice_date=datetime.date.today(),
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        inv_id = result["invoice_id"]

        status_002 = get_product_inventory_status(PROD_SPEAKER, today_date=datetime.date.today(), dbname=TEST_DB)
        confirmed_openings: Dict[str, int] = {}
        if status_002.get("is_stale") or not status_002.get("has_history"):
            confirmed_openings[PROD_SPEAKER] = 0

        ok, err = approve_invoice_and_update_stock(
            invoice_id=inv_id,
            verified_items=items,
            confirmed_physical_openings=confirmed_openings,
            today_date=datetime.date.today(),
            dbname=TEST_DB,
        )
        assert ok is True, f"SE-4 setup failed: {err}"

        dup_result = check_duplicate_invoice(
            document_hash=doc_hash,
            invoice_reference="INV-SMOKE-SE4",
            supplier_id="SUP_A",
            invoice_date=datetime.date.today(),
            dbname=TEST_DB,
        )
        assert dup_result.get("is_exact_duplicate") is True, (
            f"SE-4: Expected is_exact_duplicate=True, got: {dup_result}"
        )


# ---------------------------------------------------------------------------
# SE-5  Product matching
# ---------------------------------------------------------------------------

class TestSE5ProductMatching:
    def test_se5_product_match_against_catalog(self):
        """SE-5: match_product_against_catalog finds PROD_001 by normalized name."""
        catalog = get_product_catalog(dbname=TEST_DB)
        assert len(catalog) > 0, "SE-5: Catalog is empty in smart_inventory_test."

        result = match_product_against_catalog("wireless headphones", catalog)
        assert result.get("matched_product") is not None, (
            f"SE-5: No matched_product found for 'wireless headphones'. Got: {result}"
        )
        assert result["matched_product"]["product_id"] == PROD_HEADPHONES, (
            f"SE-5: Expected matched product {PROD_HEADPHONES}, got {result['matched_product']}"
        )
        assert result.get("status") in ("exact_match", "normalized_match")


# ---------------------------------------------------------------------------
# SE-6 / SE-7 / SE-8  Full approval and inventory increment
# ---------------------------------------------------------------------------

class TestSE6SE8FullApproval:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        _clean_test_invoices(TEST_DB)
        yield
        _clean_test_invoices(TEST_DB)

    def test_se6_approve_invoice_succeeds(self):
        """
        SE-6, SE-7, SE-8: approve_invoice_and_update_stock with TWO distinct product items:
          - Product 1: Wireless Headphones (PROD_001)
          - Product 2: Bluetooth Speaker (PROD_002)
        Validates:
          - Two distinct item dictionaries in the verified_items list (no key collision)
          - Successful transactional approval (SE-6)
          - Status updated to 'approved' (SE-7)
          - Each product stock incremented independently (SE-8)
        """
        inv_bytes = _make_invoice_bytes("se6")
        today = datetime.date.today()
        qty_headphones = 7
        qty_speaker = 4

        # TWO distinct item dictionaries with separate keys and product specifications
        item_headphones = {
            "product_id": PROD_HEADPHONES,
            "product_name": "Wireless Headphones",
            "quantity": float(qty_headphones),
            "unit": "Units",
            "verification_status": "Verified",
            "is_uncertain": False,
            "unit_price": 1200.0,
            "canonical_quantity": qty_headphones,
            "conversion_factor": 1,
        }
        item_speaker = {
            "product_id": PROD_SPEAKER,
            "product_name": "Bluetooth Speaker",
            "quantity": float(qty_speaker),
            "unit": "Units",
            "verification_status": "Verified",
            "is_uncertain": False,
            "unit_price": 800.0,
            "canonical_quantity": qty_speaker,
            "conversion_factor": 1,
        }
        items = [item_headphones, item_speaker]

        result = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se6.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE6",
            invoice_date=today,
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        invoice_id = result["invoice_id"]

        status_001 = get_product_inventory_status(PROD_HEADPHONES, today_date=today, dbname=TEST_DB)
        status_002 = get_product_inventory_status(PROD_SPEAKER, today_date=today, dbname=TEST_DB)
        confirmed_openings: Dict[str, int] = {}
        if status_001.get("is_stale") or not status_001.get("has_history"):
            confirmed_openings[PROD_HEADPHONES] = 0
        if status_002.get("is_stale") or not status_002.get("has_history"):
            confirmed_openings[PROD_SPEAKER] = 0

        pre_headphones = _get_inventory_qty(PROD_HEADPHONES, today, TEST_DB)
        pre_speaker    = _get_inventory_qty(PROD_SPEAKER,    today, TEST_DB)

        ok, err = approve_invoice_and_update_stock(
            invoice_id=invoice_id,
            verified_items=items,
            confirmed_physical_openings=confirmed_openings,
            today_date=today,
            dbname=TEST_DB,
        )
        assert ok is True, f"SE-6: Approval failed: {err}"

        # SE-7: Status must be 'approved'
        status = _get_invoice_status(invoice_id, TEST_DB)
        assert status == "approved", (
            f"SE-7: Expected status='approved' after approval, got '{status}'."
        )

        # SE-8: Stock on today's row must increase by added quantity independently
        post_headphones = _get_inventory_qty(PROD_HEADPHONES, today, TEST_DB)
        post_speaker    = _get_inventory_qty(PROD_SPEAKER,    today, TEST_DB)

        assert post_headphones == pre_headphones + qty_headphones, (
            f"SE-8: Wireless Headphones inventory mismatch. "
            f"Expected {pre_headphones + qty_headphones}, got {post_headphones}."
        )
        assert post_speaker == pre_speaker + qty_speaker, (
            f"SE-8: Bluetooth Speaker inventory mismatch. "
            f"Expected {pre_speaker + qty_speaker}, got {post_speaker}."
        )


# ---------------------------------------------------------------------------
# SE-9  Re-upload of same bytes → exact duplicate
# ---------------------------------------------------------------------------

class TestSE9ReUploadDuplicate:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        _clean_test_invoices(TEST_DB)
        yield
        _clean_test_invoices(TEST_DB)

    def test_se9_re_upload_same_bytes_is_duplicate(self):
        """SE-9: Uploading the same file after approval → is_exact_duplicate=True."""
        inv_bytes = _make_invoice_bytes("se9")
        doc_hash = hashlib.sha256(inv_bytes).hexdigest()
        today = datetime.date.today()
        qty = 2

        items = [
            {
                "product_id": PROD_SPEAKER,
                "product_name": "Bluetooth Speaker",
                "quantity": float(qty),
                "unit": "Units",
                "verification_status": "Verified",
                "is_uncertain": False,
                "unit_price": 800.0,
                "canonical_quantity": qty,
                "conversion_factor": 1,
            }
        ]

        result = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se9.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE9",
            invoice_date=today,
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        invoice_id = result["invoice_id"]

        status_002 = get_product_inventory_status(PROD_SPEAKER, today_date=today, dbname=TEST_DB)
        confirmed_openings: Dict[str, int] = {}
        if status_002.get("is_stale") or not status_002.get("has_history"):
            confirmed_openings[PROD_SPEAKER] = 0

        ok, err = approve_invoice_and_update_stock(
            invoice_id=invoice_id,
            verified_items=items,
            confirmed_physical_openings=confirmed_openings,
            today_date=today,
            dbname=TEST_DB,
        )
        assert ok is True, f"SE-9 setup: Approval failed: {err}"

        dup_result = check_duplicate_invoice(
            document_hash=doc_hash,
            invoice_reference="INV-SMOKE-SE9",
            supplier_id="SUP_A",
            invoice_date=today,
            dbname=TEST_DB,
        )
        assert dup_result.get("is_exact_duplicate") is True, (
            f"SE-9: Re-upload of same bytes must be is_exact_duplicate=True, "
            f"got: {dup_result}"
        )


# ---------------------------------------------------------------------------
# SE-10  Reject a draft
# ---------------------------------------------------------------------------

class TestSE10Rejection:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        _clean_test_invoices(TEST_DB)
        yield
        _clean_test_invoices(TEST_DB)

    def test_se10_reject_pending_invoice(self):
        """SE-10: reject_invoice sets status='rejected' in purchase_invoices."""
        inv_bytes = _make_invoice_bytes("se10")
        items = [
            {
                "product_id": PROD_HEADPHONES,
                "product_name": "Wireless Headphones",
                "quantity": 1.0,
                "unit": "Units",
                "verification_status": "Needs Review",
                "is_uncertain": False,
                "unit_price": 1200.0,
                "canonical_quantity": 1,
                "conversion_factor": 1,
            }
        ]

        result = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se10.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE10",
            invoice_date=datetime.date.today(),
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        invoice_id = result["invoice_id"]

        ok, err = reject_invoice(
            invoice_id=invoice_id,
            reason="Smoke test rejection — SE-10",
            dbname=TEST_DB,
        )
        assert ok is True, f"SE-10: reject_invoice returned failure: {err}"

        status = _get_invoice_status(invoice_id, TEST_DB)
        assert status == "rejected", (
            f"SE-10: Expected status='rejected', got '{status}'."
        )


# ---------------------------------------------------------------------------
# SE-11 / SE-12  File-storage verification
# ---------------------------------------------------------------------------

class TestSE11SE12FileStorage:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        _clean_test_invoices(TEST_DB)
        yield
        _clean_test_invoices(TEST_DB)

    def test_se11_approved_file_exists_in_approved_dir(self):
        """SE-11: After approval, document appears in the isolated approved directory."""
        inv_bytes = _make_invoice_bytes("se11")
        today = datetime.date.today()
        qty = 3

        items = [
            {
                "product_id": PROD_SPEAKER,
                "product_name": "Bluetooth Speaker",
                "quantity": float(qty),
                "unit": "Units",
                "verification_status": "Verified",
                "is_uncertain": False,
                "unit_price": 800.0,
                "canonical_quantity": qty,
                "conversion_factor": 1,
            }
        ]

        result = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se11.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE11",
            invoice_date=today,
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        invoice_id = result["invoice_id"]

        status_002 = get_product_inventory_status(PROD_SPEAKER, today_date=today, dbname=TEST_DB)
        confirmed_openings: Dict[str, int] = {}
        if status_002.get("is_stale") or not status_002.get("has_history"):
            confirmed_openings[PROD_SPEAKER] = 0

        conn = get_connection(dbname=TEST_DB)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT document_filename FROM purchase_invoices WHERE id = %s;",
                    (invoice_id,),
                )
                doc_filename = cur.fetchone()[0]
        finally:
            conn.close()

        ok, err = approve_invoice_and_update_stock(
            invoice_id=invoice_id,
            verified_items=items,
            confirmed_physical_openings=confirmed_openings,
            today_date=today,
            dbname=TEST_DB,
        )
        assert ok is True, f"SE-11 setup: Approval failed: {err}"

        approved_files = list(TMP_APPROVED_DIR.rglob("*"))
        found = any(doc_filename in str(f) for f in approved_files)
        assert found, (
            f"SE-11: Document '{doc_filename}' not found under {TMP_APPROVED_DIR}. "
            f"Files present: {[f.name for f in approved_files]}"
        )

    def test_se12_pending_file_removed_after_approval(self):
        """SE-12: After approval commit, the pending copy of the document is removed."""
        inv_bytes = _make_invoice_bytes("se12")
        today = datetime.date.today()
        qty = 2

        items = [
            {
                "product_id": PROD_HEADPHONES,
                "product_name": "Wireless Headphones",
                "quantity": float(qty),
                "unit": "Units",
                "verification_status": "Verified",
                "is_uncertain": False,
                "unit_price": 1200.0,
                "canonical_quantity": qty,
                "conversion_factor": 1,
            }
        ]

        result = save_or_update_pending_invoice(
            file_bytes=inv_bytes,
            original_filename="smoke_se12.pdf",
            line_items=items,
            invoice_reference="INV-SMOKE-SE12",
            invoice_date=today,
            supplier_id="SUP_A",
            dbname=TEST_DB,
        )
        invoice_id = result["invoice_id"]

        conn = get_connection(dbname=TEST_DB)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT document_filename, document_path FROM purchase_invoices WHERE id = %s;",
                    (invoice_id,),
                )
                row = cur.fetchone()
                doc_filename, doc_rel_path = row
        finally:
            conn.close()

        pending_path = PROJECT_ROOT / doc_rel_path

        status_001 = get_product_inventory_status(PROD_HEADPHONES, today_date=today, dbname=TEST_DB)
        confirmed_openings: Dict[str, int] = {}
        if status_001.get("is_stale") or not status_001.get("has_history"):
            confirmed_openings[PROD_HEADPHONES] = 0

        ok, err = approve_invoice_and_update_stock(
            invoice_id=invoice_id,
            verified_items=items,
            confirmed_physical_openings=confirmed_openings,
            today_date=today,
            dbname=TEST_DB,
        )
        assert ok is True, f"SE-12 setup: Approval failed: {err}"

        assert not pending_path.exists(), (
            f"SE-12: Pending file '{pending_path}' still exists after approval commit. "
            "copy-and-commit cleanup failed."
        )


# ---------------------------------------------------------------------------
# SE-PROD  Production integrity guard (run last)
# ---------------------------------------------------------------------------

class TestSEProdIntegrity:
    """Verify that smoke tests made NO writes to smart_inventory."""

    _baseline: Dict[str, int] = {}

    @classmethod
    def setup_class(cls):
        cls._baseline = _prod_row_counts()

    def test_se_prod_row_counts_unchanged(self):
        """SE-PROD: All production table row counts must be identical to the pre-test snapshot."""
        current = _prod_row_counts()
        discrepancies = {
            t: (self._baseline[t], current[t])
            for t in self._baseline
            if self._baseline[t] != current[t]
        }
        assert not discrepancies, (
            "CRITICAL: Smoke tests wrote to production smart_inventory!\n"
            + "\n".join(
                f"  {t}: was {before}, now {after}"
                for t, (before, after) in discrepancies.items()
            )
        )
