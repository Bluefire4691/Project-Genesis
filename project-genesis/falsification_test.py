#!/usr/bin/env python3
"""
Genesis Falsification Test — board item 0.3
============================================

THE QUESTION
------------
v1's relation extractor is 30 hand-written regexes (`src/processors/text.py`).
After eight months the live graph holds 89 relations over 162 concepts, a
maximum reasoning chain of 2 hops, and only 5 concepts that appear on BOTH
sides of a relation. Every faculty above the extractor — BFS inference,
curiosity, salience, contradiction, belief revision — is an algorithm
computing over that.

    Hypothesis H1: the extractor ALONE is the bottleneck.
    Prediction:    swap it for an LLM extractor emitting canonical entities
                   and inference reach rises above zero and stays there.

    If reach rises   → v1 is salvageable; the layers above it were never tested.
    If reach stays 0 → the bottleneck is architectural; the rewrite is proven.

WHAT THIS SCRIPT DOES
---------------------
Builds TWO brains on separate temp databases and feeds them the IDENTICAL
corpus, one document at a time, through the ordinary `brain.process_input`
path. Nothing else differs between the arms:

    Arm A — stock TextProcessor          (regex, or spaCy if installed)
    Arm B — LLMTextProcessor             (local llama-server)

then measures what actually decides the question:

    total relations          how much was extracted at all
    distinct concepts        graph width
    BRIDGE NODES             concepts that are both a subject and an object.
                             v1 had 5. This is the metric that matters: a
                             concept that never appears on both sides can
                             never be the middle of a chain.
    max chain length         longest directed path in the OBSERVED graph
    2+ hop chains            how many multi-hop routes exist at all
    INFERENCE REACH          rows the existing InferenceEngine derives.
                             v1: zero.
    novel derived            derived edges that were NOT already observed —
                             the honest version of "it concluded something"
    fragment rate            % of concept strings that are non-referential
    singleton rate           % of concepts appearing in exactly one edge
                             (bias-free garbage proxy — fragments are
                             unique per sentence and never recur)

Reach is measured at three checkpoints (⅓, ⅔, full corpus) because the board
asks whether it rises above zero AND STAYS THERE.

TWO CORPORA — because one hardcoded corpus cannot settle this
-------------------------------------------------------------
    designed  30 hardcoded encyclopedia-style documents (below). Dense in
              chainable relations. Measures the CEILING of each extractor
              on favourable prose. Written by hand, therefore biased by
              hand — the script reports how much of it the v1 regex table
              can even fire on.
    live      the ACTUAL 8-month input distribution, replayed read-only out
              of `data/genesis_memory.db` (the raw text of each stored text
              memory, before the processor's JSON blob). This is the corpus
              that produced 89 relations and 5 bridge nodes. It is the one
              that decides the question; the designed corpus only shows what
              is possible at best.

RUNNING
-------
    # no model needed — Arm B is reported N/A, everything else still runs
    python falsification_test.py

    # the real experiment, with llama-server up:
    #   llama-server -m Qwen3-8B-Q4_K_M.gguf -c 8192 --port 8080
    python falsification_test.py --corpus both

    python falsification_test.py --corpus live --limit 100
    python falsification_test.py --url http://localhost:8080/v1/chat/completions
    python falsification_test.py --offline        # force Arm B N/A
    python falsification_test.py --repeat 2       # feed the corpus twice

To re-run the existing eval against the LLM extractor, the same one-line swap
applies (`knowledge_eval.py` builds brains via `_new_brain`):

    brain.processors["text"] = LLMTextProcessor()

WHAT THE NO-MODEL RUN ALREADY SHOWS (Arm A only, no llama-server needed)
------------------------------------------------------------------------
    designed corpus:  26 relations,  4 bridge nodes, reach 5, 6.5% fragments
    live corpus:      44 relations,  1 bridge node,  reach 0, 12% fragments,
                      94% singleton concepts, and fragments straight out of
                      the live database: "symbol that represents",
                      "dna which controls", "mammal warmblooded"

The regex extractor CAN chain on prose written to suit it, and does not on
the text Genesis actually ate. That is why both corpora are here, and why
the script prints a CONSTRUCT WARNING whenever Arm A's reach is above zero:
a corpus on which the regexes already chain cannot distinguish the two
hypotheses, however favourable the LLM's numbers look next to it.

READ THE CORPUS CAVEAT AT THE BOTTOM OF THE OUTPUT BEFORE QUOTING A VERDICT.
"""

