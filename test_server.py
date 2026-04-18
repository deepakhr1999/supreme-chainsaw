"""
Tests for meal-tracking MCP tools in my_server.py.

Uses FastMCPTransport for in-process testing (no HTTP server needed) and
patches get_db() to return an in-memory SQLite connection so tests never
touch the real Turso database.
"""

import json
import sqlite3
import pytest
import pytest_asyncio
from unittest.mock import patch
from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport

import my_server
from my_server import mcp

MEALS_SCHEMA = """
CREATE TABLE meals (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(6)))),
  meal_type TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
  calories REAL,
  protein_g REAL,
  carbs_g REAL,
  fat_g REAL,
  logged_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
  desc TEXT NOT NULL DEFAULT ''
)
"""

TEMPLATES_SCHEMA = """
CREATE TABLE meal_templates (
  id text PRIMARY KEY DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(6)))),
  name text NOT NULL,
  calories real,
  protein_g real,
  carbs_g real,
  fat_g real,
  notes text DEFAULT '' NOT NULL
)
"""


def make_db():
    """Return a fresh in-memory SQLite connection with the meals schema."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute(MEALS_SCHEMA)
    conn.execute(TEMPLATES_SCHEMA)
    conn.commit()
    return conn


@pytest.fixture
def db():
    return make_db()


@pytest.fixture
def patched_db(db):
    """Patch get_db() in my_server to return the in-memory DB."""
    with patch.object(my_server, "get_db", return_value=db):
        yield db


@pytest_asyncio.fixture
async def client(patched_db):
    async with Client(FastMCPTransport(mcp)) as c:
        yield c


# ---------------------------------------------------------------------------
# log_meal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_meal_basic(client):
    args = {
        "meal_type": "breakfast",
        "calories": 400,
        "protein_g": 30,
        "carbs_g": 40,
        "fat_g": 10,
        "logged_at": "2026-04-15T12:00:00+00:00",
    }
    result = await client.call_tool("log_meal", args)
    meal = json.loads(result.content[0].text)
    assert meal["id"] is not None
    assert meal["meal_type"] == "breakfast"
    assert meal["calories"] == 400
    assert meal["logged_at"] == "2026-04-15T08:00:00-04:00"


@pytest.mark.asyncio
async def test_log_meal_optional_nutrients(client):
    result = await client.call_tool(
        "log_meal",
        {
            "meal_type": "snack",
            "logged_at": "2026-04-15T15:00:00+00:00",
        },
    )
    meal = json.loads(result.content[0].text)
    assert meal["meal_type"] == "snack"
    assert meal["calories"] is None
    assert meal["protein_g"] is None


# ---------------------------------------------------------------------------
# update_meal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_meal(client):
    logged = await client.call_tool(
        "log_meal",
        {
            "meal_type": "lunch",
            "calories": 500,
            "logged_at": "2026-04-15T17:00:00+00:00",
        },
    )
    meal_id = json.loads(logged.content[0].text)["id"]

    result = await client.call_tool(
        "update_meal",
        {
            "meal_id": meal_id,
            "calories": 600,
            "protein_g": 45,
        },
    )
    updated = json.loads(result.content[0].text)
    assert updated["calories"] == 600
    assert updated["protein_g"] == 45
    assert updated["meal_type"] == "lunch"  # unchanged


@pytest.mark.asyncio
async def test_update_meal_no_fields(client):
    result = await client.call_tool("update_meal", {"meal_id": "fake-id"})
    assert result.content[0].text == "No fields provided to update."


@pytest.mark.asyncio
async def test_update_meal_not_found(client):
    result = await client.call_tool(
        "update_meal",
        {
            "meal_id": "nonexistent",
            "calories": 100,
        },
    )
    assert "No meal found" in result.content[0].text


# ---------------------------------------------------------------------------
# delete_meal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_meal(client):
    logged = await client.call_tool(
        "log_meal",
        {
            "meal_type": "dinner",
            "calories": 700,
            "logged_at": "2026-04-15T23:00:00+00:00",
        },
    )
    meal_id = json.loads(logged.content[0].text)["id"]

    result = await client.call_tool("delete_meal", {"meal_id": meal_id})
    assert meal_id in result.content[0].text

    # Confirm gone
    result2 = await client.call_tool("delete_meal", {"meal_id": meal_id})
    assert "No meal found" in result2.content[0].text


@pytest.mark.asyncio
async def test_delete_meal_not_found(client):
    result = await client.call_tool("delete_meal", {"meal_id": "ghost"})
    assert "No meal found" in result.content[0].text


# ---------------------------------------------------------------------------
# get_meals_by_date  (NYC timezone filtering)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_meals_by_date(client):
    # 2026-04-15 in NYC = UTC 04:00 -> 04:00 next day
    # Meal at 2026-04-15T10:00 UTC = 6 AM NYC → should appear
    await client.call_tool(
        "log_meal",
        {
            "meal_type": "breakfast",
            "calories": 300,
            "logged_at": "2026-04-15T10:00:00+00:00",
        },
    )
    # Meal at 2026-04-15T03:00 UTC = 11 PM NYC on April 14 → should NOT appear
    await client.call_tool(
        "log_meal",
        {
            "meal_type": "dinner",
            "calories": 800,
            "logged_at": "2026-04-15T03:00:00+00:00",
        },
    )

    result = await client.call_tool("get_meals_by_date", {"date": "2026-04-15"})
    meals = json.loads(result.content[0].text)
    assert len(meals) == 1
    assert meals[0]["calories"] == 300


@pytest.mark.asyncio
async def test_get_meals_by_date_empty(client):
    result = await client.call_tool("get_meals_by_date", {"date": "2020-01-01"})
    meals = json.loads(result.content[0].text)
    assert meals == []


# ---------------------------------------------------------------------------
# get_meals_by_date_range
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_meals_by_date_range(client):
    meals_data = [
        ("breakfast", 300, "2026-04-13T12:00:00+00:00"),
        ("lunch", 500, "2026-04-14T17:00:00+00:00"),
        ("dinner", 700, "2026-04-15T22:00:00+00:00"),
        ("snack", 100, "2026-04-17T14:00:00+00:00"),  # outside range
    ]
    for meal_type, calories, logged_at in meals_data:
        await client.call_tool(
            "log_meal",
            {
                "meal_type": meal_type,
                "calories": calories,
                "logged_at": logged_at,
            },
        )

    result = await client.call_tool(
        "get_meals_by_date_range",
        {
            "start_date": "2026-04-13",
            "end_date": "2026-04-15",
        },
    )
    meals = json.loads(result.content[0].text)
    assert len(meals) == 3
    calories_list = [m["calories"] for m in meals]
    assert 100 not in calories_list


# ---------------------------------------------------------------------------
# get_nutrition_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_nutrition_summary(client):
    # Two meals on April 15 NYC (UTC 04:00–28:00)
    await client.call_tool(
        "log_meal",
        {
            "meal_type": "breakfast",
            "calories": 400,
            "protein_g": 30,
            "carbs_g": 40,
            "fat_g": 10,
            "logged_at": "2026-04-15T12:00:00+00:00",
        },
    )
    await client.call_tool(
        "log_meal",
        {
            "meal_type": "lunch",
            "calories": 600,
            "protein_g": 40,
            "carbs_g": 60,
            "fat_g": 20,
            "logged_at": "2026-04-15T18:00:00+00:00",
        },
    )

    result = await client.call_tool(
        "get_nutrition_summary",
        {
            "start_date": "2026-04-15",
            "end_date": "2026-04-15",
        },
    )
    summary = json.loads(result.content[0].text)

    assert summary["day_count"] == 1
    assert summary["totals"]["calories"] == 1000.0
    assert summary["totals"]["protein_g"] == 70.0
    assert summary["daily_averages"]["calories"] == 1000.0
    assert "2026-04-15" in summary["by_date"]
    assert summary["by_date"]["2026-04-15"]["meal_count"] == 2


@pytest.mark.asyncio
async def test_get_nutrition_summary_empty(client):
    result = await client.call_tool(
        "get_nutrition_summary",
        {
            "start_date": "2020-01-01",
            "end_date": "2020-01-01",
        },
    )
    summary = json.loads(result.content[0].text)
    assert summary["day_count"] == 0
    assert summary["totals"]["calories"] == 0.0


# ---------------------------------------------------------------------------
# meal_templates CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_meal_template(client):
    result = await client.call_tool(
        "create_meal_template",
        {
            "name": "Oatmeal",
            "calories": 350,
            "protein_g": 12,
            "carbs_g": 60,
            "fat_g": 6,
            "notes": "with blueberries",
        },
    )
    t = json.loads(result.content[0].text)
    assert t["name"] == "Oatmeal"
    assert t["calories"] == 350
    assert t["notes"] == "with blueberries"
    assert t["id"] is not None


@pytest.mark.asyncio
async def test_update_meal_template(client):
    created = await client.call_tool(
        "create_meal_template", {"name": "Rice Bowl", "calories": 500}
    )
    tid = json.loads(created.content[0].text)["id"]

    result = await client.call_tool(
        "update_meal_template", {"template_id": tid, "calories": 600, "protein_g": 30}
    )
    updated = json.loads(result.content[0].text)
    assert updated["calories"] == 600
    assert updated["protein_g"] == 30
    assert updated["name"] == "Rice Bowl"


@pytest.mark.asyncio
async def test_update_meal_template_no_fields(client):
    result = await client.call_tool("update_meal_template", {"template_id": "fake-id"})
    assert result.content[0].text == "No fields provided to update."


@pytest.mark.asyncio
async def test_update_meal_template_not_found(client):
    result = await client.call_tool(
        "update_meal_template", {"template_id": "nonexistent", "calories": 100}
    )
    assert "No meal template found" in result.content[0].text


@pytest.mark.asyncio
async def test_delete_meal_template(client):
    created = await client.call_tool(
        "create_meal_template", {"name": "Temp", "calories": 200}
    )
    tid = json.loads(created.content[0].text)["id"]

    result = await client.call_tool("delete_meal_template", {"template_id": tid})
    assert tid in result.content[0].text

    result2 = await client.call_tool("delete_meal_template", {"template_id": tid})
    assert "No meal template found" in result2.content[0].text


@pytest.mark.asyncio
async def test_delete_meal_template_not_found(client):
    result = await client.call_tool("delete_meal_template", {"template_id": "ghost"})
    assert "No meal template found" in result.content[0].text


# ---------------------------------------------------------------------------
# log_meal_from_template
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_meal_from_template(client):
    created = await client.call_tool(
        "create_meal_template",
        {
            "name": "Chicken & Rice",
            "calories": 650,
            "protein_g": 50,
            "carbs_g": 70,
            "fat_g": 12,
        },
    )
    tid = json.loads(created.content[0].text)["id"]

    result = await client.call_tool(
        "log_meal_from_template",
        {
            "template_id": tid,
            "meal_type": "lunch",
            "logged_at": "2026-04-15T17:00:00+00:00",
        },
    )
    meal = json.loads(result.content[0].text)
    assert meal["meal_type"] == "lunch"
    assert meal["calories"] == 650
    assert meal["protein_g"] == 50
    assert meal["desc"] == "Chicken & Rice"


@pytest.mark.asyncio
async def test_log_meal_from_template_not_found(client):
    result = await client.call_tool(
        "log_meal_from_template",
        {
            "template_id": "ghost",
            "meal_type": "breakfast",
        },
    )
    assert "No meal template found" in result.content[0].text
