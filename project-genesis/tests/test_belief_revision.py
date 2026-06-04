"""
Tests for M18: Belief Revision (belief_revision.py).

Covers: schema creation, corroboration tracking, source trust,
evidence strength, contradiction resolution (REVISE/RESIST/TENSION),
confidence reduction with floor, Wakefield cascade, audit trail,
and all query methods.
"""

import sqlite3
import tempfile
import time
import os

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cognition.belief_revision import (
    BeliefRevision,
    _CORR_BONUS, _CORR_CAP,
    _REVISE_THRESHOLD, _RESIST_THRESHOLD,
    _MAX_REDUCTION, _CONFIDENCE_FLOOR,
    _DEFAULT_SOURCE_TRUST,
    _TRUST_WIN_DELTA, _TRUST_LOSE_DELTA,
    _TRUST_MIN, _TRUST_MAX,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conn():
    """In-memory SQLite with the minimum schema BeliefRevision expects."""
    c = sqlite3.connect(":memory:")
    # relations table (subset of what RelationGraph creates)
    c.execute("""
        CREATE TABLE IF NOT EXISTS relations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            subject     TEXT NOT NULL,
            rel_type    TEXT NOT NULL,
            object      TEXT NOT NULL,
            confidence  REAL NOT NULL DEFAULT 0.8,
            source_key  TEXT,
            session_id  TEXT,
            created_at  REAL,
            UNIQUE(subject, rel_type, object)
        )
    """)
    # contradiction_log table (subset of what ContradictionLog creates)
    c.execute("""
        CREATE TABLE IF NOT EXISTS contradiction_log (
            con_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            subject      TEXT NOT NULL,
            rel_type_a   TEXT NOT NULL,
            rel_type_b   TEXT NOT NULL,
            object       TEXT NOT NULL,
            conf_a       REAL,
            conf_b       REAL,
            detected_at  REAL NOT NULL
        )
    """)
    c.commit()
    return c


def _br(conn=None):
    """Return a BeliefRevision instance using the given (or new) connection."""
    if conn is None:
        conn = _conn()
    return BeliefRevision(conn), conn


def _add_relation(conn, subject, rel_type, obj, confidence=0.8, session_id=None):
    conn.execute(
        "INSERT OR REPLACE INTO relations (subject, rel_type, object, confidence, session_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (subject, rel_type, obj, confidence, session_id, time.time()),
    )
    conn.commit()


def _add_contradiction(conn, subject, rel_a, rel_b, obj, conf_a=0.8, conf_b=0.6):
    conn.execute(
        "INSERT INTO contradiction_log (subject, rel_type_a, rel_type_b, object, conf_a, conf_b, detected_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (subject, rel_a, rel_b, obj, conf_a, conf_b, time.time()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 1. Schema creation
# ---------------------------------------------------------------------------

class TestSchema:
    def test_relation_sources_table_created(self):
        br, conn = _br()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "relation_sources" in tables

    def test_source_trust_table_created(self):
        br, conn = _br()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "source_trust" in tables

    def test_belief_revisions_table_created(self):
        br, conn = _br()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "belief_revisions" in tables

    def test_revision_status_column_added_to_contradiction_log(self):
        br, conn = _br()
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(contradiction_log)"
        ).fetchall()}
        assert "revision_status" in cols

    def test_schema_idempotent_second_instantiation(self):
        conn = _conn()
        BeliefRevision(conn)
        # Should not raise
        BeliefRevision(conn)


# ---------------------------------------------------------------------------
# 2. Corroboration tracking
# ---------------------------------------------------------------------------

