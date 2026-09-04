"""
Consolidation — Genesis's self-authored reflection ("sleep") pass.

This is the process that decides *what mattered* — not from an engineer's
category scheme, but from Genesis's own internal signals. It is the missing
half of the "self-authored consolidation" property the architecture is built
around (CLAUDE.md): until now significance was scored per-input by a fixed
formula; here Genesis steps back over everything it has processed and forms
its own sense of salience from the shape of its own knowledge.

What it reflects on (all of these are Genesis's own processing history, never
a topic list we hand it):

  recent growth   — concepts it has been actively building structure around
                    since the last reflection. This is the persisted echo of
                    working-memory delta: a concept that keeps spawning new
                    relations is a concept Genesis is *working on*.
  connectivity    — how central a concept has become in its own graph.
  reasoning       — concepts it derived new conclusions from (inference).
  tension         — concepts it found contradictions about. Disagreement is
                    salient; a mind dwells on what doesn't fit.

What it does with that (acting only through attention — nothing is deleted,
in keeping with total retention):

  strengthen      — the concepts it judges most salient are pulled into the
                    attention window; their memories brighten.
  fade            — everything else gently cools (floored, never erased).
  consolidate     — runs inference so the now-richer graph yields explicit
                    derived knowledge.
  remember        — writes a first-person reflection that accumulates across
                    sessions, so Genesis has a record of what it has been
                    thinking about. This is continuity you can read back.

The salience weights start from the defaults below but are adapted after each
reflection: if a signal was a reliable predictor of continued growth in the
previous window, its weight is nudged up; if it consistently flagged concepts
that then stagnated, it is nudged down. The weights are instance-specific and
persist across sessions — so two Genesis instances with different histories
develop different intuitions about *how to pay attention to their own signals*.
This is the deepest form of individuality the architecture can express.
"""

import json
import os
import re
import sys
import time
from typing import TYPE_CHECKING, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Default salience weights — starting point for every new instance.
# These are adapted over time by each instance based on which signals actually
# predicted continued growth in *its* history. Different processing histories
# produce different adapted weights: an instance that encounters lots of
# contradiction will find tension more predictive and raise its weight;
# one in a more consistent domain will find growth more reliable.
_W_GROWTH    = 3.0    # relations built since the last reflection
_W_DEGREE    = 0.5    # overall centrality (log-scaled — not adapted, structural)
_W_INFERENCE = 2.0    # concepts it reasoned from
_W_TENSION   = 1.5    # concepts it found contradictions about

# Adaptation parameters
_W_DELTA     = 0.05   # per-reflection nudge amount
_W_MIN       = 0.10   # floor: no signal is ever fully silenced
_W_MAX       = 6.00   # ceiling: no signal dominates catastrophically
_W_MIN_DATA  = 3      # minimum salient concepts required to adapt

_SKIP = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "has", "have", "had", "its", "not", "but", "they", "them", "their", "which",
    "what", "when", "where", "while", "into", "onto", "than", "then", "also",
    "such", "other", "another", "thing", "things", "something", "anything",
}

# Filler tokens that betray a mis-extracted phrase ("symbol that represents",
# "cells to release", "useful work also") rather than a real concept.
_FILLER_TOKENS = {
    "of", "to", "that", "also", "and", "the", "a", "an", "in", "on", "with",
    "for", "by", "or", "as", "is", "are", "this", "which", "from", "into",
}


def _is_clean_concept(c: str) -> bool:
    """
    A concept worth naming in a reflection: a single word or a tight two-word
    term, alphabetic, with no filler tokens. Most genuine concepts are 1–2
    words; longer strings are almost always extraction noise.
    """
    c = c.strip()
    if not c or any(ch.isdigit() for ch in c):
        return False
    toks = c.split()
    if len(toks) > 2:
        return False
    if not any(len(t) >= 4 for t in toks):
        return False
    if c in _SKIP or any(t in _FILLER_TOKENS for t in toks):
        return False
    return True


