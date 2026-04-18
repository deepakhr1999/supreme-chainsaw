from fastmcp import FastMCP
from typing import Annotated, Optional
import json
import os
import requests
import libsql  # type: ignore
from datetime import datetime, timedelta
import pytz

mcp = FastMCP("Hevy MCP Server")

NYC = pytz.timezone("America/New_York")


def get_db(sync: bool = False):
    url = os.environ.get("TURSO_DATABASE_URL", "")
    token = os.environ.get("TURSO_AUTH_TOKEN", "")
    conn = libsql.connect("/tmp/nutrition.db", sync_url=url, auth_token=token)
    if sync:
        conn.sync()
    return conn


def _nyc_day_to_utc_range(date_str: str) -> tuple[str, str]:
    """Convert a NYC calendar date (YYYY-MM-DD) to a UTC [start, end) range.
    Returns ISO strings with +00:00 suffix to match stored timestamps."""
    day_start = NYC.localize(datetime.strptime(date_str, "%Y-%m-%d"))
    day_end = day_start + timedelta(days=1)
    return (
        day_start.astimezone(pytz.utc).isoformat(),
        day_end.astimezone(pytz.utc).isoformat(),
    )


def _row_to_dict(row) -> dict:
    # used only while returning existing data to user
    return {
        "id": row[0],
        "meal_type": row[1],
        "calories": row[2],
        "protein_g": row[3],
        "carbs_g": row[4],
        "fat_g": row[5],
        "logged_at": datetime.fromisoformat(row[6]).astimezone(NYC).isoformat(),
        "desc": row[7],
    }


@mcp.tool
def get_workouts(
    page: Annotated[int, "Page number, starting from 1"],
    page_size: Annotated[int, "Number of workouts per page (max 10)"],
) -> str:
    """Get a paginated list of workouts from Hevy, ordered newest to oldest."""
    url = "https://api.hevyapp.com/v1/workouts"
    params = {"page": page, "pageSize": page_size}
    headers = {"accept": "application/json", "api-key": os.environ.get("HEVY", "")}
    response = requests.get(url, headers=headers, params=params)
    return response.text


@mcp.tool
def body_measurements(
    page: Annotated[int, "Page number, starting from 1"],
    page_size: Annotated[int, "Number of workouts per page (max 10)"],
) -> str:
    """Get a paginated list of body measurements (weight, body fat, etc.) from Hevy."""
    url = "https://api.hevyapp.com/v1/body_measurements"
    params = {"page": page, "pageSize": page_size}
    headers = {"accept": "application/json", "api-key": os.environ.get("HEVY", "")}
    response = requests.get(url, headers=headers, params=params)
    return response.text


@mcp.tool
def get_workout_count() -> str:
    """Get the total number of workouts logged in Hevy."""
    url = "https://api.hevyapp.com/v1/workouts/count"
    headers = {"accept": "application/json", "api-key": os.environ.get("HEVY", "")}
    response = requests.get(url, headers=headers)
    return response.text


@mcp.tool
def log_meal(
    meal_type: Annotated[str, "One of: breakfast, lunch, dinner, snack"],
    calories: Annotated[Optional[float], "Calories"] = None,
    protein_g: Annotated[Optional[float], "Protein in grams"] = None,
    carbs_g: Annotated[Optional[float], "Carbs in grams"] = None,
    fat_g: Annotated[Optional[float], "Fat in grams"] = None,
    logged_at: Annotated[Optional[str], "ISO timestamp (UTC). Defaults to now."] = None,
    desc: Annotated[Optional[str], "Description of the meal"] = None,
) -> str:
    """Log a meal to the database."""
    if logged_at is None:
        logged_at = datetime.now(pytz.utc).isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO meals (meal_type, calories, protein_g, carbs_g, fat_g, logged_at, desc) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (meal_type, calories, protein_g, carbs_g, fat_g, logged_at, desc or ""),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM meals WHERE logged_at = ? AND meal_type = ? ORDER BY rowid DESC LIMIT 1",
        (logged_at, meal_type),
    ).fetchone()
    return json.dumps(_row_to_dict(row))


