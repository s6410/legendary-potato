-- Toleransband för innehavsdrift per konto (±procentenheter). NULL = inget
-- band: drift flaggas som tidigare (varning ≥ 1, rött ≥ 5).
ALTER TABLE savings_accounts ADD COLUMN drift_band_pct REAL;
