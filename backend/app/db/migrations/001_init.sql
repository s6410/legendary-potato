CREATE TABLE accounts (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'checking',       -- 'checking' | 'credit_card' | 'savings_ref'
  currency TEXT NOT NULL DEFAULT 'SEK',
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE categories (
  id INTEGER PRIMARY KEY,
  parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'expense',        -- 'expense' | 'income' | 'transfer' | 'exclude'
  color TEXT,
  icon TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(parent_id, name)
);

CREATE TABLE import_format_profiles (
  id INTEGER PRIMARY KEY,
  fingerprint TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  default_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
  file_type TEXT NOT NULL,                     -- 'csv' | 'xlsx'
  delimiter TEXT,
  encoding TEXT,
  decimal_separator TEXT NOT NULL DEFAULT ',',
  thousands_separator TEXT,
  date_format TEXT NOT NULL DEFAULT '%Y-%m-%d',
  header_row_index INTEGER NOT NULL DEFAULT 0,
  invert_sign INTEGER NOT NULL DEFAULT 0,
  skip_value TEXT,                             -- rows whose date/type cell equals this are skipped (e.g. 'Reserverat')
  column_mapping TEXT NOT NULL,                -- JSON
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE import_batches (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  profile_id INTEGER NOT NULL REFERENCES import_format_profiles(id),
  filename TEXT,
  file_sha256 TEXT,
  imported_at TEXT NOT NULL DEFAULT (datetime('now')),
  row_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'committed'     -- 'committed' | 'reverted'
);

CREATE TABLE transactions (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
  booked_date TEXT NOT NULL,
  amount_ore INTEGER NOT NULL,
  description_raw TEXT NOT NULL,
  description_norm TEXT NOT NULL,
  balance_ore INTEGER,
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  category_source TEXT,                        -- 'rule' | 'manual' | NULL
  applied_rule_id INTEGER,
  dedup_hash TEXT NOT NULL,
  occurrence_index INTEGER NOT NULL DEFAULT 0,
  is_excluded INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(account_id, dedup_hash)
);
CREATE INDEX idx_txn_date ON transactions(booked_date);
CREATE INDEX idx_txn_cat  ON transactions(category_id);
CREATE INDEX idx_txn_norm ON transactions(description_norm);
CREATE INDEX idx_txn_batch ON transactions(batch_id);

CREATE TABLE categorization_rules (
  id INTEGER PRIMARY KEY,
  match_type TEXT NOT NULL,                    -- 'exact' | 'prefix' | 'contains'
  pattern TEXT NOT NULL,
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
  priority INTEGER NOT NULL DEFAULT 0,
  hit_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(match_type, pattern, account_id)
);

CREATE TABLE transaction_links (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,                          -- 'refund' | 'transfer'
  txn_a_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
  txn_b_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'suggested',    -- 'suggested' | 'confirmed' | 'dismissed'
  score REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(txn_a_id, txn_b_id)
);
CREATE UNIQUE INDEX idx_link_a ON transaction_links(txn_a_id) WHERE status='confirmed';
CREATE UNIQUE INDEX idx_link_b ON transaction_links(txn_b_id) WHERE status='confirmed';

CREATE TABLE savings_accounts (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  asset_class TEXT NOT NULL DEFAULT 'other',   -- 'equity' | 'fixed_income' | 'cash' | 'other' (fritext ok)
  is_active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE savings_snapshots (
  id INTEGER PRIMARY KEY,
  savings_account_id INTEGER NOT NULL REFERENCES savings_accounts(id) ON DELETE CASCADE,
  snapshot_date TEXT NOT NULL,
  value_ore INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(savings_account_id, snapshot_date)
);

CREATE TABLE target_allocations (
  id INTEGER PRIMARY KEY,
  asset_class TEXT NOT NULL UNIQUE,
  target_pct REAL NOT NULL
);

CREATE TABLE budgets (
  id INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  amount_ore INTEGER NOT NULL,
  valid_from TEXT NOT NULL,                    -- 'YYYY-MM'
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(category_id, valid_from)
);

CREATE TABLE recurring_overrides (
  id INTEGER PRIMARY KEY,
  description_norm TEXT NOT NULL,
  account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
  status TEXT NOT NULL,                        -- 'confirmed' | 'dismissed'
  UNIQUE(description_norm, account_id)
);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
