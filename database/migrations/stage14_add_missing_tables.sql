-- Stage 14 additive migration: create missing tables if they do not exist

-- Purchase Receipts
CREATE TABLE IF NOT EXISTS purchase_receipts (
    receipt_id VARCHAR(50) PRIMARY KEY,
    purchase_order_id VARCHAR(50) NOT NULL REFERENCES purchase_orders(purchase_order_id) ON DELETE RESTRICT,
    product_id VARCHAR(50) NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity_received INTEGER NOT NULL CHECK (quantity_received > 0),
    unit_price NUMERIC(10,2) NOT NULL CHECK (unit_price > 0),
    receipt_date DATE NOT NULL,
    operator VARCHAR(50) NOT NULL,
    UNIQUE (purchase_order_id, receipt_id)
);

-- Inventory Movements
CREATE TABLE IF NOT EXISTS inventory_movements (
    movement_id VARCHAR(50) PRIMARY KEY,
    product_id VARCHAR(50) NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit VARCHAR(20) NOT NULL,
    movement_type VARCHAR(20) NOT NULL,
    reference_id VARCHAR(50),
    operator VARCHAR(50) NOT NULL,
    movement_date DATE NOT NULL,
    -- Remove restrictive FK that only allowed purchase receipt references (now generic)
    ALTER TABLE inventory_movements DROP CONSTRAINT IF EXISTS fk_reference_receipt;

);

-- Users
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
);

-- Sessions
CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- for gen_random_uuid()
CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
