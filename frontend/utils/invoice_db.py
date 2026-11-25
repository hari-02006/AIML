"""
Invoice Database Service for Stage 9.
Handles all PostgreSQL operations for purchase invoices and inventory stock updates:
  - Pending invoice draft creation & draft resumption
  - Duplicate check (Exact hash & Heuristic re-scan warning)
  - Stale stock detection (configurable INVENTORY_STALE_DAYS = 30)
  - New product creation with foreign key validation
  - Deterministic deadlock-safe row locking (sorted product_id order)
  - Transaction-safe daily inventory UPSERT with opening_stock preservation
  - Copy-and-commit document storage coordination
  - Full transactional rollback on failure
"""

import os
import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from database.db_connection import get_connection
from frontend.utils.invoice_storage import (
    save_pending_invoice_document,
    stage_approved_document,
    commit_approved_document,
    rollback_staged_approved_document,
    stage_rejected_document
)
from frontend.utils.product_matcher import (
    normalize_string,
    validate_unit_conversion
)

INVENTORY_STALE_DAYS = 30


# -----------------------------------------------------------------------------
# Catalog & Stale Status Queries
# -----------------------------------------------------------------------------

def get_product_catalog(dbname: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all products with their category, supplier, and canonical stock_unit."""
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.product_id, p.product_name, p.category_id, c.category_name,
                       p.supplier_id, s.supplier_name, p.stock_unit
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id
                ORDER BY p.product_id;
            """)
            rows = cur.fetchall()
            catalog = []
            for r in rows:
                catalog.append({
                    "product_id": r[0],
                    "product_name": r[1],
                    "category_id": r[2],
                    "category_name": r[3],
                    "supplier_id": r[4],
                    "supplier_name": r[5],
                    "stock_unit": r[6]
                })
            return catalog
    finally:
        conn.close()


