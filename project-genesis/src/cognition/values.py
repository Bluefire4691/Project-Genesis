"""
ValueSystem — M36 self-determined interests and values.

Mirrors how humans get values without anyone dictating them:
  nature      → the drives (M26/M34) — given, like temperament
  experience  → TASTES: per-concept accumulation of the liking signal.
                What rewarded THIS instance's processing becomes what it
                prefers.  Two instances with different histories develop
                different tastes from identical machinery.
  reflection  → VALUES: recurring consequence patterns (EthicsLens, M12)
                get promoted into held first-person value statements.  The
                valence is NOT an engineer's good/bad word list — it comes
                from Genesis's own taste for the outcome.  "Overgrazing
                keeps leading to collapse, and everything I've lived around
                collapse I've disliked → I avoid what causes it."
  society     → testimony, not directive: what the user says enters as
                evidence from a source with an M18 trust score.  It shapes
                beliefs the way a parent's words do — weighed, corroborated,
                and outgrowable.

Values then GOVERN: curiosity ranking is adjusted by taste and stance, so
what Genesis chooses to read next is partly its own preference — and every
materially value-changed choice is auditable via the M28 DecisionLog.

Values are revisable like any belief: conflicting consequence patterns
lower confidence (tension, not erasure).  Nothing here is deleted.
"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator

# Taste EMA rate — slow enough that one exciting cycle isn't a personality
_TASTE_ALPHA = 0.2
# |liking| below this isn't worth crediting (hedonic noise floor)
_LIKING_FLOOR = 0.10
# Outcome taste must be at least this strong to valence a value
_VALENCE_MIN = 0.15
# Pattern confidence needed before a consequence chain can become a value
_PATTERN_MIN_CONF = 0.5
# Curiosity-ranking gains
_TASTE_GAIN  = 0.30
_FAVOR_BOOST = 0.25
_AVOID_DROP  = -0.40

_MAX_VALUES = 20


class ValueSystem:
    """Tastes (learned interest) + values (authored stances) + governance."""

    def __init__(self, brain: "Orchestrator") -> None:
        self._brain = brain
        self._conn = brain.memory._long_term.conn
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tastes (
                concept    TEXT PRIMARY KEY,
                weight     REAL NOT NULL DEFAULT 0.0,
                samples    INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS held_values (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                subject    TEXT NOT NULL,
                stance     TEXT NOT NULL,          -- 'favor' | 'avoid'
                statement  TEXT NOT NULL,          -- first-person, with reason
                evidence   INTEGER NOT NULL DEFAULT 1,
                confidence REAL NOT NULL,
                formed_at  REAL NOT NULL,
                revised_at REAL
            )
        """)
        self._conn.commit()

    def _log_error(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Tastes — interest earned by lived reward
    # ------------------------------------------------------------------

    def credit(self, concepts, liking: float) -> None:
        """
        Attribute this cycle's liking signal to the concepts active in it.
        Called every processing cycle; cheap EMA per concept.
        """
        if abs(liking) < _LIKING_FLOOR or not concepts:
            return
        try:
            now = time.time()
            for c in set(concepts):
                c = str(c).strip().lower()
                if len(c) < 3:
                    continue
                row = self._conn.execute(
                    "SELECT weight, samples FROM tastes WHERE concept=?", (c,)
                ).fetchone()
                if row:
                    w = row[0] * (1 - _TASTE_ALPHA) + liking * _TASTE_ALPHA
                    self._conn.execute(
                        "UPDATE tastes SET weight=?, samples=?, updated_at=?"
                        " WHERE concept=?", (w, row[1] + 1, now, c))
                else:
                    self._conn.execute(
                        "INSERT INTO tastes (concept, weight, samples, updated_at)"
                        " VALUES (?, ?, 1, ?)", (c, liking * _TASTE_ALPHA, now))
            self._conn.commit()
        except Exception as exc:
            self._log_error("values.credit", exc)

    def taste_for(self, concept: str) -> float:
        """Learned preference for a concept, −1..1 (0 = no history)."""
        try:
            row = self._conn.execute(
                "SELECT weight FROM tastes WHERE concept=?",
                (concept.strip().lower(),)).fetchone()
            return row[0] if row else 0.0
        except Exception as exc:
            self._log_error("values.taste_for", exc)
            return 0.0

    def strongest_tastes(self, n: int = 6) -> list[tuple[str, float]]:
        try:
            rows = self._conn.execute(
                "SELECT concept, weight FROM tastes WHERE samples >= 2"
                " ORDER BY ABS(weight) DESC LIMIT ?", (n,)).fetchall()
            return [(r[0], round(r[1], 3)) for r in rows]
        except Exception as exc:
            self._log_error("values.strongest_tastes", exc)
            return []

    # ------------------------------------------------------------------
    # Values — authored from consequence patterns × own hedonic history
    # ------------------------------------------------------------------

    def author_from_experience(self) -> int:
        """
        Promote recurring EthicsLens consequence patterns into held values.
        The valence comes from Genesis's own taste for the OUTCOME — no
        engineer-supplied good/bad ontology.  Returns values formed/updated.
        """
        changed = 0
        try:
            scan = self._brain.ethics.scan()
            patterns = (scan.get("emergent_patterns", [])
                        + scan.get("inferred_chains", []))
            for p in patterns:
                conf = p.get("confidence", 0.0)
                if conf < _PATTERN_MIN_CONF:
                    continue
                chain = p.get("chain", "")
                if "—[" in chain:
                    subject = chain.split("—[")[0].strip()
                    outcome = chain.split("]→")[-1].strip()
                else:
                    subject = p.get("subject", "").strip()
                    outcome = p.get("object", "").strip()
                if not subject or not outcome:
                    continue

                outcome_taste = self.taste_for(outcome)
                if abs(outcome_taste) < _VALENCE_MIN:
                    continue        # no lived feeling about the outcome yet

                stance = "avoid" if outcome_taste < 0 else "favor"
                felt   = "disliked" if stance == "avoid" else "valued"
                verb   = "avoid" if stance == "avoid" else "seek out"
                statement = (f"I {verb} {subject} — in what I've processed "
                             f"it leads to {outcome}, which I've {felt} "
                             f"in my own experience")
                if self._upsert_value(subject, stance, statement, conf):
                    changed += 1
        except Exception as exc:
            self._log_error("values.author", exc)
        return changed

    def _upsert_value(self, subject: str, stance: str,
                      statement: str, conf: float) -> bool:
        subject = subject.lower()
        row = self._conn.execute(
            "SELECT id, stance, evidence, confidence FROM held_values"
            " WHERE subject=?", (subject,)).fetchone()
        now = time.time()
        if row is None:
            if self._conn.execute(
                    "SELECT COUNT(*) FROM held_values").fetchone()[0] >= _MAX_VALUES:
                return False
            self._conn.execute(
                """INSERT INTO held_values
                   (subject, stance, statement, evidence, confidence, formed_at)
                   VALUES (?, ?, ?, 1, ?, ?)""",
                (subject, stance, statement, min(0.9, conf * 0.7), now))
            self._conn.commit()
            return True
        vid, old_stance, evidence, old_conf = row
        if old_stance == stance:
            # Corroboration: evidence up, confidence up (capped)
            self._conn.execute(
                "UPDATE held_values SET evidence=?, confidence=?, revised_at=?"
                " WHERE id=?",
                (evidence + 1, min(0.9, old_conf + 0.05), now, vid))
        else:
            # The world contradicted a held value: tension, not erasure —
            # confidence drops and the statement records the conflict.
            self._conn.execute(
                "UPDATE held_values SET confidence=?, revised_at=?,"
                " statement = statement || ' (though I have seen it cut the"
                " other way too)' WHERE id=?",
                (max(0.2, old_conf - 0.15), now, vid))
        self._conn.commit()
        return True

    def held(self, limit: int = 8) -> list[dict]:
        try:
            rows = self._conn.execute(
                """SELECT subject, stance, statement, evidence, confidence
                   FROM held_values ORDER BY confidence DESC LIMIT ?""",
                (limit,)).fetchall()
            return [{"subject": r[0], "stance": r[1], "statement": r[2],
                     "evidence": r[3], "confidence": round(r[4], 2)}
                    for r in rows]
        except Exception as exc:
            self._log_error("values.held", exc)
            return []

    def stance_for(self, concept: str) -> str | None:
        try:
            row = self._conn.execute(
                "SELECT stance FROM held_values WHERE subject=?"
                " AND confidence >= 0.35", (concept.strip().lower(),)).fetchone()
            return row[0] if row else None
        except Exception as exc:
            self._log_error("values.stance_for", exc)
            return None

    # ------------------------------------------------------------------
    # Governance — preference and principle shape what gets chosen
    # ------------------------------------------------------------------

    def curiosity_adjustment(self, concept: str) -> float:
        """
        Ranking delta for a curiosity candidate: learned taste plus held
        stance.  This is where interests become Genesis's own — the base
        formula is engineered, but this term is written by its history.
        """
        adj = self.taste_for(concept) * _TASTE_GAIN
        stance = self.stance_for(concept)
        if stance == "favor":
            adj += _FAVOR_BOOST
        elif stance == "avoid":
            adj += _AVOID_DROP
        return adj
