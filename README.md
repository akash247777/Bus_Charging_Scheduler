# Bus Charging Scheduler

A scheduling tool for electric bus charging on the Bengaluru–Kochi route. Built with Python + Streamlit.

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### Run Locally

```bash
# Clone the repo
git clone <repo-url>
cd bus-charging-scheduler

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app will open at `http://localhost:8501`.

### Deploy to Streamlit Community Cloud

1. Push this repo to GitHub (public)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set `app.py` as the main file
5. Deploy — Streamlit reads `requirements.txt` automatically

---

## How to Use the App

1. **Select a scenario** from the dropdown at the top
2. **View the input data** in the "Scenario Input Data" tab — see the departure schedule, route info, and weights
3. **View per-bus timetables** in the "Per-Bus Timetable" tab — each bus's full journey timeline including charging stops, wait times, and arrival
4. **View per-station logs** in the "Per-Station View" tab — the order in which buses charged at each station

---

## How to Change a Weight

### 1. In the Frontend UI (Dynamic Tuning)
Adjust the sliders in the sidebar under **"⚖️ Adjust Weights"** (Individual, Operator, Overall). The scheduler will dynamically re-run and update the charts, timelines, and logs in real-time.

### 2. In Data Files (Permanent Default)
Weights are stored in each scenario's JSON file under `data/scenarios/`.

#### Example: Increase operator fairness weight in Scenario 4
Edit `data/scenarios/scenario_4.json`:
```json
{
  "weights": {
    "individual": 1.0,
    "operator": 3.0,   // ← changed from 2.0 to 3.0
    "overall": 1.0
  }
}
```
Restart the app — the scheduler will use the new defaults.

---

## How to Add a New Rule

### 1. In the Frontend UI (Dynamic Custom Rules)
You can define scoring rules dynamically in the UI:
1. In the sidebar, expand **"🔧 Pluggable Rules"** and click **"➕ Add Custom Rule"**.
2. Give the rule a **Name** and select its **Weight Category**.
3. Write a Python mathematical expression for the formula (e.g. `estimated_wait * 1.5 + (estimated_total_time / 10)`). You have access to variables: `estimated_wait`, `estimated_total_time`, `bus_id`, `operator`, and the global `context`.
4. Click **"Create Rule"**. The rule compiles and runs immediately.

### 2. In Code Files (Permanent Pluggable Rules)
Rules live in `scheduler/rules.py`. Each rule inherits from the base `Rule` class.

#### Example: Add a "priority bus" rule
```python
# In scheduler/rules.py

class PriorityBusBoost(Rule):
    """Give priority buses a scoring advantage."""
    
    name = "priority_bus_boost"
    weight_key = "priority"  # New weight key
    
    def score(self, bus_id, operator, estimated_wait, estimated_total_time, context):
        # Priority buses get a negative score (= higher priority)
        if context.is_priority_bus(bus_id):
            return -50  # Strong boost
        return 0

# Add to DEFAULT_RULES list:
DEFAULT_RULES.append(PriorityBusBoost())
```
Then add `"priority": 1.5` to your scenario's `weights` dict.

---

## How to Add a New Scenario

### 1. In the Frontend UI (Interactive Scenario Builder)
1. Select the last option in the dropdown list: **"➕ Build Custom Scenario..."**.
2. Fill in the scenario Name and Description.
3. Configure default scenario weights.
4. Add, edit, or delete buses inside the interactive departures table.
5. Click **"⚡ Run Scenario (In-Memory)"** to test immediately, or click **"💾 Save Permanently to Disk & Run"** to write the scenario JSON file directly to the project's `data/scenarios/` directory.

### 2. In Data Files (Manual Creation)
1. Create a new file `data/scenarios/scenario_6.json`
2. Follow the JSON format:
```json
{
  "name": "Scenario 6 — My Custom Scenario",
  "description": "Description of what this scenario tests.",
  "weights": {
    "individual": 1.0,
    "operator": 1.0,
    "overall": 1.0
  },
  "buses": [
    {"id": "bus-BK-01", "operator": "kpn", "direction": "Bengaluru→Kochi", "departure_time": "19:00"},
    ...
  ]
}
```
3. Restart the app — the new scenario appears in the dropdown automatically.

---

## How to Change the World

All physical constants and route info live in `data/config/route.json`. No code changes needed.

| Change | What to edit |
|--------|-------------|
| Add a new station (E) | Add to `stops`, add segment, add to `stations` in `route.json` |
| Double chargers at B | Change `stations.B.chargers` to `2` |
| Change bus speed | Change `bus_defaults.speed_kmh` |
| Change battery range | Change `bus_defaults.battery_range_km` |
| Change charging time | Change `bus_defaults.charging_time_min` |
| Change segment distance | Edit the relevant segment in `segments` |
| Add a new operator | Just use the name in scenario bus entries |

---

## Project Structure

```
├── app.py                    # Streamlit entry point
├── requirements.txt          # Python dependencies
├── data/
│   ├── config/
│   │   └── route.json        # Route, stations, physical constants
│   └── scenarios/
│       ├── scenario_1.json   # Even spacing
│       ├── scenario_2.json   # Bunched start
│       ├── scenario_3.json   # Asymmetric load
│       ├── scenario_4.json   # Operator-heavy
│       └── scenario_5.json   # Worst case convergence
├── scheduler/
│   ├── __init__.py
│   ├── models.py             # Data classes
│   ├── engine.py             # Core scheduling engine
│   ├── rules.py              # Pluggable scoring rules
│   ├── loader.py             # JSON data loading
│   └── planner.py            # Charging plan enumeration
├── README.md
└── ARCHITECTURE.md
```
