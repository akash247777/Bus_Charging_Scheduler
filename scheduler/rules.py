"""
Pluggable scoring rules for the Bus Charging Scheduler.

Each rule is a callable that returns a numeric score for a candidate action.
Lower scores are better. Rules are combined using weighted sums where the
weights come from the scenario configuration.

To add a new rule:
1. Create a new class inheriting from Rule
2. Implement the score() method
3. Register it in DEFAULT_RULES

That's it — the engine picks up new rules automatically.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ScoringContext:
    """
    Shared context passed to all rules during scoring.
    
    Holds global state about the current schedule being built,
    allowing rules to make decisions based on the overall picture.
    """
    
    def __init__(self):
        # Track total wait time per operator: {"kpn": [10, 5, ...], ...}
        self.operator_waits: dict[str, list[float]] = {}
        # Track total wait time per bus
        self.bus_waits: dict[str, float] = {}
        # Track total charges scheduled globally
        self.total_scheduled_charges: int = 0
        # Track station queue lengths
        self.station_queue_lengths: dict[str, int] = {}
    
    def record_wait(self, bus_id: str, operator: str, wait_min: float):
        """Record a wait event for tracking."""
        if operator not in self.operator_waits:
            self.operator_waits[operator] = []
        self.operator_waits[operator].append(wait_min)
        self.bus_waits[bus_id] = self.bus_waits.get(bus_id, 0) + wait_min
    
    def get_operator_avg_wait(self, operator: str) -> float:
        """Get average wait time for an operator's fleet."""
        waits = self.operator_waits.get(operator, [])
        return sum(waits) / len(waits) if waits else 0.0
    
    def get_operator_total_wait(self, operator: str) -> float:
        """Get total wait time for an operator's fleet."""
        return sum(self.operator_waits.get(operator, []))
    
    def get_global_avg_wait(self) -> float:
        """Get average wait time across all operators."""
        all_waits = []
        for waits in self.operator_waits.values():
            all_waits.extend(waits)
        return sum(all_waits) / len(all_waits) if all_waits else 0.0


class Rule(ABC):
    """
    Base class for all scoring rules.
    
    Each rule has:
    - name: Human-readable identifier
    - weight_key: Which weight from scenario config drives this rule
    - score(): Returns a numeric score (lower is better)
    """
    
    name: str = "base_rule"
    weight_key: str = "overall"
    
    @abstractmethod
    def score(
        self,
        bus_id: str,
        operator: str,
        estimated_wait: float,
        estimated_total_time: float,
        context: ScoringContext,
    ) -> float:
        """
        Score a candidate action.
        
        Args:
            bus_id: ID of the bus being scored
            operator: Operator of the bus
            estimated_wait: Estimated wait time in minutes for this station
            estimated_total_time: Estimated total trip time with this plan
            context: Shared scoring context with global state
            
        Returns:
            Numeric score (lower is better)
        """
        raise NotImplementedError


class MinimizeIndividualWait(Rule):
    """
    Minimize wait time for individual buses.
    
    Penalizes plans that cause a single bus to wait a long time.
    This ensures no individual bus gets unfairly delayed.
    """
    
    name = "minimize_individual_wait"
    weight_key = "individual"
    
    def score(self, bus_id, operator, estimated_wait, estimated_total_time, context):
        # Current accumulated wait for this bus + the new wait
        current_wait = context.bus_waits.get(bus_id, 0)
        return current_wait + estimated_wait


class OperatorFairness(Rule):
    """
    Ensure fairness across operators.
    
    Penalizes plans where one operator's fleet is disproportionately 
    delayed compared to others. Higher weight = stronger push for
    equal treatment across operators.
    """
    
    name = "operator_fairness"
    weight_key = "operator"
    
    def score(self, bus_id, operator, estimated_wait, estimated_total_time, context):
        # How much above the global average is this operator?
        op_total = context.get_operator_total_wait(operator)
        global_avg = context.get_global_avg_wait()
        # Penalize if this operator is already above average
        deviation = max(0, (op_total + estimated_wait) - global_avg)
        return deviation + estimated_wait


class MinimizeTotalTime(Rule):
    """
    Minimize total time across the whole network.
    
    Prefers plans that result in lower overall trip times for all buses.
    This is a "system efficiency" rule.
    """
    
    name = "minimize_total_time"
    weight_key = "overall"
    
    def score(self, bus_id, operator, estimated_wait, estimated_total_time, context):
        return estimated_total_time


# Default rules — to add a new rule, just append to this list
DEFAULT_RULES: list[Rule] = [
    MinimizeIndividualWait(),
    OperatorFairness(),
    MinimizeTotalTime(),
]


def compute_priority_score(
    bus_id: str,
    operator: str,
    estimated_wait: float,
    estimated_total_time: float,
    context: ScoringContext,
    weights: dict[str, float],
    rules: list[Rule] | None = None,
) -> float:
    """
    Compute a combined priority score for a bus at a station.
    
    Lower score = higher priority (gets to charge first).
    
    Args:
        bus_id: Bus identifier
        operator: Bus operator
        estimated_wait: Expected wait time in minutes
        estimated_total_time: Expected total trip time in minutes
        context: Shared scoring context
        weights: Scenario weights dict {"individual": 1.0, "operator": 1.0, "overall": 1.0}
        rules: List of Rule objects to apply (defaults to DEFAULT_RULES)
        
    Returns:
        Combined weighted score
    """
    if rules is None:
        rules = DEFAULT_RULES
    
    total_score = 0.0
    for rule in rules:
        weight = weights.get(rule.weight_key, 1.0)
        rule_score = rule.score(bus_id, operator, estimated_wait, estimated_total_time, context)
        total_score += weight * rule_score
    
    return total_score
