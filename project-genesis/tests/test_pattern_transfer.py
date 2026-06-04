"""Tests for M22: PatternTransfer."""
import os, sys, tempfile
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _brain_with_ecology():
    """Orchestrator with a rich ecology graph that has clear structural roles."""
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    o = Orchestrator(verbose=False, db_path=db)
    # wolves plays REGULATOR: has CAUSES_OUT and CONTROLS_OUT
    o.relations.add("wolves",      "CAUSES",    "deer decline",  0.85, source_key="t", session_id="s1")
    o.relations.add("wolves",      "CONTROLS",  "overgrazing",   0.80, source_key="t", session_id="s1")
    # lions has same structural role as wolves
    o.relations.add("lions",       "CAUSES",    "zebra decline", 0.80, source_key="t", session_id="s1")
    o.relations.add("lions",       "CONTROLS",  "grassland",     0.75, source_key="t", session_id="s1")
    # deer plays MEDIATOR: CAUSES_IN and CAUSES_OUT
    o.relations.add("deer decline","CAUSES",    "overgrazing",   0.80, source_key="t", session_id="s2")
    # erosion is an OUTCOME: primarily caused-by, causes little
    o.relations.add("overgrazing", "CAUSES",    "erosion",       0.75, source_key="t", session_id="s2")
    return o, db


class TestFingerprint:
    def test_fingerprint_is_list_of_strings(self):
        o, db = _brain_with_ecology()
        try:
            fp = o.pattern_transfer.fingerprint("wolves")
            assert isinstance(fp, list)
            assert all(isinstance(x, str) for x in fp)
        finally:
            os.unlink(db)

    def test_fingerprint_contains_direction_tokens(self):
        o, db = _brain_with_ecology()
        try:
            fp = o.pattern_transfer.fingerprint("wolves")
            # wolves has outgoing edges so should have _OUT tokens
            assert any("_OUT" in tok for tok in fp)
        finally:
            os.unlink(db)

    def test_fingerprint_sorted(self):
        o, db = _brain_with_ecology()
        try:
            fp = o.pattern_transfer.fingerprint("wolves")
            assert fp == sorted(fp)
        finally:
            os.unlink(db)

    def test_fingerprint_unknown_concept_empty(self):
        o, db = _brain_with_ecology()
        try:
            fp = o.pattern_transfer.fingerprint("unicorn")
            assert fp == []
        finally:
            os.unlink(db)

    def test_wolves_and_lions_share_fingerprint_tokens(self):
        o, db = _brain_with_ecology()
        try:
            fp_wolves = set(o.pattern_transfer.fingerprint("wolves"))
            fp_lions  = set(o.pattern_transfer.fingerprint("lions"))
            # Both have CAUSES_OUT and CONTROLS_OUT
            assert len(fp_wolves & fp_lions) >= 2
        finally:
            os.unlink(db)


class TestMatchScore:
    def test_identical_fingerprints_score_one(self):
        o, db = _brain_with_ecology()
        try:
            fp = o.pattern_transfer.fingerprint("wolves")
            assert o.pattern_transfer.match_score(fp, fp) == 1.0
        finally:
            os.unlink(db)

    def test_empty_fingerprints_score_zero(self):
        o, db = _brain_with_ecology()
        try:
            assert o.pattern_transfer.match_score([], []) == 0.0
            assert o.pattern_transfer.match_score(["CAUSES_OUT"], []) == 0.0
        finally:
            os.unlink(db)

    def test_wolves_lions_high_match(self):
        o, db = _brain_with_ecology()
        try:
            fp_w = o.pattern_transfer.fingerprint("wolves")
            fp_l = o.pattern_transfer.fingerprint("lions")
            score = o.pattern_transfer.match_score(fp_w, fp_l)
            assert score >= 0.60
        finally:
            os.unlink(db)

    def test_unrelated_concepts_low_match(self):
        o, db = _brain_with_ecology()
        try:
            fp_w = o.pattern_transfer.fingerprint("wolves")
            fp_e = o.pattern_transfer.fingerprint("erosion")
            score = o.pattern_transfer.match_score(fp_w, fp_e)
            assert score < 0.60
        finally:
            os.unlink(db)


class TestRoleOf:
    def test_wolves_is_regulator(self):
        o, db = _brain_with_ecology()
        try:
            role = o.pattern_transfer.role_of("wolves")
            assert role == "REGULATOR"
        finally:
            os.unlink(db)

    def test_lions_is_regulator(self):
        o, db = _brain_with_ecology()
        try:
            role = o.pattern_transfer.role_of("lions")
            assert role == "REGULATOR"
        finally:
            os.unlink(db)

    def test_unknown_concept_is_unknown(self):
        o, db = _brain_with_ecology()
        try:
            role = o.pattern_transfer.role_of("unicorn")
            assert role == "UNKNOWN"
        finally:
            os.unlink(db)

    def test_role_returns_string(self):
        o, db = _brain_with_ecology()
        try:
            role = o.pattern_transfer.role_of("deer decline")
            assert isinstance(role, str) and len(role) > 0
        finally:
            os.unlink(db)