import argparse
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from orchestrator.orchestrator import Orchestrator
from processors.text import TextProcessor
from processors.llm_text import LLMTextProcessor
from utils.types import Stage


# ======================================================================
# CORPUS — 30 encyclopedia-style documents.
#
# Design constraints, stated so the bias is auditable:
#   1. RICH IN CHAINABLE RELATIONS. Concepts deliberately recur across
#      documents so that a working extractor produces bridge nodes:
#      wolves → elk → willow → riverbank → erosion → river channel, and
#      combustion → carbon dioxide → greenhouse effect → warming → ice loss.
#   2. MIXED SYNTAX. Roughly half the relational sentences use a verb the
#      v1 regexes recognise ("causes", "controls", "requires", "prevents");
#      the rest use passives, relative clauses, appositives and
#      nominalisations, which is what real encyclopedic prose looks like.
#      The script reports the regex-trigger coverage so the reader can see
#      how much of the corpus Arm A even had a chance at.
#   3. No sentence is written in the regexes' exact template form. Doing so
#      would rig the test toward Arm A; writing every sentence in
#      deliberately hostile syntax would rig it toward Arm B.
# ======================================================================

CORPUS: list[str] = [
    # ── Trophic cascade: wolves → elk → willow → riverbank → erosion → river
    "Wolves are apex predators of the northern Rockies. Wolves hunt elk, and "
    "their presence controls elk populations across a wide range of valleys.",

    "Elk browse heavily on willow and aspen. Where elk density is high, "
    "sustained browsing prevents willow regeneration along stream margins.",

    "Willow stabilises riverbanks. The dense root mass of mature willow "
    "protects riverbank soil from being carried away by spring flooding.",

    "Loss of riverbank vegetation causes soil erosion. Bare banks collapse "
    "during high flows, and erosion widens the channel year after year.",

    "Erosion causes river channel change. Rivers that lose their banks "
    "abandon meanders, straighten, and cut deeper into the valley floor.",

    "Beavers require willow for both food and dam construction. A beaver "
    "colony cannot persist where the willow stand has been browsed out.",

    "Beaver dams create wetlands. Ponded water behind a dam raises the local "
    "water table and enables wetland plants to establish.",

    "Wetlands support amphibians and songbirds. The shallow margins of a "
    "beaver pond provide breeding habitat that a straightened river does not.",

    "The reintroduction of wolves to Yellowstone in 1995 is the best-studied "
    "case. Elk numbers fell, willow recovered in several drainages, and "
    "beaver colonies returned to streams they had abandoned.",

    "Coyotes were suppressed by returning wolves. Reduced coyote pressure "
    "allowed pronghorn fawns to survive at higher rates.",

    # ── Carbon: combustion → CO2 → greenhouse effect → warming → ice, coral
    "Combustion of fossil fuels releases carbon dioxide into the atmosphere. "
    "Coal, oil and natural gas are the three principal fossil fuels.",

    "Atmospheric carbon dioxide is a greenhouse gas. Carbon dioxide absorbs "
    "outgoing infrared radiation, which strengthens the greenhouse effect.",

    "The greenhouse effect causes global warming. Energy retained near the "
    "surface raises mean global temperature over decades.",

    "Global warming causes ice sheet melting. Greenland and West Antarctica "
    "are both losing mass, and that melting causes sea level rise.",

    "Sea level rise threatens coastal wetlands, which require sediment supply "
    "to keep pace with rising water. Where sediment is trapped behind dams, "
    "the marsh drowns.",

    "Ocean warming causes coral bleaching. Corals expel the symbiotic algae "
    "that provide most of their energy, and a bleached reef requires years "
    "of cool water to recover.",

    "Coral reefs contain enormous biodiversity. A reef shelters fish "
    "populations that support coastal fisheries throughout the tropics.",

    "Photosynthesis removes carbon dioxide from the air. Forests are "
    "therefore carbon sinks, and deforestation reduces that removal.",

    "Photosynthesis requires sunlight, water and chlorophyll. Chlorophyll, "
    "the pigment held in chloroplasts, enables plants to capture light energy.",

    "Photosynthesis produces oxygen as a by-product. Atmospheric oxygen "
    "enables aerobic respiration in animals.",

    # ── Cell physiology: respiration → ATP → contraction → calcium
    "Aerobic respiration produces ATP. Mitochondria, the organelles where "
    "respiration takes place, contain their own circular DNA.",

    "ATP enables muscle contraction. A muscle fibre without ATP remains "
    "locked, which is why rigor mortis sets in after death.",

    "Muscle contraction requires calcium ions. Calcium release from the "
    "sarcoplasmic reticulum triggers the sliding of the filaments.",

    "Insulin controls blood glucose. The hormone, secreted by the pancreas, "
    "enables glucose uptake into muscle and fat cells.",

    "Insulin deficiency causes diabetes. Persistently elevated blood glucose "
    "damages small blood vessels in the retina and the kidney.",

    # ── History / technology chains
    "The printing press enabled mass literacy in Europe. Cheap books caused "
    "a rapid spread of vernacular texts outside the monasteries.",

    "Mass literacy enabled the Reformation. Printed pamphlets carried "
    "arguments that manuscripts could never have distributed so widely.",

    "The steam engine enabled factory production. Coal-fired power freed "
    "factories from the rivers that had constrained earlier mills.",

    "Factory production caused rapid urbanisation. Crowded cities without "
    "sewers caused cholera outbreaks throughout the nineteenth century.",

    "Sanitation reform prevents cholera. Filtered water supply and separated "
    "sewage broke the transmission route that crowding had created.",
]