@mcp.tool
def update_meal(
    meal_id: Annotated[str, "ID of the meal to update"],
    meal_type: Annotated[
        Optional[str], "One of: breakfast, lunch, dinner, snack"
    ] = None,
    calories: Annotated[Optional[float], "Calories"] = None,
    protein_g: Annotated[Optional[float], "Protein in grams"] = None,
    carbs_g: Annotated[Optional[float], "Carbs in grams"] = None,
    fat_g: Annotated[Optional[float], "Fat in grams"] = None,
    logged_at: Annotated[Optional[str], "ISO timestamp (UTC)"] = None,
    desc: Annotated[Optional[str], "Description of the meal"] = None,
) -> str:
    """Update fields of an existing meal by ID."""
    fields = {
        "meal_type": meal_type,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "logged_at": logged_at,
        "desc": desc,
    }
    updates = {k: v for k, v in fields.items() if v is not None}
    if not updates:
        return "No fields provided to update."
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [meal_id]
    conn = get_db()
    conn.execute(f"UPDATE meals SET {set_clause} WHERE id = ?", tuple(values))
    conn.commit()
    row = conn.execute("SELECT * FROM meals WHERE id = ?", (meal_id,)).fetchone()
    if row is None:
        return f"No meal found with id {meal_id}"
    return json.dumps(_row_to_dict(row))


@mcp.tool
def delete_meal(
    meal_id: Annotated[str, "ID of the meal to delete"],
) -> str:
    """Delete a meal by ID."""
    conn = get_db()
    row = conn.execute("SELECT id FROM meals WHERE id = ?", (meal_id,)).fetchone()
    if row is None:
        return f"No meal found with id {meal_id}"
    conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
    conn.commit()
    return f"Deleted meal {meal_id}"


@mcp.tool
def get_meals_by_date(
    date: Annotated[str, "Date in YYYY-MM-DD format (NYC timezone)"],
) -> str:
    """Get all meals logged on a specific NYC calendar date."""
    start_utc, end_utc = _nyc_day_to_utc_range(date)
    conn = get_db(sync=True)
    rows = conn.execute(
        "SELECT * FROM meals WHERE logged_at >= ? AND logged_at < ? ORDER BY logged_at",
        (start_utc, end_utc),
    ).fetchall()
    return json.dumps([_row_to_dict(r) for r in rows])


@mcp.tool
def get_meals_by_date_range(
    start_date: Annotated[str, "Start date YYYY-MM-DD (inclusive, NYC timezone)"],
    end_date: Annotated[str, "End date YYYY-MM-DD (inclusive, NYC timezone)"],
) -> str:
    """Get all meals in a date range, filtered by NYC timezone."""
    start_utc, _ = _nyc_day_to_utc_range(start_date)
    _, end_utc = _nyc_day_to_utc_range(end_date)
    conn = get_db(sync=True)
    rows = conn.execute(
        "SELECT * FROM meals WHERE logged_at >= ? AND logged_at < ? ORDER BY logged_at",
        (start_utc, end_utc),
    ).fetchall()
    return json.dumps([_row_to_dict(r) for r in rows])


@mcp.tool
def get_meals_today() -> str:
    """Get all meals logged today (NYC timezone)."""
    today = datetime.now(NYC).strftime("%Y-%m-%d")
    return get_meals_by_date(today)


@mcp.tool
def get_nutrition_summary(
    start_date: Annotated[str, "Start date YYYY-MM-DD (inclusive, NYC timezone)"],
    end_date: Annotated[str, "End date YYYY-MM-DD (inclusive, NYC timezone)"],
) -> str:
    """Get daily nutrition totals and averages over a date range (NYC timezone)."""
    start_utc, _ = _nyc_day_to_utc_range(start_date)
    _, end_utc = _nyc_day_to_utc_range(end_date)
    conn = get_db(sync=True)
    rows = conn.execute(
        "SELECT * FROM meals WHERE logged_at >= ? AND logged_at < ? ORDER BY logged_at",
        (start_utc, end_utc),
    ).fetchall()
    meals = [_row_to_dict(r) for r in rows]

    # Group by NYC date
    by_date: dict = {}
    for m in meals:
        logged_at_str = m["logged_at"]
        nyc_date = (
            datetime.fromisoformat(logged_at_str).astimezone(NYC).strftime("%Y-%m-%d")
        )
        if nyc_date not in by_date:
            by_date[nyc_date] = {
                "calories": 0.0,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
                "meal_count": 0,
            }
        d = by_date[nyc_date]
        d["calories"] += m["calories"] or 0
        d["protein_g"] += m["protein_g"] or 0
        d["carbs_g"] += m["carbs_g"] or 0
        d["fat_g"] += m["fat_g"] or 0
        d["meal_count"] += 1

    day_count = len(by_date)
    totals = {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    for d in by_date.values():
        for k in totals:
            totals[k] += d[k]

    averages = {
        k: round(v / day_count, 1) if day_count else 0 for k, v in totals.items()
    }
    return json.dumps(
        {
            "by_date": by_date,
            "day_count": day_count,
            "totals": {k: round(v, 1) for k, v in totals.items()},
            "daily_averages": averages,
        }
    )


def _template_row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "calories": row[2],
        "protein_g": row[3],
        "carbs_g": row[4],
        "fat_g": row[5],
        "notes": row[6],
    }


