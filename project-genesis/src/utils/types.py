"""
Shared types and data structures for Project Genesis.

All inter-module communication uses these standardized types so that
processors, orchestrator, memory, and curriculum can work together
without tight coupling.
"""

from dataclasses import dataclass, field
from typing import Any
from enum import IntEnum
import time


class Stage(IntEnum):
    """Learning stages — sequential, each builds on the last."""
    FOUNDATION = 1   # Simple facts, basic categories
    RELATIONS = 2    # Multi-fact connections, cause-effect
    REASONING = 3    # Inference from stored knowledge
    OPEN = 4         # Broader, uncurated data


@dataclass
class ProcessorOutput:
    """
    Standardized output from any sensory processor.

    Every processor — regardless of what it handles — produces this
    same structure. The orchestrator doesn't need to know what type
    of processor generated it.
    """
    source: str          # Processor name (e.g., "text", "numeric")
    input_data: Any      # The raw input that was processed
    extracted: dict      # What the processor found
    importance: float    # How important the processor thinks this is (0.0-1.0)
    suggested_key: str   # Suggested memory key
    context: str         # Context snippet for memory storage
    confidence: float = 1.0  # How confident the processor is in its output


@dataclass
class Memory:
    """
    A single memory unit.

    Unlike the proof-of-concept, this stores everything with full fidelity.
    The 'relevance' score is dynamic — it changes based on current context,
    not based on time-decay. Nothing is forgotten.
    """
    content: str              # Full original content
    context: str              # Why/when this was learned
    source_type: str          # Which processor created this
    relevance: float          # Dynamic relevance to current context (0.0-1.0)
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    associations: list = field(default_factory=list)  # Links to related memory keys

    def access(self):
        """Accessing a memory updates its metadata."""
        self.access_count += 1

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "context": self.context,
            "source": self.source_type,
            "relevance": round(self.relevance, 3),
            "access_count": self.access_count,
            "associations": self.associations,
        }


@dataclass
class ResourceBudget:
    """
    Resource allocation for the Survival OS.

    The system operates within these constraints. When resources run low,
    the system must prioritize — just like a biological organism.
    """
    cpu_cycles: int = 1000     # Available processing cycles this tick
    memory_bytes: int = 0      # Current memory usage
    memory_limit: int = 0      # Maximum memory allowed
    storage_ops: int = 100     # Available storage operations this tick
    energy: float = 1.0        # Overall energy level (0.0-1.0)

    def is_critical(self) -> bool:
        """Are we in a critical resource state?"""
        return self.energy < 0.2

    def is_healthy(self) -> bool:
        """Do we have comfortable resources?"""
        return self.energy > 0.6


@dataclass
class Directive:
    """
    A hardwired survival directive.

    Not a goal (goals imply someone decided what the system should want).
    Directives are environmental pressures that shape behavior.
    """
    name: str
    priority: float          # How important this directive is (0.0-1.0)
    satisfaction: float = 0.5  # How well this directive is currently being met
    description: str = ""
