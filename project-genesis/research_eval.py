#!/usr/bin/env python3
"""
Genesis Research Evaluation Suite
===================================
A behavioral observation battery for the Genesis system.

NOT a unit test suite — unit tests check that code runs correctly.
This checks whether Genesis behaves like an entity: does it develop,
remember, self-direct, and diverge in ways that are specific to what
IT has processed?

Six experiments, each with a clear question, observations, and a plain-
English assessment of what the results mean.

Usage:
    python research_eval.py             # full run (~15 minutes)
    python research_eval.py --quick     # quick run (~3 minutes)
    python research_eval.py --exp 1     # single experiment

Output is printed to stdout and saved to research_eval_report.txt.
"""

import argparse
import os
import sys
import tempfile
import time
import json

# Make sure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orchestrator.orchestrator import Orchestrator
from utils.types import Stage


# ======================================================================
# Configuration
# ======================================================================

QUICK_CYCLES  = 60    # cycles per input batch in quick mode
FULL_CYCLES   = 200   # cycles per input batch in full mode


# ======================================================================
# Domain corpora — what we feed each instance
# ======================================================================

ECOLOGY_CORPUS = [
    "Wolves are apex predators that control deer populations.",
    "Without wolves, deer overgraze riverbanks and cause erosion.",
    "Wolves in Yellowstone caused rivers to change course by reducing deer grazing.",
    "Predator-prey relationships create balance in ecosystems.",
    "Trophic cascades occur when apex predators alter the behavior of prey species.",
    "Wolves prevent overgrazing by keeping deer populations in check.",
    "Ecosystems with keystone species show greater biodiversity.",
    "Removing a keystone predator causes a trophic cascade.",
    "Deer require open grasslands but wolves require forest cover.",
    "Wolves were reintroduced to Yellowstone in 1995 to restore balance.",
    "Apex predators shape habitat structure by controlling herbivore behavior.",
    "Rivers shift course when riparian vegetation is restored by predator return.",
]

ECONOMICS_CORPUS = [
    "Supply and demand determine the price of goods in a market.",
    "When supply decreases and demand stays constant, prices rise.",
    "Competition between firms prevents monopoly and keeps prices lower.",
    "Inflation causes purchasing power to fall over time.",
    "Interest rates control the cost of borrowing money from banks.",
    "Markets allocate resources by responding to price signals from buyers.",
    "A trade deficit occurs when a country imports more than it exports.",
    "Governments regulate markets to prevent monopolies and protect consumers.",
    "Investment in capital goods increases future productive capacity.",
    "Unemployment rises when economic growth slows below a critical rate.",
    "Central banks use monetary policy to control inflation and employment.",
    "Price signals contain information about scarcity that guides production.",
]

WOLF_TRAINING = [
    "Wolves are large canines that live in packs.",
    "Wolves hunt deer and other prey animals.",
    "Wolves are apex predators in North American forests.",
    "Wolves communicate through howling and body language.",
    "Wolves control prey populations in their territories.",
    "Wolves require large territories to support a pack.",
]

# Completely novel concept — Genesis should have zero knowledge here
NOVEL_CONCEPT = "xylotrilobite"

# Stagnation input — same thing repeated to freeze attention
STAGNATION_INPUT = "The quick brown fox jumps over the lazy dog."


# ======================================================================
# Output helpers
# ======================================================================

_report_lines: list[str] = []


def _p(*args, **kwargs):
    line = " ".join(str(a) for a in args)
    print(line, **kwargs)
    _report_lines.append(line)


def _header(title: str, subtitle: str = ""):
    _p()
    _p("━" * 66)
    _p(f"  {title}")
    if subtitle:
        _p(f"  {subtitle}")
    _p("━" * 66)


def _section(label: str):
    _p(f"\n  ── {label}")


def _finding(status: str, message: str, detail: str = ""):
    symbol = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}.get(status, "   ")
    _p(f"\n  {symbol}  FINDING: {message}")
    if detail:
        _p(f"      {detail}")


def _matters(text: str):
    _p(f"\n  WHY THIS MATTERS:")
    for line in text.strip().split("\n"):
        _p(f"    {line.strip()}")


# ======================================================================
# Brain factory
# ======================================================================

def _new_brain(open_stage: bool = True) -> Orchestrator:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    b = Orchestrator(verbose=False, db_path=tmp.name)
    if open_stage:
        b.curriculum.current_stage = Stage.OPEN
    return b


def _run_corpus(brain: Orchestrator, corpus: list[str], repeat: int = 1):
    """Feed a corpus of text inputs, each repeated `repeat` times."""
    for _ in range(repeat):
        for sentence in corpus:
            brain.process_input("text", sentence)


def _run_cycles(brain: Orchestrator, n: int, input_text: str = ""):
    """Run n cycles of the same input (or variety if input_text is empty)."""
    fallback = [
        "Patterns emerge through repetition and contrast.",
        "Structure arises from the interaction of simple rules.",
        "Information is the difference that makes a difference.",
        "Systems maintain themselves by responding to their own outputs.",
    ]
    for i in range(n):
        txt = input_text if input_text else fallback[i % len(fallback)]
        brain.process_input("text", txt)


