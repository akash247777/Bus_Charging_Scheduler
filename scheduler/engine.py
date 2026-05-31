"""
Core scheduling simulation engine.

This is the heart of the Bus Charging Scheduler. It uses an event-driven
greedy simulation to assign charging plans and resolve charger contention.

Algorithm:
1. For each bus, enumerate all valid charging plans
2. For each bus, pick the best plan using weighted scoring
3. Simulate in chronological order:
   - Process station arrivals in time order
   - Assign charger slots (FCFS with weighted tie-breaking)
   - Track wait times and build complete timelines
4. Return ScheduleResult with per-bus timelines and per-station logs

The engine is decoupled from rules (rules.py) and data loading (loader.py),
making it easy to swap or extend each independently.
"""

from datetime import datetime, timedelta
from collections import defaultdict
from copy import deepcopy
from typing import Optional

from .models import (
    Bus, BusTimeline, ChargingPlan, Route, ScheduleResult,
    StationLog, TimelineEvent,
)
from .planner import enumerate_valid_plans, get_leg_distances
from .rules import ScoringContext, compute_priority_score, DEFAULT_RULES


class ChargerSlot:
    """
    Represents a single charger at a station.
    
    Tracks when the charger becomes free so we can compute wait times
    for arriving buses. Supports multiple chargers per station.
    """
    
    def __init__(self):
        self.free_at: datetime = datetime.min  # When this charger becomes available
    
    def schedule_charge(
        self,
        arrival_time: datetime,
        charging_time_min: float,
    ) -> tuple[datetime, datetime, float]:
        """
        Schedule a bus to charge on this charger.
        
        Args:
            arrival_time: When the bus arrives at the station
            charging_time_min: How long charging takes
            
        Returns:
            (charge_start, charge_end, wait_min) tuple
        """
        charge_start = max(arrival_time, self.free_at)
        wait_min = (charge_start - arrival_time).total_seconds() / 60
        charge_end = charge_start + timedelta(minutes=charging_time_min)
        self.free_at = charge_end
        return charge_start, charge_end, wait_min
    
    def peek_charge(
        self, arrival_time: datetime, charging_time_min: float
    ) -> tuple[datetime, datetime, float]:
        """Peek at what would happen without committing."""
        charge_start = max(arrival_time, self.free_at)
        wait_min = (charge_start - arrival_time).total_seconds() / 60
        charge_end = charge_start + timedelta(minutes=charging_time_min)
        return charge_start, charge_end, wait_min


class StationManager:
    """
    Manages all chargers at a station and tracks the charging log.
    """
    
    def __init__(self, station_name: str, num_chargers: int = 1):
        self.station_name = station_name
        self.chargers = [ChargerSlot() for _ in range(num_chargers)]
        self.log = StationLog(station_name=station_name)
    
    def get_earliest_slot(self, arrival_time: datetime) -> tuple[int, datetime, float]:
        """
        Find the charger slot that would give the earliest charge start.
        
        Returns:
            (slot_index, charge_start, wait_min)
        """
        best_slot = 0
        best_start = max(arrival_time, self.chargers[0].free_at)
        best_wait = (best_start - arrival_time).total_seconds() / 60
        
        for i, charger in enumerate(self.chargers[1:], 1):
            start = max(arrival_time, charger.free_at)
            wait = (start - arrival_time).total_seconds() / 60
            if start < best_start:
                best_slot = i
                best_start = start
                best_wait = wait
        
        return best_slot, best_start, best_wait
    
    def schedule_bus(
        self,
        bus: Bus,
        arrival_time: datetime,
        charging_time_min: float,
    ) -> tuple[datetime, datetime, float]:
        """
        Schedule a bus at the best available charger.
        
        Returns:
            (charge_start, charge_end, wait_min)
        """
        slot_idx, _, _ = self.get_earliest_slot(arrival_time)
        charge_start, charge_end, wait_min = self.chargers[slot_idx].schedule_charge(
            arrival_time, charging_time_min
        )
        
        # Log the event
        self.log.entries.append({
            "bus_id": bus.id,
            "operator": bus.operator,
            "direction": bus.direction,
            "arrival_time": arrival_time,
            "charge_start": charge_start,
            "charge_end": charge_end,
            "wait_min": wait_min,
        })
        
        return charge_start, charge_end, wait_min
    
    def peek_wait_time(self, arrival_time: datetime) -> float:
        """Estimate wait time without actually scheduling."""
        _, _, wait_min = self.get_earliest_slot(arrival_time)
        return wait_min
    
    def peek_charge_end(self, arrival_time: datetime, charging_time_min: float) -> tuple[float, datetime]:
        """Peek at wait time and when charging would end, without committing."""
        slot_idx, _, _ = self.get_earliest_slot(arrival_time)
        _, charge_end, wait_min = self.chargers[slot_idx].peek_charge(
            arrival_time, charging_time_min
        )
        return wait_min, charge_end


