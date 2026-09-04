"""
Association Graph — memory linkage system.

Two kinds of associations form:

    Co-occurrence (automatic, strength 0.3):
        Memories processed within a sliding window of N cycles are
        weakly linked. The system doesn't decide these — they emerge
        from temporal proximity, the same way episodic memory in
        biological systems links things that happened close together
        in time.

    Explicit (orchestrator-directed, strength 0.7):
        The orchestrator can say "these two memories are related"
        when it has good reason. Higher strength, semantically
        meaningful. Used when processors identify category membership,
        causal links, or other structured relationships.

Associations are stored in the LongTermStore (SQLite), so they persist
across sessions. A memory that cooled off to disk still keeps its links.

Strength accumulates: if two memories are co-occurring AND explicitly
linked, the explicit link takes the higher strength (MAX in the upsert).

The graph is undirected — links are stored bidirectionally (A→B and B→A)
so traversal from either end is symmetric.
"""

import os
import sys
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from memory.store import LongTermStore


# How many recent keys to track for co-occurrence detection
CO_OCCURRENCE_WINDOW = 5

# Strength values
STRENGTH_CO_OCCURRENCE = 0.3
STRENGTH_EXPLICIT = 0.7


class AssociationGraph:
    """
    Manages association links between memories.

    The LongTermStore owns the actual data (SQLite associations table).
    This class provides the higher-level logic: co-occurrence tracking,
    explicit linking, and graph traversal.
    """

    def __init__(self, store: LongTermStore, window: int = CO_OCCURRENCE_WINDOW):
        """
        Args:
            store:  The LongTermStore to read/write associations from.
            window: Number of recent cycles to consider for co-occurrence.
        """
        self._store = store
        self._window = window
        # Recent (key, cycle) pairs — bounded deque for co-occurrence tracking
        self._recent: deque[tuple[str, int]] = deque(maxlen=window)
        self._link_count: int = 0

    # ------------------------------------------------------------------
    # Auto-association (co-occurrence)
    # ------------------------------------------------------------------

    def record_processed(self, key: str, cycle: int) -> list[tuple[str, str]]:
        """
        Record that a memory was processed in this cycle.

        Checks the recent window for co-occurring keys and creates weak
        associations with any found. Returns list of (key_a, key_b) pairs
        that were newly linked this call.

        This is the organic side: the system learns that things processed
        close together in time are probably related.
        """
        linked = []
        for recent_key, recent_cycle in self._recent:
            cycle_gap = cycle - recent_cycle
            if cycle_gap <= self._window and recent_key != key:
                # Strength scales with proximity — closer = stronger
                proximity = 1.0 - (cycle_gap / (self._window + 1))
                strength = STRENGTH_CO_OCCURRENCE * proximity
                self._store.add_association(key, recent_key, strength, "co_occurrence")
                self._link_count += 1
                linked.append((key, recent_key))

        self._recent.append((key, cycle))
        return linked

    # ------------------------------------------------------------------
    # Explicit association (orchestrator-directed)
    # ------------------------------------------------------------------

    def associate(
        self, key_a: str, key_b: str, strength: float = STRENGTH_EXPLICIT
    ) -> None:
        """
        Create an explicit association between two memories.

        Explicit links are stronger than co-occurrence (0.7 vs 0.3).
        If a co-occurrence link already exists, the explicit strength
        wins (MAX in the upsert).

        Args:
            key_a, key_b: Memory keys to link.
            strength:     Link strength (0.0–1.0). Defaults to 0.7.
        """
        self._store.add_association(key_a, key_b, strength, "explicit")
        self._link_count += 1

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    def neighbors(
        self, key: str, min_strength: float = 0.1
    ) -> list[tuple[str, float, str]]:
        """
        Return direct neighbors of a memory with strength >= min_strength.

        Returns list of (neighbor_key, strength, kind).
        """
        return self._store.get_associations(key, min_strength)

    def traverse(
        self,
        key: str,
        depth: int = 1,
        min_strength: float = 0.1,
    ) -> list[tuple[str, float]]:
        """
        BFS traversal of the association graph from `key`.

        Returns list of (neighbor_key, strength) up to `depth` hops.
        Cycles are handled — each key appears at most once.

        Args:
            key:          Starting memory key.
            depth:        How many hops to follow (1 = direct neighbors only).
            min_strength: Minimum link strength to follow.
        """
        visited: set[str] = {key}
        results: list[tuple[str, float]] = []
        frontier: list[tuple[str, float]] = []

        # Initialize frontier with direct neighbors
        for neighbor_key, strength, _ in self.neighbors(key, min_strength):
            if neighbor_key not in visited:
                frontier.append((neighbor_key, strength))
                visited.add(neighbor_key)

        for _ in range(depth):
            if not frontier:
                break
            results.extend(frontier)
            next_frontier = []
            for frontier_key, frontier_strength in frontier:
                for neighbor_key, strength, _ in self.neighbors(frontier_key, min_strength):
                    if neighbor_key not in visited:
                        # Compound strength: following two 0.5 links = 0.25 effective
                        effective = frontier_strength * strength
                        next_frontier.append((neighbor_key, effective))
                        visited.add(neighbor_key)
            frontier = next_frontier

        return results

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        return {
            "links_created_this_session": self._link_count,
            "co_occurrence_window": self._window,
            "recent_keys": [k for k, _ in self._recent],
        }
