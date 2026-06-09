"""
Resource Manager — Milestone 1

Tracks and enforces resource budgets. The system's "metabolism."
CPU cycles, memory, storage I/O are the system's energy.

TODO:
- Map real system resources to virtual energy budget
- Throttle subsystems under pressure
- Priority-based resource allocation
- Graceful degradation when resources are critically low
"""

from utils.types import ResourceBudget


class ResourceManager:
    """Placeholder for M1 implementation."""

    def __init__(self):
        self.budget = ResourceBudget()

    def tick(self):
        """Called each cycle to update resource state."""
        pass  # M1

    def allocate(self, subsystem: str, amount: int) -> bool:
        """Request resources for a subsystem."""
        return True  # M1: always grant for now

    def report(self) -> dict:
        """Current resource state."""
        return {"status": "not_implemented", "milestone": "M1"}
