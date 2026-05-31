# Architecture

## Scheduling Framework: Weighted Priority-Based Greedy Simulation

### Why This Approach

I evaluated three categories of approaches before settling on a **weighted priority-based greedy simulation**:

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **Mathematical Optimization (LP/CP)** | Provably optimal | Hard to add soft rules incrementally; requires solver dependency; harder to debug; overkill for current scale | ❌ |
| **Metaheuristics (GA, SA)** | Can handle complex objectives | Non-deterministic; hard to explain results; slow for real-time UI | ❌ |
| **Greedy Simulation** | Fast, deterministic, debuggable, easy to extend with new rules | Not globally optimal | ✅ |

The greedy approach is the right fit because:

1. **Extensibility over optimality**: The spec explicitly emphasizes adding new rules and changing weights. A greedy engine with pluggable scoring rules makes this trivial — each new rule is a single function. An LP solver would require reformulating constraints.

2. **Debuggability**: When reviewers ask "why did bus X wait?", the answer is traceable: "Bus Y scored higher at that station because of the operator fairness weight." LP solutions are opaque.

3. **Speed**: O(n·s) complexity where n = buses, s = stations. Produces instant results for the UI.

4. **Real-world fit**: Actual transit scheduling often uses priority-based heuristics because they're interpretable to operators.

### How It Works

```
1. Load scenario (buses, route config, weights)
2. Sort buses by departure time
3. For each bus:
   a. Enumerate all valid charging plans (subsets of stations where no leg > 240 km)
   b. For each plan, estimate total wait by peeking at station queue states
   c. Score each plan using: weighted_sum(individual_wait, operator_fairness, total_time)
   d. Select the plan with the lowest score
   e. Simulate the journey: travel → arrive → queue/charge → travel → arrive → ...
   f. Record all events in the bus timeline
4. Return complete timelines + station logs
```

---

## Data Structure Design

### Separation of Concerns

The data is split into two layers:

1. **World Config** (`data/config/route.json`): Describes the physical world — route, stations, distances, bus specs. This rarely changes and is shared across all scenarios.

2. **Scenario Files** (`data/scenarios/scenario_N.json`): Describes a specific scheduling situation — which buses, when they depart, what weights to use. These are the "inputs" to the scheduler.

This separation means:
- Adding a new station → edit `route.json` only
- Adding more chargers → edit `route.json` only
- A new scenario with different departure times → add a new scenario file only
- Changing weights → edit scenario file only

### Route Config Schema

```json
{
  "route": {
    "name": "string",
    "stops": ["Bengaluru", "A", "B", "C", "D", "Kochi"],
    "segments": [{"from": "A", "to": "B", "distance_km": 120}]
  },
  "stations": {
    "A": {"chargers": 1}
  },
  "bus_defaults": {
    "battery_range_km": 240,
    "charging_time_min": 25,
    "speed_kmh": 60
  }
}
```

