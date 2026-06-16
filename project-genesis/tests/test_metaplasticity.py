"""
Tests for M33 MetaplasticityEngine — adaptive learning rate.

Verifies:
1. Plasticity starts at moderate default
2. Sustained high error pushes plasticity up (stuck regime)
3. Error falling fast → learning regime (high but not max)
4. Error spike after stability → surprised regime (near-max)
5. Stable low error → rigid/mastered regime (low plasticity)
6. Plasticity is smoothed — doesn't jump on a single cycle
7. Propagates to relation graph (relations.set_plasticity called)
8. Persist + restore across instances
9. Orchestrator has metaplasticity attribute
10. Relation graph: low plasticity → pure MAX (contradicting evidence rejected)
11. Relation graph: high plasticity → contradicting evidence reduces confidence
12. Relation graph: strengthening evidence always applies regardless of plasticity
13. Confidence floor: single input can't reduce below 70% of existing
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cognition.metaplasticity import MetaplasticityEngine


def _brain():
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    b = Orchestrator(verbose=False, db_path=db)
    return b, db


def _cleanup(db):
    if os.path.exists(db):
        os.unlink(db)


# ── MetaplasticityEngine behaviour ───────────────────────────────────────────

class TestPlasticityRegimes:
    def test_starts_at_default(self):
        b, db = _brain()
        try:
            assert 0.3 <= b.metaplasticity.plasticity <= 0.7
        finally:
            _cleanup(db)

    def test_stuck_high_error_raises_plasticity(self):
        """Sustained high prediction error → high plasticity (need to change)."""
        b, db = _brain()
        try:
            meta = b.metaplasticity
            for _ in range(25):
                meta.update(0.85)   # consistently high error
            assert meta.plasticity > 0.65, \
                f"expected high plasticity when stuck, got {meta.plasticity:.3f}"
        finally:
            _cleanup(db)

    def test_stable_low_error_lowers_plasticity(self):
        """Stable low error → low plasticity (protect solid knowledge)."""
        b, db = _brain()
        try:
            meta = b.metaplasticity
            for _ in range(30):
                meta.update(0.10)   # consistently low error
            assert meta.plasticity < 0.40, \
                f"expected low plasticity when mastered, got {meta.plasticity:.3f}"
        finally:
            _cleanup(db)

    def test_error_falling_fast_keeps_plasticity_elevated(self):
        """Error dropping quickly → learning regime — keep plasticity up."""
        b, db = _brain()
        try:
            meta = b.metaplasticity
            # Seed with high error, then drop
            for _ in range(10):
                meta.update(0.80)
            for _ in range(8):
                meta.update(0.20)
            assert meta.plasticity > 0.50, \
                f"expected elevated plasticity while learning, got {meta.plasticity:.3f}"
        finally:
            _cleanup(db)

    def test_error_spike_after_stability_raises_plasticity(self):
        """Surprise after stable period → near-max plasticity."""
        b, db = _brain()
        try:
            meta = b.metaplasticity
            for _ in range(20):
                meta.update(0.10)   # stable, low
            for _ in range(5):
                meta.update(0.90)   # sudden spike
            assert meta.plasticity > 0.60, \
                f"expected high plasticity after surprise, got {meta.plasticity:.3f}"
        finally:
            _cleanup(db)

    def test_plasticity_smoothed_single_cycle(self):
        """A single surprising cycle should not jump plasticity to maximum."""
        b, db = _brain()
        try:
            meta = b.metaplasticity
            for _ in range(20):
                meta.update(0.15)  # stable low
            p_before = meta.plasticity
            meta.update(0.95)      # one spike
            # Should move toward higher but not jump all the way
            assert meta.plasticity < 0.80, \
                "single spike should be smoothed, not jump to max"
            assert meta.plasticity > p_before, \
                "should still move upward from the spike"
        finally:
            _cleanup(db)

    def test_state_dict_keys(self):
        b, db = _brain()
        try:
            s = b.metaplasticity.state()
            for key in ("plasticity", "regime", "error_mean", "error_recent", "history_len"):
                assert key in s
        finally:
            _cleanup(db)


# ── Propagation to relation graph ─────────────────────────────────────────────

class TestPropagation:
    def test_update_propagates_to_relations(self):
        """After meta.update(), relations._plasticity matches."""
        b, db = _brain()
        try:
            meta = b.metaplasticity
            meta.update(0.8)
            assert abs(b.relations._plasticity - meta.plasticity) < 0.01
        finally:
            _cleanup(db)

    def test_set_plasticity_directly(self):
        b, db = _brain()
        try:
            b.relations.set_plasticity(0.9)
            assert abs(b.relations._plasticity - 0.9) < 0.001
        finally:
            _cleanup(db)


# ── Persist and restore ────────────────────────────────────────────────────────

class TestPersistence:
    def test_save_and_restore(self):
        b, db = _brain()
        try:
            meta = b.metaplasticity
            for _ in range(20):
                meta.update(0.80)
            p_before = meta.plasticity
            meta.save()

            # New instance, same DB
            from orchestrator.orchestrator import Orchestrator
            b2 = Orchestrator(verbose=False, db_path=db)
            # Manually restore (orchestrator auto-restores in __init__)
            assert abs(b2.metaplasticity.plasticity - p_before) < 0.05, \
                "plasticity should be close after restore"
        finally:
            _cleanup(db)


# ── Orchestrator wiring ────────────────────────────────────────────────────────

class TestOrchestratorWiring:
    def test_metaplasticity_present(self):
        b, db = _brain()
        try:
            assert hasattr(b, "metaplasticity")
            assert isinstance(b.metaplasticity, MetaplasticityEngine)
        finally:
            _cleanup(db)


# ── Plasticity-aware relation graph ───────────────────────────────────────────

class TestPlasticityAwareRelations:
    def test_strengthening_always_applies(self):
        """New evidence that increases confidence always takes effect."""
        b, db = _brain()
        try:
            b.relations.set_plasticity(0.05)   # very low plasticity
            b.relations.add("wolves", "CONTROLS", "deer", 0.60)
            b.relations.add("wolves", "CONTROLS", "deer", 0.90)   # stronger
            result = b.relations.query_subject("wolves", min_confidence=0.0)
            conf = next(r["confidence"] for r in result if r["relation"] == "CONTROLS")
            assert conf >= 0.89, f"strengthening should apply even at low plasticity, got {conf}"
        finally:
            _cleanup(db)

    def test_low_plasticity_protects_established_belief(self):
        """Low plasticity: contradicting evidence does not reduce confidence."""
        b, db = _brain()
        try:
            b.relations.set_plasticity(0.05)
            b.relations.add("wolves", "CONTROLS", "deer", 0.85)
            b.relations.add("wolves", "CONTROLS", "deer", 0.30)   # contradicting
            result = b.relations.query_subject("wolves", min_confidence=0.0)
            conf = next(r["confidence"] for r in result if r["relation"] == "CONTROLS")
            assert conf >= 0.84, \
                f"low plasticity should protect established belief, got {conf}"
        finally:
            _cleanup(db)

    def test_high_plasticity_allows_confidence_reduction(self):
        """High plasticity: contradicting evidence can reduce confidence."""
        b, db = _brain()
        try:
            b.relations.set_plasticity(0.95)
            b.relations.add("wolves", "CONTROLS", "deer", 0.85)
            b.relations.add("wolves", "CONTROLS", "deer", 0.30)   # contradicting
            result = b.relations.query_subject("wolves", min_confidence=0.0)
            conf = next(r["confidence"] for r in result if r["relation"] == "CONTROLS")
            assert conf < 0.85, \
                f"high plasticity should allow some reduction, got {conf}"
        finally:
            _cleanup(db)

    def test_confidence_floor_protects_against_single_large_drop(self):
        """Even at max plasticity, confidence can't fall below 70% of existing."""
        b, db = _brain()
        try:
            b.relations.set_plasticity(1.0)
            b.relations.add("wolves", "CONTROLS", "deer", 0.90)
            b.relations.add("wolves", "CONTROLS", "deer", 0.01)   # extreme contradiction
            result = b.relations.query_subject("wolves", min_confidence=0.0)
            conf = next(r["confidence"] for r in result if r["relation"] == "CONTROLS")
            assert conf >= 0.90 * 0.70 - 0.01, \
                f"floor should prevent extreme single-step drop, got {conf}"
        finally:
            _cleanup(db)

    def test_new_relation_uses_full_confidence(self):
        """New (never-seen) relation is always stored at full confidence."""
        b, db = _brain()
        try:
            b.relations.set_plasticity(0.01)   # minimum plasticity
            b.relations.add("ravens", "IS_A", "corvid", 0.80)
            result = b.relations.query_subject("ravens", min_confidence=0.0)
            conf = next(r["confidence"] for r in result if r["relation"] == "IS_A")
            assert conf >= 0.79
        finally:
            _cleanup(db)