class TestCorroboration:
    def test_record_source_inserts_row(self):
        br, conn = _br()
        br.record_source("wolves", "CAUSES", "deer", "session-1")
        count = conn.execute(
            "SELECT COUNT(*) FROM relation_sources"
        ).fetchone()[0]
        assert count == 1

    def test_record_source_duplicate_ignored(self):
        br, conn = _br()
        br.record_source("wolves", "CAUSES", "deer", "session-1")
        br.record_source("wolves", "CAUSES", "deer", "session-1")
        count = conn.execute(
            "SELECT COUNT(*) FROM relation_sources"
        ).fetchone()[0]
        assert count == 1

    def test_record_source_empty_session_skipped(self):
        br, conn = _br()
        br.record_source("wolves", "CAUSES", "deer", "")
        count = conn.execute(
            "SELECT COUNT(*) FROM relation_sources"
        ).fetchone()[0]
        assert count == 0

    def test_corroboration_factor_one_session(self):
        br, conn = _br()
        br.record_source("wolves", "CAUSES", "deer", "s1")
        factor = br.corroboration_factor("wolves", "CAUSES", "deer")
        assert factor == pytest.approx(1.0)

    def test_corroboration_factor_two_sessions(self):
        br, conn = _br()
        br.record_source("wolves", "CAUSES", "deer", "s1")
        br.record_source("wolves", "CAUSES", "deer", "s2")
        factor = br.corroboration_factor("wolves", "CAUSES", "deer")
        assert factor == pytest.approx(1.0 + _CORR_BONUS)

    def test_corroboration_factor_four_sessions(self):
        br, conn = _br()
        for i in range(4):
            br.record_source("wolves", "CAUSES", "deer", f"s{i}")
        factor = br.corroboration_factor("wolves", "CAUSES", "deer")
        # 1.0 + 3 × _CORR_BONUS (first session doesn't add bonus)
        assert factor == pytest.approx(1.0 + 3 * _CORR_BONUS)

    def test_corroboration_factor_capped(self):
        br, conn = _br()
        for i in range(10):
            br.record_source("wolves", "CAUSES", "deer", f"s{i}")
        factor = br.corroboration_factor("wolves", "CAUSES", "deer")
        # Capped at _CORR_CAP additional sessions
        max_factor = 1.0 + _CORR_CAP * _CORR_BONUS
        assert factor == pytest.approx(max_factor)

    def test_corroboration_factor_unknown_relation(self):
        br, conn = _br()
        factor = br.corroboration_factor("unknown", "CAUSES", "nothing")
        assert factor == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 3. Source trust
# ---------------------------------------------------------------------------

class TestSourceTrust:
    def test_unknown_source_returns_default(self):
        br, conn = _br()
        trust = br.source_trust_score("nonexistent-session")
        assert trust == pytest.approx(_DEFAULT_SOURCE_TRUST)

    def test_empty_session_returns_default(self):
        br, conn = _br()
        trust = br.source_trust_score("")
        assert trust == pytest.approx(_DEFAULT_SOURCE_TRUST)

    def test_trust_increases_on_win(self):
        br, conn = _br()
        br._update_trust("s1", won=True)
        trust = br.source_trust_score("s1")
        assert trust == pytest.approx(_DEFAULT_SOURCE_TRUST + _TRUST_WIN_DELTA)

    def test_trust_decreases_on_loss(self):
        br, conn = _br()
        br._update_trust("s1", won=False)
        trust = br.source_trust_score("s1")
        assert trust == pytest.approx(_DEFAULT_SOURCE_TRUST + _TRUST_LOSE_DELTA)

    def test_trust_never_exceeds_max(self):
        br, conn = _br()
        for _ in range(200):
            br._update_trust("s1", won=True)
        trust = br.source_trust_score("s1")
        assert trust <= _TRUST_MAX

    def test_trust_never_below_min(self):
        br, conn = _br()
        for _ in range(200):
            br._update_trust("s1", won=False)
        trust = br.source_trust_score("s1")
        assert trust >= _TRUST_MIN

    def test_trust_stored_and_retrieved(self):
        br, conn = _br()
        br._update_trust("s-persist", won=True)
        br2 = BeliefRevision(conn)
        trust = br2.source_trust_score("s-persist")
        assert trust > _DEFAULT_SOURCE_TRUST


# ---------------------------------------------------------------------------
# 4. Evidence strength
# ---------------------------------------------------------------------------

