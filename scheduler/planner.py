"""
Charging plan enumeration module.

Given a bus's direction and the route, this module enumerates all valid
charging plans — subsets of stations where the bus can stop to recharge
without exceeding the 240 km battery range on any leg.

A bus going Bengaluru→Kochi passes stations [A, B, C, D] in order.
A bus going Kochi→Bengaluru passes stations [D, C, B, A] in order.

The total trip is 540 km with a 240 km range, so at least 2 charging
stops are needed (any valid subset of size ≥2 is feasible if no leg > 240 km).
"""

from itertools import combinations
from .models import Bus, ChargingPlan, Route


def get_leg_distances(
    origin: str,
    destination: str,
    charging_stops: list[str],
    route: Route,
) -> list[float]:
    """
    Calculate the distance of each leg given the charging stops.
    
    A "leg" is the distance between consecutive charge points:
    origin → first_stop, stop1 → stop2, ..., last_stop → destination.
    
    Args:
        origin: Starting point (e.g., "Bengaluru")
        destination: Ending point (e.g., "Kochi")
        charging_stops: Ordered list of stations where the bus will charge
        route: The route configuration
        
    Returns:
        List of distances for each leg
    """
    waypoints = [origin] + charging_stops + [destination]
    distances = []
    for i in range(len(waypoints) - 1):
        d = route.get_distance(waypoints[i], waypoints[i + 1])
        distances.append(d)
    return distances


def enumerate_valid_plans(
    bus: Bus,
    route: Route,
) -> list[ChargingPlan]:
    """
    Enumerate all valid charging plans for a bus.
    
    A valid plan is a subset of the route's charging stations (in route order)
    such that no leg exceeds the battery range.
    
    Args:
        bus: The bus to plan for
        route: The route configuration
        
    Returns:
        List of valid ChargingPlan objects, sorted by number of stops (ascending)
    """
    available_stations = route.get_charging_stations_for_direction(bus.direction)
    max_range = route.bus_defaults.battery_range_km
    origin = bus.origin
    destination = bus.destination

    valid_plans = []

    # Try all subsets of stations, from smallest to largest
    for size in range(1, len(available_stations) + 1):
        for combo in combinations(available_stations, size):
            # Maintain route order
            ordered_stops = [s for s in available_stations if s in combo]
            
            leg_distances = get_leg_distances(origin, destination, ordered_stops, route)
            
            plan = ChargingPlan(
                stations=ordered_stops,
                segments_distance=leg_distances,
            )
            
            if plan.is_valid(max_range):
                valid_plans.append(plan)

    # Sort by number of stops (prefer fewer stops = less delay)
    valid_plans.sort(key=lambda p: p.num_stops)
    
    return valid_plans


def get_minimum_stops_plan(bus: Bus, route: Route) -> ChargingPlan:
    """
    Get the valid charging plan with the fewest stops.
    
    This is the "fastest possible" plan if no contention exists.
    Falls back to all stations if no minimum plan works.
    """
    plans = enumerate_valid_plans(bus, route)
    if not plans:
        # Fallback: use all stations
        all_stations = route.get_charging_stations_for_direction(bus.direction)
        return ChargingPlan(
            stations=all_stations,
            segments_distance=get_leg_distances(
                bus.origin, bus.destination, all_stations, route
            ),
        )
    return plans[0]
