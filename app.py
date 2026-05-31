"""
Bus Charging Scheduler — Streamlit App

A scheduling tool for electric bus charging on the Bengaluru-Kochi route.
Select a scenario, see the input data, and view the scheduler's output
as per-bus timetables and per-station charging logs.
"""

import os
import sys
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from scheduler.loader import load_route_config, load_scenario, discover_scenarios
from scheduler.engine import run_scheduler
from scheduler.rules import MinimizeIndividualWait, OperatorFairness, MinimizeTotalTime, CustomFormulaRule



# ─── Page Config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Bus Charging Scheduler",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ─── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* Global styles */
    .stApp {
        font-family: 'Inter', sans-serif;
    }

    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        color: white;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    .main-header h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        font-size: 1rem;
        opacity: 0.8;
        font-weight: 300;
    }

    /* Section headers */
    .section-header {
        background: linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%);
        padding: 1rem 1.5rem;
        border-radius: 12px;
        margin: 1.5rem 0 1rem 0;
        border-left: 4px solid #3f51b5;
    }
    .section-header h3 {
        margin: 0;
        color: #1a237e;
        font-weight: 600;
        font-size: 1.1rem;
    }

    /* Scenario info card */
    .scenario-card {
        background: linear-gradient(135deg, #f5f7ff 0%, #e8ecff 100%);
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        border: 1px solid #c5cae9;
        margin-bottom: 1rem;
    }
    .scenario-card h4 {
        margin: 0 0 0.5rem 0;
        color: #283593;
        font-weight: 600;
    }
    .scenario-card p {
        margin: 0;
        color: #455a64;
        font-size: 0.95rem;
    }

    /* Weight badges */
    .weight-badge {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 500;
        margin: 0.2rem;
    }
    .weight-individual { background: #e3f2fd; color: #1565c0; }
    .weight-operator { background: #f3e5f5; color: #7b1fa2; }
    .weight-overall { background: #e8f5e9; color: #2e7d32; }

    /* Stats cards */
    .stat-card {
        background: white;
        padding: 1rem 1.25rem;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .stat-card .stat-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1a237e;
    }
    .stat-card .stat-label {
        font-size: 0.85rem;
        color: #757575;
        margin-top: 0.25rem;
    }

    /* Bus timeline card */
    .bus-card {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: box-shadow 0.2s ease;
    }
    .bus-card:hover {
        box-shadow: 0 4px 16px rgba(0,0,0,0.1);
    }

    /* Operator color dots */
    .op-kpn { color: #e53935; }
    .op-freshbus { color: #43a047; }
    .op-flixbus { color: #1e88e5; }

    /* Station tab styling */
    .station-header {
        background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);
        padding: 1rem 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #ef6c00;
        margin-bottom: 1rem;
    }
    .station-header h4 {
        margin: 0;
        color: #e65100;
        font-weight: 600;
    }

    /* Dataframe styling */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Metric styling */
    [data-testid="stMetric"] {
        background-color: var(--secondary-background-color);
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }

</style>
""", unsafe_allow_html=True)


# ─── Helper Functions ─────────────────────────────────────────────────────────

def format_time(dt: datetime) -> str:
    """Format datetime to HH:MM string."""
    return dt.strftime("%H:%M")


def format_duration(minutes: float) -> str:
    """Format minutes to a human-readable duration."""
    if minutes < 1:
        return "0 min"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins} min"


def get_operator_color(operator: str) -> str:
    """Get a color for an operator."""
    colors = {
        "kpn": "#e53935",
        "freshbus": "#43a047",
        "flixbus": "#1e88e5",
    }
    return colors.get(operator.lower(), "#757575")


def get_operator_emoji(operator: str) -> str:
    """Get an emoji for an operator."""
    emojis = {
        "kpn": "🔴",
        "freshbus": "🟢",
        "flixbus": "🔵",
    }
    return emojis.get(operator.lower(), "⚪")


# ─── Data Loading ─────────────────────────────────────────────────────────────

@st.cache_data
def load_config():
    config_path = os.path.join(PROJECT_ROOT, "data", "config", "route.json")
    return load_route_config(config_path)


@st.cache_data
def get_scenarios():
    scenarios_dir = os.path.join(PROJECT_ROOT, "data", "scenarios")
    return discover_scenarios(scenarios_dir)


@st.cache_data
def load_and_run(scenario_path: str, _route_hash: str):
    """Load a scenario and run the scheduler. Cache the result."""
    route = load_config()
    scenario = load_scenario(scenario_path)
    result = run_scheduler(
        buses=scenario["buses"],
        route=route,
        weights=scenario["weights"],
        scenario_name=scenario["name"],
    )
    return scenario, result


# ─── Main App ─────────────────────────────────────────────────────────────────

# ─── Scenario Builder ─────────────────────────────────────────────────────────

def render_scenario_builder(route):
    st.markdown("""
    <div class="section-header">
        <h3>➕ Scenario Builder — Create Custom Departures Schedule</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col_meta1, col_meta2 = st.columns(2)
    with col_meta1:
        s_name = st.text_input("Scenario Name", value="Custom Scenario", placeholder="e.g. Scenario 6 — Custom Spacing")
    with col_meta2:
        s_desc = st.text_input("Description", value="Custom scenario defined in UI", placeholder="e.g. Custom bunched start")
        
    st.markdown("#### ⚖️ Default Scenario Weights")
    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        s_w_ind = st.slider("Default Individual Weight", 0.0, 5.0, 1.0, 0.1, key="s_w_ind")
    with col_w2:
        s_w_op = st.slider("Default Operator Weight", 0.0, 5.0, 1.0, 0.1, key="s_w_op")
    with col_w3:
        s_w_ov = st.slider("Default Overall Weight", 0.0, 5.0, 1.0, 0.1, key="s_w_ov")
        
    st.markdown("#### 🚌 Departures Schedule Table")
    st.info("You can add, delete, and edit rows in the table below. Make sure Bus IDs are unique and departure times are in `HH:MM` format.")
    
    # Initialize session state for editor data if not present
    if "editor_data" not in st.session_state:
        st.session_state.editor_data = [
            {"Bus ID": "bus-BK-01", "Operator": "kpn", "Direction": "Bengaluru→Kochi", "Departure Time": "08:00"},
            {"Bus ID": "bus-BK-02", "Operator": "freshbus", "Direction": "Bengaluru→Kochi", "Departure Time": "08:15"},
            {"Bus ID": "bus-KB-01", "Operator": "flixbus", "Direction": "Kochi→Bengaluru", "Departure Time": "08:00"},
            {"Bus ID": "bus-KB-02", "Operator": "kpn", "Direction": "Kochi→Bengaluru", "Departure Time": "08:15"},
        ]
        
    # Configure columns
    column_config = {
        "Bus ID": st.column_config.TextColumn("Bus ID", required=True, help="Enter a unique identifier for the bus, e.g. bus-BK-01"),
        "Operator": st.column_config.SelectboxColumn("Operator", options=["kpn", "flixbus", "freshbus"], required=True),
        "Direction": st.column_config.SelectboxColumn("Direction", options=["Bengaluru→Kochi", "Kochi→Bengaluru"], required=True),
        "Departure Time": st.column_config.TextColumn("Departure Time", required=True, help="Enter the departure time in HH:MM format, e.g. 19:30"),
    }
    
    edited_df = st.data_editor(
        pd.DataFrame(st.session_state.editor_data),
        column_config=column_config,
        num_rows="dynamic",
        use_container_width=True,
        key="scenario_data_editor"
    )
    
    # Keep session state updated with editor changes
    st.session_state.editor_data = edited_df.to_dict(orient="records")
    
    col_actions1, col_actions2 = st.columns(2)
    with col_actions1:
        run_mem = st.button("⚡ Run Scenario (In-Memory)", use_container_width=True)
    with col_actions2:
        save_disk = st.button("💾 Save Permanently to Disk & Run", use_container_width=True)
        
    if run_mem or save_disk:
        # Validate data
        rows = st.session_state.editor_data
        if not rows:
            st.error("Departure schedule cannot be empty!")
            return
            
        bus_ids = []
        parsed_buses = []
        raw_buses = []
        
        from scheduler.models import Bus
        from scheduler.loader import parse_time
        
        for idx, row in enumerate(rows):
            bid = row.get("Bus ID")
            op = row.get("Operator")
            dir_str = row.get("Direction")
            dep_time = row.get("Departure Time")
            
            if not bid or not op or not dir_str or not dep_time:
                st.error(f"Row {idx+1} is missing required values!")
                return
                
            if bid in bus_ids:
                st.error(f"Duplicate Bus ID found: {bid}")
                return
            bus_ids.append(bid)
            
            # Validate time format
            try:
                if ":" not in dep_time or len(dep_time.split(":")) != 2:
                    raise ValueError
                hours, minutes = map(int, dep_time.split(":"))
                if not (0 <= hours <= 23) or not (0 <= minutes <= 59):
                    raise ValueError
            except ValueError:
                st.error(f"Invalid Departure Time format in row {idx+1}: '{dep_time}'. Must be HH:MM.")
                return
                
            parsed_buses.append(Bus(
                id=bid,
                operator=op,
                direction=dir_str,
                departure_time=parse_time(dep_time)
            ))
            
            raw_buses.append({
                "id": bid,
                "operator": op,
                "direction": dir_str,
                "departure_time": dep_time
            })
            
        # Build custom scenario object
        custom_scenario = {
            "name": s_name,
            "path": f"custom_memory_{len(st.session_state.custom_scenarios)}",
            "is_custom": True,
            "data": {
                "name": s_name,
                "description": s_desc,
                "weights": {
                    "individual": s_w_ind,
                    "operator": s_w_op,
                    "overall": s_w_ov,
                },
                "buses": parsed_buses,
                "raw_buses": raw_buses
            }
        }
        
        if save_disk:
            # Save to disk
            import json
            import re
            # Create a slug from name
            slug = re.sub(r'[^a-z0-9_]', '', s_name.lower().replace(" ", "_"))
            if not slug:
                slug = "custom_scenario"
            file_name = f"scenario_{slug}.json"
            file_path = os.path.join(PROJECT_ROOT, "data", "scenarios", file_name)
            
            disk_data = {
                "name": s_name,
                "description": s_desc,
                "weights": {
                    "individual": s_w_ind,
                    "operator": s_w_op,
                    "overall": s_w_ov
                },
                "buses": raw_buses
            }
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(disk_data, f, indent=2)
                st.success(f"Scenario saved to {file_path}!")
                # Force refresh discover scenarios
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Failed to save scenario to disk: {e}")
                return
        else:
            # Add to memory
            st.session_state.custom_scenarios.append(custom_scenario)
            st.success("Scenario created in memory!")
            
        # Set selection pointing to the new scenario
        if save_disk:
            scenarios = get_scenarios()
            try:
                new_idx = next(i for i, s in enumerate(scenarios) if s["name"] == s_name)
                st.session_state.scenario_selector = new_idx
            except StopIteration:
                st.session_state.scenario_selector = 0
        else:
            st.session_state.scenario_selector = len(get_scenarios()) + len(st.session_state.custom_scenarios) - 1
            
        st.rerun()


# ─── Main App ─────────────────────────────────────────────────────────────────

def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🚌 Bus Charging Scheduler</h1>
        <p>Electric bus charging optimization for the Bengaluru–Kochi route</p>
    </div>
    """, unsafe_allow_html=True)

    # Load route config
    route = load_config()
    
    # Initialize session state lists if not present
    if "custom_scenarios" not in st.session_state:
        st.session_state.custom_scenarios = []
    if "custom_rules" not in st.session_state:
        st.session_state.custom_rules = []

    # Discovered scenarios + memory custom scenarios
    scenarios = get_scenarios() + st.session_state.custom_scenarios

    if not scenarios:
        st.error("No scenarios found! Please add scenario files to `data/scenarios/`.")
        return

    # ─── Scenario Selector ────────────────────────────────────────────────

    scenario_names = [s["name"] for s in scenarios] + ["➕ Build Custom Scenario..."]
    selected_idx = st.selectbox(
        "📋 Select Scenario",
        range(len(scenarios) + 1),
        format_func=lambda i: scenario_names[i],
        key="scenario_selector",
    )

    if selected_idx == len(scenarios):
        # Render Scenario Builder in the main area
        render_scenario_builder(route)
        return

    selected_scenario = scenarios[selected_idx]
    is_custom = selected_scenario.get("is_custom", False)

    # ─── Sidebar Controls (Tuning & Custom Rules) ─────────────────────────
    st.sidebar.markdown("## ⚙️ Control Panel")
    
    # Get current scenario default weights
    if is_custom:
        default_weights = selected_scenario["data"]["weights"]
    else:
        temp_scenario = load_scenario(selected_scenario["path"])
        default_weights = temp_scenario["weights"]
        
    st.sidebar.markdown("### ⚖️ Adjust Weights")
    weight_ind = st.sidebar.slider("Individual Weight", 0.0, 5.0, float(default_weights.get("individual", 1.0)), 0.1, key="weight_ind")
    weight_op = st.sidebar.slider("Operator Weight", 0.0, 5.0, float(default_weights.get("operator", 1.0)), 0.1, key="weight_op")
    weight_ov = st.sidebar.slider("Overall Weight", 0.0, 5.0, float(default_weights.get("overall", 1.0)), 0.1, key="weight_ov")
    
    overridden_weights = {
        "individual": weight_ind,
        "operator": weight_op,
        "overall": weight_ov,
    }
    
    st.sidebar.markdown("### 🔧 Pluggable Rules")
    enable_ind = st.sidebar.checkbox("Minimize Individual Wait", value=True, key="enable_ind")
    enable_op = st.sidebar.checkbox("Operator Fairness", value=True, key="enable_op")
    enable_tot = st.sidebar.checkbox("Minimize Total Time", value=True, key="enable_tot")
    
    # Build active rules list
    active_rules = []
    if enable_ind:
        active_rules.append(MinimizeIndividualWait())
    if enable_op:
        active_rules.append(OperatorFairness())
    if enable_tot:
        active_rules.append(MinimizeTotalTime())
        
    # Custom Rules checkboxes
    if st.session_state.custom_rules:
        st.sidebar.markdown("#### Custom Rules")
        for crule in st.session_state.custom_rules:
            chk = st.sidebar.checkbox(f"Custom: {crule['name']}", value=True, key=f"crule_{crule['name']}")
            if chk:
                active_rules.append(CustomFormulaRule(crule['name'], crule['weight_key'], crule['formula']))
                
    # Add custom rule form
    with st.sidebar.expander("➕ Add Custom Rule"):
        c_name = st.text_input("Rule Name", key="c_name_input")
        c_weight = st.selectbox("Weight Category", ["individual", "operator", "overall"], key="c_weight_input")
        c_formula = st.text_input("Formula (e.g. estimated_wait * 2.0)", key="c_formula_input")
        if st.button("Create Rule", key="create_rule_btn"):
            if c_name and c_formula:
                if any(r["name"] == c_name for r in st.session_state.custom_rules):
                    st.error("Rule name already exists!")
                else:
                    st.session_state.custom_rules.append({
                        "name": c_name,
                        "weight_key": c_weight,
                        "formula": c_formula
                    })
                    st.success(f"Rule '{c_name}' created!")
                    st.rerun()
            else:
                st.error("Please fill name and formula!")
                
    # Delete custom rules form
    if st.session_state.custom_rules:
        with st.sidebar.expander("🗑️ Delete Custom Rules"):
            for r in st.session_state.custom_rules:
                if st.button(f"Delete '{r['name']}'", key=f"del_{r['name']}"):
                    st.session_state.custom_rules = [x for x in st.session_state.custom_rules if x["name"] != r["name"]]
                    st.rerun()

    # ─── Load and Run Scheduler ──────────────────────────────────────────
    
    # Check overrides
    has_weight_override = (
        overridden_weights["individual"] != default_weights.get("individual") or
        overridden_weights["operator"] != default_weights.get("operator") or
        overridden_weights["overall"] != default_weights.get("overall")
    )
    has_rule_override = (not enable_ind or not enable_op or not enable_tot or len(active_rules) > (int(enable_ind) + int(enable_op) + int(enable_tot)))

    if is_custom:
        scenario = selected_scenario["data"]
        result = run_scheduler(
            buses=scenario["buses"],
            route=route,
            weights=overridden_weights,
            scenario_name=scenario["name"],
            rules=active_rules,
        )
    elif has_weight_override or has_rule_override:
        scenario = load_scenario(selected_scenario["path"])
        result = run_scheduler(
            buses=scenario["buses"],
            route=route,
            weights=overridden_weights,
            scenario_name=scenario["name"],
            rules=active_rules,
        )
    else:
        scenario, result = load_and_run(
            selected_scenario["path"],
            f"{route.name}_{route.bus_defaults.battery_range_km}_{route.bus_defaults.speed_kmh}",
        )

    # ─── Scenario Info ────────────────────────────────────────────────────

    st.markdown(f"""
    <div class="scenario-card">
        <h4>{scenario['name']}</h4>
        <p>{scenario['description']}</p>
        <div style="margin-top: 0.75rem;">
            <span class="weight-badge weight-individual">🎯 Individual: {overridden_weights['individual']}</span>
            <span class="weight-badge weight-operator">🏢 Operator: {overridden_weights['operator']}</span>
            <span class="weight-badge weight-overall">🌐 Overall: {overridden_weights['overall']}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ─── Quick Stats ──────────────────────────────────────────────────────

    total_buses = len(result.bus_timelines)
    total_wait = sum(bt.total_wait_min for bt in result.bus_timelines)
    avg_wait = total_wait / total_buses if total_buses > 0 else 0
    max_wait = max(bt.total_wait_min for bt in result.bus_timelines) if total_buses > 0 else 0
    avg_trip = sum(bt.total_trip_min or 0 for bt in result.bus_timelines) / total_buses if total_buses > 0 else 0

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Buses", total_buses)
    with col2:
        st.metric("Avg Wait", format_duration(avg_wait))
    with col3:
        st.metric("Max Wait", format_duration(max_wait))
    with col4:
        st.metric("Total Wait", format_duration(total_wait))
    with col5:
        st.metric("Avg Trip", format_duration(avg_trip))

    # ─── Tabs ─────────────────────────────────────────────────────────────

    tab_input, tab_bus, tab_station = st.tabs([
        "📊 Scenario Input Data",
        "🚌 Per-Bus Timetable",
        "🔌 Per-Station View",
    ])

    # ─── Tab 1: Input Data ────────────────────────────────────────────────

    with tab_input:
        st.markdown("""
        <div class="section-header">
            <h3>📊 Scenario Input — Departure Schedule</h3>
        </div>
        """, unsafe_allow_html=True)

        # Route info
        col_route, col_config = st.columns(2)

        with col_route:
            st.markdown("**Route:**")
            route_str = " → ".join(route.stops)
            st.markdown(f"`{route_str}`")

            seg_data = []
            for seg in route.segments:
                seg_data.append({
                    "Segment": f"{seg.from_stop} → {seg.to_stop}",
                    "Distance": f"{seg.distance_km} km",
                    "Travel Time": f"{route.travel_time_min(seg.from_stop, seg.to_stop):.0f} min",
                })
            st.dataframe(pd.DataFrame(seg_data), hide_index=True, use_container_width=True)

        with col_config:
            st.markdown("**Physical Constants:**")
            st.markdown(f"- 🔋 Battery range: **{route.bus_defaults.battery_range_km} km**")
            st.markdown(f"- ⚡ Charging time: **{route.bus_defaults.charging_time_min} min** (to full)")
            st.markdown(f"- 🚗 Speed: **{route.bus_defaults.speed_kmh} km/h**")
            st.markdown(f"- 🔌 Chargers per station: **{', '.join(f'{k}={v.chargers}' for k,v in route.stations.items())}**")

        st.markdown("---")

        # Bus departure table
        st.markdown("**Bus Departure Schedule:**")
        bus_data = []
        for b in scenario["raw_buses"]:
            bus_data.append({
                "Bus ID": b["id"],
                "Operator": f"{get_operator_emoji(b['operator'])} {b['operator'].upper()}",
                "Direction": b["direction"],
                "Departure": b["departure_time"],
            })

        df_input = pd.DataFrame(bus_data)

        # Split by direction
        col_bk, col_kb = st.columns(2)
        with col_bk:
            st.markdown("**Bengaluru → Kochi**")
            df_bk = df_input[df_input["Direction"].str.contains("Bengaluru")]
            st.dataframe(df_bk, hide_index=True, use_container_width=True)

        with col_kb:
            st.markdown("**Kochi → Bengaluru**")
            df_kb = df_input[df_input["Direction"].str.contains("Kochi→") | df_input["Direction"].str.contains("Kochi->")]
            st.dataframe(df_kb, hide_index=True, use_container_width=True)

    # ─── Tab 2: Per-Bus Timetable ─────────────────────────────────────────

    with tab_bus:
        st.markdown("""
        <div class="section-header">
            <h3>🚌 Per-Bus Timetable — Full Journey Timeline</h3>
        </div>
        """, unsafe_allow_html=True)

        # Filter options
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            operators = sorted(set(bt.bus.operator for bt in result.bus_timelines))
            selected_operator = st.selectbox(
                "Filter by Operator",
                ["All"] + [op.upper() for op in operators],
                key="operator_filter",
            )
        with col_filter2:
            directions = sorted(set(bt.bus.direction for bt in result.bus_timelines))
            selected_direction = st.selectbox(
                "Filter by Direction",
                ["All"] + directions,
                key="direction_filter",
            )

        # Filter timelines
        filtered_timelines = result.bus_timelines
        if selected_operator != "All":
            filtered_timelines = [bt for bt in filtered_timelines if bt.bus.operator.upper() == selected_operator]
        if selected_direction != "All":
            filtered_timelines = [bt for bt in filtered_timelines if bt.bus.direction == selected_direction]

        # Summary table
        summary_data = []
        for bt in filtered_timelines:
            summary_data.append({
                "Bus ID": bt.bus.id,
                "Operator": f"{get_operator_emoji(bt.bus.operator)} {bt.bus.operator.upper()}",
                "Direction": bt.bus.direction,
                "Departure": format_time(bt.departure_time),
                "Stations Used": " → ".join(bt.stations_used) if bt.stations_used else "None",
                "Total Wait": format_duration(bt.total_wait_min),
                "Total Charge": format_duration(bt.total_charge_min),
                "Arrival": format_time(bt.arrival_time) if bt.arrival_time else "N/A",
                "Trip Duration": format_duration(bt.total_trip_min) if bt.total_trip_min else "N/A",
            })

        if summary_data:
            st.dataframe(
                pd.DataFrame(summary_data),
                hide_index=True,
                use_container_width=True,
            )

        # Detailed timeline for each bus
        st.markdown("---")
        st.markdown("**Detailed Timeline per Bus:**")

        for bt in filtered_timelines:
            op_emoji = get_operator_emoji(bt.bus.operator)
            wait_str = format_duration(bt.total_wait_min)
            trip_str = format_duration(bt.total_trip_min) if bt.total_trip_min else "N/A"

            with st.expander(
                f"{op_emoji} **{bt.bus.id}** — {bt.bus.operator.upper()} | "
                f"{bt.bus.direction} | Wait: {wait_str} | Trip: {trip_str}",
                expanded=False,
            ):
                events_data = []
                for event in bt.events:
                    event_icons = {
                        "depart": "🟢",
                        "arrive_station": "📍",
                        "wait_start": "⏳",
                        "charge_start": "⚡",
                        "charge_end": "🔋",
                        "arrive_destination": "🏁",
                    }
                    icon = event_icons.get(event.event_type, "•")
                    
                    event_label = event.event_type.replace("_", " ").title()
                    
                    detail_str = ""
                    if event.event_type == "depart":
                        detail_str = f"Range: {event.details.get('range_km', 0):.0f} km"
                    elif event.event_type == "arrive_station":
                        detail_str = f"Range remaining: {event.details.get('range_remaining_km', 0):.0f} km"
                    elif event.event_type == "wait_start":
                        detail_str = f"Waiting {event.details.get('wait_min', 0):.0f} min for charger"
                    elif event.event_type == "charge_start":
                        detail_str = f"Charging for {event.details.get('charge_min', 0):.0f} min"
                    elif event.event_type == "charge_end":
                        detail_str = f"Range restored: {event.details.get('range_km', 0):.0f} km"
                    elif event.event_type == "arrive_destination":
                        detail_str = f"Range remaining: {event.details.get('range_remaining_km', 0):.0f} km"

                    events_data.append({
                        "": icon,
                        "Time": format_time(event.time),
                        "Event": event_label,
                        "Location": event.location,
                        "Details": detail_str,
                    })

                st.dataframe(
                    pd.DataFrame(events_data),
                    hide_index=True,
                    use_container_width=True,
                )

    # ─── Tab 3: Per-Station View ──────────────────────────────────────────

    with tab_station:
        st.markdown("""
        <div class="section-header">
            <h3>🔌 Per-Station View — Charging Order at Each Station</h3>
        </div>
        """, unsafe_allow_html=True)

        station_names = route.get_station_names()

        for station_name in station_names:
            log = result.station_logs.get(station_name)

            st.markdown(f"""
            <div class="station-header">
                <h4>⚡ Station {station_name} — {route.stations[station_name].chargers} charger(s)</h4>
            </div>
            """, unsafe_allow_html=True)

            if not log or not log.entries:
                st.info(f"No buses charged at Station {station_name} in this scenario.")
                continue

            # Sort entries by charge_start time
            sorted_entries = sorted(log.entries, key=lambda e: e["charge_start"])

            station_data = []
            for i, entry in enumerate(sorted_entries, 1):
                op_emoji = get_operator_emoji(entry["operator"])
                station_data.append({
                    "#": i,
                    "Bus ID": entry["bus_id"],
                    "Operator": f"{op_emoji} {entry['operator'].upper()}",
                    "Direction": entry["direction"],
                    "Arrival": format_time(entry["arrival_time"]),
                    "Charge Start": format_time(entry["charge_start"]),
                    "Charge End": format_time(entry["charge_end"]),
                    "Wait": format_duration(entry["wait_min"]),
                })

            st.dataframe(
                pd.DataFrame(station_data),
                hide_index=True,
                use_container_width=True,
            )

            # Station utilization summary
            total_charges = len(sorted_entries)
            total_wait_at_station = sum(e["wait_min"] for e in sorted_entries)
            buses_that_waited = sum(1 for e in sorted_entries if e["wait_min"] > 0)

            mcol1, mcol2, mcol3 = st.columns(3)
            with mcol1:
                st.metric(f"Buses Charged", total_charges)
            with mcol2:
                st.metric(f"Buses Waited", buses_that_waited)
            with mcol3:
                st.metric(f"Total Wait", format_duration(total_wait_at_station))

            st.markdown("---")


if __name__ == "__main__":
    main()
