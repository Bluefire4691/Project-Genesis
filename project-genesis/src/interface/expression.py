"""
Expression — Genesis surfaces its internal state.

This is the outward-facing side of community. Not a report we request,
but what Genesis has to show based on what it's actually been processing.

Three things get surfaced:

    Attention state    — what's currently in working memory, ranked by heat.
                         What Genesis is "thinking about" right now.

    Association clusters — what has been linking to what. Organic structure
                           that emerged from processing, not from us defining
                           categories.

    Unresolved items   — things that were processed but didn't fit anywhere
                         well. Low confidence, weak associations, no clear
                         category. These are the edges of what Genesis
                         currently understands.

None of this is a request for Genesis to do something. It's a window.
We can choose to engage with what we see or not. If we do engage —
feed something related, ask a question, introduce a contrasting idea —
that goes in as ordinary input. No special weight. Genesis processes it
the same way it processes everything else.

The expression is also the basis for stagnation detection in observer.py:
if consecutive expressions look identical, nothing is developing.
"""

import time
from dataclasses import dataclass, field

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory.memory import MemorySystem
from memory.associations import AssociationGraph


@dataclass
class ExpressionSnapshot:
    """
    What Genesis is surfacing at a point in time.

    This is a read-only view — it describes state, it doesn't change it.
    """
    timestamp: float

    # What's in working memory right now, ranked by attention heat
    attention_top: list[dict]           # [{key, content, context, relevance, access_count}]

    # What has been actively associating — clusters of related keys
    association_clusters: list[dict]    # [{anchor, neighbors: [{key, strength, kind}]}]

    # Things that didn't fit well — uncertain, uncategorized, isolated
    unresolved: list[dict]              # [{key, content, reason}]

    # Diversity signal: how many distinct source types are in working memory
    source_diversity: dict              # {source_type: count}

    # How many items are in working memory vs capacity
    working_memory_load: float          # 0.0–1.0

    # Cycle count at time of expression
    cycle: int

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "cycle": self.cycle,
            "working_memory_load": round(self.working_memory_load, 3),
            "source_diversity": self.source_diversity,
            "attention_top": self.attention_top,
            "association_clusters": self.association_clusters,
            "unresolved": self.unresolved,
        }

    def summary(self) -> str:
        """Human-readable one-paragraph summary of current state."""
        lines = [
            f"[Cycle {self.cycle}] Working memory: "
            f"{int(self.working_memory_load * 100)}% full. "
            f"Source diversity: {dict(self.source_diversity)}."
        ]
        if self.attention_top:
            top = self.attention_top[0]
            lines.append(
                f"Top attention: '{top['key']}' "
                f"(relevance {top['relevance']:.2f}, "
                f"accessed {top['access_count']}x): {top['context']}"
            )
        if self.association_clusters:
            cluster = self.association_clusters[0]
            neighbor_keys = [n["key"] for n in cluster["neighbors"][:3]]
            lines.append(
                f"Strongest cluster: '{cluster['anchor']}' "
                f"linked to {neighbor_keys}."
            )
        if self.unresolved:
            lines.append(
                f"{len(self.unresolved)} unresolved item(s) — "
                f"things at the edge of current understanding."
            )
        return " ".join(lines)


class ExpressionEngine:
    """
    Generates expression snapshots from Genesis's current memory state.

    Called by the InteractionLayer on a configurable cadence (e.g. every
    N cycles, or on demand). The resulting ExpressionSnapshot can be
    logged, displayed, or used by the Observer for stagnation detection.
    """

    def __init__(
        self,
        memory: MemorySystem,
        attention_top_k: int = 10,
        cluster_top_k: int = 5,
        unresolved_threshold: float = 0.25,
    ):
        """
        Args:
            memory:               The MemorySystem to read from.
            attention_top_k:      How many top-attention items to surface.
            cluster_top_k:        How many association clusters to surface.
            unresolved_threshold: Relevance below this = candidate for unresolved.
        """
        self._memory = memory
        self._attention_top_k = attention_top_k
        self._cluster_top_k = cluster_top_k
        self._unresolved_threshold = unresolved_threshold

    def snapshot(self, cycle: int) -> ExpressionSnapshot:
        """
        Generate an expression snapshot of Genesis's current state.
        Safe to call at any time — never modifies state, never raises.
        """
        try:
            return self._build_snapshot(cycle)
        except Exception:
            # Expression failure should never disrupt the main cycle
            return ExpressionSnapshot(
                timestamp=time.time(),
                cycle=cycle,
                attention_top=[],
                association_clusters=[],
                unresolved=[],
                source_diversity={},
                working_memory_load=0.0,
            )

    def _build_snapshot(self, cycle: int) -> ExpressionSnapshot:
        working = self._memory.memories  # current working memory dict
        wm_stats = self._memory._working.stats()
        load = wm_stats["occupied"] / max(1, wm_stats["capacity"])

        # --- Attention top-K ---
        attention_window = self._memory._working.attention_window(
            top_k=self._attention_top_k
        )
        attention_top = [
            {
                "key": key,
                "content": mem.content[:120],   # truncate for readability
                "context": mem.context[:80],
                "relevance": round(mem.relevance, 3),
                "access_count": mem.access_count,
                "source": mem.source_type,
            }
            for key, mem in attention_window
        ]

        # --- Association clusters ---
        # Take the top-K most-accessed working memory items as anchor points
        sorted_by_access = sorted(
            working.items(),
            key=lambda kv: kv[1].access_count,
            reverse=True,
        )[:self._cluster_top_k]

        clusters = []
        for anchor_key, _ in sorted_by_access:
            neighbors = self._memory._long_term.get_associations(
                anchor_key, min_strength=0.2
            )
            if neighbors:
                clusters.append({
                    "anchor": anchor_key,
                    "neighbors": [
                        {"key": k, "strength": round(s, 3), "kind": kind}
                        for k, s, kind in sorted(neighbors, key=lambda x: x[1], reverse=True)[:5]
                    ],
                })

        # --- Unresolved items ---
        # Low relevance in working memory + no strong associations + low confidence
        unresolved = []
        for key, mem in working.items():
            if mem.relevance < self._unresolved_threshold:
                neighbors = self._memory._long_term.get_associations(key, min_strength=0.2)
                if not neighbors:
                    reason = "low relevance, no associations"
                    if mem.access_count == 0:
                        reason = "never accessed, no associations"
                    unresolved.append({
                        "key": key,
                        "content": mem.content[:80],
                        "reason": reason,
                        "relevance": round(mem.relevance, 3),
                    })

        # --- Source diversity ---
        diversity: dict[str, int] = {}
        for mem in working.values():
            diversity[mem.source_type] = diversity.get(mem.source_type, 0) + 1

        return ExpressionSnapshot(
            timestamp=time.time(),
            cycle=cycle,
            attention_top=attention_top,
            association_clusters=clusters,
            unresolved=unresolved,
            source_diversity=diversity,
            working_memory_load=round(load, 3),
        )
