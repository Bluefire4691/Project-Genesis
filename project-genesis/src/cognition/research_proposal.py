"""
Research Proposal — M30.2: Generative Cognition (second component).

The Hypothesis Engine (M30) gave Genesis conjectures — single falsifiable
claims. This gives it the ability to *author a document*: a first-person
research direction that weaves together what it understands, what it cannot
yet explain, what it predicts, and what it intends to read to find out.

A proposal is not retrieved or templated from input text. It is composed from
Genesis's own current cognitive state at the moment of writing — its salient
concepts, its knowledge frontier, the structural parallels it has noticed, the
contradictions it is holding, and the hypotheses it has formed. Two instances
with different histories write different proposals; the same instance writes a
different proposal next week because its state has moved. The artifact is the
point: something Genesis produced that did not exist in any source, that records
an intention to find something out.

This is the difference between a mind that answers and a mind that *wonders in
an organized way*. The proposal is stored, persists across sessions, and can be
revisited — Genesis can later note which of its stated directions it actually
pursued, and what it found.

Structure of a proposal (sections degrade gracefully — absent material is
simply omitted, never faked):

    1. What I understand     — anchored on well-connected, salient concepts
    2. What I don't yet grasp — a pure knowledge gap and/or a held contradiction
    3. A parallel I've noticed — a structural analog across domains (M22)
    4. What I predict          — an open hypothesis with its rationale (M30)
    5. What I'll read to find out — concrete curiosity targets

No LLM. Everything is assembled from graph state with deterministic phrasing.
"""

import json
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Concept must have at least this confidence on its edges to anchor "understand"
_ANCHOR_CONF = 0.6

# A gap concept needs at least this many incoming references to be worth naming
# (something Genesis has met repeatedly but cannot explain)
_GAP_MIN_INCOMING = 2

# Verb phrasing for relation types, infinitive form for "may <verb>"
_VERB_BASE = {
    "CAUSES": "cause", "CONTROLS": "govern", "PREVENTS": "prevent",
    "ENABLES": "enable", "REQUIRES": "depend on", "IS_A": "be a kind of",
    "PREDATES": "prey on", "AFFECTS": "affect", "CONTAINS": "contain",
}

# Third-person singular form, for "something that <verb> X"
_VERB_3P = {
    "CAUSES": "causes", "CONTROLS": "governs", "PREVENTS": "prevents",
    "ENABLES": "enables", "REQUIRES": "depends on", "IS_A": "is a kind of",
    "PREDATES": "preys on", "AFFECTS": "affects", "CONTAINS": "contains",
}