def _simulate_plan(
    bus: Bus,
    plan: ChargingPlan,
    route: Route,
    station_managers: dict[str, StationManager],
) -> tuple[float, float]:
    """
    Simulate a candidate charging plan WITHOUT committing to station queues.
    
    Returns:
        (estimated_total_wait, estimated_total_trip_time) in minutes
    """
    estimated_total_wait = 0.0
    current_time = bus.departure_time
    current_stop = bus.origin
    
    for station_name in plan.stations:
        # Travel time to this station
        travel_min = route.travel_time_min(current_stop, station_name)
        arrival_time = current_time + timedelta(minutes=travel_min)
        
        # Peek at wait time at this station
        if station_name in station_managers:
            wait, charge_end = station_managers[station_name].peek_charge_end(
                arrival_time, route.bus_defaults.charging_time_min
            )
        else:
            wait = 0
            charge_end = arrival_time + timedelta(minutes=route.bus_defaults.charging_time_min)
        
        estimated_total_wait += wait
        
        # After charging, update current position and time
        current_time = charge_end
        current_stop = station_name
    
    # Travel to destination
    final_travel = route.travel_time_min(current_stop, bus.destination)
    estimated_total_time = (
        current_time + timedelta(minutes=final_travel) - bus.departure_time
    ).total_seconds() / 60
    
    return estimated_total_wait, estimated_total_time


def _select_charging_plan(
    bus: Bus,
    route: Route,
    weights: dict[str, float],
    station_managers: dict[str, StationManager],
    context: ScoringContext,
) -> ChargingPlan:
    """
    Select the best charging plan for a bus by scoring all valid plans.
    
    For each valid plan, we simulate the journey (without committing)
    to estimate total wait and trip time, then use weighted scoring.
    """
    valid_plans = enumerate_valid_plans(bus, route)
    
    if not valid_plans:
        # Fallback: use all stations
        all_stations = route.get_charging_stations_for_direction(bus.direction)
        return ChargingPlan(
            stations=all_stations,
            segments_distance=get_leg_distances(
                bus.origin, bus.destination, all_stations, route
            ),
        )
    
    if len(valid_plans) == 1:
        return valid_plans[0]
    
    # Score each plan
    best_plan = valid_plans[0]
    best_score = float("inf")
    
    for plan in valid_plans:
        estimated_total_wait, estimated_total_time = _simulate_plan(
            bus, plan, route, station_managers
        )
        
        # Score this plan using the weighted rule engine
        score = compute_priority_score(
            bus.id, bus.operator,
            estimated_total_wait,
            estimated_total_time,
            context, weights,
        )
        
        # Prefer fewer stops as a tiebreaker (less delay from charging itself)
        score += plan.num_stops * 0.1
        
        if score < best_score:
            best_score = score
            best_plan = plan
    
    return best_plan