@mcp.tool
def create_meal_template(
    name: Annotated[str, "Name of the meal template"],
    calories: Annotated[Optional[float], "Calories"] = None,
    protein_g: Annotated[Optional[float], "Protein in grams"] = None,
    carbs_g: Annotated[Optional[float], "Carbs in grams"] = None,
    fat_g: Annotated[Optional[float], "Fat in grams"] = None,
    notes: Annotated[Optional[str], "Notes about the template"] = None,
) -> str:
    """Create a new meal template."""
    conn = get_db()
    conn.execute(
        "INSERT INTO meal_templates (name, calories, protein_g, carbs_g, fat_g, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (name, calories, protein_g, carbs_g, fat_g, notes or ""),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM meal_templates WHERE name = ? ORDER BY rowid DESC LIMIT 1",
        (name,),
    ).fetchone()
    return json.dumps(_template_row_to_dict(row))


@mcp.tool
def update_meal_template(
    template_id: Annotated[str, "ID of the template to update"],
    name: Annotated[Optional[str], "Name of the meal template"] = None,
    calories: Annotated[Optional[float], "Calories"] = None,
    protein_g: Annotated[Optional[float], "Protein in grams"] = None,
    carbs_g: Annotated[Optional[float], "Carbs in grams"] = None,
    fat_g: Annotated[Optional[float], "Fat in grams"] = None,
    notes: Annotated[Optional[str], "Notes about the template"] = None,
) -> str:
    """Update fields of an existing meal template by ID."""
    fields = {
        "name": name,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "notes": notes,
    }
    updates = {k: v for k, v in fields.items() if v is not None}
    if not updates:
        return "No fields provided to update."
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [template_id]
    conn = get_db()
    conn.execute(f"UPDATE meal_templates SET {set_clause} WHERE id = ?", tuple(values))
    conn.commit()
    row = conn.execute(
        "SELECT * FROM meal_templates WHERE id = ?", (template_id,)
    ).fetchone()
    if row is None:
        return f"No meal template found with id {template_id}"
    return json.dumps(_template_row_to_dict(row))


@mcp.tool
def delete_meal_template(
    template_id: Annotated[str, "ID of the template to delete"],
) -> str:
    """Delete a meal template by ID."""
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM meal_templates WHERE id = ?", (template_id,)
    ).fetchone()
    if row is None:
        return f"No meal template found with id {template_id}"
    conn.execute("DELETE FROM meal_templates WHERE id = ?", (template_id,))
    conn.commit()
    return f"Deleted meal template {template_id}"


@mcp.tool
def log_meal_from_template(
    template_id: Annotated[str, "ID of the meal template to log"],
    meal_type: Annotated[str, "One of: breakfast, lunch, dinner, snack"],
    logged_at: Annotated[Optional[str], "ISO timestamp (UTC). Defaults to now."] = None,
) -> str:
    """Log a meal using macros from a saved template."""
    conn = get_db(sync=True)
    row = conn.execute(
        "SELECT * FROM meal_templates WHERE id = ?", (template_id,)
    ).fetchone()
    if row is None:
        return f"No meal template found with id {template_id}"
    t = _template_row_to_dict(row)
    if logged_at is None:
        logged_at = datetime.now(pytz.utc).isoformat()
    conn.execute(
        "INSERT INTO meals (meal_type, calories, protein_g, carbs_g, fat_g, logged_at, desc) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            meal_type,
            t["calories"],
            t["protein_g"],
            t["carbs_g"],
            t["fat_g"],
            logged_at,
            t["name"],
        ),
    )
    conn.commit()
    meal_row = conn.execute(
        "SELECT * FROM meals WHERE logged_at = ? AND meal_type = ? ORDER BY rowid DESC LIMIT 1",
        (logged_at, meal_type),
    ).fetchone()
    return json.dumps(_row_to_dict(meal_row))


if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