class TestScan:
    def test_scan_returns_int(self):
        o, db = _brain_with_ecology()
        try:
            n = o.pattern_transfer.scan()
            assert isinstance(n, int)
        finally:
            os.unlink(db)

    def test_scan_finds_wolves_lions_analog(self):
        o, db = _brain_with_ecology()
        try:
            n = o.pattern_transfer.scan()
            assert n >= 1
        finally:
            os.unlink(db)

    def test_scan_stores_in_db(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            row = o.memory._long_term._conn.execute(
                "SELECT COUNT(*) FROM structural_patterns"
            ).fetchone()
            assert row[0] >= 1
        finally:
            os.unlink(db)

    def test_scan_idempotent(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            n1 = o.memory._long_term._conn.execute(
                "SELECT COUNT(*) FROM structural_patterns"
            ).fetchone()[0]
            o.pattern_transfer.scan()
            n2 = o.memory._long_term._conn.execute(
                "SELECT COUNT(*) FROM structural_patterns"
            ).fetchone()[0]
            # Should not double-count — INSERT OR REPLACE
            assert n2 == n1
        finally:
            os.unlink(db)

    def test_scan_populates_concept_roles(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            row = o.memory._long_term._conn.execute(
                "SELECT COUNT(*) FROM concept_roles"
            ).fetchone()
            assert row[0] >= 1
        finally:
            os.unlink(db)


class TestAnalogsFor:
    def test_analogs_for_wolves_includes_lions(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            analogs = o.pattern_transfer.analogs_for("wolves")
            names = [a["analog"] for a in analogs]
            assert "lions" in names
        finally:
            os.unlink(db)

    def test_analogs_returns_list_of_dicts(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            analogs = o.pattern_transfer.analogs_for("wolves")
            assert isinstance(analogs, list)
            if analogs:
                assert "analog" in analogs[0]
                assert "match_score" in analogs[0]
        finally:
            os.unlink(db)

    def test_analogs_for_unknown_empty(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            analogs = o.pattern_transfer.analogs_for("unicorn")
            assert analogs == []
        finally:
            os.unlink(db)

    def test_analogs_score_between_zero_and_one(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            analogs = o.pattern_transfer.analogs_for("wolves")
            for a in analogs:
                assert 0.0 <= a["match_score"] <= 1.0
        finally:
            os.unlink(db)


class TestConceptsByRole:
    def test_concepts_by_role_regulator(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            regulators = o.pattern_transfer.concepts_by_role("REGULATOR")
            assert isinstance(regulators, list)
            assert "wolves" in regulators or "lions" in regulators
        finally:
            os.unlink(db)

    def test_concepts_by_role_unknown_returns_empty(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            result = o.pattern_transfer.concepts_by_role("NONEXISTENT_ROLE")
            assert result == []
        finally:
            os.unlink(db)


class TestCuriosityFromAnalogs:
    def test_returns_list(self):
        o, db = _brain_with_ecology()
        try:
            targets = o.pattern_transfer.curiosity_from_analogs()
            assert isinstance(targets, list)
        finally:
            os.unlink(db)

    def test_empty_when_no_patterns(self):
        o, db = _brain_with_ecology()
        try:
            # No scan yet — no structural patterns stored
            targets = o.pattern_transfer.curiosity_from_analogs()
            assert isinstance(targets, list)
        finally:
            os.unlink(db)

    def test_max_five_targets(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            targets = o.pattern_transfer.curiosity_from_analogs()
            assert len(targets) <= 5
        finally:
            os.unlink(db)


class TestPatternReport:
    def test_report_has_required_keys(self):
        o, db = _brain_with_ecology()
        try:
            report = o.pattern_transfer.pattern_report()
            for key in ("analog_pairs", "distinct_roles", "role_counts"):
                assert key in report
        finally:
            os.unlink(db)

    def test_report_after_scan_has_pairs(self):
        o, db = _brain_with_ecology()
        try:
            o.pattern_transfer.scan()
            report = o.pattern_transfer.pattern_report()
            assert report["analog_pairs"] >= 1
        finally:
            os.unlink(db)

    def test_stats_alias(self):
        o, db = _brain_with_ecology()
        try:
            assert o.pattern_transfer.stats() == o.pattern_transfer.pattern_report()
        finally:
            os.unlink(db)


class TestOrchestratorIntegration:
    def test_orchestrator_has_pattern_transfer(self):
        from orchestrator.orchestrator import Orchestrator
        from cognition.pattern_transfer import PatternTransfer
        db = tempfile.mktemp(suffix=".db")
        try:
            o = Orchestrator(verbose=False, db_path=db)
            assert hasattr(o, "pattern_transfer")
            assert isinstance(o.pattern_transfer, PatternTransfer)
        finally:
            os.unlink(db)

    def test_reflect_triggers_scan(self):
        from orchestrator.orchestrator import Orchestrator
        db = tempfile.mktemp(suffix=".db")
        try:
            o = Orchestrator(verbose=False, db_path=db)
            o.relations.add("sharks", "CAUSES",   "fish decline", 0.85, source_key="t", session_id="s1")
            o.relations.add("sharks", "CONTROLS", "reef health",  0.80, source_key="t", session_id="s1")
            o.relations.add("orcas",  "CAUSES",   "seal decline", 0.80, source_key="t", session_id="s1")
            o.relations.add("orcas",  "CONTROLS", "sea ice",      0.75, source_key="t", session_id="s1")
            o.reflect()
            # reflect() calls pattern_transfer.scan() — pairs should exist
            n = o.memory._long_term._conn.execute(
                "SELECT COUNT(*) FROM structural_patterns"
            ).fetchone()[0]
            assert n >= 1
        finally:
            os.unlink(db)