def run_scheduler(
    buses: list[Bus],
    route: Route,
    weights: dict[str, float],
    scenario_name: str = "",
) -> ScheduleResult:
    """
    Run the scheduling simulation for a set of buses on a route.
    
    This is the main entry point for the scheduling engine. It:
    1. Initializes station managers for each charging station
    2. Sorts buses by departure time
    3. For each bus, selects the best charging plan
    4. Simulates the journey, resolving charger contention
    5. Returns complete timelines and station logs
    
    Args:
        buses: List of Bus objects to schedule
        route: Route configuration
        weights: Scoring weights {"individual": float, "operator": float, "overall": float}
        scenario_name: Name of the scenario (for display)
        
    Returns:
        ScheduleResult with per-bus timelines and per-station logs
    """
    # Initialize station managers
    station_managers: dict[str, StationManager] = {}
    for station_name, station_cfg in route.stations.items():
        station_managers[station_name] = StationManager(
            station_name, station_cfg.chargers
        )
    
    # Initialize scoring context
    context = ScoringContext()
    
    # Sort buses by departure time for greedy processing
    sorted_buses = sorted(buses, key=lambda b: b.departure_time)
    
    # Build timelines
    bus_timelines: list[BusTimeline] = []
    
    for bus in sorted_buses:
        timeline = BusTimeline(bus=bus)
        
        # Select charging plan
        plan = _select_charging_plan(bus, route, weights, station_managers, context)
        
        # Simulate the journey
        current_time = bus.departure_time
        current_stop = bus.origin
        remaining_range = route.bus_defaults.battery_range_km
        
        # Departure event
        timeline.events.append(TimelineEvent(
            event_type="depart",
            location=current_stop,
            time=current_time,
            details={"range_km": remaining_range},
        ))
        
        # Process each charging stop
        for station_name in plan.stations:
            # Travel to station
            travel_dist = route.get_distance(current_stop, station_name)
            travel_min = route.travel_time_min(current_stop, station_name)
            arrival_time = current_time + timedelta(minutes=travel_min)
            remaining_range -= travel_dist
            
            # Arrive at station
            timeline.events.append(TimelineEvent(
                event_type="arrive_station",
                location=station_name,
                time=arrival_time,
                details={"range_remaining_km": remaining_range},
            ))
            
            # Schedule charging (handles queuing) — this COMMITS to the queue
            charge_start, charge_end, wait_min = station_managers[station_name].schedule_bus(
                bus, arrival_time, route.bus_defaults.charging_time_min
            )
            
            # Record wait in context for scoring future buses
            context.record_wait(bus.id, bus.operator, wait_min)
            
            # Wait event (if any)
            if wait_min > 0:
                timeline.events.append(TimelineEvent(
                    event_type="wait_start",
                    location=station_name,
                    time=arrival_time,
                    details={"wait_min": wait_min},
                ))
            
            # Charge event
            timeline.events.append(TimelineEvent(
                event_type="charge_start",
                location=station_name,
                time=charge_start,
                details={"charge_min": route.bus_defaults.charging_time_min},
            ))
            
            timeline.events.append(TimelineEvent(
                event_type="charge_end",
                location=station_name,
                time=charge_end,
                details={"range_km": route.bus_defaults.battery_range_km},
            ))
            
            # Update state
            current_time = charge_end
            current_stop = station_name
            remaining_range = route.bus_defaults.battery_range_km
        
        # Travel to destination
        final_dist = route.get_distance(current_stop, bus.destination)
        final_travel_min = route.travel_time_min(current_stop, bus.destination)
        arrival_time = current_time + timedelta(minutes=final_travel_min)
        remaining_range -= final_dist
        
        # Arrive at destination
        timeline.events.append(TimelineEvent(
            event_type="arrive_destination",
            location=bus.destination,
            time=arrival_time,
            details={"range_remaining_km": remaining_range},
        ))
        
        bus_timelines.append(timeline)
    
    # Build station logs dict
    station_logs = {
        name: manager.log
        for name, manager in station_managers.items()
    }
    
    return ScheduleResult(
        scenario_name=scenario_name,
        bus_timelines=bus_timelines,
        station_logs=station_logs,
    )
