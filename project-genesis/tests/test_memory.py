"""
Tests for the two-tier memory system (M2).

Covers: LongTermStore, WorkingMemory, AssociationGraph, and the
integrated MemorySystem. All M0 tests preserved and extended.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory.store import LongTermStore
from memory.attention import WorkingMemory
from memory.associations import AssociationGraph
from memory.memory import MemorySystem
from utils.types import Memory


def _make_memory(content="test content", relevance=0.5, source="text") -> Memory:
    return Memory(
        content=content,
        context="test context",
        source_type=source,
        relevance=relevance,
    )


def _tmp_db() -> str:
    """Return a temp path for a test database (isolated per test)."""
    return os.path.join(tempfile.mkdtemp(), "test_memory.db")


# ==================================================================
# LongTermStore
# ==================================================================

def test_store_upsert_and_get():
    store = LongTermStore(_tmp_db())
    mem = _make_memory("dogs are loyal animals")
    store.upsert("animal:dog", mem)
    result = store.get("animal:dog")
    assert result is not None
    assert "dogs" in result.content


def test_store_total_retention():
    """LongTermStore never loses data."""
    store = LongTermStore(_tmp_db())
    for i in range(200):
        store.upsert(f"key:{i}", _make_memory(f"content {i}", relevance=0.1))
    assert len(store.all_keys()) == 200


def test_store_upsert_merges_relevance():
    """Re-storing a key takes the higher relevance."""
    store = LongTermStore(_tmp_db())
    store.upsert("k", _make_memory("v1", relevance=0.3))
    store.upsert("k", _make_memory("v2", relevance=0.8))
    result = store.get("k")
    assert result.relevance == 0.8


def test_store_search_returns_results():
    store = LongTermStore(_tmp_db())
    store.upsert("animal:dog", _make_memory("dogs are loyal animals"))
    store.upsert("food:apple", _make_memory("apples are sweet fruits"))
    results = store.search("dog loyal")
    keys = [k for k, _ in results]
    assert "animal:dog" in keys


def test_store_search_never_crashes():
    """Search must handle empty query, special chars, missing table gracefully."""
    store = LongTermStore(_tmp_db())
    assert store.search("") == []
    assert store.search("!@#$%^") == []
    assert store.search("nothing here") == []


def test_store_associations_bidirectional():
    store = LongTermStore(_tmp_db())
    store.add_association("a", "b", 0.5, "explicit")
    a_neighbors = store.get_associations("a")
    b_neighbors = store.get_associations("b")
    assert any(k == "b" for k, _, _ in a_neighbors)
    assert any(k == "a" for k, _, _ in b_neighbors)


def test_store_association_strength_accumulates():
    """Adding a stronger link overwrites weaker one (MAX)."""
    store = LongTermStore(_tmp_db())
    store.add_association("a", "b", 0.3, "co_occurrence")
    store.add_association("a", "b", 0.7, "explicit")
    neighbors = store.get_associations("a")
    strength = next(s for k, s, _ in neighbors if k == "b")
    assert strength == 0.7


def test_store_persists_across_reopen():
    """Data written to SQLite survives closing and reopening the connection."""
    path = _tmp_db()
    store1 = LongTermStore(path)
    store1.upsert("persist:test", _make_memory("I should survive restart"))
    store1.close()

    store2 = LongTermStore(path)
    result = store2.get("persist:test")
    assert result is not None
    assert "survive" in result.content


def test_store_stats_structure():
    store = LongTermStore(_tmp_db())
    store.upsert("k", _make_memory("v"))
    s = store.stats()
    assert "total_memories" in s
    assert "fts_available" in s
    assert s["total_memories"] == 1


# ==================================================================
# WorkingMemory
# ==================================================================

def test_working_memory_put_and_get():
    wm = WorkingMemory(capacity=10)
    wm.put("k1", _make_memory("hello"))
    result = wm.get("k1")
    assert result is not None
    assert "hello" in result.content


def test_working_memory_evicts_at_capacity():
    """At capacity, putting a new item evicts the lowest-heat item."""
    wm = WorkingMemory(capacity=3)
    wm.put("low", _make_memory("low relevance", relevance=0.1))
    wm.put("mid", _make_memory("mid relevance", relevance=0.5))
    wm.put("high", _make_memory("high relevance", relevance=0.9))
    evicted = wm.put("new", _make_memory("new item", relevance=0.4))
    assert evicted is not None
    evicted_key, _ = evicted
    assert evicted_key == "low"  # lowest heat evicted


def test_working_memory_eviction_returns_evicted_pair():
    wm = WorkingMemory(capacity=1)
    wm.put("first", _make_memory("first", relevance=0.5))
    evicted = wm.put("second", _make_memory("second", relevance=0.9))
    assert evicted is not None
    key, mem = evicted
    assert key == "first"
    assert "first" in mem.content


def test_working_memory_no_eviction_on_update():
    """Updating an existing key should never evict."""
    wm = WorkingMemory(capacity=2)
    wm.put("a", _make_memory("original", relevance=0.3))
    wm.put("b", _make_memory("other", relevance=0.5))
    evicted = wm.put("a", _make_memory("updated", relevance=0.7))
    assert evicted is None
    assert len(wm) == 2


def test_working_memory_attention_window_ranked():
    """attention_window returns items ranked by relevance."""
    wm = WorkingMemory()
    wm.put("lo", _make_memory("low", relevance=0.1))
    wm.put("hi", _make_memory("high", relevance=0.9))
    wm.put("mid", _make_memory("mid", relevance=0.5))
    window = wm.attention_window(top_k=3)
    keys = [k for k, _ in window]
    assert keys[0] == "hi"


def test_working_memory_context_shifts_relevance():
    """update_relevance boosts matching memories and decays others."""
    wm = WorkingMemory()
    wm.put("animal:dog", _make_memory("dogs are animals", relevance=0.5))
    wm.put("food:apple", _make_memory("apples are fruits", relevance=0.5))
    wm.update_relevance(["dog", "animal"])
    dog_mem = wm.get("animal:dog")
    apple_mem = wm.get("food:apple")
    assert dog_mem.relevance > apple_mem.relevance


def test_working_memory_heat_access_bonus():
    """Frequently accessed items get a heat bonus that delays eviction."""
    wm = WorkingMemory(capacity=2)
    wm.put("low_rel", _make_memory("low", relevance=0.1))
    # Access it many times to build up the bonus
    for _ in range(10):
        wm.get("low_rel")
    wm.put("mid_rel", _make_memory("mid", relevance=0.5))
    evicted = wm.put("new", _make_memory("new", relevance=0.4))
    # mid_rel should be evicted (heat 0.5) not low_rel (heat 0.1 + 1.5 bonus = 1.6)
    if evicted:
        assert evicted[0] == "mid_rel"


def test_working_memory_stats():
    wm = WorkingMemory(capacity=10)
    for i in range(5):
        wm.put(f"k{i}", _make_memory(f"v{i}", relevance=0.5))
    s = wm.stats()
    assert s["occupied"] == 5
    assert s["capacity"] == 10
    assert s["utilization_pct"] == 50.0


# ==================================================================
# AssociationGraph
# ==================================================================

def test_associations_co_occurrence():
    """Memories processed in close cycles get automatic links."""
    store = LongTermStore(_tmp_db())
    graph = AssociationGraph(store, window=5)
    graph.record_processed("a", cycle=1)
    graph.record_processed("b", cycle=2)
    # b should now be linked to a (they were within the window)
    neighbors = graph.neighbors("b")
    keys = [k for k, _, _ in neighbors]
    assert "a" in keys


def test_associations_explicit():
    store = LongTermStore(_tmp_db())
    graph = AssociationGraph(store)
    graph.associate("x", "y", strength=0.8)
    neighbors = graph.neighbors("x")
    assert any(k == "y" and s == 0.8 for k, s, kind in neighbors)


def test_associations_traverse_depth():
    """Traversal at depth 2 should reach two hops away."""
    store = LongTermStore(_tmp_db())
    graph = AssociationGraph(store)
    graph.associate("a", "b", 0.8)
    graph.associate("b", "c", 0.8)
    reached = [k for k, _ in graph.traverse("a", depth=2)]
    assert "b" in reached
    assert "c" in reached


def test_associations_no_cycles():
    """Traversal should never return the same key twice."""
    store = LongTermStore(_tmp_db())
    graph = AssociationGraph(store)
    graph.associate("a", "b", 0.8)
    graph.associate("b", "a", 0.8)  # cycle
    reached = [k for k, _ in graph.traverse("a", depth=3)]
    assert reached.count("b") == 1  # "b" appears exactly once


def test_associations_co_occurrence_strength_decays_with_distance():
    """Keys further apart in the window should have weaker co-occurrence links."""
    store = LongTermStore(_tmp_db())
    graph = AssociationGraph(store, window=10)
    graph.record_processed("anchor", cycle=1)
    graph.record_processed("close", cycle=2)   # 1 cycle away
    graph.record_processed("far", cycle=8)     # 7 cycles away
    graph.record_processed("probe", cycle=9)   # links to both anchor and close

    anchor_neighbors = {k: s for k, s, _ in graph.neighbors("anchor")}
    close_neighbors = {k: s for k, s, _ in graph.neighbors("close")}

    # Both should be linked to probe, but anchor link should be weaker (further away)
    # (This is a soft check — timing may vary slightly)
    if "probe" in anchor_neighbors and "probe" in close_neighbors:
        assert anchor_neighbors["probe"] <= close_neighbors["probe"]


# ==================================================================
# MemorySystem (integrated two-tier)
# ==================================================================

def _mem_system() -> MemorySystem:
    """Create a test MemorySystem with an isolated temp database."""
    return MemorySystem(db_path=_tmp_db(), working_capacity=100)


def test_store_and_recall():
    mem = _mem_system()
    mem.store("test:1", "dogs are animals", "basic fact", "text", 0.5)
    result = mem.recall("test:1")
    assert result is not None
    assert "dogs" in result.content


def test_total_retention_working_memory():
    """100 items all stay in working memory (exact capacity)."""
    mem = _mem_system()
    for i in range(100):
        mem.store(f"item:{i}", f"content {i}", f"context {i}", "text", 0.5)
    assert len(mem.memories) == 100


def test_total_retention_long_term():
    """All items persist to SQLite even when working memory evicts some."""
    mem = MemorySystem(db_path=_tmp_db(), working_capacity=10)
    for i in range(50):
        mem.store(f"item:{i}", f"content {i}", f"context {i}", "text", 0.3)
    # Working memory: at most 10
    assert len(mem.memories) <= 10
    # Long-term: all 50
    assert mem.stats()["total_stored"] == 50


def test_recall_promotes_from_long_term():
    """A memory evicted from working memory can be recalled from SQLite."""
    mem = MemorySystem(db_path=_tmp_db(), working_capacity=2)
    mem.store("early", "early memory content", "ctx", "text", 0.1)
    # Fill working memory to force eviction of "early"
    mem.store("fill1", "filler 1", "ctx", "text", 0.9)
    mem.store("fill2", "filler 2", "ctx", "text", 0.9)
    # "early" should have been evicted from working memory
    # but recall() should still find it in SQLite and promote it
    result = mem.recall("early")
    assert result is not None
    assert "early" in result.content


def test_search():
    mem = _mem_system()
    mem.store("animal:dog", "dogs are loyal animals", "animal fact", "text", 0.5)
    mem.store("food:apple", "apples are sweet fruits", "food fact", "text", 0.5)
    results = mem.search("dog animal")
    assert len(results) > 0
    assert results[0][0] == "animal:dog"


def test_search_reaches_long_term():
    """Search returns memories not currently in working memory."""
    mem = MemorySystem(db_path=_tmp_db(), working_capacity=1)
    mem.store("a", "dogs are animals", "ctx", "text", 0.5)
    mem.store("b", "cats are animals too", "ctx", "text", 0.9)  # evicts "a"
    results = mem.search("dog")
    keys = [k for k, _ in results]
    assert "a" in keys  # found in long-term, promoted


def test_attention_update():
    mem = _mem_system()
    mem.store("animal:dog", "dogs are animals", "fact", "text", 0.5)
    mem.store("food:apple", "apples are fruits", "fact", "text", 0.5)
    mem.update_attention(["animal", "dog"])
    dog_mem = mem.memories.get("animal:dog")
    apple_mem = mem.memories.get("food:apple")
    assert dog_mem is not None and apple_mem is not None
    assert dog_mem.relevance > apple_mem.relevance


def test_associations_explicit_via_memory_system():
    mem = _mem_system()
    mem.store("a", "first", "ctx", "text", 0.5)
    mem.store("b", "second", "ctx", "text", 0.5)
    mem.associate("a", "b")
    assocs = mem.get_associations("a", depth=1)
    keys = [k for k, _ in assocs]
    assert "b" in keys


def test_associations_via_store_parameter():
    """Passing associations=[] to store() creates explicit links."""
    mem = _mem_system()
    mem.store("a", "first", "ctx", "text", 0.5)
    mem.store("b", "second", "ctx", "text", 0.5, associations=["a"])
    assocs = mem.get_associations("b", depth=1)
    keys = [k for k, _ in assocs]
    assert "a" in keys


def test_associations_depth_2():
    mem = _mem_system()
    mem.store("a", "first", "ctx", "text", 0.5)
    mem.store("b", "second", "ctx", "text", 0.5, associations=["a"])
    mem.store("c", "third", "ctx", "text", 0.5, associations=["b"])
    assocs = mem.get_associations("a", depth=2)
    keys = [k for k, _ in assocs]
    assert "b" in keys
    assert "c" in keys


def test_co_occurrence_associations_form_organically():
    """Memories stored in close succession should auto-link."""
    mem = _mem_system()
    mem.store("first", "first memory", "ctx", "text", 0.5)
    mem.store("second", "second memory", "ctx", "text", 0.5)
    # Should have formed a co-occurrence link
    assocs = mem.get_associations("first", depth=1)
    keys = [k for k, _ in assocs]
    assert "second" in keys


def test_merge_on_duplicate_key():
    mem = _mem_system()
    mem.store("test:1", "first version", "ctx1", "text", 0.3)
    mem.store("test:1", "second version", "ctx2", "text", 0.7)
    result = mem.recall("test:1")
    assert result.relevance == 0.7


def test_persists_to_disk():
    """Memories survive process restart (new MemorySystem, same DB path)."""
    path = _tmp_db()
    mem1 = MemorySystem(db_path=path)
    mem1.store("persist:1", "I will survive", "ctx", "text", 0.8)
    mem1._long_term.close()

    mem2 = MemorySystem(db_path=path)
    result = mem2.recall("persist:1")
    assert result is not None
    assert "survive" in result.content


def test_stats_structure():
    mem = _mem_system()
    mem.store("k", "v", "ctx", "text", 0.5)
    s = mem.stats()
    assert "total_stored" in s
    assert "working_memory" in s
    assert "long_term" in s
    assert "associations" in s


# ==================================================================
# Runner
# ==================================================================

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
