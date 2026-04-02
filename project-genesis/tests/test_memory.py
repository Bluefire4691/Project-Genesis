"""Tests for total-retention memory system."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory.memory import MemorySystem


def test_store_and_recall():
    mem = MemorySystem()
    mem.store("test:1", "dogs are animals", "basic fact", "text", 0.5)
    result = mem.recall("test:1")
    assert result is not None
    assert "dogs" in result.content


def test_total_retention():
    """Nothing should ever be lost."""
    mem = MemorySystem()
    for i in range(100):
        mem.store(f"item:{i}", f"content {i}", f"context {i}", "text", 0.1)
    assert len(mem.memories) == 100  # All 100 should be there


def test_search():
    mem = MemorySystem()
    mem.store("animal:dog", "dogs are loyal animals", "animal fact", "text", 0.5)
    mem.store("food:apple", "apples are fruits", "food fact", "text", 0.5)
    results = mem.search("dog animal")
    assert len(results) > 0
    assert results[0][0] == "animal:dog"


def test_attention_update():
    mem = MemorySystem()
    mem.store("animal:dog", "dogs are animals", "fact", "text", 0.5)
    mem.store("food:apple", "apples are fruits", "fact", "text", 0.5)
    # Focus attention on animals
    mem.update_attention(["animal", "dog"])
    dog_mem = mem.memories["animal:dog"]
    apple_mem = mem.memories["food:apple"]
    assert dog_mem.relevance > apple_mem.relevance


def test_associations():
    mem = MemorySystem()
    mem.store("a", "first", "ctx", "text", 0.5, associations=["b"])
    mem.store("b", "second", "ctx", "text", 0.5, associations=["c"])
    mem.store("c", "third", "ctx", "text", 0.5)
    assocs = mem.get_associations("a", depth=2)
    keys = [k for k, _ in assocs]
    assert "b" in keys
    assert "c" in keys


def test_merge_on_duplicate_key():
    mem = MemorySystem()
    mem.store("test:1", "first version", "ctx1", "text", 0.3)
    mem.store("test:1", "second version", "ctx2", "text", 0.7)
    result = mem.recall("test:1")
    assert "first version" in result.content
    assert "second version" in result.content
    assert result.relevance == 0.7  # Takes the higher relevance


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