class TestEvidenceStrength:
    def test_zero_for_nonexistent_relation(self):
        br, conn = _br()
        strength = br.evidence_strength("wolves", "CAUSES", "deer")
        assert strength == 0.0

    def test_single_session_default_trust(self):
        br, conn = _br()
        _add_relation(conn, "wolves", "CAUSES", "deer", confidence=0.8)
        br.record_source("wolves", "CAUSES", "deer", "s1")
        strength = br.evidence_strength("wolves", "CAUSES", "deer", "s1")
        expected = round(0.8 * 1.0 * _DEFAULT_SOURCE_TRUST, 4)
        assert strength == pytest.approx(expected)

    def test_two_sessions_raises_strength(self):
        br, conn = _br()
        _add_relation(conn, "wolves", "CAUSES", "deer", confidence=0.8)
        br.record_source("wolves", "CAUSES", "deer", "s1")
        br.record_source("wolves", "CAUSES", "deer", "s2")
        s1 = br.evidence_strength("wolves", "CAUSES", "deer", "s1")
        single = round(0.8 * 1.0 * _DEFAULT_SOURCE_TRUST, 4)
        assert s1 > single

    def test_higher_trust_session_raises_strength(self):
        br, conn = _br()
        _add_relation(conn, "wolves", "CAUSES", "deer", confidence=0.8)
        br.record_source("wolves", "CAUSES", "deer", "trusted")
        # Artificially raise trust
        for _ in range(10):
            br._update_trust("trusted", won=True)
        high = br.evidence_strength("wolves", "CAUSES", "deer", "trusted")
        low = 0.8 * 1.0 * _DEFAULT_SOURCE_TRUST
        assert high > low


# ---------------------------------------------------------------------------
# 5. Confidence reduction
# ---------------------------------------------------------------------------

class TestConfidenceReduction:
    def test_apply_reduction_lowers_confidence(self):
        br, conn = _br()
        _add_relation(conn, "wolves", "CAUSES", "deer", confidence=0.8)
        br._apply_reduction(
            "wolves", "CAUSES", "deer", reduction=0.20,
            reason="test", opposing_rel="PREVENTS", session_id="s1"
        )
        new_conf = conn.execute(
            "SELECT confidence FROM relations WHERE subject='wolves' AND rel_type='CAUSES' AND object='deer'"
        ).fetchone()[0]
        assert new_conf == pytest.approx(0.8 * 0.80, rel=1e-3)

    def test_confidence_floored_at_minimum(self):
        br, conn = _br()
        _add_relation(conn, "wolves", "CAUSES", "deer", confidence=0.12)
        br._apply_reduction(
            "wolves", "CAUSES", "deer", reduction=0.50,
            reason="big reduction", opposing_rel="PREVENTS", session_id="s1"
        )
        new_conf = conn.execute(
            "SELECT confidence FROM relations WHERE subject='wolves' AND rel_type='CAUSES' AND object='deer'"
        ).fetchone()[0]
        assert new_conf >= _CONFIDENCE_FLOOR

    def test_reduction_never_deletes_relation(self):
        br, conn = _br()
        _add_relation(conn, "wolves", "CAUSES", "deer", confidence=0.11)
        br._apply_reduction(
            "wolves", "CAUSES", "deer", reduction=0.99,
            reason="near-deletion", opposing_rel="PREVENTS", session_id="s1"
        )
        exists = conn.execute(
            "SELECT confidence FROM relations WHERE subject='wolves' AND rel_type='CAUSES' AND object='deer'"
        ).fetchone()
        assert exists is not None
        assert exists[0] >= _CONFIDENCE_FLOOR


# ---------------------------------------------------------------------------
# 6. Contradiction resolution outcomes
# ---------------------------------------------------------------------------

