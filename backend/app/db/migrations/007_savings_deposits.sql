-- Engångsinsättningar (negativt belopp = uttag) på toppnivåkonton. Räknas in
-- i insatt kapital så att klumpinsättningar inte visas som avkastning.
CREATE TABLE savings_deposits (
    id INTEGER PRIMARY KEY,
    savings_account_id INTEGER NOT NULL REFERENCES savings_accounts(id) ON DELETE CASCADE,
    deposit_date TEXT NOT NULL,
    amount_ore INTEGER NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_savings_deposits_account ON savings_deposits(savings_account_id);
