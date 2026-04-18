CREATE TABLE meals (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(6)))),
  meal_type TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
  calories REAL,
  protein_g REAL,
  carbs_g REAL,
  fat_g REAL,
  logged_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
);

CREATE TABLE meal_templates (
  id text PRIMARY KEY DEFAULT lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(6))),
  name text NOT NULL,
  calories real,
  protein_g real,
  carbs_g real,
  fat_g real,
  notes text DEFAULT '' NOT NULL
);
