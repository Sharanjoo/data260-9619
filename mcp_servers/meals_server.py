"""HW5 Part 2A: TheMealDB tutorial MCP server (local, STDIO transport).

Four tools wrapping TheMealDB's public JSON API using the published test
key "1" (no registration/API key needed, per the assignment spec):

    search_meals_by_name(query, limit=5)
    meals_by_ingredient(ingredient, limit=12)
    random_meal()
    meal_details(id)

Run with the MCP Inspector:
    mcp dev meals_server.py

Output shapes (per spec):
  - search_meals_by_name / meals_by_ingredient: a list of per-item objects
    ({id, name, area, category, thumb} / {id, name, thumb}), wrapped as
    {"meals": [...], "message": None}. On no results (TheMealDB returns
    "meals": null), returns {"meals": [], "message": "no matches"} instead
    of raising -- a clear, empty result rather than an error.
  - meal_details / random_meal: a single object
    {id, name, category, area, instructions, image, source, youtube,
    ingredients: [{name, measure}]}, wrapped as {"meal": {...}, "message":
    None}, or {"meal": None, "message": "no matches"} when not found.
  - Network errors and malformed JSON from TheMealDB are NOT swallowed --
    they're raised as clean RuntimeErrors so the MCP Inspector/client shows
    them directly, per the spec's error-handling rule.

Logging rule (STDIO transport): never write to stdout -- that corrupts the
JSON-RPC stream. All logging here goes to stderr via the standard logging
module.

Version pin note: `mcp dev <file>` launches this server via
`uv run --with mcp ... mcp run <file>`, which otherwise pulls the latest
`mcp` package (currently 2.x, where FastMCP was renamed/replaced). The
FastMCP(..., dependencies=[...]) call below adds "mcp[cli]<2" to that uv
invocation so it resolves to the last 1.x release instead -- no extra
flags needed when you run `mcp dev meals_server.py`.
"""
from __future__ import annotations

import logging
import sys

import requests
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [meals_server] %(levelname)s: %(message)s",
)
logger = logging.getLogger("meals_server")

# Published TheMealDB test key "1" -- sufficient for this assignment, no
# registration needed.
API_BASE = "https://www.themealdb.com/api/json/v1/1"
TIMEOUT_SECONDS = 10

mcp = FastMCP("meals", dependencies=["mcp[cli]<2", "requests"])


def _get(path: str, params: dict) -> dict:
    url = f"{API_BASE}/{path}"
    logger.info("GET %s params=%r", url, params)
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("network error calling %s: %s", url, exc)
        raise RuntimeError(f"TheMealDB request failed: {exc}") from exc
    try:
        return resp.json()
    except ValueError as exc:  # JSON decode error
        logger.error("bad JSON from %s: %s", url, exc)
        raise RuntimeError(f"TheMealDB returned invalid JSON: {exc}") from exc


def _meal_summary(meal: dict) -> dict:
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "area": meal.get("strArea"),
        "category": meal.get("strCategory"),
        "thumb": meal.get("strMealThumb"),
    }


def _meal_card(meal: dict) -> dict:
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "thumb": meal.get("strMealThumb"),
    }


def _meal_full(meal: dict) -> dict:
    ingredients = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        measure = (meal.get(f"strMeasure{i}") or "").strip()
        if name:
            ingredients.append({"name": name, "measure": measure})
    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource"),
        "youtube": meal.get("strYoutube"),
        "ingredients": ingredients,
    }


@mcp.tool()
def search_meals_by_name(query: str, limit: int = 5) -> dict:
    """Search TheMealDB for meals by name. Returns up to `limit` (1-25)
    {id, name, area, category, thumb} objects."""
    if not isinstance(query, str) or not query.strip():
        return {"meals": [], "message": "no matches: query must be non-empty"}
    try:
        limit = max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        raise RuntimeError("limit must be an integer")

    data = _get("search.php", {"s": query.strip()})
    meals = data.get("meals")
    if not meals:
        return {"meals": [], "message": "no matches"}
    return {"meals": [_meal_summary(m) for m in meals[:limit]], "message": None}


@mcp.tool()
def meals_by_ingredient(ingredient: str, limit: int = 12) -> dict:
    """Filter TheMealDB meals by main ingredient. Returns up to `limit`
    {id, name, thumb} cards."""
    if not isinstance(ingredient, str) or not ingredient.strip():
        return {"meals": [], "message": "no matches: ingredient must be non-empty"}
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        raise RuntimeError("limit must be an integer")

    data = _get("filter.php", {"i": ingredient.strip()})
    meals = data.get("meals")
    if not meals:
        return {"meals": [], "message": "no matches"}
    return {"meals": [_meal_card(m) for m in meals[:limit]], "message": None}


@mcp.tool()
def random_meal() -> dict:
    """Return one random meal with full recipe details (same shape as meal_details)."""
    data = _get("random.php", {})
    meals = data.get("meals")
    if not meals:
        return {"meal": None, "message": "no matches"}
    return {"meal": _meal_full(meals[0]), "message": None}


@mcp.tool()
def meal_details(id: str) -> dict:
    """Look up one TheMealDB meal by id and return its full recipe details."""
    if id is None or str(id).strip() == "":
        return {"meal": None, "message": "no matches: id must be non-empty"}
    data = _get("lookup.php", {"i": str(id).strip()})
    meals = data.get("meals")
    if not meals:
        return {"meal": None, "message": "no matches"}
    return {"meal": _meal_full(meals[0]), "message": None}


if __name__ == "__main__":
    mcp.run(transport="stdio")
