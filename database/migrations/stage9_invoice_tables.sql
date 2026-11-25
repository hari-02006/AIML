-- =========================================================================
-- Stage 9 Database Migration: Purchase Invoices & Line Items Schema
-- Safe, repeatable, and idempotent transactional migration script.
-- =========================================================================

BEGIN;

-- 1. Add canonical stock_unit column to products table if not present
ALTER TABLE products ADD COLUMN IF NOT EXISTS stock_unit VARCHAR(50) NULL;

-- 2. Create purchase_invoices table
CREATE TABLE IF NOT EXISTS purchase_invoices (
    id                  SERIAL PRIMARY KEY,
    invoice_reference   VARCHAR(100),
    invoice_date        DATE NULL,
    supplier_id         VARCHAR(50) REFERENCES suppliers(supplier_id) ON DELETE RESTRICT,
    raw_supplier_name   VARCHAR(255),
    document_hash       CHAR(64) NOT NULL,
    document_filename   VARCHAR(255) NOT NULL,
    document_path       VARCHAR(500) NOT NULL,
    document_type       VARCHAR(50) DEFAULT 'Supplier Invoice',
    total_pages         INTEGER DEFAULT 1,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at         TIMESTAMPTZ NULL,
    notes               TEXT
);

-- Unique index prevents duplicate approval of identical document content
CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_invoices_approved_hash 
ON purchase_invoices (document_hash) 
WHERE status = 'approved';

CREATE INDEX IF NOT EXISTS idx_pi_supplier_id ON purchase_invoices(supplier_id);
CREATE INDEX IF NOT EXISTS idx_pi_reference ON purchase_invoices(invoice_reference);
CREATE INDEX IF NOT EXISTS idx_pi_invoice_date ON purchase_invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_pi_status ON purchase_invoices(status);

-- 3. Create purchase_invoice_items table
CREATE TABLE IF NOT EXISTS purchase_invoice_items (
    id                      SERIAL PRIMARY KEY,
    invoice_id              INTEGER NOT NULL REFERENCES purchase_invoices(id) ON DELETE RESTRICT,
    product_id              VARCHAR(50) REFERENCES products(product_id) ON DELETE RESTRICT,
    raw_line_text           TEXT NULL,
    original_product_name   VARCHAR(500) NULL,
    normalized_product_name VARCHAR(500) NULL,
    quantity                NUMERIC(12, 3) NULL CHECK (quantity IS NULL OR quantity > 0),
    unit                    VARCHAR(50) NULL,
    canonical_quantity      NUMERIC(12, 3) NULL CHECK (canonical_quantity IS NULL OR canonical_quantity > 0),
    conversion_factor       NUMERIC(12, 4) NULL CHECK (conversion_factor IS NULL OR conversion_factor > 0),
    source_page             INTEGER DEFAULT 1,
    verification_status     VARCHAR(30) NOT NULL DEFAULT 'Needs Review'
                            CHECK (verification_status IN ('Needs Review', 'Verified', 'Rejected')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pi_items_invoice_id ON purchase_invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_pi_items_product_id ON purchase_invoice_items(product_id);

COMMIT;