def get_available_categories(dbname: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all categories for new product creation."""
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT category_id, category_name FROM categories ORDER BY category_id;")
            return [{"category_id": r[0], "category_name": r[1]} for r in cur.fetchall()]
    finally:
        conn.close()


def get_available_suppliers(dbname: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all suppliers for new product or invoice assignment."""
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT supplier_id, supplier_name FROM suppliers ORDER BY supplier_id;")
            return [{"supplier_id": r[0], "supplier_name": r[1]} for r in cur.fetchall()]
    finally:
        conn.close()


def get_product_inventory_status(
    product_id: str,
    today_date: Optional[datetime.date] = None,
    dbname: Optional[str] = None
) -> Dict[str, Any]:
    """
    Checks the inventory history for a product.
    Returns:
      {
        "has_history": bool,
        "is_stale": bool,
        "latest_date": Optional[date],
        "latest_closing_stock": Optional[int],
        "days_ago": Optional[int],
        "requires_physical_confirmation": bool
      }
    """
    if today_date is None:
        today_date = datetime.date.today()

    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT date, closing_stock
                FROM inventory
                WHERE product_id = %s
                ORDER BY date DESC
                LIMIT 1;
            """, (product_id,))
            row = cur.fetchone()
            if not row:
                return {
                    "has_history": False,
                    "is_stale": False,
                    "latest_date": None,
                    "latest_closing_stock": None,
                    "days_ago": None,
                    "requires_physical_confirmation": True
                }

            latest_date, closing_stock = row[0], row[1]
            days_ago = (today_date - latest_date).days
            is_stale = days_ago > INVENTORY_STALE_DAYS

            return {
                "has_history": True,
                "is_stale": is_stale,
                "latest_date": latest_date,
                "latest_closing_stock": closing_stock,
                "days_ago": days_ago,
                "requires_physical_confirmation": is_stale
            }
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Duplicate Detection
# -----------------------------------------------------------------------------

def check_duplicate_invoice(
    document_hash: str,
    invoice_reference: Optional[str] = None,
    supplier_id: Optional[str] = None,
    invoice_date: Optional[datetime.date] = None,
    dbname: Optional[str] = None
) -> Dict[str, Any]:
    """
    Checks for exact binary duplicate or heuristic re-scan warning.
    Returns:
      {
        "is_exact_duplicate": bool,
        "has_rescan_warning": bool,
        "existing_invoice_id": Optional[int],
        "message": str
      }
    """
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            # 1. Exact Binary Duplicate on Approved Invoices
            cur.execute("""
                SELECT id, invoice_reference, approved_at, document_filename
                FROM purchase_invoices
                WHERE document_hash = %s AND status = 'approved';
            """, (document_hash,))
            exact = cur.fetchone()
            if exact:
                return {
                    "is_exact_duplicate": True,
                    "has_rescan_warning": False,
                    "existing_invoice_id": exact[0],
                    "message": f"This identical document was already approved on {exact[2].strftime('%Y-%m-%d %H:%M')} (Invoice #{exact[0]}). Duplicate stock update is blocked."
                }

            # Check if there is an existing PENDING draft for this exact hash
            cur.execute("""
                SELECT id, invoice_reference, created_at, document_filename
                FROM purchase_invoices
                WHERE document_hash = %s AND status = 'pending'
                ORDER BY id DESC LIMIT 1;
            """, (document_hash,))
            pending_draft = cur.fetchone()

            # 2. Heuristic Re-Scan Warning
            if invoice_reference and (supplier_id or invoice_date):
                query = """
                    SELECT id, invoice_reference, supplier_id, raw_supplier_name, invoice_date, approved_at
                    FROM purchase_invoices
                    WHERE status = 'approved'
                      AND LOWER(invoice_reference) = LOWER(%s)
                """
                params = [invoice_reference.strip()]
                if supplier_id:
                    query += " AND supplier_id = %s"
                    params.append(supplier_id)
                elif invoice_date:
                    query += " AND invoice_date = %s"
                    params.append(invoice_date)

                cur.execute(query + " ORDER BY id DESC LIMIT 1;", tuple(params))
                match = cur.fetchone()
                if match:
                    s_label = match[3] or match[2] or "Unknown Supplier"
                    d_label = match[4].strftime('%Y-%m-%d') if match[4] else "N/A"
                    return {
                        "is_exact_duplicate": False,
                        "has_rescan_warning": True,
                        "existing_invoice_id": match[0],
                        "pending_draft_id": pending_draft[0] if pending_draft else None,
                        "message": f"Potential Duplicate Re-Scan: Invoice reference '{match[1]}' from supplier '{s_label}' (Date: {d_label}) was already approved on {match[5].strftime('%Y-%m-%d')}. Verify whether this is a distinct physical delivery."
                    }

            return {
                "is_exact_duplicate": False,
                "has_rescan_warning": False,
                "existing_invoice_id": None,
                "pending_draft_id": pending_draft[0] if pending_draft else None,
                "message": "Document is unique and clear for review."
            }
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Draft Persistence (Pending Invoices)
# -----------------------------------------------------------------------------

def save_or_update_pending_invoice(
    file_bytes: bytes,
    original_filename: str,
    line_items: List[Dict[str, Any]],
    invoice_reference: Optional[str] = None,
    invoice_date: Optional[datetime.date] = None,
    supplier_id: Optional[str] = None,
    raw_supplier_name: Optional[str] = None,
    total_pages: int = 1,
    dbname: Optional[str] = None
) -> Dict[str, Any]:
    """
    Saves document file into data/invoices/pending/ and records a pending draft in DB.
    Allows NULL product_id, NULL quantity, and unreadable names for pending drafts.
    """
    doc_hash, safe_name, rel_doc_path = save_pending_invoice_document(file_bytes, original_filename)

    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            # Check if pending draft already exists for this document_hash
            cur.execute("""
                SELECT id FROM purchase_invoices
                WHERE document_hash = %s AND status = 'pending'
                ORDER BY id DESC LIMIT 1;
            """, (doc_hash,))
            existing = cur.fetchone()

            if existing:
                inv_id = existing[0]
                cur.execute("""
                    UPDATE purchase_invoices
                    SET invoice_reference = %s,
                        invoice_date = %s,
                        supplier_id = %s,
                        raw_supplier_name = %s,
                        document_path = %s,
                        total_pages = %s
                    WHERE id = %s;
                """, (invoice_reference, invoice_date, supplier_id, raw_supplier_name, rel_doc_path, total_pages, inv_id))
                # Delete existing pending items to replace with updated state
                cur.execute("DELETE FROM purchase_invoice_items WHERE invoice_id = %s;", (inv_id,))
            else:
                cur.execute("""
                    INSERT INTO purchase_invoices (
                        invoice_reference, invoice_date, supplier_id, raw_supplier_name,
                        document_hash, document_filename, document_path, document_type,
                        total_pages, status
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, 'Supplier Invoice',
                        %s, 'pending'
                    ) RETURNING id;
                """, (invoice_reference, invoice_date, supplier_id, raw_supplier_name,
                      doc_hash, safe_name, rel_doc_path, total_pages))
                inv_id = cur.fetchone()[0]

            # Insert line items (allowing NULL product_id, NULL quantity)
            for it in line_items:
                cur.execute("""
                    INSERT INTO purchase_invoice_items (
                        invoice_id, product_id, raw_line_text, original_product_name,
                        normalized_product_name, quantity, unit, canonical_quantity,
                        conversion_factor, source_page, verification_status
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s
                    );
                """, (
                    inv_id,
                    it.get("product_id"),
                    it.get("raw_line_text") or it.get("product_name"),
                    it.get("product_name"),
                    normalize_string(it.get("product_name")),
                    it.get("quantity"),
                    it.get("unit"),
                    it.get("canonical_quantity"),
                    it.get("conversion_factor", 1.0),
                    it.get("source_page", 1),
                    it.get("verification_status", "Needs Review")
                ))

        conn.commit()
        return {
            "success": True,
            "invoice_id": inv_id,
            "document_hash": doc_hash,
            "document_path": rel_doc_path
        }
    except Exception as exc:
        conn.rollback()
        return {
            "success": False,
            "error": f"Failed to save pending invoice draft: {str(exc)}"
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# New Product Creation
# -----------------------------------------------------------------------------

def create_new_product(
    product_name: str,
    category_id: int,
    supplier_id: Optional[str] = None,
    stock_unit: Optional[str] = "Units",
    cost_price: Optional[float] = 0.0,
    base_price: Optional[float] = 0.0,
    conn=None,
    dbname: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Creates a new product with category foreign key validation and safe PROD_XXX sequence generation.
    Can run within an external transaction if conn is provided.
    """
    own_conn = False
    if conn is None:
        conn = get_connection(dbname=dbname)
        own_conn = True

    try:
        with conn.cursor() as cur:
            # 1. Validate Category FK
            cur.execute("SELECT 1 FROM categories WHERE category_id = %s;", (category_id,))
            if not cur.fetchone():
                return False, None, f"Category ID {category_id} does not exist."

            # 2. Check Supplier FK if provided
            if supplier_id:
                cur.execute("SELECT 1 FROM suppliers WHERE supplier_id = %s;", (supplier_id,))
                if not cur.fetchone():
                    return False, None, f"Supplier ID '{supplier_id}' does not exist."

            # 3. Check duplicate product_name
            norm_name = normalize_string(product_name)
            cur.execute("SELECT product_id, product_name FROM products;")
            for p in cur.fetchall():
                if normalize_string(p[1]) == norm_name:
                    return False, p[0], f"Product '{product_name}' already exists with ID {p[0]}."

            # 4. Generate next product_id safely using a session-level advisory lock.
            # pg_try_advisory_xact_lock(hashtext('create_product')) serialises concurrent
            # new-product creations so that two concurrent callers cannot compute the same
            # PROD_XXX id simultaneously. The lock is released automatically at the end of
            # the enclosing transaction.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('create_product'));")
            cur.execute("SELECT product_id FROM products WHERE product_id LIKE 'PROD_%';")
            existing_ids = [r[0] for r in cur.fetchall()]
            max_num = 0
            for pid in existing_ids:
                try:
                    num = int(pid.replace("PROD_", ""))
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
            new_prod_id = f"PROD_{max_num + 1:03d}"

            # 5. Insert new product
            cur.execute("""
                INSERT INTO products (
                    product_id, product_name, category_id, supplier_id,
                    stock_unit, cost_price, base_price, popularity_class, demand_pattern_class
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, 'Regular', 'Stable'
                );
            """, (new_prod_id, product_name.strip(), category_id, supplier_id,
                  stock_unit.strip() if stock_unit else "Units", cost_price, base_price))

        if own_conn:
            conn.commit()
        return True, new_prod_id, None
    except Exception as exc:
        if own_conn:
            conn.rollback()
        return False, None, str(exc)
    finally:
        if own_conn:
            conn.close()


# -----------------------------------------------------------------------------
# Approval & Transactional Stock Update
# -----------------------------------------------------------------------------

def approve_invoice_and_update_stock(
    invoice_id: int,
    verified_items: List[Dict[str, Any]],
    confirmed_physical_openings: Dict[str, int],
    today_date: Optional[datetime.date] = None,
    dbname: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Transactional Invoice Approval & Inventory Stock Increment.
    Enforces:
      1. Every line item must be 'Verified'
      2. product_id must be valid and non-null
      3. canonical_quantity must be strictly > 0 and conversion_factor > 0
      4. Stale/no-history products must have confirmed physical opening counts
      5. Pre-commit copy of document to data/invoices/approved/ with hash verification
      6. Deterministic alphabetical product row locking (SELECT ... FOR UPDATE)
      7. Daily inventory UPSERT with opening_stock preservation on same-day multiple invoices
      8. Post-commit cleanup of pending file
      9. Full rollback on any error
    """
    if today_date is None:
        today_date = datetime.date.today()

    conn = get_connection(dbname=dbname)
    approved_staged_path = None
    pending_path = None

    try:
        # Step 1: Pre-Transaction Validation & Document Staging
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, document_hash, document_path, status
                FROM purchase_invoices
                WHERE id = %s;
            """, (invoice_id,))
            inv_row = cur.fetchone()
            if not inv_row:
                return False, f"Invoice #{invoice_id} not found."
            if inv_row[3] == "approved":
                return False, f"Invoice #{invoice_id} is already approved. Duplicate approval rejected."
            if inv_row[3] == "rejected":
                return False, f"Invoice #{invoice_id} is rejected and cannot be approved."

            doc_hash = inv_row[1]
            pending_path = inv_row[2]

        # Stage document in approved/ and verify SHA-256
        stage_ok, approved_staged_path, stage_err = stage_approved_document(pending_path, doc_hash)
        if not stage_ok:
            return False, f"Document staging failed: {stage_err}"

        # Step 2: Validate Every Single Item
        if not verified_items or len(verified_items) == 0:
            rollback_staged_approved_document(approved_staged_path)
            return False, "Cannot approve an invoice with zero product line items."

        for idx, it in enumerate(verified_items, start=1):
            if it.get("verification_status") != "Verified":
                rollback_staged_approved_document(approved_staged_path)
                return False, f"Line #{idx} ('{it.get('product_name')}') is not verified. All items must be marked 'Verified'."

            pid = it.get("product_id")
            if not pid:
                rollback_staged_approved_document(approved_staged_path)
                return False, f"Line #{idx} ('{it.get('product_name')}') has no matched product ID."

            cq = it.get("canonical_quantity")
            if cq is None or cq <= 0:
                rollback_staged_approved_document(approved_staged_path)
                return False, f"Line #{idx} has invalid canonical quantity ({cq}). Must be strictly greater than zero."

            cf = it.get("conversion_factor")
            if cf is not None and cf <= 0:
                rollback_staged_approved_document(approved_staged_path)
                return False, f"Line #{idx} has non-positive conversion factor ({cf}). Must be > 0."

        # Step 3: Transaction Execution with Deterministic Row Locking
        with conn.cursor() as cur:
            # Re-lock invoice record
            cur.execute("SELECT status FROM purchase_invoices WHERE id = %s FOR UPDATE;", (invoice_id,))
            curr_status = cur.fetchone()[0]
            if curr_status != "pending":
                rollback_staged_approved_document(approved_staged_path)
                return False, f"Invoice status changed to '{curr_status}'. Approval aborted."

            # Sort product IDs deterministically to eliminate deadlock risks
            sorted_product_ids = sorted(list(set(it["product_id"] for it in verified_items)))
            for pid in sorted_product_ids:
                cur.execute("SELECT product_id, stock_unit FROM products WHERE product_id = %s FOR UPDATE;", (pid,))
                p_row = cur.fetchone()
                if not p_row:
                    rollback_staged_approved_document(approved_staged_path)
                    return False, f"Product ID '{pid}' does not exist in database."

            # Aggregate incoming quantities per product
            product_incoming: Dict[str, float] = {}
            for it in verified_items:
                pid = it["product_id"]
                product_incoming[pid] = product_incoming.get(pid, 0.0) + float(it["canonical_quantity"])

            # Process inventory row for each product
            for pid, qty_to_add in product_incoming.items():
                qty_int = int(round(qty_to_add))

                # Check existing row for today
                cur.execute("""
                    SELECT inventory_id, opening_stock, units_received, closing_stock
                    FROM inventory
                    WHERE date = %s AND product_id = %s
                    FOR UPDATE;
                """, (today_date, pid))
                existing_today = cur.fetchone()

                if existing_today:
                    # Subsequent receipt on same date: aggregate units_received and closing_stock; PRESERVE opening_stock
                    cur.execute("""
                        UPDATE inventory
                        SET units_received = units_received + %s,
                            closing_stock  = closing_stock  + %s
                        WHERE date = %s AND product_id = %s;
                    """, (qty_int, qty_int, today_date, pid))
                else:
                    # First receipt on today_date: determine opening_stock
                    cur.execute("""
                        SELECT date, closing_stock
                        FROM inventory
                        WHERE product_id = %s AND date < %s
                        ORDER BY date DESC
                        LIMIT 1;
                    """, (pid, today_date))
                    hist_row = cur.fetchone()

                    if hist_row:
                        last_date, last_closing = hist_row[0], hist_row[1]
                        days_diff = (today_date - last_date).days
                        if days_diff > INVENTORY_STALE_DAYS:
                            # Stale: must use shopkeeper-confirmed physical opening stock
                            if pid not in confirmed_physical_openings:
                                rollback_staged_approved_document(approved_staged_path)
                                return False, f"Physical stock count not confirmed for stale product '{pid}' ({days_diff} days old)."
                            opening_stock = int(confirmed_physical_openings[pid])
                        else:
                            # Recent inventory (<= 30 days): carry forward closing stock
                            opening_stock = int(last_closing)
                    else:
                        # No history: check if confirmed
                        if pid in confirmed_physical_openings:
                            opening_stock = int(confirmed_physical_openings[pid])
                        else:
                            # Genuinely new product explicitly approved defaults opening to 0
                            opening_stock = 0

                    closing_stock = opening_stock + qty_int
                    inv_id_str = f"INV_{today_date.strftime('%Y%m%d')}_{pid}"

                    cur.execute("""
                        INSERT INTO inventory (
                            inventory_id, date, product_id,
                            opening_stock, units_received, closing_stock,
                            true_demand, observed_units_sold, lost_sales_units, stockout_flag
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s, %s,
                            0, 0, 0, false
                        )
                        ON CONFLICT (date, product_id) DO UPDATE SET
                            units_received = inventory.units_received + EXCLUDED.units_received,
                            closing_stock  = inventory.closing_stock  + EXCLUDED.units_received;
                    """, (inv_id_str, today_date, pid, opening_stock, qty_int, closing_stock))

            # Update purchase_invoice_items records to match verified state
            cur.execute("DELETE FROM purchase_invoice_items WHERE invoice_id = %s;", (invoice_id,))
            for it in verified_items:
                cur.execute("""
                    INSERT INTO purchase_invoice_items (
                        invoice_id, product_id, raw_line_text, original_product_name,
                        normalized_product_name, quantity, unit, canonical_quantity,
                        conversion_factor, source_page, verification_status
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, 'Verified'
                    );
                """, (
                    invoice_id,
                    it["product_id"],
                    it.get("raw_line_text") or it.get("product_name"),
                    it.get("product_name"),
                    normalize_string(it.get("product_name")),
                    it.get("quantity"),
                    it.get("unit"),
                    it.get("canonical_quantity"),
                    it.get("conversion_factor", 1.0),
                    it.get("source_page", 1)
                ))

            # Mark invoice as approved and store verified approved document path
            cur.execute("""
                UPDATE purchase_invoices
                SET status = 'approved',
                    approved_at = now(),
                    document_path = %s
                WHERE id = %s;
            """, (approved_staged_path, invoice_id))

        # Commit PostgreSQL transaction
        conn.commit()

        # Step 4: Post-Commit Cleanup of redundant pending file
        commit_approved_document(pending_path)
        return True, None

    except Exception as exc:
        conn.rollback()
        rollback_staged_approved_document(approved_staged_path)
        return False, f"Invoice approval transaction failed: {str(exc)}"
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Rejection & History
# -----------------------------------------------------------------------------

def reject_invoice(invoice_id: int, reason: str = "Rejected by shopkeeper", dbname: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Marks an invoice as rejected and moves document to rejected/ folder."""
    conn = get_connection(dbname=dbname)
    rejected_staged = None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, document_hash, document_path, status FROM purchase_invoices WHERE id = %s FOR UPDATE;", (invoice_id,))
            row = cur.fetchone()
            if not row:
                return False, "Invoice not found"
            if row[3] == "approved":
                return False, "Cannot reject an already approved invoice."

            pending_path = row[2]
            doc_hash = row[1]

            stage_ok, rejected_staged, err = stage_rejected_document(pending_path, doc_hash)
            if not stage_ok:
                return False, f"Failed to stage rejected document: {err}"

            cur.execute("""
                UPDATE purchase_invoices
                SET status = 'rejected',
                    notes = %s,
                    document_path = %s
                WHERE id = %s;
            """, (reason, rejected_staged, invoice_id))
            cur.execute("UPDATE purchase_invoice_items SET verification_status = 'Rejected' WHERE invoice_id = %s;", (invoice_id,))

        conn.commit()
        commit_approved_document(pending_path)  # removes pending copy
        return True, None
    except Exception as exc:
        conn.rollback()
        return False, str(exc)
    finally:
        conn.close()


def get_invoice_history(limit: int = 50, dbname: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves history of processed purchase invoices and their item summaries."""
    conn = get_connection(dbname=dbname)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pi.id, pi.invoice_reference, pi.invoice_date, pi.supplier_id,
                       s.supplier_name, pi.raw_supplier_name, pi.document_filename,
                       pi.document_path, pi.total_pages, pi.status, pi.created_at,
                       pi.approved_at,
                       COUNT(pii.id) AS item_count,
                       COALESCE(SUM(pii.canonical_quantity), 0) AS total_units
                FROM purchase_invoices pi
                LEFT JOIN suppliers s ON pi.supplier_id = s.supplier_id
                LEFT JOIN purchase_invoice_items pii ON pi.id = pii.invoice_id
                GROUP BY pi.id, s.supplier_name
                ORDER BY pi.id DESC
                LIMIT %s;
            """, (limit,))
            rows = cur.fetchall()
            history = []
            for r in rows:
                history.append({
                    "id": r[0],
                    "invoice_reference": r[1] or "N/A",
                    "invoice_date": r[2],
                    "supplier_id": r[3],
                    "supplier_name": r[4] or r[5] or "Unassigned",
                    "document_filename": r[6],
                    "document_path": r[7],
                    "total_pages": r[8],
                    "status": r[9],
                    "created_at": r[10],
                    "approved_at": r[11],
                    "item_count": r[12],
                    "total_units": float(r[13])
                })
            return history
    finally:
        conn.close()
