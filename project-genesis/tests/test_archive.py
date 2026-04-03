"""Tests for ArchiveStore — tagging, querying, and snapshots."""

import sys, os, sqlite3, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory.archive import ArchiveStore


def _store() -> ArchiveStore:
    """Fresh in-memory ArchiveStore for each test."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return ArchiveStore(conn)


# ==================================================================
# Tagging
# ==================================================================

def test_tag_stores_entry():
    a = _store()
    a.tag("key:wolf", 0.8, "sess1", source_type="text")
    results = a.query()
    assert len(results) == 1
    assert results[0]["key"] == "key:wolf"


def test_tag_auto_tags_from_source_type():
    a = _store()
    a.tag("key:a", 0.5, "sess1", source_type="text")
    r = a.query()[0]
    assert "language" in r["domain_tags"]
    assert "symbolic" in r["domain_tags"]


def test_tag_auto_tags_numeric():
    a = _store()
    a.tag("numeric:x", 0.5, "sess1", source_type="numeric")
    r = a.query()[0]
    assert "quantitative" in r["domain_tags"]


def test_tag_auto_tags_pattern():
    a = _store()
    a.tag("pattern:x", 0.5, "sess1", source_type="pattern")
    r = a.query()[0]
    assert "structural" in r["domain_tags"]


def test_tag_manual_domain_tags():
    a = _store()
    a.tag("key:z", 0.6, "sess1", domain_tags=["ecology", "wolves"])
    r = a.query()[0]
    assert "ecology" in r["domain_tags"]
    assert "wolves" in r["domain_tags"]


def test_tag_retag_merges_tags():
    a = _store()
    a.tag("key:x", 0.5, "sess1", domain_tags=["alpha"])
    a.tag("key:x", 0.5, "sess1", domain_tags=["beta"])
    r = a.query()[0]
    assert "alpha" in r["domain_tags"]
    assert "beta" in r["domain_tags"]


def test_tag_retag_takes_higher_significance():
    a = _store()
    a.tag("key:x", 0.3, "sess1")
    a.tag("key:x", 0.9, "sess1")
    r = a.query()[0]
    assert r["significance"] >= 0.9


def test_tag_retag_does_not_lower_significance():
    a = _store()
    a.tag("key:x", 0.9, "sess1")
    a.tag("key:x", 0.1, "sess1")  # lower — should not override
    r = a.query()[0]
    assert r["significance"] >= 0.9


def test_tag_significance_clamped():
    a = _store()
    a.tag("key:x", 2.5, "sess1")   # above 1.0
    r = a.query()[0]
    assert r["significance"] <= 1.0
    a.tag("key:y", -0.5, "sess1")  # below 0.0
    results = a.query()
    y = next(r for r in results if r["key"] == "key:y")
    assert y["significance"] >= 0.0


# ==================================================================
# Query filtering
# ==================================================================

def test_query_min_significance_filter():
    a = _store()
    a.tag("key:low",  0.2, "sess1")
    a.tag("key:high", 0.8, "sess1")
    results = a.query(min_significance=0.5)
    keys = [r["key"] for r in results]
    assert "key:high" in keys
    assert "key:low" not in keys


def test_query_domain_filter():
    a = _store()
    a.tag("key:wolf",  0.7, "sess1", domain_tags=["ecology"])
    a.tag("key:prime", 0.7, "sess1", domain_tags=["math"])
    ecology_results = a.query(domain="ecology")
    assert all("ecology" in r["domain_tags"] for r in ecology_results)
    assert not any(r["key"] == "key:prime" for r in ecology_results)


def test_query_session_filter():
    a = _store()
    a.tag("key:a", 0.5, "sess_A")
    a.tag("key:b", 0.5, "sess_B")
    results = a.query(session_id="sess_A")
    assert all(r["session_id"] == "sess_A" for r in results)


def test_query_since_filter():
    a = _store()
    past = time.time() - 10
    a.tag("key:old", 0.5, "sess1")
    future_ts = time.time() + 1
    a.tag("key:new", 0.5, "sess1")
    results = a.query(since_ts=future_ts)
    # Only key:new was tagged after future_ts
    assert not any(r["key"] == "key:old" for r in results)


def test_query_limit_respected():
    a = _store()
    for i in range(20):
        a.tag(f"key:{i}", 0.5, "sess1")
    results = a.query(limit=5)
    assert len(results) <= 5


def test_query_returns_all_by_default():
    a = _store()
    for i in range(10):
        a.tag(f"key:{i}", 0.5, "sess1")
    results = a.query()
    assert len(results) == 10


def test_query_ordered_by_significance_desc():
    a = _store()
    a.tag("key:low",  0.3, "sess1")
    a.tag("key:high", 0.9, "sess1")
    a.tag("key:mid",  0.6, "sess1")
    results = a.query()
    sigs = [r["significance"] for r in results]
    assert sigs == sorted(sigs, reverse=True)


# ==================================================================
# Snapshots
# ==================================================================

def test_snapshot_returns_id():
    a = _store()
    snap_id = a.snapshot("test", ["key:a", "key:b"], "sess1")
    assert isinstance(snap_id, int)
    assert snap_id > 0


def test_snapshot_retrievable():
    a = _store()
    snap_id = a.snapshot("checkpoint-1", ["key:a", "key:b", "key:c"], "sess1")
    snap = a.retrieve_snapshot(snap_id)
    assert snap is not None
    assert snap["label"] == "checkpoint-1"
    assert snap["memory_keys"] == ["key:a", "key:b", "key:c"]


def test_snapshot_nonexistent_returns_none():
    a = _store()
    result = a.retrieve_snapshot(9999)
    assert result is None


def test_list_snapshots_ordered_newest_first():
    a = _store()
    a.snapshot("first",  ["key:a"], "sess1")
    a.snapshot("second", ["key:b"], "sess1")
    snaps = a.list_snapshots()
    assert snaps[0]["label"] == "second"
    assert snaps[1]["label"] == "first"


def test_list_snapshots_includes_key_count():
    a = _store()
    a.snapshot("snap", ["k1", "k2", "k3"], "sess1")
    snap = a.list_snapshots()[0]
    assert snap["key_count"] == 3


def test_multiple_snapshots_independent():
    a = _store()
    id1 = a.snapshot("snap1", ["key:a"], "sess1")
    id2 = a.snapshot("snap2", ["key:b", "key:c"], "sess1")
    s1 = a.retrieve_snapshot(id1)
    s2 = a.retrieve_snapshot(id2)
    assert s1["memory_keys"] == ["key:a"]
    assert s2["memory_keys"] == ["key:b", "key:c"]


# ==================================================================
# Stats
# ==================================================================

def test_stats_empty():
    a = _store()
    s = a.stats()
    assert s["total_tagged"] == 0
    assert s["total_snapshots"] == 0


def test_stats_after_tagging():
    a = _store()
    a.tag("key:x", 0.8, "sess1")
    a.tag("key:y", 0.4, "sess1")
    s = a.stats()
    assert s["total_tagged"] == 2


def test_stats_after_snapshot():
    a = _store()
    a.snapshot("snap", ["key:x"], "sess1")
    s = a.stats()
    assert s["total_snapshots"] == 1


def test_stats_avg_significance():
    a = _store()
    a.tag("key:x", 0.6, "sess1")
    a.tag("key:y", 0.8, "sess1")
    s = a.stats()
    assert abs(s["avg_significance"] - 0.7) < 0.01


# ==================================================================
# Runner
# ==================================================================

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