DEFAULT_LIVE_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "data", "genesis_memory.db")


def load_live_corpus(db_path: str, limit: int) -> list[str]:
    """
    Replay the real input distribution, read-only.

    Every text memory in the live database stores the raw input followed by
    " | {json}". We recover the raw half, drop non-prose (numeric/pattern
    payloads that were routed to the text processor), dedupe, and keep
    chronological order so the replay matches what Genesis actually saw.

    Opened with mode=ro — this script never writes to the live database.
    Returns [] if the database is missing or unreadable; the caller then
    skips the live corpus instead of failing.
    """
    import sqlite3

    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT content FROM memories WHERE source_type = 'text' "
            "ORDER BY created_at"
        ).fetchall()
        conn.close()
    except Exception as exc:                     # missing table, locked, corrupt
        _p(f"    (could not read live corpus: {type(exc).__name__}: {exc})")
        return []

    docs: list[str] = []
    seen: set[str] = set()
    for (content,) in rows:
        raw = (content or "").split(" | {")[0].strip()
        if len(raw) < 40:
            continue
        if raw.startswith(("{", "[")) or "'label':" in raw:
            continue                              # a numeric/pattern payload
        if raw in seen:
            continue
        seen.add(raw)
        docs.append(raw)
        if limit and len(docs) >= limit:
            break
    return docs


# The relation-bearing verbs the v1 regex table can fire on. Used only to
# report how much of the corpus Arm A had a template for — not to score it.
_REGEX_TRIGGERS = re.compile(
    r"\b(is an?|are an?|refers to|means|defined as|is part of|contains?|"
    r"consists? of|comprises?|made of|requires?|needs?|depends? on|relies? on|"
    r"causes?|caused|led to|leads to|results? in|resulted in|triggers?|"
    r"triggered|produces?|produced|responsible for|destroys?|kills?|"
    r"controls?|regulates?|manages?|governs?|shapes?|keeps?|kept|prevents?|"
    r"stops?|blocks?|blocked|suppresses?|protects?|defends?|enables?|allows?|"
    r"permits?|supports?|supported|facilitated|is used (?:for|to|in|as)|"
    r"provides?|supplies|eats?|feeds? on|preys? on|hunts?|increased?|"
    r"decreased?|reduced?|elevated?|affects?|affected|influences?|influenced|"
    r"is involved in|plays? an? \w* ?role in|is associated with|is related to)\b",
    re.I,
)


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
    _p("━" * 76)
    _p(f"  {title}")
    if subtitle:
        _p(f"  {subtitle}")
    _p("━" * 76)


# ======================================================================
# Fragment judge
#
# Deliberately INDEPENDENT of llm_text.canonicalize_entity. Arm B filters
# on that predicate, so scoring with it would make Arm B's fragment rate
# zero by construction and prove nothing. This judge asks a simpler,
# arm-neutral question: is this string a name, or a piece of a sentence?
# ======================================================================

