-- Svensk grundkategoristruktur. Huvudkategorier med underkategorier.
INSERT INTO categories (name, kind, color, icon, sort_order) VALUES
  ('Boende',        'expense',  '#6366f1', 'home',        10),
  ('Mat',           'expense',  '#f59e0b', 'utensils',    20),
  ('Transport',     'expense',  '#0ea5e9', 'car',         30),
  ('Nöje & Fritid', 'expense',  '#ec4899', 'sparkles',    40),
  ('Hälsa',         'expense',  '#10b981', 'heart',       50),
  ('Barn',          'expense',  '#f97316', 'baby',        60),
  ('Shopping',      'expense',  '#8b5cf6', 'bag',         70),
  ('Abonnemang',    'expense',  '#14b8a6', 'repeat',      80),
  ('Övrigt',        'expense',  '#64748b', 'dots',        90),
  ('Inkomst',       'income',   '#22c55e', 'trending-up', 100),
  ('Sparande',      'transfer', '#3b82f6', 'piggy-bank',  110),
  ('Överföringar',  'transfer', '#94a3b8', 'arrows',      120);

INSERT INTO categories (parent_id, name, kind, sort_order)
SELECT c.id, sub.column2, c.kind, sub.column3 FROM categories c
JOIN (VALUES
  ('Boende', 'Hyra/Avgift', 1), ('Boende', 'Bolåneränta', 2), ('Boende', 'El', 3),
  ('Boende', 'Bredband & TV', 4), ('Boende', 'Försäkring', 5), ('Boende', 'Underhåll', 6),
  ('Mat', 'Livsmedel', 1), ('Mat', 'Restaurang', 2), ('Mat', 'Café', 3), ('Mat', 'Lunch', 4),
  ('Transport', 'Kollektivtrafik', 1), ('Transport', 'Drivmedel', 2), ('Transport', 'Parkering', 3),
  ('Transport', 'Bil övrigt', 4), ('Transport', 'Taxi', 5),
  ('Nöje & Fritid', 'Aktiviteter', 1), ('Nöje & Fritid', 'Resor', 2), ('Nöje & Fritid', 'Sport', 3),
  ('Nöje & Fritid', 'Kultur', 4),
  ('Hälsa', 'Vård', 1), ('Hälsa', 'Apotek', 2), ('Hälsa', 'Träning', 3),
  ('Barn', 'Barnomsorg', 1), ('Barn', 'Kläder barn', 2), ('Barn', 'Fritidsaktiviteter', 3),
  ('Shopping', 'Kläder', 1), ('Shopping', 'Hem & Inredning', 2), ('Shopping', 'Elektronik', 3),
  ('Shopping', 'Presenter', 4),
  ('Abonnemang', 'Streaming', 1), ('Abonnemang', 'Mobil', 2), ('Abonnemang', 'Övriga abonnemang', 3),
  ('Inkomst', 'Lön', 1), ('Inkomst', 'Barnbidrag', 2), ('Inkomst', 'Återbäring', 3), ('Inkomst', 'Övrig inkomst', 4),
  ('Sparande', 'Månadssparande', 1), ('Sparande', 'Buffert', 2),
  ('Överföringar', 'Egna konton', 1), ('Överföringar', 'Kreditkortsbetalning', 2)
) AS sub ON c.name = sub.column1 AND c.parent_id IS NULL;

INSERT INTO target_allocations (asset_class, target_pct) VALUES
  ('equity', 60.0), ('fixed_income', 20.0), ('cash', 20.0);

INSERT INTO settings (key, value) VALUES ('theme', 'system'), ('include_refunds', '0');
