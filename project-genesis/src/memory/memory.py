"""
Memory system — Total retention with selective attention.

Stores everything. Forgets nothing. But manages what's relevant
to the current context through dynamic attention scoring.

"Having a perfect library but still needing a librarian
who knows what book to pull."
"""

import re
import time
from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import Memory


class MemorySystem:
    """
    Total-retention memory with selective attention.

    Every piece of data is stored permanently. The attention system
    dynamically scores relevance based on current context, so the
    right memories surface when needed without scanning everything.
    """

    def __init__(self):
        self.memories: dict[str, Memory] = {}
        self.attention_context: list[str] = []  # Current focus terms

    def store(self, key: str, content: str, context: str,
              source_type: str, relevance: float,
              associations: list = None) -> bool:
        """
        Store a memory. Always succeeds — we never refuse to store.
        Returns True always (retained for API compatibility).
        """
        if key in self.memories:
            # Update existing memory — merge, don't overwrite
            existing = self.memories[key]
            existing.content = f"{existing.content} | {content}"
            existing.context = f"{existing.context}; {context}"
            existing.relevance = max(existing.relevance, relevance)
            if associations:
                existing.associations = list(set(existing.associations + associations))
        else:
            self.memories[key] = Memory(
                content=content,
                context=context,
                source_type=source_type,
                relevance=min(1.0, relevance),
                associations=associations or [],
            )
        return True

    def recall(self, key: str) -> Memory | None:
        """Recall a specific memory by key."""
        mem = self.memories.get(key)
        if mem:
            mem.access()
        return mem

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, Memory]]:
        """
        Search memories by relevance to query.
        Uses keyword overlap weighted by current relevance scores.
        """
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        # Remove noise words
        query_words -= {"what", "do", "you", "know", "about", "tell", "me",
                        "have", "seen", "the", "any", "how", "why", "where",
                        "when", "which", "does", "did", "can", "could"}
        if not query_words:
            query_words = set(re.findall(r'\b\w+\b', query.lower()))

        scored = []
        for key, mem in self.memories.items():
            searchable = f"{mem.content} {mem.context} {key}".lower()
            searchable_words = set(re.findall(r'\b\w+\b', searchable))
            overlap = len(query_words & searchable_words)
            if overlap > 0:
                score = overlap * max(mem.relevance, 0.1)  # Even low-relevance memories can match
                scored.append((score, key, mem))
                mem.access()

        scored.sort(reverse=True, key=lambda x: x[0])
        return [(key, mem) for _, key, mem in scored[:top_k]]

    def update_attention(self, context_terms: list[str]):
        """
        Shift attention to new context. This adjusts relevance scores
        across all memories based on what's currently important.
        """
        self.attention_context = context_terms
        context_set = set(t.lower() for t in context_terms)

        for key, mem in self.memories.items():
            searchable = f"{mem.content} {mem.context} {key}".lower()
            searchable_words = set(re.findall(r'\b\w+\b', searchable))
            overlap = len(context_set & searchable_words)
            if overlap > 0:
                # Boost relevance for contextually relevant memories
                mem.relevance = min(1.0, mem.relevance + overlap * 0.1)
            else:
                # Slightly reduce relevance for non-contextual memories
                # But never below a floor — nothing becomes invisible
                mem.relevance = max(0.05, mem.relevance * 0.95)

    def get_associations(self, key: str, depth: int = 1) -> list[tuple[str, Memory]]:
        """Follow association links from a memory, up to given depth."""
        mem = self.memories.get(key)
        if not mem:
            return []

        visited = {key}
        results = []
        frontier = mem.associations[:]

        for _ in range(depth):
            next_frontier = []
            for assoc_key in frontier:
                if assoc_key not in visited and assoc_key in self.memories:
                    visited.add(assoc_key)
                    assoc_mem = self.memories[assoc_key]
                    assoc_mem.access()
                    results.append((assoc_key, assoc_mem))
                    next_frontier.extend(assoc_mem.associations)
            frontier = next_frontier

        return results

    def stats(self) -> dict:
        return {
            "total_stored": len(self.memories),
            "avg_relevance": (
                round(sum(m.relevance for m in self.memories.values()) / len(self.memories), 3)
                if self.memories else 0
            ),
            "most_accessed": (
                max(self.memories.items(), key=lambda x: x[1].access_count)[0]
                if self.memories else None
            ),
            "attention_context": self.attention_context,
        }
