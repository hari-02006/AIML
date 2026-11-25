-- Extend tables for Stage 14 idempotency and generic movement references

-- Add a stable receipt reference (unique) to purchase_receipts
ALTER TABLE IF EXISTS purchase_receipts
    ADD COLUMN IF NOT EXISTS receipt_reference VARCHAR(100);

    -- Ensure receipt_reference is NOT NULL and non-empty
    ALTER TABLE purchase_receipts
        ALTER COLUMN receipt_reference SET NOT NULL;
    ALTER TABLE purchase_receipts
        ADD CONSTRAINT ck_receipt_reference_not_blank CHECK (trim(receipt_reference) <> '');

    -- Add a unique constraint explicitly (idempotent via IF NOT EXISTS)
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_receipt_reference') THEN
            ALTER TABLE purchase_receipts ADD CONSTRAINT uq_receipt_reference UNIQUE (receipt_reference);
        END IF;
    END $$;

-- Expand inventory_movements to support generic reference types
ALTER TABLE IF EXISTS inventory_movements
    ADD COLUMN IF NOT EXISTS movement_reference_type VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS reference_id VARCHAR(100);

    -- Ensure movement_type allows IN, OUT, PHYSICAL_ADJUSTMENT (idempotent)
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_movement_type') THEN
            ALTER TABLE inventory_movements ADD CONSTRAINT ck_movement_type CHECK (movement_type IN ('IN','OUT','PHYSICAL_ADJUSTMENT'));
        END IF;
    END $$;

-- Create a lookup table for movement reference types (optional, but improves referential integrity)
CREATE TABLE IF NOT EXISTS movement_reference_types (
    type VARCHAR(20) PRIMARY KEY,
    description TEXT
);
INSERT INTO movement_reference_types (type, description) VALUES
    ('RECEIPT', 'Reference to a purchase receipt'),
    ('SALE', 'Reference to a sale'),
    ('ADJUSTMENT', 'Physical inventory adjustment')
ON CONFLICT DO NOTHING;