**Design choices:**
- `stops` is an ordered list — the route is linear, so order matters
- `segments` defines distances between consecutive stops — this makes the route extensible (add a stop + its segments)
- `stations` is separate from `stops` — not every stop is a charging station (Bengaluru and Kochi aren't)
- `bus_defaults` holds physical constants — could be moved to per-bus overrides in future

### Scenario Schema

```json
{
  "name": "string",
  "description": "string",
  "weights": {"individual": 1.0, "operator": 1.0, "overall": 1.0},
  "buses": [
    {"id": "bus-BK-01", "operator": "kpn", "direction": "Bengaluru→Kochi", "departure_time": "19:00"}
  ]
}
```

**Design choices:**
- `weights` is a flat dict keyed by rule name — adding a new rule = adding a new key
- `direction` uses the full "Origin→Destination" format — self-documenting, works for any route
- `operator` is a free string — no enum, so new operators require zero code changes
- Bus IDs follow a convention (`bus-{direction}-{number}`) but aren't enforced — the system works with any ID

---

## Anticipated Future Changes

This section documents changes I anticipated when designing the data structure, and how each is handled **without code changes**.

### 1. Add a new station (E)
**Edit**: `route.json` — add "E" to `stops`, add segments connecting it, add to `stations`.
**Why it works**: The scheduler reads stops and segments dynamically. `enumerate_valid_plans()` discovers all available stations from the route config.

### 2. Double chargers at a station
**Edit**: `route.json` — change `stations.B.chargers` from 1 to 2.
**Why it works**: `StationManager` creates `N` `ChargerSlot` instances based on the config. `get_earliest_slot()` picks the best available charger.

### 3. Add a new operator
**Edit**: Just use the operator name in the scenario bus entries (e.g., `"operator": "redbus"`).
**Why it works**: Operators are free strings. The `OperatorFairness` rule groups by operator dynamically. No enum or registration needed.

### 4. Change segment distance
**Edit**: `route.json` — change the `distance_km` of the relevant segment.
**Why it works**: All distances are computed from config. The planner re-enumerates valid plans based on the new distances.

### 5. Change bus speed
**Edit**: `route.json` — change `bus_defaults.speed_kmh`.
**Why it works**: Travel time = distance / speed. Computed dynamically.

### 6. Per-bus battery range (mixed fleet)
**Edit**: Add `battery_range_km` to individual bus entries in the scenario. Modify `Bus` dataclass to accept optional override.
**Why it works**: The planner already takes max range as a parameter. Override `bus_defaults` with per-bus values.

### 7. Multiple routes sharing stations
**Edit**: Create separate route config files. Stations are referenced by name, so a station appearing in two routes will naturally share charger contention if the engine processes both.
**Why it works**: `StationManager` is keyed by station name, not by route.

### 8. Priority buses
**Edit**: Add `"priority": true` to bus entries. Add a `PriorityBusBoost` rule to `rules.py`. Add `"priority": 1.5` to weights.
**Why it works**: Rules are pluggable. Each rule only needs to look at the fields it cares about.

### 9. Time-of-day electricity costs
**Edit**: Add a cost schedule to `route.json` (e.g., `"electricity_cost": [{"start": "18:00", "end": "22:00", "rate": 1.5}]`). Add an `ElectricityCost` rule.
**Why it works**: Rules have access to the full context including timestamps. The cost schedule is data, not code.

### 10. Driver shift constraints
**Edit**: Add shift data to scenario bus entries. Add a hard constraint check in the engine.
**Why it works**: Hard constraints are separate from soft scoring rules. The engine validates hard constraints before accepting a plan.

---

## How to Change a Weight

Weights are in the scenario JSON file:

```json
// data/scenarios/scenario_4.json
{
  "weights": {
    "individual": 1.0,
    "operator": 2.0,   // ← change this value
    "overall": 1.0
  }
}
```

Each weight multiplies the corresponding rule's score. Higher weight = that rule matters more.

- `individual = 3.0`: System strongly avoids making any single bus wait too long
- `operator = 0.0`: Operator fairness is ignored
- `overall = 2.0`: System prioritizes total network efficiency

---

## How to Add a New Rule

### Example: "No back-to-back same-operator charges at a station"

```python
# In scheduler/rules.py

class AvoidSameOperatorBackToBack(Rule):
    """
    Penalize a bus if the previous charge at this station 
    was from the same operator. Encourages mixing.
    """
    
    name = "avoid_same_operator_back_to_back"
    weight_key = "operator_mixing"  # New weight key
    
    def score(self, bus_id, operator, estimated_wait, estimated_total_time, context):
        last_op = context.get_last_operator_at_station(station_name)
        if last_op == operator:
            return 20  # Penalty
        return 0

# Register:
DEFAULT_RULES.append(AvoidSameOperatorBackToBack())
```

Then add `"operator_mixing": 1.0` to the scenario's weights.

**Steps:**
1. Write the rule class (inherits from `Rule`)
2. Add it to `DEFAULT_RULES`
3. Add its weight key to the scenario JSON

**No engine changes needed.**

---

## Assumptions

1. **Speed**: All buses travel at 60 km/h constantly. No traffic, no variation. 100 km = 100 min.
2. **Charging**: Always to full (240 km range restored), always exactly 25 min, regardless of current charge level. No partial charges.
3. **Queue discipline**: First-come-first-served at each charger, with weighted scoring to break ties for simultaneous arrivals.
4. **Direction**: Kochi→Bengaluru buses visit stations D→C→B→A (reverse route order). They share the same physical chargers as Bengaluru→Kochi buses.
5. **Single route**: All buses in a scenario share the same Bengaluru↔Kochi route.
6. **No overnight**: All departures and arrivals happen within the same day.
7. **In-memory**: No database. All state is computed fresh per scenario selection.
8. **Departure times are fixed**: The scheduler doesn't delay departures — it only controls which stations a bus charges at and the order at each charger.
