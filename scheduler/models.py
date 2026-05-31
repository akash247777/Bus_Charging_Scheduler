"""
Data models for the Bus Charging Scheduler.

All domain objects are represented as dataclasses for clarity and immutability.
The models are designed to be data-driven — the scheduler reads these from JSON
config files, making it easy to change the world without code changes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class Segment:
    """A segment of the route between two consecutive stops."""
    from_stop: str
    to_stop: str
    distance_km: float

    @property
    def travel_time_min(self) -> float:
        """Travel time in minutes, calculated from distance and default speed."""
        # This will be overridden by the route's speed_kmh
        raise NotImplementedError("Use Route.travel_time_min() instead")


@dataclass
class StationConfig:
    """Configuration for a charging station."""
    name: str
    chargers: int = 1


@dataclass
class BusDefaults:
    """Default physical constants for buses."""
    battery_range_km: float = 240.0
    charging_time_min: float = 25.0
    speed_kmh: float = 60.0


@dataclass
class Route:
    """
    A route with ordered stops and segments.
    
    The route knows how to compute distances and travel times between
    any two stops, in either direction.
    """
    name: str
    stops: list[str]
    segments: list[Segment]
    stations: dict[str, StationConfig]
    bus_defaults: BusDefaults

    def get_station_names(self) -> list[str]:
        """Return names of charging stations (excluding endpoints)."""
        return [s for s in self.stops if s in self.stations]

    def get_stops_for_direction(self, direction: str) -> list[str]:
        """Return the ordered list of stops for a given direction."""
        if "→" in direction:
            origin, destination = direction.split("→")
        else:
            origin, destination = direction.split("->")
        origin = origin.strip()
        destination = destination.strip()

        origin_idx = self.stops.index(origin)
        dest_idx = self.stops.index(destination)

        if origin_idx < dest_idx:
            return self.stops[origin_idx:dest_idx + 1]
        else:
            return list(reversed(self.stops[dest_idx:origin_idx + 1]))

    def get_charging_stations_for_direction(self, direction: str) -> list[str]:
        """Return ordered charging stations a bus passes through."""
        stops = self.get_stops_for_direction(direction)
        return [s for s in stops if s in self.stations]

    def get_distance(self, from_stop: str, to_stop: str) -> float:
        """
        Get the total distance between two stops along the route.
        Works in either direction.
        """
        from_idx = self.stops.index(from_stop)
        to_idx = self.stops.index(to_stop)

        if from_idx > to_idx:
            from_idx, to_idx = to_idx, from_idx

        total = 0.0
        for seg in self.segments:
            seg_from = self.stops.index(seg.from_stop)
            seg_to = self.stops.index(seg.to_stop)
            if seg_from >= from_idx and seg_to <= to_idx:
                total += seg.distance_km
        return total

    def travel_time_min(self, from_stop: str, to_stop: str) -> float:
        """Travel time in minutes between two stops."""
        distance = self.get_distance(from_stop, to_stop)
        return (distance / self.bus_defaults.speed_kmh) * 60


@dataclass
class Bus:
    """A bus with its schedule information."""
    id: str
    operator: str
    direction: str
    departure_time: datetime

    @property
    def origin(self) -> str:
        if "→" in self.direction:
            return self.direction.split("→")[0].strip()
        return self.direction.split("->")[0].strip()

    @property
    def destination(self) -> str:
        if "→" in self.direction:
            return self.direction.split("→")[1].strip()
        return self.direction.split("->")[1].strip()


@dataclass
class TimelineEvent:
    """A single event in a bus's journey timeline."""
    event_type: str  # "depart", "arrive_station", "wait_start", "charge_start", "charge_end", "arrive_destination"
    location: str
    time: datetime
    details: dict = field(default_factory=dict)

    def __repr__(self):
        time_str = self.time.strftime("%H:%M")
        return f"{time_str} | {self.event_type:20s} | {self.location} | {self.details}"


@dataclass
class BusTimeline:
    """Complete timeline for a single bus's journey."""
    bus: Bus
    events: list[TimelineEvent] = field(default_factory=list)

    @property
    def departure_time(self) -> datetime:
        return self.bus.departure_time

    @property
    def arrival_time(self) -> Optional[datetime]:
        for event in reversed(self.events):
            if event.event_type == "arrive_destination":
                return event.time
        return None

    @property
    def total_wait_min(self) -> float:
        total = 0.0
        for event in self.events:
            if event.event_type == "wait_start":
                total += event.details.get("wait_min", 0)
        return total

    @property
    def total_charge_min(self) -> float:
        total = 0.0
        for event in self.events:
            if event.event_type == "charge_start":
                total += event.details.get("charge_min", 0)
        return total

    @property
    def total_trip_min(self) -> Optional[float]:
        arrival = self.arrival_time
        if arrival is None:
            return None
        delta = arrival - self.departure_time
        return delta.total_seconds() / 60

    @property
    def stations_used(self) -> list[str]:
        return [e.location for e in self.events if e.event_type == "charge_start"]


@dataclass
class StationLog:
    """Log of all charging events at a single station."""
    station_name: str
    entries: list[dict] = field(default_factory=list)
    # Each entry: {"bus_id": str, "operator": str, "arrival_time": datetime,
    #              "charge_start": datetime, "charge_end": datetime, "wait_min": float}


@dataclass
class ScheduleResult:
    """Complete output of the scheduler for one scenario."""
    scenario_name: str
    bus_timelines: list[BusTimeline]
    station_logs: dict[str, StationLog]

    def get_timeline_for_bus(self, bus_id: str) -> Optional[BusTimeline]:
        for bt in self.bus_timelines:
            if bt.bus.id == bus_id:
                return bt
        return None

    def get_all_operators(self) -> set[str]:
        return {bt.bus.operator for bt in self.bus_timelines}

    def get_operator_avg_wait(self, operator: str) -> float:
        waits = [bt.total_wait_min for bt in self.bus_timelines if bt.bus.operator == operator]
        return sum(waits) / len(waits) if waits else 0.0


@dataclass
class ChargingPlan:
    """
    A candidate charging plan for a bus — which stations it will stop at.
    The scheduler evaluates multiple plans and picks the best one.
    """
    stations: list[str]  # ordered list of stations to charge at
    segments_distance: list[float]  # distance of each leg (origin->first station, station->station, last station->dest)

    def is_valid(self, max_range_km: float) -> bool:
        """Check if all legs are within battery range."""
        return all(d <= max_range_km for d in self.segments_distance)

    @property
    def num_stops(self) -> int:
        return len(self.stations)
