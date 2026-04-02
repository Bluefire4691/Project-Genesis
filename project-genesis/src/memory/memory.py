"""
Memory System — Two-tier total-retention memory.

Coordinates the three memory subsystems into a single interface:

    WorkingMemory   (attention.py)   — bounded RAM, fast, context-aware
    LongTermStore   (store.py)       — SQLite on disk, persistent, FTS search
    AssociationGraph (associations.py) — organic + explicit memory links

Write-through design: every store() call writes to SQLite immediately,
then puts the memory into working memory. A crash can't lose a memory.

Recall path:
    1. Check working memory first  (O(1), in RAM)
    2. If not there, query SQLite  (disk I/O)
    3. If found on disk, promote to working memory (may evict another)

Search path:
    1. FTS5 search on SQLite (full corpus, ranked)
    2. Re-rank results by blending FTS score with current attention context
    3. Promote top results to working memory

The `memories` property returns the working memory dict — this keeps
compatibility with main.py and gives a "what's in mind right now" view.
Long-term memories are accessible via recall() and search().
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.types import Memory
from memory.store import LongTermStore
from memory.attention import WorkingMemory
from memory.associations import AssociationGraph


# Resolve project root so the DB ends up at project-genesis/data/genesis_memory.db
# regardless of where the process is launched from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
_DEFAULT_DB = os.path.join(_PROJECT_ROOT, "data", "genesis_memory.db")


class MemorySystem:
    """
    Total-retention memory with two-tier architecture.

    Public interface is the same as the M0 MemorySystem so the
    Orchestrator and tests need minimal changes.

    New capabilities vs M0:
        - All memories persist to disk (SQLite) — survive process restart
        - Working memory bounded to `working_capacity` items (default 100)
        - FTS5 full-text search across the full corpus (not just working mem)
        - Organic co-occurrence associations + explicit links
        - Evicted memories migrate to long-term, not dropped
    """

    def __init__(
        self,
        db_path: str = _DEFAULT_DB,
        working_capacity: int = 100,
    ):
        self._long_term = LongTermStore(db_path)
        self._working = WorkingMemory(capacity=working_capacity)
        self._associations = AssociationGraph(self._long_term)
        self._cycle: int = 0  # tracks current cognitive cycle for co-occurrence

    # ------------------------------------------------------------------
    # Primary write path
    # ------------------------------------------------------------------

    def store(
        self,
        key: str,
        content: str,
        context: str,
        source_type: str,
        relevance: float,
        associations: list | None = None,
    ) -> bool:
        """
        Store a memory. Always succeeds — we never refuse to store.

        Write-through: SQLite is written first, then working memory.
        If working memory is full, the lowest-heat item is evicted
        (it stays in SQLite — nothing is lost).

        Returns True always (retained for API compatibility).
        """
        self._cycle += 1
        memory = Memory(
            content=content,
            context=context,
            source_type=source_type,
            relevance=min(1.0, max(0.0, relevance)),
            created_at=time.time(),
        )

        # 1. Write to long-term storage first (source of truth)
        self._long_term.upsert(key, memory)

        # 2. Put in working memory; handle any eviction
        evicted = self._working.put(key, memory)
        if evicted:
            evicted_key, evicted_mem = evicted
            # Sync final access count back to SQLite before cooling off
            self._long_term.update_access(evicted_key, evicted_mem.access_count)
            # Evicted memory stays in SQLite — nothing is lost

        # 3. Record for co-occurrence association tracking
        self._associations.record_processed(key, self._cycle)

        # 4. Create any explicit associations requested by the caller
        if associations:
            for assoc_key in associations:
                self._associations.associate(key, assoc_key)

        return True

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def recall(self, key: str) -> Memory | None:
        """
        Recall a specific memory by key.

        Checks working memory first (fast), falls back to SQLite (slower).
        A SQLite hit promotes the memory back into working memory.
        """
        # Fast path
        mem = self._working.get(key)
        if mem is not None:
            self._long_term.update_access(key, mem.access_count)
            return mem

        # Slow path — load from long-term and promote
        mem = self._long_term.get(key)
        if mem is not None:
            mem.access()
            self._long_term.update_access(key, mem.access_count)
            evicted = self._working.promote(key, mem)
            if evicted:
                evict_key, evict_mem = evicted
                self._long_term.update_access(evict_key, evict_mem.access_count)
        return mem

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, Memory]]:
        """
        Search memories by relevance to query.

        Uses FTS5 on the full SQLite corpus (not just working memory),
        then re-ranks by blending search score with attention context.
        Top results are promoted into working memory.
        """
        # Search long-term (FTS5 / LIKE fallback, returns up to 3×top_k candidates)
        candidates = self._long_term.search(query, limit=top_k * 3)

        if not candidates:
            return []

        # Re-rank: blend stored relevance with working-memory context
        context_terms = self._working._context_terms
        ctx_set = {t.lower() for t in context_terms}

        def rank_score(key: str, mem: Memory) -> float:
            base = mem.relevance
            if ctx_set:
                import re
                words = set(re.findall(r"\b\w+\b", f"{mem.content} {mem.context}".lower()))
                overlap = len(ctx_set & words)
                base = base * 0.6 + min(1.0, overlap * 0.15) * 0.4
            return base

        candidates.sort(key=lambda kv: rank_score(kv[0], kv[1]), reverse=True)
        top = candidates[:top_k]

        # Promote to working memory and record accesses
        for key, mem in top:
            mem.access()
            self._long_term.update_access(key, mem.access_count)
            evicted = self._working.promote(key, mem)
            if evicted:
                evict_key, evict_mem = evicted
                self._long_term.update_access(evict_key, evict_mem.access_count)

        return top

    # ------------------------------------------------------------------
    # Attention
    # ------------------------------------------------------------------

    def update_attention(self, context_terms: list[str]) -> None:
        """
        Shift attention to new context terms.

        Updates relevance scores in working memory. Long-term relevance
        scores are updated lazily — only when memories are accessed.
        """
        self._working.update_relevance(context_terms)

    # ------------------------------------------------------------------
    # Associations
    # ------------------------------------------------------------------

    def get_associations(self, key: str, depth: int = 1) -> list[tuple[str, Memory]]:
        """
        Follow association links from a memory up to `depth` hops.

        Returns list of (key, Memory) pairs. Memories found in long-term
        storage are loaded and promoted to working memory.
        """
        linked = self._associations.traverse(key, depth=depth)
        results = []
        for assoc_key, _strength in linked:
            mem = self.recall(assoc_key)  # uses the two-tier recall path
            if mem is not None:
                results.append((assoc_key, mem))
        return results

    def associate(self, key_a: str, key_b: str, strength: float = 0.7) -> None:
        """Explicitly link two memories (orchestrator-directed)."""
        self._associations.associate(key_a, key_b, strength)

    # ------------------------------------------------------------------
    # Compatibility & introspection
    # ------------------------------------------------------------------

    @property
    def memories(self) -> dict[str, Memory]:
        """
        Working memory contents — the system's current active attention.

        Used by main.py to display "what's in mind right now." Full
        long-term corpus is accessible via search() and recall().
        """
        return self._working.all()

    def stats(self) -> dict:
        lt_stats = self._long_term.stats()
        wm_stats = self._working.stats()
        return {
            # Backward-compatible keys (Orchestrator uses these)
            "total_stored": lt_stats["total_memories"],
            "avg_relevance": lt_stats["avg_relevance"],
            "most_accessed": (
                max(
                    self._working.all().items(),
                    key=lambda kv: kv[1].access_count,
                    default=(None, None),
                )[0]
            ),
            "attention_context": self._working._context_terms,
            # New M2 detail
            "working_memory": wm_stats,
            "long_term": lt_stats,
            "associations": self._associations.stats(),
        }