_PREPOSITIONS = {
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "into",
    "about", "over", "under", "through", "during", "between", "among",
    "as", "without", "within", "across", "upon", "near", "per", "than",
}
_COPULAS = {
    "is", "are", "was", "were", "be", "been", "being", "that", "which",
    "who", "and", "or", "but", "has", "have", "had", "will", "would",
}


def looks_like_fragment(concept: str) -> bool:
    """True when a stored concept string is not a referential noun phrase."""
    words = concept.split()
    if not words:
        return True
    if len(words) > 4:
        return True
    if words[-1] in _PREPOSITIONS:
        return True
    if any(w in _COPULAS for w in words):
        return True
    if words[-1].endswith("ed") and len(words[-1]) >= 5:
        return True
    return False


# ======================================================================
# Measurement
# ======================================================================

def _conn(brain: Orchestrator):
    return brain.memory._long_term.conn


def _concepts(brain: Orchestrator) -> list[str]:
    rows = _conn(brain).execute(
        "SELECT subject AS c FROM relations UNION SELECT object AS c FROM relations"
    ).fetchall()
    return [r[0] for r in rows]


def _bridge_nodes(brain: Orchestrator) -> list[str]:
    """Concepts appearing as BOTH a subject and an object. Chains need these."""
    rows = _conn(brain).execute(
        "SELECT subject FROM relations INTERSECT SELECT object FROM relations"
    ).fetchall()
    return [r[0] for r in rows]


def _edges(brain: Orchestrator, min_conf: float = 0.5) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {}
    for subj, obj in _conn(brain).execute(
        "SELECT subject, object FROM relations WHERE confidence >= ?", (min_conf,)
    ).fetchall():
        adj.setdefault(subj, set()).add(obj)
    return adj


def _chain_stats(brain: Orchestrator, max_depth: int = 6) -> tuple[int, int]:
    """
    (longest directed path in hops, number of distinct 2+-hop start→end pairs)
    over the OBSERVED graph. Simple paths only — no revisiting a concept.
    """
    adj = _edges(brain)
    longest = 0
    multi_hop_pairs: set[tuple[str, str]] = set()

    for start in adj:
        stack = [(start, [start])]
        while stack:
            node, path = stack.pop()
            hops = len(path) - 1
            if hops > longest:
                longest = hops
            if hops >= 2:
                multi_hop_pairs.add((start, node))
            if hops >= max_depth:
                continue
            for nxt in adj.get(node, ()):
                if nxt not in path:
                    stack.append((nxt, path + [nxt]))
    return longest, len(multi_hop_pairs)


def _inference_metrics(brain: Orchestrator) -> dict:
    """Run the existing InferenceEngine over the whole graph and score it."""
    try:
        brain.inference.run(session_id="falsification")
    except Exception as exc:
        brain.survival.resilience.error_log.log("falsification.inference", exc)

    c = _conn(brain)
    total = c.execute("SELECT COUNT(*) FROM relation_inferences").fetchone()[0]
    novel = c.execute("""
        SELECT COUNT(*) FROM relation_inferences i
        WHERE NOT EXISTS (
            SELECT 1 FROM relations r
            WHERE r.subject = i.subject AND r.rel_type = i.rel_type
              AND r.object = i.object
        )
    """).fetchone()[0]
    max_chain = c.execute(
        "SELECT COALESCE(MAX(chain_len), 0) FROM relation_inferences"
    ).fetchone()[0]
    return {"reach": total, "novel": novel, "inferred_max_chain": max_chain}