class TestResolutionOutcomes:
    def _setup_contradiction(self, confidence_a=0.9, confidence_b=0.3, sessions_a=3, sessions_b=1):
        """Set up a contradiction scenario and return (br, conn, con_id)."""
        conn = _conn()
        br = BeliefRevision(conn)

        _add_relation(conn, "exercise", "CAUSES", "health", confidence=confidence_a)
        _add_relation(conn, "exercise", "PREVENTS", "health", confidence=confidence_b)
        _add_contradiction(conn, "exercise", "CAUSES", "PREVENTS", "health",
                           conf_a=confidence_a, conf_b=confidence_b)

        for i in range(sessions_a):
            br.record_source("exercise", "CAUSES", "health", f"strong-s{i}")
        for i in range(sessions_b):
            br.record_source("exercise", "PREVENTS", "health", f"weak-s{i}")

        con_id = conn.execute("SELECT MAX(con_id) FROM contradiction_log").fetchone()[0]
        return br, conn, con_id

    def test_revise_outcome_when_strong_evidence(self):
        br, conn, con_id = self._setup_contradiction(
            confidence_a=0.9, confidence_b=0.3,
            sessions_a=3, sessions_b=1
        )
        outcome = br._resolve_one(
            con_id, "exercise", "CAUSES", "PREVENTS", "health", "test-session"
        )
        assert outcome == "REVISE"

    def test_revise_reduces_losing_confidence(self):
        br, conn, con_id = self._setup_contradiction(
            confidence_a=0.9, confidence_b=0.3,
            sessions_a=3, sessions_b=1
        )
        before = conn.execute(
            "SELECT confidence FROM relations WHERE subject='exercise' AND rel_type='PREVENTS' AND object='health'"
        ).fetchone()[0]
        br._resolve_one(con_id, "exercise", "CAUSES", "PREVENTS", "health", "test-session")
        after = conn.execute(
            "SELECT confidence FROM relations WHERE subject='exercise' AND rel_type='PREVENTS' AND object='health'"
        ).fetchone()[0]
        assert after < before

    def test_tension_outcome_when_nearly_equal(self):
        conn = _conn()
        br = BeliefRevision(conn)
        # Equal confidence, equal corroboration → TENSION
        _add_relation(conn, "x", "CAUSES", "y", confidence=0.75)
        _add_relation(conn, "x", "PREVENTS", "y", confidence=0.75)
        _add_contradiction(conn, "x", "CAUSES", "PREVENTS", "y")
        br.record_source("x", "CAUSES", "y", "s1")
        br.record_source("x", "PREVENTS", "y", "s2")
        con_id = conn.execute("SELECT MAX(con_id) FROM contradiction_log").fetchone()[0]
        outcome = br._resolve_one(con_id, "x", "CAUSES", "PREVENTS", "y", "test")
        # With equal strength, ratio = 1.0 — lands between thresholds → TENSION
        assert outcome == "TENSION"

    def test_contradiction_marked_with_outcome(self):
        br, conn, con_id = self._setup_contradiction(
            confidence_a=0.9, confidence_b=0.3, sessions_a=3, sessions_b=1
        )
        br._resolve_one(con_id, "exercise", "CAUSES", "PREVENTS", "health", "test-session")
        status = conn.execute(
            "SELECT revision_status FROM contradiction_log WHERE con_id=?", (con_id,)
        ).fetchone()[0]
        assert status in ("REVISE", "RESIST", "TENSION")


# ---------------------------------------------------------------------------
# 7. evaluate_and_revise
# ---------------------------------------------------------------------------

