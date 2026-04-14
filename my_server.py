from fastmcp import FastMCP
from typing import Annotated
import os
import requests

mcp = FastMCP("Hevy MCP Server")


@mcp.tool
def greet(name: Annotated[str, "Name to greet"]) -> str:
    """Greet a person by name."""
    return f"Hello, {name}!"


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


if __name__ == "__main__":
    mcp.run(transport="http", port=8000)