class ResearchProposal:
    """
    Composes and stores first-person research directions from Genesis's state.

    Usage:
        rp = ResearchProposal(brain)
        doc = rp.compose()          # build + store a proposal, return its text
        latest = rp.latest()        # most recent proposal
        history = rp.history()      # past directions
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain
        self._conn = brain.relations._conn
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS research_proposals (
                prop_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle       INTEGER,
                title       TEXT,
                body        TEXT NOT NULL,
                focus       TEXT,
                targets     TEXT,
                created_at  REAL NOT NULL,
                session_id  TEXT
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_prop_time "
            "ON research_proposals(created_at DESC)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self, store: bool = True) -> Optional[str]:
        """
        Assemble a research-direction document from current cognitive state.

        Returns the document text, or None if Genesis has too little to say yet
        (an honest floor: no graph, no proposal). When store=True, persists it.
        """
        try:
            sections, focus, targets = self._build_sections()
        except Exception as exc:
            self._log("proposal.compose", exc)
            return None

        # Require at least an understanding anchor plus one forward-looking
        # section (a gap, a prediction, or something to read). Otherwise Genesis
        # has nothing genuine to propose and should say nothing.
        if len(sections) < 2:
            return None

        title = self._title(focus)
        body = self._render(title, sections)

        if store:
            self._store(title, body, focus, targets)
        return body

    def _build_sections(self) -> tuple[list[tuple[str, str]], Optional[str], list[str]]:
        """Return (ordered [(heading, paragraph)], focus_concept, read_targets)."""
        sections: list[tuple[str, str]] = []
        focus: Optional[str] = None
        targets: list[str] = []

        # ── 1. What I understand ──────────────────────────────────────────
        anchor_para, anchor = self._understand_section()
        if anchor_para:
            sections.append(("What I understand", anchor_para))
            focus = anchor

        # ── 2. What I don't yet grasp ─────────────────────────────────────
        gap_para, gap_focus = self._gap_section()
        if gap_para:
            sections.append(("What I don't yet grasp", gap_para))
            focus = focus or gap_focus
            if gap_focus:
                targets.append(gap_focus)

        # ── 3. A parallel I've noticed ────────────────────────────────────
        analog_para = self._analogy_section()
        if analog_para:
            sections.append(("A parallel I've noticed", analog_para))

        # ── 4. What I predict ─────────────────────────────────────────────
        predict_para, predict_targets = self._prediction_section()
        if predict_para:
            sections.append(("What I predict", predict_para))
            targets.extend(predict_targets)

        # ── 5. What I'll read to find out ─────────────────────────────────
        targets = list(dict.fromkeys(t for t in targets if t))[:5]
        if not targets:
            targets = self._fallback_targets()
        if targets:
            read_para = (
                "To make progress on this I intend to read about "
                f"{_english_list(targets)}. Each is a place where what I predict "
                "could be confirmed or shown wrong."
            )
            sections.append(("What I'll read to find out", read_para))

        return sections, focus, targets

    # ── Section builders ──────────────────────────────────────────────────

    def _understand_section(self) -> tuple[Optional[str], Optional[str]]:
        """Anchor on a salient, well-connected concept Genesis can actually speak to."""
        # Prefer concepts from the latest reflection (its own sense of what matters),
        # falling back to the most-connected nodes in the graph.
        candidates: list[str] = []
        try:
            candidates.extend(self._brain.consolidation.salient_concepts(limit=6))
        except Exception:
            pass
        try:
            candidates.extend(
                c["concept"] for c in self._brain.relations.most_connected(limit=8)
            )
        except Exception:
            pass

        rel = self._brain.relations
        for raw in candidates:
            concept = _clean(raw)
            if not _is_clean(concept):
                continue
            outgoing = rel.query_subject(concept, min_confidence=_ANCHOR_CONF)
            if len(outgoing) < 2:
                continue
            facts = outgoing[:3]
            phrases = [
                f"{_VERB_BASE.get(f['relation'], f['relation'].lower())} "
                f"{_clean(f['object'])}"
                for f in facts
            ]
            para = (
                f"I've built up a working picture around {concept}. From what I've "
                f"processed, it appears to {_english_list(phrases)}. This is solid "
                f"enough ground that I can reason outward from it."
            )
            return para, concept
        return None, None

    def _gap_section(self) -> tuple[Optional[str], Optional[str]]:
        """Name a pure gap and/or a held contradiction — the edge of understanding."""
        parts: list[str] = []
        focus: Optional[str] = None

        # Pure gap: high incoming references, zero outgoing explanation
        try:
            row = self._conn.execute("""
                WITH
                  inc AS (SELECT LOWER(object) AS c, COUNT(*) AS n
                          FROM relations GROUP BY LOWER(object)),
                  out AS (SELECT LOWER(subject) AS c, COUNT(*) AS n
                          FROM relations GROUP BY LOWER(subject))
                SELECT inc.c, inc.n FROM inc
                LEFT JOIN out ON inc.c = out.c
                WHERE COALESCE(out.n, 0) = 0 AND inc.n >= ?
                ORDER BY inc.n DESC LIMIT 1
            """, (_GAP_MIN_INCOMING,)).fetchone()
        except Exception:
            row = None
        if row:
            gap, incoming = _clean(row[0]), row[1]
            if _is_clean(gap):
                parts.append(
                    f"{gap} keeps surfacing — {incoming} of the things I know point "
                    f"to it — yet I cannot say what it does. I know of it without "
                    f"understanding it."
                )
                focus = gap

        # Held contradiction
        try:
            conflicts = self._brain.contradictions.query(limit=5)
        except Exception:
            conflicts = []
        if conflicts:
            c = conflicts[0]
            subj, obj = _clean(c["subject"]), _clean(c["object"])
            if _is_clean(subj) and _is_clean(obj):
                verb_a = _VERB_3P.get(c["rel_type_a"], c["rel_type_a"].lower())
                verb_b = _VERB_3P.get(c["rel_type_b"], c["rel_type_b"].lower())
                parts.append(
                    f"I am also holding a contradiction I can't resolve: {subj} has "
                    f"been described as something that {verb_a} {obj}, and elsewhere "
                    f"as something that {verb_b} it. Both cannot be unconditionally true."
                )
                focus = focus or subj

        if not parts:
            return None, None
        return " ".join(parts), focus

    def _analogy_section(self) -> Optional[str]:
        """Surface a structural parallel Genesis has detected across domains."""
        pt = getattr(self._brain, "pattern_transfer", None)
        if pt is None:
            return None
        try:
            rows = self._conn.execute(
                "SELECT concept_a, concept_b, role, match_score "
                "FROM structural_patterns ORDER BY match_score DESC LIMIT 5"
            ).fetchall()
        except Exception:
            return None
        for a, b, role, score in rows:
            a, b = _clean(a), _clean(b)
            if not (_is_clean(a) and _is_clean(b)):
                continue
            role_txt = (role or "").lower()
            role_clause = f" — both seem to act as a kind of {role_txt}" if role and role != "UNKNOWN" else ""
            return (
                f"I've noticed that {a} and {b} behave the same way structurally"
                f"{role_clause}. They come from different material, but the pattern "
                f"of how they relate to other things lines up. If that parallel is "
                f"real, what I know about one should tell me where to look in the other."
            )
        return None

    def _prediction_section(self) -> tuple[Optional[str], list[str]]:
        """State an open hypothesis with its rationale — the generative core."""
        engine = getattr(self._brain, "hypotheses", None)
        if engine is None:
            return None, []
        try:
            open_hyps = engine.open_hypotheses(limit=6)
        except Exception:
            open_hyps = []
        if not open_hyps:
            return None, []

        h = open_hyps[0]
        subj = _clean(h["subject"])
        verb = _VERB_BASE.get(h["rel_type"], h["rel_type"].lower())
        obj = _clean(h["object"] or "")
        tail = f" {obj}" if obj else " something I haven't pinned down"
        rationale = (h.get("rationale") or "").strip()
        conf_txt = _confidence_word(h.get("confidence", 0.5))

        para = (
            f"Reasoning from what I hold, I suspect {subj} may {verb}{tail}. "
            f"{rationale} "
            f"I'd put no more than {conf_txt} confidence in this yet — it is a "
            f"prediction I made, not something I've read."
        )
        targets = [subj] + engine.curiosity_targets(limit=3)
        return para, targets

    def _fallback_targets(self) -> list[str]:
        """If nothing else named targets, fall back to the curiosity frontier."""
        try:
            return [
                t for t in self._brain.curiosity_directives()[:4]
                if _is_clean(t)
            ]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _title(self, focus: Optional[str]) -> str:
        if focus:
            return f"A direction I want to pursue: {focus}"
        return "A direction I want to pursue"

    def _render(self, title: str, sections: list[tuple[str, str]]) -> str:
        lines = [title, ""]
        for heading, para in sections:
            lines.append(f"{heading}.")
            lines.append(para)
            lines.append("")
        return "\n".join(lines).strip()

    # ------------------------------------------------------------------
    # Persistence + query
    # ------------------------------------------------------------------

    def _store(self, title: str, body: str, focus: Optional[str],
               targets: list[str]) -> None:
        try:
            self._conn.execute(
                "INSERT INTO research_proposals "
                "(cycle, title, body, focus, targets, created_at, session_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    getattr(self._brain, "cycle_count", 0),
                    title, body, focus, json.dumps(targets),
                    time.time(), getattr(self._brain, "session_id", None),
                ),
            )
            self._conn.commit()
        except Exception as exc:
            self._log("proposal._store", exc)

    def latest(self) -> Optional[dict]:
        """The most recent research direction Genesis drafted."""
        try:
            row = self._conn.execute(
                "SELECT cycle, title, body, focus, targets, created_at "
                "FROM research_proposals ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        except Exception:
            row = None
        if not row:
            return None
        return self._row_to_dict(row)

    def history(self, limit: int = 10) -> list[dict]:
        """Past research directions, newest first."""
        try:
            rows = self._conn.execute(
                "SELECT cycle, title, body, focus, targets, created_at "
                "FROM research_proposals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:
            return []
        return [self._row_to_dict(r) for r in rows]

    def stats(self) -> dict:
        try:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM research_proposals"
            ).fetchone()[0]
        except Exception:
            total = 0
        return {"total_proposals": total}

    @staticmethod
    def _row_to_dict(r) -> dict:
        try:
            targets = json.loads(r[4]) if r[4] else []
        except Exception:
            targets = []
        return {
            "cycle": r[0],
            "title": r[1],
            "body": r[2],
            "focus": r[3],
            "targets": targets,
            "created_at": r[5],
        }

    def _log(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Phrasing helpers
# ---------------------------------------------------------------------------

def _clean(s: str) -> str:
    return (s or "").replace("_", " ").strip().lower()


def _is_clean(s: str) -> bool:
    """A concept worth putting in a document: 1-3 real words, no token junk."""
    if not s:
        return False
    words = s.split()
    if not (1 <= len(words) <= 3):
        return False
    return all(w.isalpha() and len(w) >= 2 for w in words)


def _english_list(items: list[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _confidence_word(conf: float) -> str:
    if conf >= 0.6:
        return "moderate"
    if conf >= 0.45:
        return "low-to-moderate"
    return "low"
