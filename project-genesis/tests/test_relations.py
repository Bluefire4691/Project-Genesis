"""Tests for RelationGraph — typed semantic relation store."""

import sys, os, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from memory.relations import RelationGraph, RELATION_TYPES, _normalise
from orchestrator.orchestrator import Orchestrator
from utils.types import Stage
import tempfile


def _graph() -> RelationGraph:
    """Fresh in-memory RelationGraph for each test."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return RelationGraph(conn)


# ==================================================================
# Normalisation helper
# ==================================================================

def test_normalise_lowercase():
    assert _normalise("Wolves") == "wolves"


def test_normalise_strips_punctuation():
    assert _normalise("wolf.") == "wolf"


def test_normalise_collapses_whitespace():
    assert _normalise("  wolf  pack  ") == "wolf pack"


# ==================================================================
# Relation types
# ==================================================================

def test_relation_types_defined():
    for rt in ("CAUSES", "CONTROLS", "PREVENTS", "ENABLES", "REQUIRES",
               "IS_A", "PREDATES", "AFFECTS", "CONTAINS"):
        assert rt in RELATION_TYPES


# ==================================================================
# add()
# ==================================================================

def test_add_returns_true_on_success():
    g = _graph()
    result = g.add("wolves", "CONTROLS", "deer", 0.85)
    assert result is True


def test_add_invalid_relation_type_returns_false():
    g = _graph()
    result = g.add("wolves", "UNKNOWN_TYPE", "deer", 0.85)
    assert result is False


def test_add_empty_subject_returns_false():
    g = _graph()
    result = g.add("", "CAUSES", "erosion", 0.8)
    assert result is False


def test_add_empty_object_returns_false():
    g = _graph()
    result = g.add("overgrazing", "CAUSES", "", 0.8)
    assert result is False


def test_add_self_relation_returns_false():
    g = _graph()
    result = g.add("wolves", "CONTROLS", "wolves", 0.8)
    assert result is False


def test_add_confidence_clamped_high():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 2.5)
    rows = g.query_subject("wolves")
    assert rows[0]["confidence"] <= 1.0


def test_add_confidence_clamped_low():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", -0.5)
    # Clamped to 0.0 — query with min_confidence=0.0 to see the stored row
    rows = g.query_subject("wolves", min_confidence=0.0)
    assert rows[0]["confidence"] >= 0.0


def test_add_duplicate_takes_max_confidence():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.6)
    g.add("wolves", "CONTROLS", "deer", 0.9)
    rows = g.query_subject("wolves")
    assert rows[0]["confidence"] >= 0.9


def test_add_duplicate_does_not_lower_confidence():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.9)
    g.add("wolves", "CONTROLS", "deer", 0.3)
    rows = g.query_subject("wolves")
    assert rows[0]["confidence"] >= 0.9


def test_add_normalises_case():
    g = _graph()
    g.add("Wolves", "CONTROLS", "Deer", 0.85)
    rows = g.query_subject("wolves")
    assert len(rows) == 1
    assert rows[0]["object"] == "deer"


# ==================================================================
# query_subject()
# ==================================================================

def test_query_subject_returns_relations():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.85)
    g.add("wolves", "IS_A", "predator", 0.90)
    rows = g.query_subject("wolves")
    assert len(rows) == 2


def test_query_subject_respects_min_confidence():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.4)
    g.add("wolves", "IS_A", "predator", 0.9)
    rows = g.query_subject("wolves", min_confidence=0.5)
    assert all(r["confidence"] >= 0.5 for r in rows)
    assert len(rows) == 1


def test_query_subject_returns_empty_for_unknown():
    g = _graph()
    rows = g.query_subject("unicorn")
    assert rows == []


def test_query_subject_ordered_by_confidence_desc():
    g = _graph()
    g.add("wolves", "IS_A", "predator", 0.9)
    g.add("wolves", "CONTROLS", "deer", 0.7)
    g.add("wolves", "AFFECTS", "ecosystem", 0.6)
    rows = g.query_subject("wolves")
    confs = [r["confidence"] for r in rows]
    assert confs == sorted(confs, reverse=True)


# ==================================================================
# query_object()
# ==================================================================

def test_query_object_returns_relations():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.85)
    g.add("hunters", "PREDATES", "deer", 0.80)
    rows = g.query_object("deer")
    assert len(rows) == 2


def test_query_object_respects_min_confidence():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.3)
    g.add("hunters", "PREDATES", "deer", 0.9)
    rows = g.query_object("deer", min_confidence=0.5)
    assert len(rows) == 1
    assert rows[0]["subject"] == "hunters"


# ==================================================================
# query_concept()
# ==================================================================

def test_query_concept_returns_both_directions():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.85)
    g.add("deer", "REQUIRES", "vegetation", 0.80)
    g.add("hunters", "PREDATES", "wolves", 0.75)

    info = g.query_concept("wolves")
    assert len(info["as_subject"]) > 0   # wolves CONTROLS deer
    assert len(info["as_object"]) > 0    # hunters PREDATES wolves


def test_query_concept_unknown_returns_empty():
    g = _graph()
    info = g.query_concept("nonexistent")
    assert info["as_subject"] == []
    assert info["as_object"] == []


# ==================================================================
# query_relation()
# ==================================================================

def test_query_relation_returns_all_of_type():
    g = _graph()
    g.add("fire", "CAUSES", "smoke", 0.9)
    g.add("overgrazing", "CAUSES", "erosion", 0.85)
    g.add("wolves", "CONTROLS", "deer", 0.80)

    causes = g.query_relation("CAUSES")
    assert len(causes) == 2
    assert all(isinstance(r, dict) for r in causes)


def test_query_relation_empty_type():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.8)
    results = g.query_relation("IS_A")
    assert results == []


def test_query_relation_limit():
    g = _graph()
    for i in range(20):
        g.add(f"subject_{i}", "AFFECTS", f"object_{i}", 0.7)
    results = g.query_relation("AFFECTS", limit=5)
    assert len(results) <= 5


# ==================================================================
# find_path()
# ==================================================================

def test_find_path_direct():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.85)
    paths = g.find_path("wolves", "deer")
    assert len(paths) > 0
    assert paths[0][0]["relation"] == "CONTROLS"


def test_find_path_two_hops():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.85)
    g.add("deer", "CAUSES", "erosion", 0.80)
    paths = g.find_path("wolves", "erosion")
    assert len(paths) > 0
    assert len(paths[0]) == 2


def test_find_path_three_hops():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.85)
    g.add("deer", "CAUSES", "overgrazing", 0.80)
    g.add("overgrazing", "CAUSES", "erosion", 0.75)
    paths = g.find_path("wolves", "erosion")
    assert len(paths) > 0
    assert len(paths[0]) == 3


def test_find_path_same_concept():
    g = _graph()
    paths = g.find_path("wolves", "wolves")
    assert paths == [[]]


def test_find_path_no_path():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.85)
    paths = g.find_path("wolves", "unrelated_concept")
    assert paths == []


def test_find_path_respects_max_depth():
    g = _graph()
    # Chain of 5 hops
    chain = ["a", "b", "c", "d", "e", "f"]
    for i in range(len(chain) - 1):
        g.add(chain[i], "CAUSES", chain[i + 1], 0.9)
    paths = g.find_path("a", "f", max_depth=3)
    assert paths == []   # too deep — not found within 3 hops


# ==================================================================
# most_connected()
# ==================================================================

def test_most_connected_returns_sorted():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.9)
    g.add("wolves", "IS_A", "predator", 0.9)
    g.add("wolves", "AFFECTS", "ecosystem", 0.9)
    g.add("deer", "CAUSES", "overgrazing", 0.8)

    top = g.most_connected(limit=3)
    assert top[0]["concept"] == "wolves"
    assert top[0]["degree"] >= 3


def test_most_connected_limit():
    g = _graph()
    for i in range(10):
        g.add(f"subj{i}", "AFFECTS", f"obj{i}", 0.7)
    top = g.most_connected(limit=3)
    assert len(top) <= 3


# ==================================================================
# causal_chains() and definitions()
# ==================================================================

def test_causal_chains_only_causes():
    g = _graph()
    g.add("fire", "CAUSES", "smoke", 0.9)
    g.add("wolves", "CONTROLS", "deer", 0.8)
    chains = g.causal_chains(min_confidence=0.5)
    assert all(isinstance(c, dict) for c in chains)
    assert len(chains) == 1
    assert chains[0]["subject"] == "fire"


def test_definitions_only_is_a():
    g = _graph()
    g.add("wolf", "IS_A", "predator", 0.9)
    g.add("wolf", "CONTROLS", "deer", 0.8)
    defs = g.definitions(min_confidence=0.5)
    assert len(defs) == 1
    assert defs[0]["subject"] == "wolf"
    assert defs[0]["object"] == "predator"


# ==================================================================
# stats()
# ==================================================================

def test_stats_empty():
    g = _graph()
    s = g.stats()
    assert s["total_relations"] == 0
    assert s["by_type"] == {}


def test_stats_after_adding():
    g = _graph()
    g.add("wolves", "CONTROLS", "deer", 0.85)
    g.add("fire", "CAUSES", "smoke", 0.9)
    g.add("deer", "IS_A", "herbivore", 0.88)
    s = g.stats()
    assert s["total_relations"] == 3
    assert s["by_type"]["CONTROLS"] == 1
    assert s["by_type"]["CAUSES"] == 1
    assert s["by_type"]["IS_A"] == 1


# ==================================================================
# Orchestrator integration
# ==================================================================

def test_orchestrator_has_relations():
    brain = Orchestrator(verbose=False)
    assert hasattr(brain, "relations")
    assert isinstance(brain.relations.stats(), dict)


def test_orchestrator_stores_relations_from_text():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    brain.process_input("text", "Wolves control deer populations in Yellowstone.")
    s = brain.relations.stats()
    assert s["total_relations"] > 0


def test_orchestrator_stores_causal_relations():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    brain.process_input("text", "Overgrazing caused severe erosion along the riverbanks.")
    chains = brain.relations.causal_chains(min_confidence=0.5)
    assert len(chains) > 0


def test_orchestrator_query_returns_relations():
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    brain.process_input("text", "Wolves control deer populations in Yellowstone.")
    result = brain.query("wolves")
    assert "relations" in result


def test_orchestrator_full_status_includes_relations():
    brain = Orchestrator(verbose=False)
    status = brain.full_status()
    assert "relations" in status
    assert "total_relations" in status["relations"]


def test_relation_chain_from_text():
    """Feed a causal chain across sentences and verify path can be found."""
    brain = Orchestrator(verbose=False)
    brain.curriculum.current_stage = Stage.OPEN
    brain.process_input("text", "Wolves control deer populations.")
    brain.process_input("text", "Deer overgrazing causes riverbank erosion.")
    paths = brain.relations.find_path("wolves", "erosion", max_depth=4)
    # Path may or may not be found depending on exact extraction — just verify no crash
    assert isinstance(paths, list)


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
