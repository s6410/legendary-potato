-- Hushållsmedlem per transaktion: sätts från kortexportens ägarkolumn
-- (t.ex. Handelsbanken) eller manuellt. NULL = ej angiven.
ALTER TABLE transactions ADD COLUMN member TEXT;
CREATE INDEX idx_txn_member ON transactions(member);
