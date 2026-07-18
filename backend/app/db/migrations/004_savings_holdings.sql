-- Innehav inom sparkonton: ett innehav är ett sparkonto med förälder.
-- target_pct är innehavets målandel inom förälderkontot (klassmålen är kvar
-- i target_allocations för den övergripande driften).
ALTER TABLE savings_accounts ADD COLUMN parent_id INTEGER REFERENCES savings_accounts(id) ON DELETE CASCADE;
ALTER TABLE savings_accounts ADD COLUMN target_pct REAL;