def measure(brain: Orchestrator) -> dict:
    concepts = _concepts(brain)
    bridges = _bridge_nodes(brain)
    total_rel = brain.relations.stats().get("total_relations", 0)
    longest, multi_hop = _chain_stats(brain)

    # singleton concepts: appear in exactly one edge anywhere
    singletons = _conn(brain).execute("""
        SELECT COUNT(*) FROM (
            SELECT concept FROM (
                SELECT subject AS concept FROM relations
                UNION ALL SELECT object AS concept FROM relations
            ) GROUP BY concept HAVING COUNT(*) = 1
        )
    """).fetchone()[0]

    fragments = [c for c in concepts if looks_like_fragment(c)]
    inf = _inference_metrics(brain)

    return {
        "relations":      total_rel,
        "concepts":       len(concepts),
        "bridges":        len(bridges),
        "bridge_names":   sorted(bridges)[:12],
        "max_chain":      longest,
        "multi_hop":      multi_hop,
        "reach":          inf["reach"],
        "novel":          inf["novel"],
        "inf_max_chain":  inf["inferred_max_chain"],
        "fragment_rate":  (100.0 * len(fragments) / len(concepts)) if concepts else 0.0,
        "fragments":      sorted(fragments)[:8],
        "singleton_rate": (100.0 * singletons / len(concepts)) if concepts else 0.0,
        "by_type":        brain.relations.stats().get("by_type", {}),
    }


# ======================================================================
# Arms
# ======================================================================

