# supreme-chainsaw

A personal [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server for tracking fitness and nutrition — built with [FastMCP](https://github.com/jlowin/fastmcp) and deployed so Claude can log meals, query workout history, and summarize nutrition data on your behalf.

## What it does

**supreme-chainsaw** bridges two data sources:

- **Hevy** — your workout app. The server reads workout history and body measurements via the Hevy REST API.
- **A Turso (libSQL) database** — a personal nutrition log. The server provides full CRUD for meals and reusable meal templates.

All timestamps are handled in the **America/New_York** timezone, so daily summaries line up with your calendar.

## Tools

### Workouts (Hevy)

| Tool | Description |
|---|---|
| `get_workouts` | Paginated list of workouts, newest first |
| `get_workout_count` | Total number of workouts logged |
| `body_measurements` | Paginated body measurements (weight, body fat, etc.) |

### Meal Logging

| Tool | Description |
|---|---|
| `log_meal` | Log a meal with calories, protein, carbs, fat, type, and optional description |
| `update_meal` | Edit any field of an existing meal by ID |
| `delete_meal` | Remove a meal by ID |
| `get_meals_today` | All meals logged today (NYC timezone) |
| `get_meals_by_date` | All meals on a specific `YYYY-MM-DD` date |
| `get_meals_by_date_range` | All meals between two dates (inclusive) |
| `get_nutrition_summary` | Daily totals + averages over a date range |

### Meal Templates

Reusable macro presets so you don't re-enter the same meals every day.

| Tool | Description |
|---|---|
| `list_templates` | List all saved templates |
| `create_meal_template` | Create a new template with name, macros, and notes |
| `update_meal_template` | Edit an existing template by ID |
| `delete_meal_template` | Remove a template by ID |
| `log_meal_from_template` | Log a meal using a saved template's macros |

## Database schema

```sql
-- nutrition log
CREATE TABLE meals (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(6)))),
  meal_type TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
  calories REAL,
  protein_g REAL,
  carbs_g REAL,
  fat_g REAL,
  logged_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
);

-- reusable templates
CREATE TABLE meal_templates (
  id text PRIMARY KEY DEFAULT lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(6))),
  name text NOT NULL,
  calories real,
  protein_g real,
  carbs_g real,
  fat_g real,
  notes text DEFAULT '' NOT NULL
);
```

## Self-hosting

This repo is designed to be forked and deployed as your own personal MCP server. Here's how:

### 1. Fork this repo

Click **Fork** on GitHub to get your own copy.

### 2. Create a Turso database

1. Sign up at [turso.tech](https://turso.tech) and create a new database called `nutrition`
2. Run the schema against it:
   ```bash
   turso db shell nutrition < create_table.sql
   ```
3. Note your **database URL** (`libsql://...`) and generate an **auth token** from the Turso dashboard.

### 3. Deploy on Prefect Horizon

1. Sign up at [Prefect Horizon](https://www.prefect.io/horizon) and create a new MCP server deployment pointing at your forked repo.
2. Add the following environment variables in the Prefect Horizon platform:

| Variable | Description |
|---|---|
| `TURSO_DATABASE_URL` | Your Turso database URL (`libsql://...`) |
| `TURSO_AUTH_TOKEN` | Your Turso auth token |
| `HEVY` | Your [Hevy](https://www.hevyapp.com/) API key |

### 4. Connect to Claude

Add the MCP server URL provided by Prefect Horizon to Claude's MCP settings. That's it — Claude can now log and query your personal nutrition and workout data.

## Connecting to Claude

Add the deployed server URL to Claude's MCP settings. Once connected, Claude can answer questions like:

- *"What did I eat yesterday?"*
- *"Log my lunch — chicken and rice, 600 cal, 45g protein, 60g carbs, 15g fat."*
- *"Show me my average daily protein this week."*
- *"How many workouts have I done this month?"*
- *"Create a template for my usual breakfast and log it."*

## Tech stack

- [FastMCP](https://github.com/jlowin/fastmcp) — MCP server framework
- [libsql](https://github.com/tursodatabase/libsql-python) — Turso/libSQL client with sync support
- [pytz](https://pypi.org/project/pytz/) — Timezone handling
- [pandas](https://pandas.pydata.org/) — Used for template queries
- [requests](https://requests.readthedocs.io/) — Hevy API calls
