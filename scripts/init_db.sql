-- =============================================================================
-- ecombot — Database initialisation + seed data
-- Runs automatically when the postgres container starts for the first time.
-- To re-run manually:
--   docker exec -i ecombot-postgres psql -U ecombot -d ecombot < scripts/init_db.sql
-- =============================================================================

-- ---------------------------------------------------------------------------
-- PRODUCTS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    product_id      VARCHAR(20)     PRIMARY KEY,
    name            VARCHAR(255)    NOT NULL,
    description     TEXT,
    price           NUMERIC(10, 2)  NOT NULL,
    stock_qty       INT             NOT NULL DEFAULT 0,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- ORDERS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    order_id        VARCHAR(20)     PRIMARY KEY,
    customer_name   VARCHAR(255)    NOT NULL,
    customer_email  VARCHAR(255)    NOT NULL,
    product_id      VARCHAR(20)     REFERENCES products(product_id),
    quantity        INT             NOT NULL DEFAULT 1,
    total_amount    NUMERIC(10, 2)  NOT NULL,
    status          VARCHAR(50)     NOT NULL DEFAULT 'processing',
    -- status values: processing | shipped | delivered | cancelled | refunded
    placed_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_status     ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_customer   ON orders(customer_email);

-- ---------------------------------------------------------------------------
-- SESSION HISTORY  (stores ADK conversation turns)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_history (
    id              SERIAL          PRIMARY KEY,
    session_id      VARCHAR(100)    NOT NULL,
    user_id         VARCHAR(100)    NOT NULL,
    role            VARCHAR(20)     NOT NULL,   -- 'user' | 'assistant'
    message         TEXT            NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_history_session ON session_history(session_id);

-- =============================================================================
-- SEED DATA
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Products
-- ---------------------------------------------------------------------------
INSERT INTO products (product_id, name, description, price, stock_qty, is_active) VALUES
-- normal, in-stock products
('PRD-101', 'Wireless Noise-Cancelling Headphones',
 'Over-ear headphones with 30hr battery and ANC technology.',
 129.99, 42, TRUE),

('PRD-102', 'Mechanical Keyboard — TKL',
 'Tenkeyless mechanical keyboard with Cherry MX Brown switches.',
 89.99, 15, TRUE),

('PRD-103', 'USB-C 4-Port Hub',
 'Compact hub with 2x USB-A, 1x USB-C PD 100W, 1x HDMI 4K.',
 34.99, 78, TRUE),

-- edge case: out of stock
('PRD-104', 'Ergonomic Laptop Stand',
 'Aluminium adjustable stand, fits laptops 11–17 inch.',
 49.99, 0, TRUE),

-- edge case: inactive / discontinued product
('PRD-105', 'Bluetooth Speaker Mini',
 'Discontinued model — replaced by PRD-106.',
 29.99, 0, FALSE);


-- ---------------------------------------------------------------------------
-- Orders
-- ---------------------------------------------------------------------------
INSERT INTO orders (order_id, customer_name, customer_email, product_id, quantity, total_amount, status, placed_at) VALUES
-- normal delivered order
('ORD-001', 'Alice Johnson', 'alice@example.com',
 'PRD-101', 1, 129.99, 'delivered',
 NOW() - INTERVAL '10 days'),

-- shipped, in transit
('ORD-002', 'Bob Smith', 'bob@example.com',
 'PRD-102', 1, 89.99, 'shipped',
 NOW() - INTERVAL '3 days'),

-- still processing
('ORD-003', 'Carol White', 'carol@example.com',
 'PRD-103', 2, 69.98, 'processing',
 NOW() - INTERVAL '1 day'),

-- edge case: cancelled order
('ORD-004', 'David Lee', 'david@example.com',
 'PRD-101', 1, 129.99, 'cancelled',
 NOW() - INTERVAL '7 days'),

-- edge case: refunded order
('ORD-005', 'Eva Martinez', 'eva@example.com',
 'PRD-104', 1, 49.99, 'refunded',
 NOW() - INTERVAL '14 days');