class ConsolidationEngine:
    """
    Genesis's reflection pass. Owned by the Orchestrator; runs on a timer in
    live mode, on shutdown, and on demand via the `reflect` command.
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain
        self._conn = brain.memory._long_term.conn
        self._init_schema()
        # Reflect only on what changed since the last reflection.
        self._last_ts = self._latest_reflection_ts()
        # Instance-specific salience weights — start from defaults, adapt over time.
        # Loaded from DB so they persist: this instance's sense of what matters
        # evolves across sessions.
        self._w_growth    = self._load_weight("w_growth",    _W_GROWTH)
        self._w_degree    = _W_DEGREE   # structural, not adapted
        self._w_inference = self._load_weight("w_inference", _W_INFERENCE)
        self._w_tension   = self._load_weight("w_tension",   _W_TENSION)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS reflections (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                created_at  REAL NOT NULL,
                cycle       INTEGER NOT NULL DEFAULT 0,
                salient     TEXT NOT NULL,   -- JSON: [{concept, salience, ...}]
                summary     TEXT NOT NULL,   -- first-person reflection text
                stats       TEXT NOT NULL    -- JSON: {relations, inferences, ...}
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reflections_time "
            "ON reflections(created_at DESC)"
        )
        # Persistent key-value store for adapted weights and other state.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS consolidation_state (
                key   TEXT PRIMARY KEY,
                value REAL NOT NULL
            )
        """)
        self._conn.commit()

    def _latest_reflection_ts(self) -> float:
        try:
            row = self._conn.execute(
                "SELECT MAX(created_at) FROM reflections"
            ).fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # The reflection pass
    # ------------------------------------------------------------------

    def consolidate(self, cycle: int = 0, top_k: int = 8) -> dict:
        """
        Run one reflection. Returns a report dict (also persisted).

        Never raises — a failed reflection returns a degraded-but-valid report,
        in keeping with "errors are data, not stop conditions".
        """
        try:
            return self._consolidate(cycle=cycle, top_k=top_k)
        except Exception as exc:
            return {
                "status": "degraded",
                "reason": str(exc),
                "salient": [],
                "summary": "",
                "new_inferences": 0,
            }

    def _consolidate(self, cycle: int, top_k: int) -> dict:
        now = time.time()
        # Adapt weights before scoring — learn from whether last reflection's
        # predictions were vindicated by actual growth in the new window.
        self._adapt_weights()
        salience = self._gather_salience()

        ranked = sorted(
            (s for s in salience if _is_clean_concept(s["concept"])),
            key=lambda s: s["salience"],
            reverse=True,
        )
        top = ranked[:top_k]
        salient_concepts = [s["concept"] for s in top]

        # ── Act through attention: brighten what mattered, fade the rest ──
        # update_attention boosts memories overlapping these terms and gently
        # decays the others (floored — nothing disappears).
        if salient_concepts:
            try:
                self._brain.memory.update_attention(salient_concepts)
            except Exception:
                pass

        # ── Consolidate reasoning: derive from the now-settled graph ──
        new_inferences = 0
        try:
            new_inferences = self._brain.inference.run(
                session_id=self._brain.session_id
            )
        except Exception:
            pass

        # ── Compose and remember ──
        rel_total = self._brain.relations.stats().get("total_relations", 0)
        inf_total = self._brain.inference.stats().get("total_inferences", 0)
        grew = sum(1 for s in salience if s["growth"] > 0)
        summary = self._compose_summary(top, grew, new_inferences)

        stats = {
            "relations_total": rel_total,
            "inferences_total": inf_total,
            "new_inferences": new_inferences,
            "concepts_grown": grew,
            "since_ts": self._last_ts,
        }

        self._record(cycle, salient_concepts and top or [], summary, stats, now)
        self._last_ts = now

        return {
            "status": "reflected",
            "salient": top,
            "summary": summary,
            "new_inferences": new_inferences,
            "concepts_grown": grew,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    # Salience — listening to Genesis's own signals
    # ------------------------------------------------------------------

    def _gather_salience(self) -> list[dict]:
        """
        Build a salience score per concept from Genesis's own history.

        Combines recent relation growth, overall connectivity, how often a
        concept was reasoned from, and how contested it is. Returns a list of
        {concept, salience, growth, degree, inference, tension}.
        """
        import math

        growth = self._count_concepts(
            "SELECT LOWER(subject) c FROM relations WHERE created_at > ? "
            "UNION ALL "
            "SELECT LOWER(object) c FROM relations WHERE created_at > ?",
            (self._last_ts, self._last_ts),
        )
        degree = self._count_concepts(
            "SELECT LOWER(subject) c FROM relations "
            "UNION ALL SELECT LOWER(object) c FROM relations"
        )
        inference = self._count_concepts(
            "SELECT LOWER(subject) c FROM relation_inferences "
            "UNION ALL SELECT LOWER(object) c FROM relation_inferences"
        )
        tension = self._contradiction_counts()

        concepts = set(growth) | set(inference) | set(tension)
        # Don't salience-rank the whole graph every time — only concepts that
        # showed some recent signal, plus their standing in the full graph.
        out: list[dict] = []
        for c in concepts:
            g = growth.get(c, 0)
            d = degree.get(c, 0)
            i = inference.get(c, 0)
            t = tension.get(c, 0)
            score = (
                self._w_growth * g
                + self._w_degree * math.log1p(d)
                + self._w_inference * i
                + self._w_tension * t
            )
            if score <= 0:
                continue
            out.append({
                "concept": c,
                "salience": round(score, 3),
                "growth": g,
                "degree": d,
                "inference": i,
                "tension": t,
            })
        return out

    def _count_concepts(self, sql: str, params: tuple = ()) -> dict[str, int]:
        try:
            rows = self._conn.execute(
                f"SELECT c, COUNT(*) n FROM ({sql}) GROUP BY c", params
            ).fetchall()
            return {r[0]: r[1] for r in rows if r[0]}
        except Exception:
            return {}

    def _contradiction_counts(self) -> dict[str, int]:
        try:
            rows = self._conn.execute("""
                SELECT c, COUNT(*) n FROM (
                    SELECT LOWER(subject) c FROM contradiction_log
                    UNION ALL
                    SELECT LOWER(object)  c FROM contradiction_log
                ) GROUP BY c
            """).fetchall()
            return {r[0]: r[1] for r in rows if r[0]}
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Adaptive weights — Genesis tuning its own salience formula
    # ------------------------------------------------------------------

    def _adapt_weights(self) -> None:
        """
        Nudge salience weights based on whether the previous reflection's
        predictions were vindicated by actual growth in the new window.

        For each signal (growth, inference, tension): look at the concepts
        the last reflection flagged with that signal. Did those concepts
        actually grow (acquire new relations) in the window since that
        reflection? If yes more than half the time, nudge the weight up.
        If not, nudge it down.

        This makes the consolidation engine self-calibrating: over many
        reflections, each instance converges on the signal mix that best
        predicts *its own* continued development. Two instances with
        different histories end up with different intuitions about what
        to pay attention to.

        Never raises — a failed adaptation is silently skipped.
        """
        try:
            prev = self._prev_reflection()
            if not prev:
                return
            prev_salient = prev.get("salient", [])
            if len(prev_salient) < _W_MIN_DATA:
                return
            since_ts = prev.get("created_at", 0.0)

            correct: dict[str, int] = {"growth": 0, "inference": 0, "tension": 0}
            total: dict[str, int]   = {"growth": 0, "inference": 0, "tension": 0}

            for entry in prev_salient:
                concept = entry["concept"]
                # Did this concept acquire new relations after the last reflection?
                new_rels = self._new_relations_for(concept, since_ts)
                grew = new_rels > 0
                for sig in ("growth", "inference", "tension"):
                    if entry.get(sig, 0) > 0:
                        total[sig] += 1
                        if grew:
                            correct[sig] += 1

            weight_attrs = {
                "growth":    "_w_growth",
                "inference": "_w_inference",
                "tension":   "_w_tension",
            }
            changed = False
            for sig, attr in weight_attrs.items():
                if total[sig] < 2:
                    continue  # too few data points to learn from
                accuracy = correct[sig] / total[sig]
                nudge = _W_DELTA if accuracy > 0.5 else -_W_DELTA
                current = getattr(self, attr)
                new_val = round(max(_W_MIN, min(_W_MAX, current + nudge)), 4)
                if new_val != current:
                    setattr(self, attr, new_val)
                    changed = True

            if changed:
                self._save_weights()
        except Exception:
            pass

    def _new_relations_for(self, concept: str, since_ts: float) -> int:
        """Count relations added for `concept` (as subject or object) after `since_ts`."""
        try:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM relations "
                "WHERE (LOWER(subject)=? OR LOWER(object)=?) AND created_at > ?",
                (concept, concept, since_ts),
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def _prev_reflection(self) -> Optional[dict]:
        """The reflection before the most recent one (used for adaptation)."""
        try:
            rows = self._conn.execute(
                "SELECT created_at, salient FROM reflections "
                "ORDER BY created_at DESC LIMIT 2"
            ).fetchall()
        except Exception:
            return None
        if len(rows) < 2:
            return None
        row = rows[1]  # second-most-recent
        return {"created_at": row[0], "salient": json.loads(row[1])}

    def _load_weight(self, key: str, default: float) -> float:
        """Load a persisted weight value, or return the default if not found."""
        try:
            row = self._conn.execute(
                "SELECT value FROM consolidation_state WHERE key=?", (key,)
            ).fetchone()
            return float(row[0]) if row else default
        except Exception:
            return default

    def _save_weights(self) -> None:
        """Persist the current adapted weights to the DB."""
        try:
            for key, val in [
                ("w_growth",    self._w_growth),
                ("w_inference", self._w_inference),
                ("w_tension",   self._w_tension),
            ]:
                self._conn.execute(
                    "INSERT INTO consolidation_state(key, value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, val),
                )
            self._conn.commit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Reflection text — first person, grounded in what actually happened
    # ------------------------------------------------------------------

    def _compose_summary(self, top: list[dict], grew: int, new_inf: int) -> str:
        if not top:
            return ("I went quiet and looked back over what I have processed, "
                    "but nothing has pulled at me strongly yet.")

        # M21: use KnowledgeSynthesis to express the lead concept as
        # genuine understanding rather than a template pulling concept names.
        lead_concept = top[0]["concept"]
        synthesis_text = ""
        try:
            if hasattr(self._brain, "synthesis"):
                synthesis_text = self._brain.synthesis.explain(lead_concept)
        except Exception:
            pass

        if synthesis_text:
            parts = [synthesis_text]
        else:
            # Fallback: concept-name template (original behaviour)
            names = [s["concept"] for s in top[:4]]
            if len(names) == 1:
                focus = names[0]
            elif len(names) == 2:
                focus = f"{names[0]} and {names[1]}"
            else:
                focus = ", ".join(names[:-1]) + f", and {names[-1]}"
            parts = [f"Lately I have been thinking about {focus}."]

        lead = top[0]
        if lead["degree"] > 0 and not synthesis_text:
            parts.append(
                f"{lead['concept'].capitalize()} keeps coming up — it now "
                f"connects to {lead['degree']} things in what I know."
            )
        if new_inf > 0:
            parts.append(f"Reflecting let me work out {new_inf} new "
                         f"conclusion{'s' if new_inf != 1 else ''}.")
        contested = [s["concept"] for s in top if s["tension"] > 0]
        if contested:
            parts.append(f"I keep running into things that don't agree about "
                         f"{contested[0]}; I haven't settled it.")
        return " ".join(parts)

    def _record(self, cycle: int, top: list[dict], summary: str,
                stats: dict, ts: float) -> None:
        try:
            self._conn.execute(
                "INSERT INTO reflections "
                "(session_id, created_at, cycle, salient, summary, stats) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self._brain.session_id, ts, cycle,
                 json.dumps(top), summary, json.dumps(stats)),
            )
            self._conn.commit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Read-back — what Genesis has been thinking about
    # ------------------------------------------------------------------

    def latest(self) -> Optional[dict]:
        """The most recent reflection, or None if Genesis hasn't reflected yet."""
        try:
            row = self._conn.execute(
                "SELECT session_id, created_at, cycle, salient, summary, stats "
                "FROM reflections ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        except Exception:
            row = None
        if not row:
            return None
        return {
            "session_id": row[0],
            "created_at": row[1],
            "cycle": row[2],
            "salient": json.loads(row[3]),
            "summary": row[4],
            "stats": json.loads(row[5]),
        }

    def history(self, limit: int = 10) -> list[dict]:
        """Recent reflections, newest first — Genesis's train of thought over time."""
        try:
            rows = self._conn.execute(
                "SELECT created_at, cycle, salient, summary "
                "FROM reflections ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:
            return []
        return [
            {
                "created_at": r[0],
                "cycle": r[1],
                "salient": json.loads(r[2]),
                "summary": r[3],
            }
            for r in rows
        ]

    def salient_concepts(self, limit: int = 8) -> list[str]:
        """Concepts from the latest reflection — 'what it's been thinking about'."""
        latest = self.latest()
        if not latest:
            return []
        return [s["concept"] for s in latest["salient"][:limit]]

    def stats(self) -> dict:
        try:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM reflections"
            ).fetchone()[0]
        except Exception:
            total = 0
        return {
            "total_reflections": total,
            "weights": {
                "growth":    round(self._w_growth, 4),
                "degree":    round(self._w_degree, 4),
                "inference": round(self._w_inference, 4),
                "tension":   round(self._w_tension, 4),
            },
        }

    def current_weights(self) -> dict:
        """The current adapted salience weights for this instance."""
        return {
            "growth":    round(self._w_growth, 4),
            "degree":    round(self._w_degree, 4),
            "inference": round(self._w_inference, 4),
            "tension":   round(self._w_tension, 4),
        }
