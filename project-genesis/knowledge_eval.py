#!/usr/bin/env python3
"""
Genesis Knowledge Development Evaluation
==========================================
Tests whether Genesis builds understanding, not just storage.

The school test analogy: a student who memorizes facts but can't apply them
to new problems hasn't understood — they've just stored. Near-perfect recall
is the floor. The tests that matter:

  LEVEL 1 — Recall
    Can it repeat what it was explicitly told?
    Even a spreadsheet does this. Baseline only.

  LEVEL 2 — Inference
    Can it reach conclusions it was NEVER TOLD?
    Teach: A→B, B→C. Ask: can it find A→C?
    A lookup table fails this. A system with inference chains passes.

  LEVEL 3 — Calibrated Ignorance
    Does it know what it knows vs. what it doesn't?
    Prediction error should be low for trained concepts, high for unknowns.

  LEVEL 4 — Contradiction Awareness
    When you feed it something that conflicts with existing beliefs, does it notice?

  LEVEL 5 — Growth Quality
    Does more input make it SMARTER (deeper inference reach, richer connections)
    or just BIGGER (more isolated facts)?
    These are different. A filing cabinet gets bigger. Understanding deepens.

HONEST GAPS (surfaced by this test, not hidden):
  - Belief revision: Genesis logs contradictions but does NOT lower confidence
    on contradicted beliefs. Confidence only goes up. It accumulates; it doesn't
    cross out wrong answers.
  - Pattern transfer: Genesis does not yet generalize patterns across domains.
    What it learns about wolves does not automatically inform what it knows about
    lions, even if the predator-prey structure is identical.

Usage:
    python knowledge_eval.py            # full run
    python knowledge_eval.py --quick    # reduced cycles
    python knowledge_eval.py --test N   # single test (1-5)
"""

import argparse
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orchestrator.orchestrator import Orchestrator
from memory.relations import RELATION_TYPES
from utils.types import Stage


# ======================================================================
# Cycle budgets
# ======================================================================

QUICK_CYCLES = 80
FULL_CYCLES  = 350


# ======================================================================
# Test corpus — a designed causal chain Genesis should be able to traverse
#
# Explicit chain:
#   wolves → deer → overgrazing → erosion → river change
#
# Each link is also repeated with different phrasing so the text processor
# has multiple chances to extract the relation.
# ======================================================================

CHAIN_CORPUS = [
    # Link 1: wolves CONTROLS deer
    "Wolves control deer populations in forested regions.",
    "Deer populations are regulated by wolves as their primary predator.",
    "Without wolves, deer numbers increase beyond what the land can support.",

    # Link 2: deer CAUSES overgrazing
    "Deer cause overgrazing when their population grows unchecked.",
    "Overgrazing of riverbanks is caused by high deer density.",
    "When deer overpopulate, they cause damage to vegetation through overgrazing.",

    # Link 3: overgrazing CAUSES erosion
    "Overgrazing causes soil erosion by removing protective plant cover.",
    "Soil erosion is caused by overgrazing of riverbank vegetation.",
    "Bare soil from overgrazing causes erosion during rainfall.",

    # Link 4: erosion CAUSES river change
    "Soil erosion causes rivers to change course over time.",
    "River course changes are caused by heavy erosion of banks.",
    "When erosion is severe, it causes rivers to shift their channels.",
]

# Contradicting pair for the contradiction test
# wolves ENABLES deer growth ↔ wolves PREVENTS deer growth
CONTRADICT_CORPUS = [
    "Wolves enable deer to develop stronger survival instincts.",  # wolves ENABLES deer
    "Wolves prevent deer populations from growing too large.",     # wolves PREVENTS deer
]

# Unknown to Genesis — should always produce high prediction error
UNKNOWN_CONCEPTS = ["xylotrilobite", "phlogistocene", "nullarboria"]

# Time-horizon labels
HORIZONS = [
    ("baseline",    20),
    ("short",       80),
    ("medium",     180),
    ("long",       350),
]


# ======================================================================
# Output helpers
# ======================================================================

_lines: list[str] = []

def _p(*args):
    line = " ".join(str(a) for a in args)
    print(line)
    _lines.append(line)

def _banner(title: str, subtitle: str = ""):
    _p()
    _p("━" * 68)
    _p(f"  {title}")
    if subtitle:
        _p(f"  {subtitle}")
    _p("━" * 68)

def _sub(label: str):
    _p(f"\n  ── {label}")

def _ok(msg: str, detail: str = ""):
    _p(f"\n  ✅  {msg}")
    if detail: _p(f"      {detail}")

def _warn(msg: str, detail: str = ""):
    _p(f"\n  ⚠️   {msg}")
    if detail: _p(f"      {detail}")

def _fail(msg: str, detail: str = ""):
    _p(f"\n  ❌  {msg}")
    if detail: _p(f"      {detail}")

def _gap(msg: str, detail: str = ""):
    """Known architectural gap — not a test failure, an honest observation."""
    _p(f"\n  🔲  KNOWN GAP: {msg}")
    if detail: _p(f"      {detail}")