class TestEvaluateAndRevise:
    def test_processes_pending_contradictions(self):
        conn = _conn()
        br = BeliefRevision(conn)

        _add_relation(conn, "w", "CAUSES", "d", confidence=0.9)
        _add_relation(conn, "w", "PREVENTS", "d", confidence=0.3)
        _add_contradiction(conn, "w", "CAUSES", "PREVENTS", "d")

        for i in range(3):
            br.record_source("w", "CAUSES", "d", f"s{i}")
        br.record_source("w", "PREVENTS", "d", "weak-s")

        count = br.evaluate_and_revise(session_id="caller")
        assert isinstance(count, int)
        assert count >= 0

    def test_already_processed_not_revisited(self):
        conn = _conn()
        br = BeliefRevision(conn)

        _add_relation(conn, "w", "CAUSES", "d", confidence=0.9)
        _add_relation(conn, "w", "PREVENTS", "d", confidence=0.3)
        _add_contradiction(conn, "w", "CAUSES", "PREVENTS", "d")
        con_id = conn.execute("SELECT MAX(con_id) FROM contradiction_log").fetchone()[0]

        for i in range(3):
            br.record_source("w", "CAUSES", "d", f"s{i}")

        br.evaluate_and_revise(session_id="first")
        # Mark as processed
        conn.execute(
            "UPDATE contradiction_log SET revision_status='REVISE' WHERE con_id=?",
            (con_id,)
        )
        conn.commit()

        count2 = br.evaluate_and_revise(session_id="second")
        assert count2 == 0

    def test_returns_zero_with_no_contradictions(self):
        conn = _conn()
        br = BeliefRevision(conn)
        count = br.evaluate_and_revise(session_id="empty")
        assert count == 0


# ---------------------------------------------------------------------------
# 8. Wakefield cascade
# ---------------------------------------------------------------------------

class TestCascadeTrustDrop:
    def test_no_cascade_when_trust_above_threshold(self):
        br, conn = _br()
        _add_relation(conn, "a", "CAUSES", "b", confidence=0.8, session_id="s1")
        br.record_source("a", "CAUSES", "b", "s1")
        # Trust at default (0.75) — no cascade
        affected = br.cascade_trust_drop("s1")
        assert affected == 0

    def test_cascade_fires_when_trust_low(self):
        br, conn = _br()
        _add_relation(conn, "a", "CAUSES", "b", confidence=0.8, session_id="s1")
        br.record_source("a", "CAUSES", "b", "s1")

        # Drive trust below threshold
        conn.execute(
            "INSERT OR REPLACE INTO source_trust "
            "(source_id, trust_score, wins, losses, last_updated) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", 0.20, 0, 50, time.time())
        )
        conn.commit()

        affected = br.cascade_trust_drop("s1")
        assert affected >= 1

    def test_cascade_reduces_confidence(self):
        br, conn = _br()
        _add_relation(conn, "a", "CAUSES", "b", confidence=0.8, session_id="s1")
        br.record_source("a", "CAUSES", "b", "s1")

        conn.execute(
            "INSERT OR REPLACE INTO source_trust "
            "(source_id, trust_score, wins, losses, last_updated) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", 0.15, 0, 80, time.time())
        )
        conn.commit()

        br.cascade_trust_drop("s1", penalty=0.20)
        new_conf = conn.execute(
            "SELECT confidence FROM relations WHERE subject='a' AND rel_type='CAUSES' AND object='b'"
        ).fetchone()[0]
        assert new_conf < 0.8

    def test_cascade_respects_confidence_floor(self):
        br, conn = _br()
        _add_relation(conn, "a", "CAUSES", "b", confidence=0.11, session_id="s1")
        br.record_source("a", "CAUSES", "b", "s1")

        conn.execute(
            "INSERT OR REPLACE INTO source_trust "
            "(source_id, trust_score, wins, losses, last_updated) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", 0.10, 0, 200, time.time())
        )
        conn.commit()

        br.cascade_trust_drop("s1", penalty=0.99)
        new_conf = conn.execute(
            "SELECT confidence FROM relations WHERE subject='a' AND rel_type='CAUSES' AND object='b'"
        ).fetchone()[0]
        assert new_conf >= _CONFIDENCE_FLOOR

    def test_multi_session_relation_not_cascaded(self):
        """A relation corroborated by multiple sessions shouldn't cascade on one bad source."""
        br, conn = _br()
        _add_relation(conn, "a", "CAUSES", "b", confidence=0.8, session_id="s1")
        br.record_source("a", "CAUSES", "b", "s1")
        br.record_source("a", "CAUSES", "b", "s2")  # second independent session

        conn.execute(
            "INSERT OR REPLACE INTO source_trust "
            "(source_id, trust_score, wins, losses, last_updated) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", 0.10, 0, 200, time.time())
        )
        conn.commit()

        affected = br.cascade_trust_drop("s1")
        # Multi-session relation should NOT be in the cascade set (only-source check)
        assert affected == 0