def _new_brain() -> tuple[Orchestrator, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    brain = Orchestrator(verbose=False, db_path=tmp.name)
    brain.curriculum.current_stage = Stage.OPEN
    return brain, tmp.name


def _feed(brain: Orchestrator, docs: list[str]) -> int:
    """
    Feed documents through the ordinary orchestrator path.

    The interaction layer can pause a run (attention fixation / diversity
    collapse). We resume and retry once so both arms are guaranteed to see
    the same number of documents — otherwise the comparison is meaningless.
    """
    delivered = 0
    for doc in docs:
        result = brain.process_input("text", doc)
        if isinstance(result, dict) and result.get("status") == "paused":
            try:
                brain.interaction.resume()
            except Exception as exc:
                brain.survival.resilience.error_log.log("falsification.resume", exc)
            result = brain.process_input("text", doc)
        delivered += 1
    return delivered


def run_arm(label: str, processor, docs: list[str], checkpoints: int = 3) -> dict:
    """Build a brain, install `processor` as the text processor, feed, measure."""
    brain, db_path = _new_brain()
    brain.processors["text"] = processor
    if hasattr(processor, "_brain"):
        processor._brain = brain          # route failures to the error log

    t0 = time.time()
    step = max(1, len(docs) // checkpoints)
    trail: list[dict] = []
    fed = 0
    for i in range(0, len(docs), step):
        chunk = docs[i:i + step]
        fed += _feed(brain, chunk)
        snap = measure(brain)
        trail.append({"docs": fed, "relations": snap["relations"],
                      "bridges": snap["bridges"], "reach": snap["reach"],
                      "novel": snap["novel"]})

    final = measure(brain)
    final.update({
        "label":    label,
        "seconds":  round(time.time() - t0, 1),
        "docs":     fed,
        "trail":    trail,
        "db_path":  db_path,
        "errors":   len(getattr(brain.survival.resilience.error_log, "entries", []) or []),
    })
    if hasattr(processor, "diagnostics"):
        final["diagnostics"] = processor.diagnostics()
    return final


# ======================================================================
# Reporting
# ======================================================================

_ROWS = [
    ("Total relations",              "relations",      "{:d}"),
    ("Distinct concepts",            "concepts",       "{:d}"),
    ("BRIDGE NODES (subj AND obj)",  "bridges",        "{:d}"),
    ("Max chain length (observed)",  "max_chain",      "{:d}"),
    ("2+ hop chains",                "multi_hop",      "{:d}"),
    ("INFERENCE REACH (derived)",    "reach",          "{:d}"),
    ("  of which novel",             "novel",          "{:d}"),
    ("Max inferred chain length",    "inf_max_chain",  "{:d}"),
    ("Fragment rate %",              "fragment_rate",  "{:.1f}"),
    ("Singleton concept rate %",     "singleton_rate", "{:.1f}"),
]

# The live v1 database after eight months, for scale.
_V1_LIVE = {
    "relations": 89, "concepts": 162, "bridges": 5,
    "max_chain": 2, "reach": 0,
}


def report(arm_a: dict, arm_b: dict | None, corpus_name: str = ""):
    _banner(f"COMPARISON — {corpus_name} corpus" if corpus_name else "COMPARISON",
            "identical corpus, identical pipeline, one component swapped")

    b_col = (lambda key, fmt: fmt.format(arm_b[key])) if arm_b else (lambda key, fmt: "N/A")

    _p()
    _p(f"    {'Metric':<32}{'v1 live':>10}{'A: regex':>12}{'B: LLM':>12}")
    _p(f"    {'-'*32}{'-'*10}{'-'*12}{'-'*12}")
    for name, key, fmt in _ROWS:
        live = fmt.format(_V1_LIVE[key]) if key in _V1_LIVE else "—"
        _p(f"    {name:<32}{live:>10}{fmt.format(arm_a[key]):>12}{b_col(key, fmt):>12}")

    _p()
    _p(f"    Relation types A: {arm_a['by_type'] or '(none)'}")
    if arm_b:
        _p(f"    Relation types B: {arm_b['by_type'] or '(none)'}")

    _p()
    _p(f"    Bridge nodes A: {', '.join(arm_a['bridge_names']) or '(none)'}")
    if arm_b:
        _p(f"    Bridge nodes B: {', '.join(arm_b['bridge_names']) or '(none)'}")

    if arm_a["fragments"]:
        _p()
        _p(f"    Sample fragments A: {' | '.join(arm_a['fragments'])}")
    if arm_b and arm_b["fragments"]:
        _p(f"    Sample fragments B: {' | '.join(arm_b['fragments'])}")

    # ── trajectory: did reach rise AND STAY ──────────────────────────
    _p()
    _p("    Trajectory (does reach rise above zero and stay there?)")
    _p(f"      {'docs':>6}{'A rel':>8}{'A brid':>8}{'A reach':>9}"
       f"{'B rel':>8}{'B brid':>8}{'B reach':>9}")
    trail_b = arm_b["trail"] if arm_b else []
    for i, ta in enumerate(arm_a["trail"]):
        tb = trail_b[i] if i < len(trail_b) else None
        _p(f"      {ta['docs']:>6}{ta['relations']:>8}{ta['bridges']:>8}{ta['reach']:>9}"
           f"{(tb['relations'] if tb else '—'):>8}"
           f"{(tb['bridges'] if tb else '—'):>8}"
           f"{(tb['reach'] if tb else '—'):>9}")

    if arm_b and "diagnostics" in arm_b:
        d = arm_b["diagnostics"]
        _p()
        _p(f"    LLM extractor: {d['calls']} calls, {d['failures']} failures, "
           f"{d['triples_seen']} triples proposed, {d['triples_kept']} kept, "
           f"{d['rejected_entity']} rejected on entity form, "
           f"{d['rejected_relation']} on relation type, "
           f"{d['truncated_outputs']} doc(s) hit the 8-relation cap")

    # ── verdict ──────────────────────────────────────────────────────
    _banner(f"VERDICT — {corpus_name} corpus" if corpus_name else "VERDICT")
    if arm_b is None:
        _p()
        _p("    INCONCLUSIVE — no llama-server reachable, Arm B not run.")
        _p("    The harness itself executed end to end; Arm A numbers above are real.")
        _p()
        _p("    To decide the question, start a local server and re-run:")
        _p("      llama-server -m <model>.gguf -c 8192 --port 8080")
        _p("      python falsification_test.py")
        return

    rose = arm_b["reach"] > 0
    stayed = all(t["reach"] > 0 for t in arm_b["trail"][1:]) if len(arm_b["trail"]) > 1 else rose
    beat_a = arm_b["reach"] > arm_a["reach"]

    # Construct-validity check. The experiment asks why the LIVE graph has
    # zero reach. If the regex arm already chains on this corpus, the corpus
    # is not reproducing the condition under investigation, and no verdict
    # drawn from it transfers to the live system.
    if arm_a["reach"] > 0:
        _p()
        _p(f"    ⚠ CONSTRUCT WARNING: Arm A reached {arm_a['reach']} on this corpus, "
           f"but reaches 0 on the live graph.")
        _p("      This corpus does not reproduce v1's failure condition, so what")
        _p("      follows is a ceiling comparison, not a diagnosis. Run --corpus live.")

    _p()
    if rose and stayed and beat_a:
        _p(f"    INFERENCE REACH ROSE ABOVE ZERO AND STAYED: "
           f"{arm_a['reach']} → {arm_b['reach']} derived relations "
           f"({arm_b['novel']} of them novel).")
        _p(f"    Bridge nodes {arm_a['bridges']} → {arm_b['bridges']}; "
           f"max observed chain {arm_a['max_chain']} → {arm_b['max_chain']} hops.")
        _p()
        _p("    H1 SUPPORTED. The extractor was the bottleneck. The inference")
        _p("    engine, unchanged, produced multi-hop conclusions the moment it")
        _p("    was given canonical entities. v1's upper layers were never tested,")
        _p("    not proven broken → salvage is a real option (board item 0.4).")
    elif rose and not stayed:
        _p(f"    REACH ROSE BUT DID NOT HOLD: final reach {arm_b['reach']}, "
           f"trajectory {[t['reach'] for t in arm_b['trail']]}.")
        _p("    PARTIAL. Chains form intermittently. Look at the bridge-node count:")
        _p("    if it is not growing, canonicalisation is still too loose to make")
        _p("    the same concept recur across documents.")
    elif rose:
        _p(f"    BOTH ARMS CHAIN ON THIS CORPUS: reach A={arm_a['reach']}, "
           f"B={arm_b['reach']}. The swap did not clearly improve reach here.")
        _p("    NO VERDICT from this corpus — when the regex arm already chains,")
        _p("    the corpus is easier than the live input distribution and cannot")
        _p("    tell the two hypotheses apart. Compare bridge nodes and fragment")
        _p("    rate instead, and re-run with --corpus live.")
    else:
        _p(f"    INFERENCE REACH REMAINED ZERO with a clean extractor "
           f"({arm_b['relations']} relations, {arm_b['bridges']} bridge nodes).")
        _p()
        _p("    H1 NOT SUPPORTED. Canonical triples went in and no chain came out.")
        _p("    The bottleneck is above the extractor — the rewrite is justified")
        _p("    on evidence rather than on taste (board item 0.4).")
        _p()
        _p("    Before recording that: check bridge nodes. If Arm B also produced")
        _p("    near-zero bridges, the extractor is still the suspect and the")
        _p("    model or the prompt, not the architecture, is what failed.")


def trigger_coverage(docs: list[str]) -> tuple[int, int]:
    """(sentences containing a v1-regex-triggering verb, total sentences)."""
    sentences = [s.strip() for d in docs for s in re.split(r"[.!?]+", d) if s.strip()]
    hits = [s for s in sentences if _REGEX_TRIGGERS.search(s)]
    return len(hits), len(sentences)


def corpus_notes(designed: list[str], live: list[str]):
    _banner("CORPUS CAVEAT", "read this before quoting any verdict above")

    d_hits, d_total = trigger_coverage(designed)
    _p()
    _p(f"    DESIGNED corpus: {len(designed)} documents, {d_total} sentences.")
    _p(f"      Sentences containing a verb the v1 regex table can fire on: "
       f"{d_hits} ({100.0*d_hits/max(1,d_total):.0f}%)")
    _p("      Hardcoded and written for this test — deliberately dense in")
    _p("      chainable relations, which flatters BOTH arms: the regexes get more")
    _p("      triggers than real prose offers, and the model gets clean, short,")
    _p("      single-topic paragraphs. It measures each extractor's CEILING, not")
    _p("      field performance. What generalises from it is the RATIO between the")
    _p("      arms on bridge nodes and inference reach, not the absolute counts.")

    if live:
        l_hits, l_total = trigger_coverage(live)
        _p()
        _p(f"    LIVE corpus: {len(live)} documents, {l_total} sentences — the real")
        _p("      8-month input distribution, replayed read-only from the live DB.")
        _p(f"      Regex-trigger coverage: {l_hits} ({100.0*l_hits/max(1,l_total):.0f}%)")
        _p("      This is the distribution that produced 89 relations, 162 concepts")
        _p("      and 5 bridge nodes. It, not the designed corpus, is what board")
        _p("      item 0.4 should be decided on. A swap that lifts reach on the")
        _p("      designed corpus but not on this one has not salvaged anything.")
    else:
        _p()
        _p("    LIVE corpus: not run. Re-run with --corpus both (or --corpus live)")
        _p("      to replay the real 8-month input distribution from")
        _p(f"      {DEFAULT_LIVE_DB}. A verdict from the designed corpus alone is")
        _p("      a ceiling measurement, not a decision.")


# ======================================================================
# Main
# ======================================================================

def run_corpus(name: str, docs: list[str], args) -> None:
    """Run both arms over one corpus and report."""
    from processors.spacy_extractor import SPACY_AVAILABLE

    _banner(f"ARM A — stock TextProcessor · {name} corpus",
            f"relation path: {'spaCy dependency parse' if SPACY_AVAILABLE else '30 regexes'}")
    arm_a = run_arm("regex", TextProcessor(), docs)
    _p()
    _p(f"    {arm_a['docs']} documents in {arm_a['seconds']}s → "
       f"{arm_a['relations']} relations, {arm_a['concepts']} concepts, "
       f"{arm_a['bridges']} bridge nodes, reach {arm_a['reach']}")

    arm_b = None
    proc = LLMTextProcessor(url=args.url, model=args.model, offline=args.offline,
                            glossary=args.glossary)
    _banner(f"ARM B — LLMTextProcessor · {name} corpus",
            f"endpoint: {proc._url}"
            + ("  |  cross-document glossary ON" if args.glossary else ""))
    if args.offline:
        _p()
        _p("    SKIPPED — --offline requested.")
    elif not proc.is_available():
        _p()
        _p(f"    SKIPPED — no llama-server answering at {proc._url}.")
        _p("    Start one with:  llama-server -m <model>.gguf -c 8192 --port 8080")
        _p("    (the rest of this harness still ran — that is the point of the")
        _p("     no-model path: the experiment is testable before the model exists)")
    else:
        arm_b = run_arm("llm", proc, docs)
        _p()
        _p(f"    {arm_b['docs']} documents in {arm_b['seconds']}s → "
           f"{arm_b['relations']} relations, {arm_b['concepts']} concepts, "
           f"{arm_b['bridges']} bridge nodes, reach {arm_b['reach']}")

    report(arm_a, arm_b, corpus_name=name)


def main() -> int:
    ap = argparse.ArgumentParser(description="Genesis falsification test (board 0.3)")
    ap.add_argument("--url", default=None, help="llama-server chat-completions endpoint")
    ap.add_argument("--model", default=None, help="model name to send")
    ap.add_argument("--offline", action="store_true", help="skip Arm B (report N/A)")
    ap.add_argument("--corpus", choices=("designed", "live", "both"), default="designed",
                    help="designed = 30 hardcoded docs; live = replay the real "
                         "8-month input distribution; both = run each in turn")
    ap.add_argument("--live-db", default=DEFAULT_LIVE_DB,
                    help="live memory DB to replay (opened read-only)")
    ap.add_argument("--limit", type=int, default=60,
                    help="max documents taken from the live corpus")
    ap.add_argument("--glossary", action="store_true",
                    help="Arm B only: show the model the names already extracted, "
                         "so the same concept keeps the same string across "
                         "documents. Run it as a SEPARATE arm — it is entity "
                         "linking, a second variable, not part of the swap.")
    ap.add_argument("--repeat", type=int, default=1, help="feed the corpus N times")
    ap.add_argument("--out", default=None, help="report path (default: alongside this file)")
    args = ap.parse_args()

    designed = CORPUS * max(1, args.repeat)
    live: list[str] = []
    if args.corpus in ("live", "both"):
        live = load_live_corpus(args.live_db, args.limit) * max(1, args.repeat)

    _p()
    _p("╔" + "═" * 74 + "╗")
    _p("║" + "  GENESIS FALSIFICATION TEST — board item 0.3".center(74) + "║")
    _p("║" + f"  {time.strftime('%Y-%m-%d %H:%M')}  |  corpus: {args.corpus}  |  "
              f"identical documents per arm".center(74) + "║")
    _p("╚" + "═" * 74 + "╝")
    _p()
    _p("  Does replacing 30 regexes with an LLM extractor lift inference reach")
    _p("  above zero — and keep it there? Everything else is held constant.")

    if args.corpus in ("designed", "both"):
        run_corpus("designed", designed, args)
    if args.corpus in ("live", "both"):
        if live:
            run_corpus("live", live, args)
        else:
            _banner("LIVE CORPUS UNAVAILABLE")
            _p()
            _p(f"    No replayable text found in {args.live_db}.")
            _p("    Point --live-db at a Genesis memory database to run this arm.")

    corpus_notes(CORPUS, live)

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "falsification_report.txt")
    try:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("\n".join(_lines) + "\n")
        _p()
        _p(f"  Report saved to: {out}")
    except OSError as exc:
        _p()
        _p(f"  (Could not save report: {exc})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