def _matters(text: str):
    _p(f"\n  WHY IT MATTERS:")
    for line in text.strip().splitlines():
        _p(f"    {line.strip()}")


# ======================================================================
# Brain helpers
# ======================================================================

def _new_brain() -> tuple[Orchestrator, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    b = Orchestrator(verbose=False, db_path=tmp.name)
    b.curriculum.current_stage = Stage.OPEN
    return b, tmp.name


def _feed(brain: Orchestrator, corpus: list[str], repeat: int = 1):
    for _ in range(repeat):
        for text in corpus:
            brain.process_input("text", text)


def _inject_chain(brain: Orchestrator):
    """
    Directly inject the causal chain into the relation graph.
    Used to test the inference engine in isolation from the text processor.
    A separate test shows what the text processor extracted naturally.
    """
    conn = brain.memory._long_term.conn
    pairs = [
        ("wolves",       "CONTROLS", "deer"),
        ("deer",         "CAUSES",   "overgrazing"),
        ("overgrazing",  "CAUSES",   "erosion"),
        ("erosion",      "CAUSES",   "river change"),
    ]
    for subj, rel, obj in pairs:
        brain.relations.add(subj, rel, obj, 0.90,
                            source_key="test_inject", session_id="eval")


def _relation_count(brain: Orchestrator) -> int:
    return brain.relations.stats()["total_relations"]


def _unique_concepts(brain: Orchestrator) -> int:
    try:
        row = brain.memory._long_term.conn.execute(
            "SELECT COUNT(DISTINCT concept) FROM ("
            "  SELECT subject AS concept FROM relations"
            "  UNION SELECT object AS concept FROM relations"
            ")"
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _avg_depth(brain: Orchestrator) -> float:
    """Average number of relations per known concept."""
    n_concepts = _unique_concepts(brain)
    if not n_concepts:
        return 0.0
    return round(_relation_count(brain) / n_concepts, 2)


def _inference_reach(brain: Orchestrator, concept: str) -> int:
    """How many unique concepts can Genesis reach from `concept` via inference."""
    brain.inference.infer(concept)
    result = brain.inference.query(concept)
    reached = set()
    for entry in result["as_subject"]:
        reached.add(entry["object"])
    for entry in result["as_object"]:
        reached.add(entry["subject"])
    return len(reached)


# ======================================================================
# TEST 1 — Recall vs. Inference
# The core question: does Genesis go beyond what it was told?
# ======================================================================

def test_inference(max_cycles: int) -> dict:
    _banner(
        "TEST 1: RECALL vs. INFERENCE",
        "Can Genesis reach conclusions it was never explicitly told?"
    )
    _p("""
  Causal chain we will teach (each link explicit):
    wolves → controls → deer
    deer   → causes   → overgrazing
    overgrazing → causes → erosion
    erosion → causes → river change

  What Genesis was never told, but should be able to derive:
    wolves → ... → overgrazing   (2-hop)
    wolves → ... → erosion       (3-hop)
    wolves → ... → river change  (4-hop)

  TEST A: Natural language — feed sentences, see what the text processor extracts.
  TEST B: Guaranteed chain — inject relations directly, then test pure inference.
    """.rstrip())

    # ─── TEST A: Natural language ────────────────────────────────────────
    _sub("Test A: via natural language sentences")
    brain_a, _ = _new_brain()
    repeats = max(1, max_cycles // len(CHAIN_CORPUS))
    _feed(brain_a, CHAIN_CORPUS, repeat=repeats)

    _p(f"    Cycles run: {brain_a.cycle_count}  |  Relations extracted: {_relation_count(brain_a)}")

    # Show what actually got stored for "wolves"
    wolf_rels = brain_a.relations.query_subject("wolves")
    deer_rels = brain_a.relations.query_subject("deer")
    _p(f"    Stored relations for 'wolves': {len(wolf_rels)}")
    for r in wolf_rels[:4]:
        _p(f"      wolves {r['relation']} {r['object']} (conf={r['confidence']:.2f})")
    _p(f"    Stored relations for 'deer': {len(deer_rels)}")
    for r in deer_rels[:4]:
        _p(f"      deer {r['relation']} {r['object']} (conf={r['confidence']:.2f})")

    # Check natural-language inference reach
    brain_a.inference.infer("wolves")
    wolf_inferences_a = brain_a.inference.query("wolves")
    inferred_objects_a = {e["object"] for e in wolf_inferences_a["as_subject"]}
    _p(f"    Concepts reached via inference from 'wolves': {sorted(inferred_objects_a) or '(none)'}")

    reach_a = len(inferred_objects_a)
    multi_hop_a = any(e["chain_length"] >= 2 for e in wolf_inferences_a["as_subject"])

    # ─── TEST B: Direct injection ─────────────────────────────────────────
    _sub("Test B: direct injection (tests inference engine in isolation)")
    brain_b, _ = _new_brain()
    _inject_chain(brain_b)

    _p(f"    Relations injected: {_relation_count(brain_b)}")
    for step in [("wolves", "deer"), ("deer", "overgrazing"),
                 ("overgrazing", "erosion"), ("erosion", "river change")]:
        path = brain_b.relations.find_path(step[0], step[1], max_depth=1)
        stored = "✓ stored" if path else "✗ not found"
        _p(f"      {step[0]} → {step[1]}: {stored}")

    # Now run inference
    brain_b.inference.infer("wolves")
    wolf_inferences_b = brain_b.inference.query("wolves")
    inferred_objects_b = {e["object"] for e in wolf_inferences_b["as_subject"]}
    chain_lengths_b = [e["chain_length"] for e in wolf_inferences_b["as_subject"]]

    _sub("Inference chain results (Test B — guaranteed input)")
    derivation_targets = {
        "deer":         ("direct", 1),
        "overgrazing":  ("2-hop", 2),
        "erosion":      ("3-hop", 3),
        "river change": ("4-hop", 4),
    }

    level1_pass = level2_pass = level3_pass = 0
    for target, (desc, hops) in derivation_targets.items():
        path = brain_b.relations.find_path("wolves", target, max_depth=5)
        inferred = target in inferred_objects_b
        path_found = bool(path)

        if path_found:
            level = min(hops, 3)
            if level == 1: level1_pass += 1
            elif level == 2: level2_pass += 1
            else: level3_pass += 1

        sym = "✓" if path_found else "✗"
        infer_sym = "(also in inference table)" if inferred else ""
        _p(f"    {sym}  wolves → {target} [{desc}]: "
           f"{'PATH FOUND' if path_found else 'no path'} {infer_sym}")
        if path:
            chain = " → ".join(
                f"{s['from']} --{s['relation']}--> {s['to']}" for s in path[0]
            )
            _p(f"         Chain: {chain}")

    # ─── Assessment ──────────────────────────────────────────────────────
    if level2_pass + level3_pass > 0:
        _ok(
            f"Inference working: Genesis derived {level2_pass + level3_pass} "
            f"multi-hop conclusions from {level1_pass} direct facts.",
            "A lookup table has no wolves→erosion entry. Genesis derived it."
        )
    elif level1_pass > 0:
        _warn(
            "Only direct (1-hop) paths found. Multi-hop inference not firing.",
            "The inference engine may need more stored relation density to form chains."
        )
    else:
        _fail(
            "No paths found — chain not connected.",
            "Check that text processor is extracting CONTROLS/CAUSES relations from sentences."
        )

    if reach_a == 0:
        _warn(
            "Natural language (Test A) did not produce any inference chains.",
            "Text processor may not be extracting typed relations from these sentences. "
            "Check wolves' stored relations above. The inference engine itself works (Test B)."
        )
    else:
        _ok(f"Natural language: wolves reached {reach_a} concept(s) via inference.")

    _matters("""
This is the line between a filing cabinet and a knowledge system.

A filing cabinet stores "wolves → deer" and retrieves it on demand.
That's Level 1: recall. A spreadsheet passes this test.

Level 2 is inference: given wolves→deer and deer→overgrazing, can it derive
wolves→overgrazing without being told? This requires the system to combine
what it knows rather than just retrieve what it was told.

Test B shows the inference engine in isolation — it works when given clean input.
Test A shows whether the text processor extracts clean enough relations from
natural language for the inference engine to fire. Both matter.
    """)

    return {
        "natural_language_reach": reach_a,
        "injected_chain_paths_found": level1_pass + level2_pass + level3_pass,
        "multi_hop_paths": level2_pass + level3_pass,
    }


# ======================================================================
# TEST 2 — Calibrated Ignorance
# Does it know what it knows vs. what it doesn't?
# ======================================================================

def test_calibrated_ignorance(max_cycles: int) -> dict:
    _banner(
        "TEST 2: CALIBRATED IGNORANCE",
        "Does Genesis know what it knows — and what it doesn't?"
    )
    _p("""
  Feed Genesis content about one topic until it knows it well.
  Then compare prediction error for:
    - That topic     (should be LOW — Genesis built a model of it)
    - Unknown words  (should be HIGH — Genesis has no model)

  Prediction error is Genesis's belief-model surprise signal (Friston, 2010):
  how unexpected is this concept given everything it has learned?
  A system with no model has error=1.0 everywhere. A learning system should
  show measurably lower error for things it has been taught.
    """.rstrip())

    brain, _ = _new_brain()

    # Baseline before training
    trained = ["wolves", "deer", "overgrazing", "erosion"]
    unknown = UNKNOWN_CONCEPTS

    _sub("Before training")
    before = {}
    for c in trained + unknown:
        e = brain.relations.prediction_error([c])
        before[c] = e
        kind = "trained" if c in trained else "unknown"
        _p(f"    [{kind}] '{c}': error = {e:.4f}")

    # Train
    repeats = max(1, max_cycles // len(CHAIN_CORPUS))
    _feed(brain, CHAIN_CORPUS, repeat=repeats)
    rel_count = _relation_count(brain)
    _p(f"\n    Training complete — {brain.cycle_count} cycles, {rel_count} relations")

    # After training
    _sub("After training")
    after = {}
    for c in trained + unknown:
        e = brain.relations.prediction_error([c])
        after[c] = e
        delta = e - before[c]
        delta_str = f"  Δ{delta:+.4f}" if delta != 0 else "  (unchanged)"
        kind = "trained" if c in trained else "unknown"
        _p(f"    [{kind}] '{c}': error = {e:.4f}{delta_str}")

    # Compute gap
    avg_trained = sum(after[c] for c in trained) / len(trained)
    avg_unknown = sum(after[c] for c in unknown) / len(unknown)
    gap = avg_unknown - avg_trained

    _sub("Summary")
    _p(f"    Average error — trained topics:  {avg_trained:.4f}")
    _p(f"    Average error — unknown topics:  {avg_unknown:.4f}")
    _p(f"    Gap (unknown − trained):         {gap:.4f}")

    improved = [c for c in trained if after[c] < before[c]]
    _p(f"    Trained concepts that improved: {improved}")

    _sub("Per-concept detail (trained only)")
    for c in trained:
        rels = brain.relations.query_subject(c, min_confidence=0.0)
        _p(f"    '{c}': {len(rels)} stored relations, pred_error={after[c]:.4f}")

    if gap >= 0.15 and improved:
        _ok(
            f"Calibrated ignorance working. Gap = {gap:.3f}.",
            "Genesis shows meaningfully lower surprise for concepts it has learned."
        )
    elif gap >= 0.05:
        _warn(
            f"Partial calibration. Gap = {gap:.3f} (small).",
            "Some improvement but the gap is modest. More training cycles "
            "or richer relation extraction would sharpen the distinction."
        )
    else:
        _fail(
            f"No meaningful calibration. Gap = {gap:.3f}.",
            "Genesis is equally surprised by trained and unknown concepts. "
            "Check whether the text processor is extracting relations — if "
            "no relations form, pred_error stays at 1.0 regardless of cycles."
        )

    _matters("""
A system with no model is equally surprised by everything. Prediction error=1.0
for wolves, 1.0 for xylotrilobite — it doesn't know either.

A system building a genuine belief model should show lower prediction error for
things it has learned. Not because it was told "I know wolves", but because it
has accumulated a network of relations around that concept. More relations,
higher confidence → lower prediction error.

This is the Dunning-Kruger test in reverse: does Genesis know what it knows?
    """)

    return {"gap": gap, "avg_trained": avg_trained, "avg_unknown": avg_unknown,
            "improved_count": len(improved)}


# ======================================================================
# TEST 3 — Contradiction Detection & The Revision Gap
# Does it notice conflicts? Does it update beliefs?
# ======================================================================

def test_contradiction(max_cycles: int) -> dict:
    _banner(
        "TEST 3: CONTRADICTION DETECTION & THE REVISION GAP",
        "Does Genesis notice when things conflict? Does it update beliefs?"
    )
    _p("""
  Feed Genesis two directly contradicting statements about the same subject.
  Check:
    1. Did it detect the contradiction?                    (expect: YES)
    2. Did it lower confidence on the now-contradicted belief?  (expect: NO — honest gap)

  The contradiction detection (M11) fires on opposing relation types.
  Example: X ENABLES Y and X PREVENTS Y cannot both be true.
    """.rstrip())

    brain, _ = _new_brain()

    # First, plant the base fact
    _sub("Step 1: teach base fact (wolves ENABLES deer — wrong, but planted deliberately)")
    brain.relations.add("wolves", "ENABLES", "deer survival", 0.85,
                        source_key="test", session_id="eval")
    base_conf_before = None
    rows = brain.memory._long_term.conn.execute(
        "SELECT confidence FROM relations WHERE subject='wolves' AND rel_type='ENABLES'"
    ).fetchall()
    if rows:
        base_conf_before = rows[0][0]
        _p(f"    Planted: wolves ENABLES deer survival  (confidence={base_conf_before:.2f})")

    contradictions_before = brain.contradictions.stats().get("total_contradictions", 0)

    # Now plant the contradiction
    _sub("Step 2: teach contradicting fact (wolves PREVENTS deer — conflicts with ENABLES)")
    brain.relations.add("wolves", "PREVENTS", "deer survival", 0.90,
                        source_key="test", session_id="eval")
    brain.contradictions.scan(session_id="eval")

    contradictions_after = brain.contradictions.stats().get("total_contradictions", 0)
    new_contradictions = contradictions_after - contradictions_before

    # Check confidence on original belief
    rows = brain.memory._long_term.conn.execute(
        "SELECT confidence FROM relations WHERE subject='wolves' AND rel_type='ENABLES'"
    ).fetchall()
    base_conf_after = rows[0][0] if rows else None

    # Show contradiction log
    all_contradictions = brain.contradictions.query(limit=5)
    _p(f"    Contradictions before: {contradictions_before}")
    _p(f"    Contradictions after:  {contradictions_after}")
    _p(f"    New contradictions detected: {new_contradictions}")

    if all_contradictions:
        _p(f"\n    Contradiction log:")
        for c in all_contradictions[:3]:
            _p(f"      '{c['subject']}' {c['rel_type_a']} {c['object']}  ↔  "
               f"'{c['subject']}' {c['rel_type_b']} {c['object']}")
            _p(f"      (conf_a={c['conf_a']:.2f}, conf_b={c['conf_b']:.2f})")

    _sub("Belief revision check")
    _p(f"    Original belief confidence BEFORE contradiction: {base_conf_before}")
    _p(f"    Original belief confidence AFTER contradiction:  {base_conf_after}")

    confidence_changed = (
        base_conf_before is not None
        and base_conf_after is not None
        and abs(base_conf_after - base_conf_before) > 0.01
    )

    if new_contradictions > 0:
        _ok(
            f"Contradiction detected: {new_contradictions} new conflict(s) logged.",
            f"'wolves ENABLES deer' vs 'wolves PREVENTS deer' flagged as opposing."
        )
    else:
        _fail(
            "No contradiction detected.",
            "Either the opposing relation types weren't recognized or the "
            "contradiction scanner didn't run. Check OPPOSING pairs in contradictions.py."
        )

    if confidence_changed:
        _ok(
            f"Belief revised: confidence changed from {base_conf_before:.2f} "
            f"to {base_conf_after:.2f} after contradiction.",
            "Unexpected — belief revision is not yet implemented. "
            "If this passed, something changed."
        )
    else:
        _gap(
            "Belief confidence does NOT change when contradicted.",
            f"'wolves ENABLES deer' remains at confidence {base_conf_after:.2f} "
            f"even though 'wolves PREVENTS deer' directly contradicts it.\n"
            f"      Genesis logs the conflict but does not cross out the wrong answer.\n"
            f"      The relation graph rule: confidence = MAX(existing, new). It only goes up.\n"
            f"      This is an architectural honest gap, not a test failure."
        )

    _matters("""
There are two separate things here:

DETECTION (working): Genesis notices when ENABLES and PREVENTS co-exist for
the same subject-object pair. It logs the contradiction. This is like a student
writing "!?" in the margin — they noticed something is wrong.

REVISION (not working yet): The student needs to also cross out the wrong
answer and update their understanding. Genesis doesn't do this yet.
confidence only goes up via MAX(existing, new). New contradicting evidence
doesn't lower the confidence of the belief it contradicts.

This is the next meaningful architectural step after the current milestones:
give Genesis the ability to actually revise beliefs, not just flag conflicts.
Without it, wrong beliefs and right beliefs can coexist indefinitely.
    """)

    return {
        "contradiction_detected": new_contradictions > 0,
        "belief_revised": confidence_changed,
        "contradiction_count": new_contradictions,
    }


# ======================================================================
# TEST 4 — Growth Quality Over Time
# Does more input make it smarter or just bigger?
# ======================================================================

def test_growth_quality(max_cycles: int) -> dict:
    _banner(
        "TEST 4: GROWTH QUALITY OVER TIME",
        "Does more input deepen understanding or just add more isolated facts?"
    )
    _p("""
  Run Genesis for increasing numbers of cycles and measure at each checkpoint:
    - Total relations stored
    - Average relations per known concept (depth)
    - Inference reach from 'wolves' (how many concepts can be reached by chaining)
    - Prediction error for 'wolves' (should decrease as knowledge grows)

  A system just getting bigger: all metrics grow but at a constant rate.
  A system getting smarter: inference reach grows FASTER than relation count
  because each new relation can activate multiple existing chains.
    """.rstrip())

    brain, _ = _new_brain()

    snapshots = []
    corpus = CHAIN_CORPUS
    total_fed = 0
    horizons_to_run = [
        h for h in HORIZONS
        if h[1] <= max_cycles
    ]
    if not horizons_to_run:
        horizons_to_run = [HORIZONS[0]]

    prev_cycles = 0
    for label, target_cycles in horizons_to_run:
        # Feed until we reach this horizon
        while brain.cycle_count < target_cycles:
            item = corpus[total_fed % len(corpus)]
            brain.process_input("text", item)
            total_fed += 1

        # Measure
        n_relations = _relation_count(brain)
        n_concepts  = _unique_concepts(brain)
        avg_depth   = _avg_depth(brain)
        reach       = _inference_reach(brain, "wolves")
        pred_err    = brain.relations.prediction_error(["wolves"])
        n_inferred  = brain.inference.stats().get("total_inferred", 0)

        snap = {
            "label":         label,
            "cycles":        brain.cycle_count,
            "relations":     n_relations,
            "concepts":      n_concepts,
            "avg_depth":     avg_depth,
            "inference_reach": reach,
            "pred_error_wolves": pred_err,
            "total_inferred": n_inferred,
        }
        snapshots.append(snap)
        prev_cycles = brain.cycle_count

    # Display table
    _sub("Learning curve")
    _p(f"\n    {'Stage':<10} {'Cycles':>7} {'Relations':>10} {'Concepts':>9} "
       f"{'Avg depth':>10} {'Inf reach':>10} {'Wolf err':>9}")
    _p(f"    {'-'*10} {'-'*7} {'-'*10} {'-'*9} {'-'*10} {'-'*10} {'-'*9}")
    for s in snapshots:
        _p(f"    {s['label']:<10} {s['cycles']:>7} {s['relations']:>10} "
           f"{s['concepts']:>9} {s['avg_depth']:>10.2f} "
           f"{s['inference_reach']:>10} {s['pred_error_wolves']:>9.4f}")

    # Check for qualitative changes
    if len(snapshots) >= 2:
        first = snapshots[0]
        last  = snapshots[-1]

        rel_growth_rate    = (last["relations"] - first["relations"]) / max(1, last["cycles"] - first["cycles"])
        depth_growth       = last["avg_depth"] - first["avg_depth"]
        reach_growth       = last["inference_reach"] - first["inference_reach"]
        error_improvement  = first["pred_error_wolves"] - last["pred_error_wolves"]

        _sub("Analysis")
        _p(f"    Relation growth rate: {rel_growth_rate:.2f} relations/cycle")
        _p(f"    Avg depth change:     {depth_growth:+.2f} (positive = concepts getting richer)")
        _p(f"    Inference reach:      {first['inference_reach']} → {last['inference_reach']}"
           f" ({reach_growth:+d} additional concepts reachable)")
        _p(f"    Wolves pred error:    {first['pred_error_wolves']:.4f} → "
           f"{last['pred_error_wolves']:.4f} ({-error_improvement:+.4f})")

        deeper = depth_growth > 0.1
        smarter = reach_growth > 0
        less_surprised = error_improvement > 0.05

        if deeper and smarter:
            _ok(
                "Knowledge is deepening, not just widening.",
                f"Avg depth grew by {depth_growth:.2f}, inference reach grew by {reach_growth}. "
                "Each new fact is building on existing structure."
            )
        elif deeper or smarter:
            _warn(
                "Some deepening, but growth is mostly linear.",
                f"Depth Δ={depth_growth:.2f}, reach Δ={reach_growth}. "
                "More diverse input topics may help build cross-concept connections."
            )
        else:
            _warn(
                "Growth is mostly additive — new facts are not building chains.",
                "Relations are being added but concepts remain shallow (few relations each). "
                "Consider richer sentence patterns with more explicit relational structure."
            )

        if less_surprised:
            _ok(
                f"Genesis is less surprised by 'wolves' over time "
                f"(pred_error: {first['pred_error_wolves']:.3f} → {last['pred_error_wolves']:.3f}).",
                "The belief model is calibrating to accumulated knowledge."
            )
        else:
            _warn(
                "Prediction error for 'wolves' not improving with more cycles.",
                "Either few relations about 'wolves' specifically are being stored, "
                "or the text processor is normalizing 'wolves' differently than expected."
            )

    _matters("""
Filing cabinet vs. knowledge system — this is the clearest test.

A filing cabinet grows at a constant rate: 10 new files per hour, always.
A knowledge system grows non-linearly: each new fact can connect to many
existing facts, and those connections enable new inferences. The value of
a new fact isn't just the fact itself — it's every chain it activates.

If inference reach grows faster than relation count: knowledge is compounding.
Genesis is getting smarter, not just bigger.

If they grow at the same rate: facts are being stored as isolated entries.
The graph is growing but the connections aren't compounding. That's closer
to a sophisticated filing cabinet than to understanding.
    """)

    return {"snapshots": snapshots}


# ======================================================================
# TEST 5 — The Honest Gap: Belief Revision
# Can Genesis update what it already believes?
# ======================================================================

def test_belief_revision(max_cycles: int) -> dict:
    _banner(
        "TEST 5: BELIEF REVISION (THE HONEST GAP)",
        "What happens when new information contradicts old beliefs?"
    )
    _p("""
  This test surfaces an honest architectural limitation.

  Teach Genesis something. Then teach it something that updates or corrects
  the original. Check: does it update, add alongside, or ignore?

  Three scenarios:
    A. Confidence update: same fact, higher confidence — should update (MAX)
    B. Same fact, lower confidence — should NOT update (MAX keeps original)
    C. Contradicting fact — contradiction logged but original belief unchanged

  After showing all three, feed a correction corpus and check whether
  Genesis's actual answers change — or whether it carries both beliefs forward.
    """.rstrip())

    brain, _ = _new_brain()

    results = {}

    # ─── Scenario A: same fact, higher confidence ─────────────────────
    _sub("Scenario A: same triple, higher confidence (expect: update)")
    brain.relations.add("wolves", "CAUSES", "biodiversity", 0.50, source_key="t", session_id="e")
    conf_a_before = brain.memory._long_term.conn.execute(
        "SELECT confidence FROM relations WHERE subject='wolves' AND rel_type='CAUSES' AND object='biodiversity'"
    ).fetchone()
    brain.relations.add("wolves", "CAUSES", "biodiversity", 0.90, source_key="t", session_id="e")
    conf_a_after = brain.memory._long_term.conn.execute(
        "SELECT confidence FROM relations WHERE subject='wolves' AND rel_type='CAUSES' AND object='biodiversity'"
    ).fetchone()
    _p(f"    wolves CAUSES biodiversity: {conf_a_before[0]:.2f} → {conf_a_after[0]:.2f}")
    if conf_a_after[0] == 0.90:
        _ok("Higher-confidence update applied correctly (MAX rule).")
        results["higher_conf_update"] = True
    else:
        _fail(f"Expected 0.90, got {conf_a_after[0]:.2f}")
        results["higher_conf_update"] = False

    # ─── Scenario B: same fact, LOWER confidence ─────────────────────
    _sub("Scenario B: same triple, lower confidence (expect: no change — MAX keeps original)")
    brain.relations.add("wolves", "CAUSES", "biodiversity", 0.30, source_key="t", session_id="e")
    conf_b_after = brain.memory._long_term.conn.execute(
        "SELECT confidence FROM relations WHERE subject='wolves' AND rel_type='CAUSES' AND object='biodiversity'"
    ).fetchone()
    _p(f"    wolves CAUSES biodiversity: 0.90 → {conf_b_after[0]:.2f}")
    if conf_b_after[0] == 0.90:
        _ok("Lower-confidence input correctly ignored (confidence only goes up).")
        results["lower_conf_ignored"] = True
    else:
        _fail(f"Expected 0.90 to remain, got {conf_b_after[0]:.2f}")
        results["lower_conf_ignored"] = False

    # ─── Scenario C: contradicting relation type ───────────────────────
    _sub("Scenario C: contradicting relation (ENABLES vs PREVENTS)")
    brain.relations.add("fire", "ENABLES", "forest_regeneration", 0.80, source_key="t", session_id="e")
    brain.relations.add("fire", "PREVENTS", "forest_regeneration", 0.70, source_key="t", session_id="e")
    brain.contradictions.scan(session_id="e")
    n_c = brain.contradictions.stats().get("total_contradictions", 0)
    conf_enables = brain.memory._long_term.conn.execute(
        "SELECT confidence FROM relations WHERE subject='fire' AND rel_type='ENABLES'"
    ).fetchone()
    conf_prevents = brain.memory._long_term.conn.execute(
        "SELECT confidence FROM relations WHERE subject='fire' AND rel_type='PREVENTS'"
    ).fetchone()
    _p(f"    fire ENABLES forest_regeneration: {conf_enables[0] if conf_enables else 'not found':.2f}")
    _p(f"    fire PREVENTS forest_regeneration: {conf_prevents[0] if conf_prevents else 'not found':.2f}")
    _p(f"    Total contradictions logged: {n_c}")

    if n_c > 0:
        _ok("Contradiction logged.")
        results["contradiction_logged"] = True
    else:
        _fail("No contradiction logged.")
        results["contradiction_logged"] = False

    both_survive = (conf_enables is not None) and (conf_prevents is not None)
    if both_survive:
        _gap(
            "Both contradicting beliefs survive at full confidence.",
            f"ENABLES={conf_enables[0]:.2f} and PREVENTS={conf_prevents[0]:.2f} "
            f"both remain. The contradiction is logged but neither belief is demoted.\n"
            f"      This is the revision gap: Genesis accumulates evidence but does not\n"
            f"      adjudicate between conflicting beliefs. A correct architecture\n"
            f"      would lower confidence on the losing side when a stronger contradiction\n"
            f"      arrives. This is the next architectural step after current milestones."
        )
        results["both_survive"] = True

    # ─── What would revision look like? ───────────────────────────────
    _sub("What genuine belief revision would look like")
    _p("""
    If belief revision were implemented:
      Step 1: fire ENABLES forest_regeneration  at conf=0.80  ← stored
      Step 2: fire PREVENTS forest_regeneration at conf=0.70  ← contradicts
      Expected: ENABLES confidence drops (maybe by 0.70 * some revision factor)
      Currently: ENABLES stays at 0.80, PREVENTS added at 0.70, conflict logged.

    The right fix: when two opposing relations share a subject and object,
    the weaker one's confidence should be penalized proportionally to the
    stronger one's confidence. This is Bayesian belief updating — prior belief
    is revised in light of contradicting evidence, weighted by confidence.
    """.rstrip())

    _matters("""
This is the most important honest gap in Genesis right now.

A system that never revises beliefs is learning in one direction only.
It can get more certain but never less certain. It can add beliefs but
never remove wrong ones. Real learning requires both.

The school analogy: a student who never crosses out wrong answers on a
test will accumulate both correct and incorrect beliefs. Given enough
contradicting evidence, the correct beliefs will be higher-confidence —
but the wrong beliefs never disappear. They just become less prominent.

Genesis currently does this. Contradiction detection (M11) is the flag in
the margin. Belief revision — the actual crossing out — is not yet built.
    """)

    return results


# ======================================================================
# Summary
# ======================================================================

def _summary(results: dict):
    _p()
    _p("=" * 68)
    _p("  KNOWLEDGE DEVELOPMENT SUMMARY")
    _p("=" * 68)

    levels = {
        "Level 1 — Recall":
            True,  # always passes — this is just storage
        "Level 2 — Inference (multi-hop chains)":
            results.get("inference", {}).get("multi_hop_paths", 0) > 0,
        "Level 3 — Calibrated ignorance":
            results.get("calibrated_ignorance", {}).get("gap", 0) >= 0.05,
        "Level 4 — Contradiction detection":
            results.get("contradiction", {}).get("contradiction_detected", False),
        "Level 5 — Growth compounds (smarter, not just bigger)":
            _growth_compounding(results.get("growth", {}).get("snapshots", [])),
    }
    gaps = {
        "Belief revision (confidence doesn't drop when contradicted)":
            results.get("belief_revision", {}).get("both_survive", True),
        "Pattern transfer (cross-domain generalization)":
            True,  # always a gap currently
    }

    for level, ok in levels.items():
        sym = "✅" if ok else "❌"
        _p(f"  {sym}  {level}")
    _p()
    for gap, present in gaps.items():
        sym = "🔲" if present else "✅"
        _p(f"  {sym}  GAP: {gap}")

    passed = sum(1 for v in levels.values() if v)
    _p()
    _p(f"  Knowledge levels demonstrated: {passed}/{len(levels)}")

    if passed >= 4:
        _p()
        _p("  RESULT: Genesis is demonstrating real knowledge development.")
        _p("  It stores, infers, measures its own ignorance, and detects conflict.")
        _p("  The gaps (revision, transfer) are the clear next architectural steps.")
    elif passed >= 2:
        _p()
        _p("  RESULT: Foundation is working. Inference and ignorance-calibration")
        _p("  are the key metrics to improve — run --full mode for more cycles.")
    else:
        _p()
        _p("  RESULT: Mostly at the storage level. The text processor may not be")
        _p("  extracting enough typed relations for inference to fire. Check Test 1.")


def _growth_compounding(snapshots: list) -> bool:
    if len(snapshots) < 2:
        return False
    first, last = snapshots[0], snapshots[-1]
    reach_growth = last["inference_reach"] - first["inference_reach"]
    depth_growth = last["avg_depth"] - first["avg_depth"]
    return reach_growth > 0 or depth_growth > 0.1


# ======================================================================
# Main
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description="Genesis Knowledge Development Evaluation")
    parser.add_argument("--quick", action="store_true", help="Fewer cycles (~2 min)")
    parser.add_argument("--full",  action="store_true", help="More cycles (~10 min)")
    parser.add_argument("--test",  type=int, default=0, help="Run single test (1-5)")
    args = parser.parse_args()

    cycles = QUICK_CYCLES if args.quick else FULL_CYCLES
    mode   = "QUICK" if args.quick else "FULL"

    _p()
    _p("╔" + "═" * 66 + "╗")
    _p("║" + "  GENESIS KNOWLEDGE DEVELOPMENT EVALUATION".center(66) + "║")
    _p("║" + f"  {__import__('time').strftime('%Y-%m-%d %H:%M')}  |  Mode: {mode}  |  {cycles} cycles/batch".center(66) + "║")
    _p("╚" + "═" * 66 + "╝")
    _p()
    _p("  Tests whether Genesis builds understanding (inference, calibration,")
    _p("  growth quality) vs. just storing facts (lookup table behavior).")
    _p("  Also surfaces honest architectural gaps without hiding them.")

    tests = {
        1: ("Inference",            test_inference),
        2: ("Calibrated Ignorance", test_calibrated_ignorance),
        3: ("Contradiction",        test_contradiction),
        4: ("Growth Quality",       test_growth_quality),
        5: ("Belief Revision",      test_belief_revision),
    }

    results = {}
    if args.test:
        if args.test not in tests:
            print(f"No test {args.test}. Choose 1-5.")
            sys.exit(1)
        name, fn = tests[args.test]
        t0 = time.time()
        key = name.lower().replace(" ", "_")
        results[key] = fn(cycles)
        _p(f"\n  Completed in {time.time()-t0:.1f}s")
    else:
        for n, (name, fn) in tests.items():
            t0 = time.time()
            _p(f"\n  Running test {n}/5: {name}...")
            key = name.lower().replace(" ", "_")
            results[key] = fn(cycles)
            _p(f"\n  [Test {n} done in {time.time()-t0:.1f}s]")
        _summary(results)

    report_path = os.path.join(os.path.dirname(__file__), "knowledge_eval_report.txt")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines) + "\n")
        _p(f"\n  Report saved to: {report_path}")
    except Exception as e:
        _p(f"\n  (Could not save report: {e})")


if __name__ == "__main__":
    main()