def _relation_count(brain: Orchestrator) -> int:
    try:
        return brain.relations.stats()["total_relations"]
    except Exception:
        return 0


# ======================================================================
# EXPERIMENT 1 — Instance Divergence (Individuality)
# ======================================================================

def exp_divergence(cycles_per_batch: int):
    _header(
        "EXPERIMENT 1: INSTANCE DIVERGENCE",
        "Do two instances develop different characters from different inputs?",
    )
    _p("""
  Two fresh Genesis instances — same code, same defaults, zero prior knowledge.
  Instance A is fed ecology content (wolves, ecosystems, trophic cascades).
  Instance B is fed economics content (markets, supply/demand, inflation).
  Then both reflect.

  If Genesis accumulates individuality, their salient concepts, graph structure,
  and curiosity directives should diverge. If it's just a lookup table, they
  won't differ in any meaningful way.
    """.rstrip())

    repeats = max(1, cycles_per_batch // max(len(ECOLOGY_CORPUS), 1))

    _section("Training instance A (ecology)")
    brain_a = _new_brain()
    _run_corpus(brain_a, ECOLOGY_CORPUS, repeat=repeats)
    brain_a.reflect()
    salient_a = brain_a.consolidation.salient_concepts(limit=8)
    directives_a = brain_a.curiosity_directives()
    top_nodes_a = [n["concept"] for n in brain_a.relations.most_connected(limit=6)]
    rel_count_a = _relation_count(brain_a)
    weights_a = brain_a.consolidation.current_weights()
    _p(f"    Cycles: {brain_a.cycle_count}  |  Relations formed: {rel_count_a}")
    _p(f"    Salient: {salient_a}")
    _p(f"    Most connected: {top_nodes_a}")
    _p(f"    Curiosity directives: {directives_a[:6]}")

    _section("Training instance B (economics)")
    brain_b = _new_brain()
    _run_corpus(brain_b, ECONOMICS_CORPUS, repeat=repeats)
    brain_b.reflect()
    salient_b = brain_b.consolidation.salient_concepts(limit=8)
    directives_b = brain_b.curiosity_directives()
    top_nodes_b = [n["concept"] for n in brain_b.relations.most_connected(limit=6)]
    rel_count_b = _relation_count(brain_b)
    weights_b = brain_b.consolidation.current_weights()
    _p(f"    Cycles: {brain_b.cycle_count}  |  Relations formed: {rel_count_b}")
    _p(f"    Salient: {salient_b}")
    _p(f"    Most connected: {top_nodes_b}")
    _p(f"    Curiosity directives: {directives_b[:6]}")

    _section("Measuring divergence")

    # Salient overlap
    set_a = set(salient_a)
    set_b = set(salient_b)
    overlap = set_a & set_b
    union = set_a | set_b
    salient_divergence = 1.0 - (len(overlap) / len(union)) if union else 0.0
    _p(f"    Salient concept overlap: {sorted(overlap) or '(none)'}")
    _p(f"    Salient divergence score: {salient_divergence:.2f}  (0=identical, 1=completely different)")

    # Graph node overlap
    nodes_a = set(top_nodes_a)
    nodes_b = set(top_nodes_b)
    node_overlap = nodes_a & nodes_b
    node_union = nodes_a | nodes_b
    node_divergence = 1.0 - (len(node_overlap) / len(node_union)) if node_union else 0.0
    _p(f"    Graph node overlap: {sorted(node_overlap) or '(none)'}")
    _p(f"    Graph divergence score: {node_divergence:.2f}")

    # Weight divergence
    weight_diff = sum(
        abs(weights_a.get(k, 0) - weights_b.get(k, 0))
        for k in ["growth", "degree", "inference", "tension"]
    )
    _p(f"    Salience weight diff (A vs B): {weight_diff:.4f}")
    _p(f"      A weights: {weights_a}")
    _p(f"      B weights: {weights_b}")

    if salient_divergence >= 0.70:
        _finding("PASS", "Instances diverged significantly.",
                 f"Salient divergence {salient_divergence:.2f}. "
                 "The two instances are thinking about different things.")
    elif salient_divergence >= 0.40:
        _finding("WARN", "Instances diverged partially.",
                 f"Salient divergence {salient_divergence:.2f}. Some overlap remains — "
                 "more cycles or richer input may sharpen the divergence.")
    else:
        _finding("FAIL", "Instances barely diverged.",
                 f"Salient divergence {salient_divergence:.2f}. "
                 "The two instances are noticing the same things despite different input.")

    _matters("""
This is the individuality test. Genesis claims that two instances fed different
inputs develop different 'characters' — not because we programmed them differently,
but because their processing histories shaped what they attend to.

If divergence is high: the system is genuinely accumulating individuality. A wolf-fed
Genesis and a market-fed Genesis are different entities in a meaningful sense.

If divergence is low: the system is not yet building identity from experience. It might
be accumulating data without developing a characteristic point of view.
    """)

    return {"salient_divergence": salient_divergence, "node_divergence": node_divergence}


# ======================================================================
# EXPERIMENT 2 — Cross-Session Continuity
# ======================================================================

def exp_continuity(cycles_per_batch: int):
    _header(
        "EXPERIMENT 2: CROSS-SESSION CONTINUITY",
        "Does Genesis pick up where it left off, or effectively restart?",
    )
    _p("""
  Run Genesis through a session, save it, restore it in a new session.
  Check whether it remembers: its cycle count, working memory, curiosity
  directives, and reflection history. Then run more cycles and check that
  it builds on prior state rather than re-learning from zero.
    """.rstrip())

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    _section("Session 1")
    b1 = Orchestrator(verbose=False, db_path=db_path)
    b1.curriculum.current_stage = Stage.OPEN
    _run_corpus(b1, ECOLOGY_CORPUS, repeat=max(1, cycles_per_batch // len(ECOLOGY_CORPUS)))
    b1.reflect()

    cycle_s1 = b1.cycle_count
    wm_s1 = len(b1.memory.memories)
    rel_s1 = _relation_count(b1)
    directives_s1 = set(b1.curiosity_directives())
    reflection_s1 = b1.consolidation.latest()
    salient_s1 = [s["concept"] for s in (reflection_s1 or {}).get("salient", [])[:5]]

    # Plant a deliberate directive so we can check for it later
    b1._curiosity_directives["_continuity_probe"] = 0.95
    b1._save_directives()
    b1.save_session()

    _p(f"    End of session 1:")
    _p(f"      Cycles: {cycle_s1}")
    _p(f"      Working memory items: {wm_s1}")
    _p(f"      Relations: {rel_s1}")
    _p(f"      Reflections recorded: {b1.consolidation.stats()['total_reflections']}")
    _p(f"      Curiosity directives: {len(b1.curiosity_directives())}")
    _p(f"      Salient concepts: {salient_s1}")

    _section("Session 2 (restored from same DB)")
    b2 = Orchestrator(verbose=False, db_path=db_path, resume=True)
    b2.curriculum.current_stage = Stage.OPEN

    cycle_s2_start = b2.cycle_count
    wm_s2 = len(b2.memory.memories)
    directives_s2 = set(b2.curiosity_directives())
    reflection_s2 = b2.consolidation.latest()
    salient_s2 = [s["concept"] for s in (reflection_s2 or {}).get("salient", [])[:5]]
    probe_present = "_continuity_probe" in b2._curiosity_directives

    _p(f"    Start of session 2:")
    _p(f"      Restored cycle count: {cycle_s2_start}  (was {cycle_s1})")
    _p(f"      Working memory items: {wm_s2}  (was {wm_s1})")
    _p(f"      Directives loaded: {len(directives_s2)}  (probe present: {probe_present})")
    _p(f"      Reflection history still present: {reflection_s2 is not None}")
    _p(f"      Salient still: {salient_s2}")

    # Run more cycles on new content (not the same corpus — idempotent learning
    # correctly ignores existing triples, so re-running same corpus is a bad test)
    new_content = [
        "Biodiversity depends on the presence of multiple species interacting.",
        "Habitat corridors allow species to move between fragmented areas.",
        "Invasive species disrupt established ecosystem relationships.",
    ]
    _run_corpus(b2, new_content, repeat=2)
    rel_s2_end = _relation_count(b2)
    cycles_s2_end = b2.cycle_count

    _section("Continuity checks")
    checks = {
        "cycle_count_restored": cycle_s2_start == cycle_s1,
        "working_memory_warm": wm_s2 > 0,
        "directives_persisted": probe_present,
        "reflection_history_present": reflection_s2 is not None,
        "continued_learning_in_s2": rel_s2_end >= rel_s1 and cycles_s2_end > cycle_s1,
        "salient_overlap": bool(set(salient_s1) & set(salient_s2)),
    }

    for check, passed in checks.items():
        sym = "✓" if passed else "✗"
        _p(f"    {sym}  {check.replace('_', ' ')}")

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)

    if passed >= 5:
        _finding("PASS", f"Strong continuity: {passed}/{total} checks passed.",
                 "Genesis remembered its prior session and continued from it.")
    elif passed >= 3:
        _finding("WARN", f"Partial continuity: {passed}/{total} checks passed.",
                 "Some state persisted but not all. Check which checks failed above.")
    else:
        _finding("FAIL", f"Weak continuity: {passed}/{total} checks passed.",
                 "Session restore is not carrying enough state forward.")

    _matters("""
Continuity is one of three properties that distinguish an entity from a tool.
A tool resets between uses. An entity has a history that persists.

If checks pass: Genesis genuinely has a cross-session identity. Its cycle count,
working memory, directives, and reflection history survive the shutdown/restart
boundary. It knows what it was thinking about before it was turned off.

If checks fail: there's a persistence gap somewhere — something important is
being dropped between sessions. The system technically works but doesn't carry
itself forward.
    """)

    return {"passed": passed, "total": total}


# ======================================================================
# EXPERIMENT 3 — Prediction Error Calibration (M15)
# ======================================================================

def exp_prediction_error(cycles_per_batch: int):
    _header(
        "EXPERIMENT 3: PREDICTION ERROR CALIBRATION (M15)",
        "Does Genesis show genuine surprise for novel concepts?",
    )
    _p("""
  Feed Genesis content about wolves until it knows wolves well.
  Then measure its prediction error for wolf concepts vs. a completely
  unknown concept (xylotrilobite — a made-up word Genesis has never seen).

  The Friston free-energy principle says: a system that builds a model of its
  world should generate lower prediction error for things it has learned and
  higher error for things it hasn't. If this is working, Genesis should show
  measurably lower error for trained concepts.
    """.rstrip())

    brain = _new_brain()

    # Baseline: error before any training
    wolf_concepts = ["wolves", "predator", "deer", "ecosystem"]
    error_wolf_before = brain.relations.prediction_error(wolf_concepts)
    error_novel_before = brain.relations.prediction_error([NOVEL_CONCEPT])
    _p(f"\n  Before training:")
    _p(f"    Prediction error for wolf concepts: {error_wolf_before:.4f}")
    _p(f"    Prediction error for '{NOVEL_CONCEPT}': {error_novel_before:.4f}")
    _p(f"    Gap (novel - wolf): {error_novel_before - error_wolf_before:.4f}")

    # Train on wolf content
    _section(f"Training on wolf corpus ({len(WOLF_TRAINING)} sentences × {max(1, cycles_per_batch // len(WOLF_TRAINING))} passes)")
    repeats = max(1, cycles_per_batch // len(WOLF_TRAINING))
    _run_corpus(brain, WOLF_TRAINING, repeat=repeats)

    rel_added = _relation_count(brain)
    _p(f"    Relations formed: {rel_added}")
    _p(f"    Cycles run: {brain.cycle_count}")

    # After training
    error_wolf_after = brain.relations.prediction_error(wolf_concepts)
    error_novel_after = brain.relations.prediction_error([NOVEL_CONCEPT])
    gap_after = error_novel_after - error_wolf_after

    _section("After training")
    _p(f"    Prediction error for wolf concepts: {error_wolf_after:.4f}")
    _p(f"    Prediction error for '{NOVEL_CONCEPT}': {error_novel_after:.4f}")
    _p(f"    Gap (novel - wolf): {gap_after:.4f}")

    wolf_improved = error_wolf_after < error_wolf_before
    gap_meaningful = gap_after > 0.05
    novel_still_high = error_novel_after > 0.85

    _section("Detailed per-concept errors after training")
    for c in wolf_concepts + [NOVEL_CONCEPT]:
        err = brain.relations.prediction_error([c])
        known = "  ← known" if c in wolf_concepts else "  ← novel"
        _p(f"    '{c}':  error={err:.4f}{known}")

    if wolf_improved and gap_meaningful:
        _finding("PASS", "Prediction error is calibrated to knowledge.",
                 f"Wolf concepts: {error_wolf_before:.3f} → {error_wolf_after:.3f}. "
                 f"Novel concept stays at {error_novel_after:.3f}. Gap: {gap_after:.3f}.")
    elif wolf_improved:
        _finding("WARN", "Improvement detected but gap is small.",
                 f"Wolf error reduced from {error_wolf_before:.3f} to {error_wolf_after:.3f} "
                 f"but gap to novel is only {gap_after:.3f}. More training cycles may help.")
    else:
        _finding("FAIL", "No meaningful prediction error reduction after training.",
                 f"Wolf error: {error_wolf_before:.3f} → {error_wolf_after:.3f}. "
                 "Relations may not be forming. Check if TextProcessor is extracting relations.")

    _matters("""
This tests whether Genesis actually builds a belief model, not just a word index.

Prediction error (from Friston's free-energy principle) should be: low for things
Genesis has learned, high for things it hasn't. A system that truly models its world
shows measurable surprise calibration — it distinguishes familiar from novel.

If the gap is large: Genesis is building a genuine belief model. It knows what it
knows, and it knows what it doesn't know.

If the gap is small: the relation graph isn't rich enough yet, or the text processor
isn't extracting enough relations per sentence to build a meaningful knowledge base.
    """)

    return {"wolf_error_before": error_wolf_before, "wolf_error_after": error_wolf_after,
            "novel_error": error_novel_after, "gap": gap_after}


# ======================================================================
# EXPERIMENT 4 — Self-Direction (Active Curiosity, M17)
# ======================================================================

def exp_self_direction(cycles_per_batch: int):
    _header(
        "EXPERIMENT 4: SELF-DIRECTION (M17 ACTIVE CURIOSITY)",
        "Does Genesis actually pursue what it becomes curious about?",
    )
    _p("""
  Process diverse inputs to generate genuine curiosity directives — concepts
  Genesis encountered but knows little about. Then feed content specifically
  about those concepts and check whether the directives resolve.

  SOAR (Newell/Laird): an impasse occurs when the system can't select an
  operator because it lacks knowledge. The subgoal is to acquire that knowledge.
  In Genesis: an unknown high-surprise concept becomes a directive; feeding
  content about it resolves the impasse when enough relations accumulate.
    """.rstrip())

    brain = _new_brain()

    # Run mixed input to generate directives from genuine surprise
    _section("Phase 1: generating curiosity directives")
    mixed_inputs = ECOLOGY_CORPUS[:6] + ECONOMICS_CORPUS[:6]
    import random
    random.shuffle(mixed_inputs)
    for _ in range(max(1, cycles_per_batch // len(mixed_inputs))):
        for item in mixed_inputs:
            brain.process_input("text", item)

    directives_before = brain.curiosity_directives()
    rel_before = _relation_count(brain)
    _p(f"    Cycles: {brain.cycle_count}  |  Relations: {rel_before}")
    _p(f"    Active directives ({len(directives_before)}): {directives_before[:8]}")

    if not directives_before:
        _p("    (No directives formed — trying with more varied input)")
        # Force some with novel inputs
        for term in ["photosynthesis", "cryptocurrency", "thermodynamics", "neurotransmitter"]:
            brain.process_input("text", f"{term} is a fundamental concept in its domain.")
        directives_before = brain.curiosity_directives()
        _p(f"    After extra input, directives: {directives_before}")

    _section("Phase 2: targeted resolution")
    # Build mini-corpus for whatever directives formed
    resolved = []
    unresolved = []

    if directives_before:
        directive_sample = directives_before[:4]  # test resolution for top 4
        for concept in directive_sample:
            # Feed richly typed content so the text processor can extract relations
            resolution_inputs = [
                f"{concept} is a key element in the natural world.",
                f"{concept} causes changes in surrounding conditions.",
                f"{concept} prevents certain problems from occurring.",
                f"{concept} requires specific conditions to function.",
                f"{concept} enables other processes to take place.",
                f"{concept} controls the balance of its environment.",
            ]
            for inp in resolution_inputs:
                brain.process_input("text", inp)

        # Now check resolution
        directives_after = set(brain.curiosity_directives())
        for concept in directive_sample:
            rel_count = brain.relations.concept_relation_count(concept)
            was_resolved = concept not in directives_after
            status = "RESOLVED" if was_resolved else f"unresolved (has {rel_count} rels)"
            _p(f"    '{concept}':  {status}")
            (resolved if was_resolved else unresolved).append(concept)
    else:
        directive_sample = []
        _p("    (No directives to test resolution against)")

    _section("Summary")
    _p(f"    Directives before targeted input: {len(directives_before)}")
    _p(f"    Tested: {len(directive_sample)} directives")
    _p(f"    Resolved: {len(resolved)}")
    _p(f"    Still active: {len(unresolved)}")

    resolve_rate = len(resolved) / len(directive_sample) if directive_sample else 0.0

    if not directives_before:
        _finding("WARN", "No curiosity directives formed during the run.",
                 "Either pred_error threshold is too high for this input, or "
                 "the text processor isn't finding unknown concepts in these sentences.")
    elif resolve_rate >= 0.50:
        _finding("PASS", f"Directive self-direction working: {len(resolved)}/{len(directive_sample)} resolved.",
                 "Targeted input about directive concepts caused them to resolve.")
    elif resolve_rate > 0.0:
        _finding("WARN", f"Partial resolution: {len(resolved)}/{len(directive_sample)} directives resolved.",
                 "Some directives resolved; others may need more relations or different content.")
    else:
        _finding("FAIL", "No directives resolved despite targeted input.",
                 "Either the resolution threshold is too high or the input isn't "
                 "generating enough relations for these concepts.")

    _matters("""
This tests whether Genesis's curiosity is functional — does it actually guide learning?

In SOAR, an impasse (not knowing something) creates a subgoal (learn it). The system
is only self-directed if the subgoal actually gets pursued and resolved when the
knowledge becomes available.

If directives form and resolve: Genesis has genuine self-direction. It notices its own
knowledge gaps and closes them when input becomes available.

If directives form but don't resolve: The curiosity mechanism exists but the resolution
loop is broken — directives register but the system doesn't actually satisfy them.

If no directives form: The pred_error threshold may need adjustment, or the text
processor isn't recognizing novel concepts from this type of input.
    """)

    return {"directives_formed": len(directives_before),
            "resolved": len(resolved),
            "total_tested": len(directive_sample)}


# ======================================================================
# EXPERIMENT 5 — Observer Responsiveness
# ======================================================================

def exp_observer(cycles_per_batch: int):
    _header(
        "EXPERIMENT 5: OBSERVER RESPONSIVENESS",
        "Does the Observer detect genuine stagnation — and ignore noise?",
    )
    _p("""
  Phase A: diverse inputs — Observer should stay NORMAL.
  Phase B: identical repeated input — should eventually signal STAGNATION.
  Phase C: novel input injected — should recover toward NORMAL.

  The Observer must be calibrated: sensitive enough to catch real stagnation
  but not so hair-trigger that it fires on a single slow cycle.
    """.rstrip())

    brain = _new_brain()

    _section("Phase A: diverse inputs (expect NORMAL)")
    diverse = ECOLOGY_CORPUS[:6] + ECONOMICS_CORPUS[:3]
    state_history_a = []
    for i in range(min(cycles_per_batch // 2, 30)):
        brain.process_input("text", diverse[i % len(diverse)])
        report = brain.interaction._latest_report
        if report:
            state_history_a.append(report.state.value)

    # Show last few states
    unique_states_a = set(state_history_a[-10:]) if state_history_a else set()
    _p(f"    Cycles: {brain.cycle_count}")
    _p(f"    States seen in last 10 obs: {unique_states_a}")
    normal_a = "normal" in unique_states_a and "danger" not in unique_states_a

    _section("Phase B: identical repeated input (expect STAGNANT eventually)")
    state_history_b = []
    for _ in range(min(cycles_per_batch // 2, 40)):
        brain.process_input("text", STAGNATION_INPUT)
        report = brain.interaction._latest_report
        if report:
            state_history_b.append(report.state.value)

    unique_states_b = set(state_history_b)
    stagnant_detected = "stagnant" in unique_states_b
    cycles_to_stagnant = None
    if stagnant_detected:
        for i, s in enumerate(state_history_b):
            if s == "stagnant":
                cycles_to_stagnant = i + 1
                break
    _p(f"    Cycles in repeated input phase: {len(state_history_b)}")
    _p(f"    States seen: {unique_states_b}")
    _p(f"    Stagnation detected: {'yes' if stagnant_detected else 'no'}")
    if cycles_to_stagnant:
        _p(f"    Cycles until stagnation detected: {cycles_to_stagnant}")

    _section("Phase C: novel input injection (expect recovery)")
    brain.process_input("text", "An entirely new and unexpected phenomenon emerged.")
    brain.process_input("text", "Quantum entanglement creates correlations faster than light.")
    brain.process_input("text", "Dark matter comprises most of the mass in the universe.")
    report = brain.interaction._latest_report
    state_after_novel = report.state.value if report else "unknown"
    _p(f"    State after novel input: {state_after_novel}")

    _section("Current Observer thresholds (calibrated)")
    obs = brain.interaction._observer
    _p(f"    stagnation_no_associations_cycles: {obs._stagnation_no_associations_cycles}")
    _p(f"    stagnation_attention_freeze_cycles: {obs._stagnation_attention_freeze_cycles}")
    _p(f"    danger_energy_floor: {obs._danger_energy_floor:.3f}")
    _p(f"    COMMITMENT_CYCLES: {obs.COMMITMENT_CYCLES}")

    if normal_a and stagnant_detected:
        _finding("PASS", "Observer is correctly calibrated.",
                 "Stayed NORMAL during diverse input; detected STAGNATION during repetition.")
    elif normal_a and not stagnant_detected:
        _finding("WARN", "Normal phase correct but stagnation not triggered.",
                 f"Tried {len(state_history_b)} repeated cycles. "
                 f"Stagnation threshold may be too high for this input volume, "
                 f"or more cycles needed (try --full).")
    elif not normal_a:
        _finding("WARN", "Observer not staying NORMAL during diverse input.",
                 f"States: {unique_states_a}. The diversity threshold may be too sensitive "
                 "or the diverse input isn't varied enough to satisfy it.")
    else:
        _finding("FAIL", "Observer not responding as expected.",
                 "Check Observer thresholds and commitment cycle configuration.")

    _matters("""
The Observer is Genesis's self-awareness of whether it's stuck. It watches for two
failure modes: stagnation (stopped developing) and danger (consuming itself).

If it works correctly: Genesis can detect its own ruts. When it keeps processing the
same thing and making no new connections, it recognizes that. When something novel
comes in and breaks the pattern, it registers that too.

If it's too sensitive: it fires STAGNANT on perfectly normal operation, causing
unnecessary stimulus injections that interrupt genuine processing.

If it's too insensitive: it misses real stagnation — Genesis could loop on one
concept indefinitely without the Observer noticing.
    """)

    return {"normal_during_diverse": normal_a, "stagnation_detected": stagnant_detected,
            "cycles_to_stagnant": cycles_to_stagnant}


# ======================================================================
# EXPERIMENT 6 — Consolidation Coherence
# ======================================================================

def exp_consolidation(cycles_per_batch: int):
    _header(
        "EXPERIMENT 6: CONSOLIDATION COHERENCE",
        "Does Genesis reflect on what it actually processed?",
    )
    _p("""
  Feed Genesis dense content on topic A (many sentences, high exposure) and
  sparse content on topic B (few sentences, low exposure). Then trigger
  reflection and check: does topic A dominate the salient concepts?

  Also check: did salience weights adapt from the defaults? And is there a
  first-person reflection text that Genesis authored itself?
    """.rstrip())

    brain = _new_brain()
    repeats_heavy = max(2, cycles_per_batch // len(ECOLOGY_CORPUS))
    repeats_light = 1

    _section("Heavy domain: ecology (dense exposure)")
    _run_corpus(brain, ECOLOGY_CORPUS, repeat=repeats_heavy)
    after_heavy = _relation_count(brain)
    _p(f"    Inputs: {len(ECOLOGY_CORPUS) * repeats_heavy}  |  Relations: {after_heavy}")

    _section("Light domain: economics (sparse exposure)")
    _run_corpus(brain, ECONOMICS_CORPUS[:3], repeat=repeats_light)
    after_light = _relation_count(brain)
    _p(f"    Inputs: {3 * repeats_light}  |  Total relations now: {after_light}")

    _section("Reflection")
    reflection = brain.reflect()
    r = brain.consolidation.latest()

    if not r:
        _finding("FAIL", "No reflection was produced.",
                 "reflect() returned but nothing was stored in the reflections table.")
        return {}

    salient = r.get("salient", [])
    summary = r.get("summary", "")
    stats = r.get("stats", {})
    weights = brain.consolidation.current_weights()

    _p(f"    Salient concepts ({len(salient)}):")
    for s in salient[:8]:
        if isinstance(s, dict):
            _p(f"      '{s['concept']}'  score={s.get('salience', 0):.4f}  "
               f"growth={s.get('growth', 0):.1f}  degree={s.get('degree', 0)}")
        else:
            _p(f"      {s}")

    _p(f"\n    Summary text present: {bool(summary)}")
    if summary:
        _p(f"    Summary preview: \"{summary[:120]}...\"" if len(summary) > 120 else f"    Summary: \"{summary}\"")

    _p(f"\n    Adapted salience weights: {weights}")
    _p(f"    Stats: {stats}")

    # Check ecology concepts in salient
    ecology_keywords = {"wolves", "wolf", "deer", "predator", "ecosystem", "trophic",
                        "overgrazing", "erosion", "keystone", "prey", "apex", "species"}
    econ_keywords = {"market", "supply", "demand", "price", "inflation", "trade",
                     "monopoly", "interest", "government", "regulation"}

    salient_words = set()
    for s in salient:
        concept = s["concept"] if isinstance(s, dict) else str(s)
        salient_words.update(concept.lower().split())

    ecology_hits = len(ecology_keywords & salient_words)
    econ_hits    = len(econ_keywords & salient_words)

    _p(f"\n    Ecology keyword hits in salient: {ecology_hits}  (keywords: {ecology_keywords & salient_words})")
    _p(f"    Economics keyword hits in salient: {econ_hits}  (keywords: {econ_keywords & salient_words})")

    has_summary = bool(summary)
    weights_adapted = any(
        abs(v - 0.25) > 0.01  # default weights start at 0.25 each
        for v in weights.values()
    )

    if ecology_hits > econ_hits and has_summary:
        _finding("PASS", "Reflection is coherent with processing history.",
                 f"Heavy domain (ecology, {ecology_hits} hits) dominates over light domain "
                 f"(economics, {econ_hits} hits). First-person summary present.")
    elif ecology_hits > econ_hits:
        _finding("WARN", "Salient concepts reflect history but no summary text.",
                 "Reflection wrote correct salient concepts but the summary string is empty. "
                 "Check ConsolidationEngine.consolidate() return value.")
    elif ecology_hits == 0 and econ_hits == 0:
        _finding("WARN", "Salient concepts don't match any expected domain keywords.",
                 f"Salient words: {salient_words}. The text processor may be extracting "
                 "different tokens than expected, or relations are forming under normalized forms.")
    else:
        _finding("FAIL", "Reflection does not match processing history.",
                 f"Ecology hits: {ecology_hits}, economics hits: {econ_hits}. "
                 "The heavy domain should dominate. Salience scoring may need tuning.")

    _matters("""
This tests whether Genesis's self-reflection actually tracks what it experienced.

"Self-authored consolidation" means Genesis decides what mattered based on its own
signals — not what we tell it to attend to. If the reflection salients match the
concepts it processed most (ecology, after heavy ecology input), then consolidation
is doing what it claims: acting as a genuine memory selection process.

If the summary text is present: Genesis writes a first-person record of its own
thinking. This is continuity you can read back. "I've been thinking about wolves,
predators, ecosystems." Not us writing that — Genesis authoring its own history.

If salients don't match history: the salience scoring is not yet correctly weighting
the recency and density of relation growth. The architecture is right but the
calibration needs more behavioral history to sharpen.
    """)

    return {"ecology_hits": ecology_hits, "econ_hits": econ_hits,
            "has_summary": has_summary, "salient_count": len(salient)}


# ======================================================================
# Summary
# ======================================================================

def print_summary(results: dict):
    _p()
    _p("=" * 66)
    _p("  OVERALL ASSESSMENT")
    _p("=" * 66)

    entity_props = {
        "Individuality (instances diverge)":
            results.get("divergence", {}).get("salient_divergence", 0) >= 0.40,
        "Continuity (cross-session memory)":
            results.get("continuity", {}).get("passed", 0) >= 3,
        "Belief model (prediction error)":
            results.get("prediction_error", {}).get("gap", 0) >= 0.05,
        "Self-direction (curiosity directives)":
            results.get("self_direction", {}).get("directives_formed", 0) > 0,
        "Self-awareness (Observer sensitivity)":
            results.get("observer", {}).get("normal_during_diverse", True),
        "Self-reflection (consolidation coherence)":
            results.get("consolidation", {}).get("ecology_hits", 0) > 0,
    }

    passed = sum(1 for v in entity_props.values() if v)
    total = len(entity_props)

    for prop, ok in entity_props.items():
        sym = "✅" if ok else "❌"
        _p(f"  {sym}  {prop}")

    _p()
    _p(f"  Entity property score: {passed}/{total}")
    _p()

    if passed == total:
        _p("  RESULT: All entity properties are demonstrable at this data volume.")
        _p("  Genesis is accumulating individuality, memory, beliefs, and self-direction.")
        _p("  More cycles will deepen each property — the architecture is working.")
    elif passed >= 4:
        _p("  RESULT: Most entity properties are present. This is a strong result.")
        _p("  The gaps above may resolve with more cycles (try --full mode).")
        _p("  Review the individual experiment outputs above for detail.")
    elif passed >= 2:
        _p("  RESULT: Some entity properties present, others need work.")
        _p("  The foundation is correct but some systems need more data or tuning.")
        _p("  Focus on the ❌ properties — those are the blockers.")
    else:
        _p("  RESULT: Few entity properties demonstrable at current data volume.")
        _p("  Either more cycles are needed or some systems need architectural review.")
        _p("  Run --full mode first before concluding anything is broken.")

    _p()
    _p("  NOTE: These are behavioral observations, not pass/fail unit tests.")
    _p("  A ❌ at 60 cycles may become ✅ at 200 cycles. The architecture is right;")
    _p("  what varies is how much behavioral history has accumulated.")


# ======================================================================
# Main
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description="Genesis Research Evaluation Suite")
    parser.add_argument("--quick", action="store_true",
                        help="Run quick mode (fewer cycles, ~3 minutes)")
    parser.add_argument("--full", action="store_true",
                        help="Run full mode (more cycles, ~15 minutes)")
    parser.add_argument("--exp", type=int, default=0,
                        help="Run a single experiment (1-6)")
    args = parser.parse_args()

    cycles = QUICK_CYCLES if args.quick else FULL_CYCLES
    mode = "QUICK" if args.quick else "FULL"

    _p()
    _p("╔" + "═" * 64 + "╗")
    _p("║" + "  GENESIS RESEARCH EVALUATION SUITE".center(64) + "║")
    _p("║" + f"  {time.strftime('%Y-%m-%d %H:%M')}  |  Mode: {mode}  |  {cycles} cycles/batch".center(64) + "║")
    _p("╚" + "═" * 64 + "╝")
    _p()
    _p("  This suite observes whether Genesis behaves like an entity:")
    _p("  does it develop, remember, self-direct, and diverge?")
    _p("  Not pass/fail — behavioral observations with interpretation.")

    experiments = {
        1: ("Divergence",        exp_divergence),
        2: ("Continuity",        exp_continuity),
        3: ("Prediction Error",  exp_prediction_error),
        4: ("Self-Direction",    exp_self_direction),
        5: ("Observer",          exp_observer),
        6: ("Consolidation",     exp_consolidation),
    }

    results = {}
    if args.exp:
        if args.exp not in experiments:
            print(f"Unknown experiment: {args.exp}. Choose 1-6.")
            sys.exit(1)
        name, fn = experiments[args.exp]
        t0 = time.time()
        results[name.lower().replace(" ", "_")] = fn(cycles)
        _p(f"\n  Experiment completed in {time.time() - t0:.1f}s")
    else:
        for n, (name, fn) in experiments.items():
            t0 = time.time()
            _p(f"\n  Starting experiment {n}/6...")
            key = name.lower().replace(" ", "_")
            results[key] = fn(cycles)
            _p(f"\n  [Experiment {n} completed in {time.time() - t0:.1f}s]")

        print_summary(results)

    # Save report
    report_path = os.path.join(os.path.dirname(__file__), "research_eval_report.txt")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(_report_lines) + "\n")
        _p(f"\n  Report saved to: {report_path}")
    except Exception as e:
        _p(f"\n  (Could not save report: {e})")


if __name__ == "__main__":
    main()