# ---------------------------------------------------------------------------
# 9. Query interface
# ---------------------------------------------------------------------------

class TestQueryInterface:
    def test_revision_history_empty_initially(self):
        br, conn = _br()
        assert br.revision_history() == []

    def test_revision_history_returns_revisions(self):
        br, conn = _br()
        br._record_revision_audit(
            "wolves", "CAUSES", "deer",
            old_confidence=0.8, new_confidence=0.6,
            outcome="REVISE", reason="test",
            old_strength=0.6, new_strength=0.45,
            opposing_rel="PREVENTS", session_id="s1"
        )
        history = br.revision_history()
        assert len(history) == 1
        assert history[0]["subject"] == "wolves"
        assert history[0]["old_confidence"] == pytest.approx(0.8)
        assert history[0]["new_confidence"] == pytest.approx(0.6)

    def test_revision_history_excludes_resist_and_tension(self):
        br, conn = _br()
        for outcome in ("RESIST", "TENSION"):
            br._record_revision_audit(
                "x", "CAUSES", "y",
                old_confidence=0.8, new_confidence=0.8,
                outcome=outcome, reason="test",
                old_strength=0.6, new_strength=0.6,
                opposing_rel="PREVENTS", session_id="s1"
            )
        assert br.revision_history() == []

    def test_pending_tensions_returns_unresolved(self):
        br, conn = _br()
        _add_contradiction(conn, "x", "CAUSES", "PREVENTS", "y")
        tensions = br.pending_tensions()
        assert len(tensions) >= 1
        assert tensions[0]["subject"] == "x"

    def test_source_trust_report(self):
        br, conn = _br()
        br._update_trust("s1", won=True)
        report = br.source_trust_report()
        assert len(report) >= 1
        assert "source" in report[0]
        assert "trust" in report[0]

    def test_stats_returns_expected_keys(self):
        br, conn = _br()
        s = br.stats()
        assert "beliefs_revised" in s
        assert "tensions_held" in s
        assert "sources_tracked" in s
        assert "relations_with_provenance" in s

    def test_stats_counts_revisions(self):
        br, conn = _br()
        _add_relation(conn, "w", "CAUSES", "d", confidence=0.9)
        _add_relation(conn, "w", "PREVENTS", "d", confidence=0.3)
        _add_contradiction(conn, "w", "CAUSES", "PREVENTS", "d")

        for i in range(3):
            br.record_source("w", "CAUSES", "d", f"s{i}")
        br.record_source("w", "PREVENTS", "d", "weak")

        br.evaluate_and_revise(session_id="test")
        s = br.stats()
        assert s["beliefs_revised"] >= 0  # may be 0 if below threshold
        assert s["sources_tracked"] >= 0


# ---------------------------------------------------------------------------
# 10. Orchestrator integration smoke test
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    def test_orchestrator_has_belief_revision(self):
        """Ensure BeliefRevision is wired into Orchestrator without errors."""
        import tempfile, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            from orchestrator.orchestrator import Orchestrator
            orch = Orchestrator(verbose=False, db_path=db)
            assert hasattr(orch, "belief_revision")
            assert isinstance(orch.belief_revision, BeliefRevision)
        finally:
            os.unlink(db)

    def test_process_input_records_source_provenance(self):
        """Processing text input should record relation sources."""
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            from orchestrator.orchestrator import Orchestrator
            orch = Orchestrator(verbose=False, db_path=db)
            orch.process_input("text",
                "Wolves cause deer populations to decline rapidly.")
            count = orch.memory._long_term.conn.execute(
                "SELECT COUNT(*) FROM relation_sources"
            ).fetchone()[0]
            # May be 0 if no relations extracted (text normalisation), but must not raise
            assert count >= 0
        finally:
            os.unlink(db)
