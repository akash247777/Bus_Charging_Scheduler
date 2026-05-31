"""
Loader module for reading route config and scenario JSON files.

This module translates raw JSON data into typed model objects.
It serves as the single point of contact between the file system
and the rest of the application.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    Bus, BusDefaults, Route, Segment, StationConfig,
)


# Base date for time calculations (arbitrary — we only care about relative times)
BASE_DATE = datetime(2025, 1, 1)


def parse_time(time_str: str) -> datetime:
    """Parse a time string like '19:00' into a datetime object."""
    hours, minutes = map(int, time_str.split(":"))
    return BASE_DATE.replace(hour=hours, minute=minutes, second=0, microsecond=0)


def load_route_config(config_path: str) -> Route:
    """
    Load route configuration from a JSON file.
    
    Args:
        config_path: Path to the route.json config file.
        
    Returns:
        A fully populated Route object.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    route_data = data["route"]
    segments = [
        Segment(
            from_stop=seg["from"],
            to_stop=seg["to"],
            distance_km=seg["distance_km"],
        )
        for seg in route_data["segments"]
    ]

    stations = {
        name: StationConfig(name=name, chargers=cfg["chargers"])
        for name, cfg in data["stations"].items()
    }

    defaults_data = data.get("bus_defaults", {})
    bus_defaults = BusDefaults(
        battery_range_km=defaults_data.get("battery_range_km", 240),
        charging_time_min=defaults_data.get("charging_time_min", 25),
        speed_kmh=defaults_data.get("speed_kmh", 60),
    )

    return Route(
        name=route_data["name"],
        stops=route_data["stops"],
        segments=segments,
        stations=stations,
        bus_defaults=bus_defaults,
    )


def load_scenario(scenario_path: str) -> dict:
    """
    Load a scenario from a JSON file.
    
    Args:
        scenario_path: Path to the scenario JSON file.
        
    Returns:
        A dict with keys: 'name', 'description', 'weights', 'buses' (list of Bus objects)
    """
    with open(scenario_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    buses = [
        Bus(
            id=b["id"],
            operator=b["operator"],
            direction=b["direction"],
            departure_time=parse_time(b["departure_time"]),
        )
        for b in data["buses"]
    ]

    return {
        "name": data["name"],
        "description": data.get("description", ""),
        "weights": data.get("weights", {"individual": 1.0, "operator": 1.0, "overall": 1.0}),
        "buses": buses,
        "raw_buses": data["buses"],  # Keep raw data for UI display
    }


def discover_scenarios(scenarios_dir: str) -> list[dict]:
    """
    Discover all scenario files in a directory.
    
    Returns a list of dicts with 'name' and 'path' for each scenario,
    sorted by filename.
    """
    scenarios = []
    scenarios_path = Path(scenarios_dir)

    if not scenarios_path.exists():
        return scenarios

    for f in sorted(scenarios_path.glob("scenario_*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            scenarios.append({
                "name": data.get("name", f.stem),
                "path": str(f),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return scenarios
