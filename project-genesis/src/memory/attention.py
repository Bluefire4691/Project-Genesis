"""
Working Memory — Bounded RAM cache with attention window.

Short-term memory: what the system is actively holding in mind right now.
Fast (O(1) dict lookup), bounded, and alive to current context (relevance
scores shift with each attention update).

Two things live here:
    WorkingMemory   — the bounded RAM store itself
    AttentionWindow — a relevance-ranked view over working memory

When WorkingMemory is full and a new item arrives, the item with the
lowest "heat" (relevance + small access bonus) is evicted and returned
to the caller so it can be persisted to long-term storage (store.py).

Nothing is deleted. Eviction = migration to long-term. The memory lives
on — it just cools off to disk.

On working memory capacity:
The original default of 100 items was grounded in human-cognitive research
(OpenCog's ECAN attentional focus, ACT-R's goal buffer). Genesis is not
trying to model human cognitive limits — its working memory is bounded to
create *attention pressure*, not to match neuroscience. At 2000+ items the
eviction choices become genuinely meaningful: Genesis must decide, based on
relevance and access heat, what stays active. The O(n) eviction scan remains
fast (sub-millisecond) at this scale.
"""

import math
import os
import re
import sys
import time
from collections import OrderedDict
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.types import Memory


class WorkingMemory:
    """
    Bounded in-RAM memory store with LRU-aware eviction.

    Eviction strategy: when at capacity, evict the item with the
    lowest "heat" score:
        heat = relevance + 0.15 * min(access_count, 10)
    This gives a meaningful but bounded bonus to frequently-accessed
    items, so the system tends to retain useful memories even if their
    base relevance is low. Relevance still dominates.

    Access order is tracked via an OrderedDict. Items move to the
    front on each access. Eviction candidate is found by scanning
    for minimum heat (O(n), fast even at thousands of items).
    """

    def __init__(self, capacity: int = 2000):
        self.capacity = capacity
        # OrderedDict preserves insertion/access order (most recent at end)
        self._store: OrderedDict[str, Memory] = OrderedDict()
        self._context_terms: list[str] = []

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def put(self, key: str, memory: Memory) -> Optional[tuple[str, Memory]]:
        """
        Insert or update a memory in working memory.

        Returns the (key, memory) pair that was evicted to make room,
        or None if no eviction was needed. The caller is responsible
        for persisting the evicted memory to long-term storage.
        """
        if key in self._store:
            # Update in place and move to most-recently-used end
            self._store.move_to_end(key)
            existing = self._store[key]
            existing.content = memory.content
            existing.context = memory.context
            existing.relevance = max(existing.relevance, memory.relevance)
            existing.access_count = max(existing.access_count, memory.access_count)
            return None  # No eviction — just an update

        evicted = None
        if len(self._store) >= self.capacity:
            evicted = self._evict()

        self._store[key] = memory
        return evicted

    def get(self, key: str) -> Optional[Memory]:
        """Retrieve a memory by key. Updates access metadata and LRU order."""
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        mem = self._store[key]
        mem.access()
        return mem

    def has(self, key: str) -> bool:
        """Check if a key is in working memory (no access recorded)."""
        return key in self._store

    def promote(self, key: str, memory: Memory) -> Optional[tuple[str, Memory]]:
        """
        Bring a memory in from long-term storage into working memory.
        Same as put() — the name signals intent.
        """
        return self.put(key, memory)

    def remove(self, key: str) -> Optional[Memory]:
        """Remove a key from working memory (used during eviction pipeline)."""
        return self._store.pop(key, None)

    # ------------------------------------------------------------------
    # Attention
    # ------------------------------------------------------------------

    def update_relevance(self, context_terms: list[str]) -> None:
        """
        Shift relevance scores based on what's currently in focus.

        Memories whose content/context overlaps with current terms get
        a relevance boost. Others gently decay (but never to zero —
        nothing becomes invisible, just less prominent).
        """
        self._context_terms = context_terms
        if not context_terms:
            return

        context_set = {t.lower() for t in context_terms}

        for key, mem in self._store.items():
            searchable = f"{mem.content} {mem.context} {key}".lower()
            words = set(re.findall(r"\b\w+\b", searchable))
            overlap = len(context_set & words)
            if overlap > 0:
                mem.relevance = min(1.0, mem.relevance + overlap * 0.08)
            else:
                mem.relevance = max(0.05, mem.relevance * 0.96)

    def attention_window(
        self, top_k: int = 10, context_terms: list[str] | None = None
    ) -> list[tuple[str, Memory]]:
        """
        Return the top-k most relevant memories in working memory.

        If context_terms provided, scores are blended with context overlap.
        This is the "what am I thinking about right now" view.
        """
        if not self._store:
            return []

        ctx_set = {t.lower() for t in (context_terms or self._context_terms)}

        def score(key: str, mem: Memory) -> float:
            base = mem.relevance
            if ctx_set:
                words = set(re.findall(r"\b\w+\b", f"{mem.content} {mem.context} {key}".lower()))
                overlap = len(ctx_set & words)
                base = base * 0.6 + min(1.0, overlap * 0.2) * 0.4
            # Small recency bonus from access count (diminishing returns)
            return base + 0.05 * math.log1p(mem.access_count)

        ranked = sorted(self._store.items(), key=lambda kv: score(kv[0], kv[1]), reverse=True)
        return ranked[:top_k]

    # ------------------------------------------------------------------
    # Bulk access
    # ------------------------------------------------------------------

    def all(self) -> dict[str, Memory]:
        """Return a shallow copy of all working memory contents."""
        return dict(self._store)

    def keys(self) -> list[str]:
        return list(self._store.keys())

    def __len__(self) -> int:
        return len(self._store)

    def stats(self) -> dict:
        if not self._store:
            return {
                "capacity": self.capacity,
                "occupied": 0,
                "utilization_pct": 0.0,
                "avg_relevance": 0.0,
                "avg_access_count": 0.0,
                "context_terms": self._context_terms,
            }
        mems = list(self._store.values())
        return {
            "capacity": self.capacity,
            "occupied": len(self._store),
            "utilization_pct": round(100.0 * len(self._store) / self.capacity, 1),
            "avg_relevance": round(sum(m.relevance for m in mems) / len(mems), 3),
            "avg_access_count": round(sum(m.access_count for m in mems) / len(mems), 2),
            "context_terms": self._context_terms,
        }

    # ------------------------------------------------------------------
    # Eviction
    # ------------------------------------------------------------------

    def _evict(self) -> tuple[str, Memory]:
        """
        Select and remove the lowest-heat item.
        heat = relevance + 0.15 * min(access_count, 10)
        """
        evict_key = min(
            self._store.keys(),
            key=lambda k: self._store[k].relevance + 0.15 * min(self._store[k].access_count, 10),
        )
        return evict_key, self._store.pop(evict_key)

    def _heat(self, key: str) -> float:
        """Heat score for a key — used externally for diagnostics."""
        mem = self._store.get(key)
        if mem is None:
            return 0.0
        return mem.relevance + 0.15 * min(mem.access_count, 10)
