-- Sparplaner: antaget månadssparande per toppnivåkonto. Vid beloppsändring
-- kedjas rader: den aktiva avslutas (end_date) och en ny börjar med
-- ackumulerat insatt kapital i start_value_ore.
CREATE TABLE savings_plans (
    id INTEGER PRIMARY KEY,
    savings_account_id INTEGER NOT NULL REFERENCES savings_accounts(id) ON DELETE CASCADE,
    monthly_amount_ore INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    start_value_ore INTEGER NOT NULL DEFAULT 0,
    end_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_savings_plans_account ON savings_plans(savings_account_id);
