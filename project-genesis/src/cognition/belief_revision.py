"""
Belief Revision — M18.

Implements evidence-weighted belief revision: when contradicting information
arrives, Genesis evaluates both sides by evidence strength — not by whichever
arrived first, and not by blind source authority.

Core principle: every belief is a working model, held at its current confidence
until better evidence warrants revision. "Better" means more independently
corroborated, from sources that have been reliable, with stronger structural
support in the graph.

Research grounding:
- Quine (1951) "Two Dogmas of Empiricism": beliefs form an interconnected web.
  When contradiction arrives you choose which belief to revise — and that
  choice is guided by the centrality and corroboration of each belief, not
  just the strength of the contradiction.
- AGM belief revision (Alchourrón, Gärdenfors, Makinson 1985): rational belief
  revision satisfies success (new belief is accepted), consistency (no
  contradiction after revision), and minimal change (disturb as little as
  possible). Here: revise the least-supported side.
- Wakefield principle (informal): high citation count from a single source
  chain is not independent corroboration. The Lancet paper was cited hundreds
  of times, all tracing back to one fraudulent study. Corroboration must be
  verified as independent.

Three revision outcomes when contradiction detected:
    REVISE   — new evidence substantially stronger; reduce losing confidence
    RESIST   — existing belief substantially stronger; log counter-evidence
    TENSION  — genuinely uncertain; register curiosity directive, hold both

Beliefs are NEVER erased (total retention principle). Revision means reducing
confidence toward a floor, not deletion. A belief at confidence 0.10 still
exists — it's just marked as nearly disbelieved.

Source trust is tracked per session: if a session's beliefs are repeatedly
corroborated by independent sessions, its trust score rises. If they are
repeatedly contradicted by independent sessions, trust falls. This means a
fraudulent source's contributions degrade over time as independent evidence
accumulates against them.
"""

import json
import time
from typing import Optional


# Corroboration: each additional independent session adds this bonus
_CORR_BONUS = 0.20
_CORR_CAP   = 4        # max independent sessions counted (diminishing returns)

# Evidence strength ratio thresholds for revision decisions
_REVISE_THRESHOLD  = 1.40   # new must be 1.4× stronger to trigger revision
_RESIST_THRESHOLD  = 0.714  # existing must be 1/0.714 = 1.4× stronger to resist

# How much to reduce the losing belief's confidence per revision
_MAX_REDUCTION = 0.50       # never reduce by more than 50% in a single pass

# Beliefs are never erased — minimum confidence floor
_CONFIDENCE_FLOOR = 0.10

# Default trust for any new session/source
_DEFAULT_SOURCE_TRUST = 0.75

# Trust change per revision outcome
_TRUST_WIN_DELTA  = +0.04
_TRUST_LOSE_DELTA = -0.04
_TRUST_MIN = 0.10
_TRUST_MAX = 0.99


class BeliefRevision:
    """
    Evidence-weighted belief revision, tied to the memory DB connection.

    Usage:
        br = BeliefRevision(conn)
        br.record_source(subject, rel_type, obj, session_id)  # on each add
        count = br.evaluate_and_revise(session_id)            # after contradiction scan
    """

    def __init__(self, conn):
        self._conn = conn
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        # Track every (session, relation) pairing — the corroboration ledger.
        # Multiple independent sessions storing the same triple = genuine
        # independent corroboration, not one source cited many times.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS relation_sources (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                rel_type    TEXT NOT NULL,
                object      TEXT NOT NULL,
                session_id  TEXT NOT NULL,
                added_at    REAL NOT NULL,
                UNIQUE(subject, rel_type, object, session_id)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_relsrc_triple "
            "ON relation_sources(subject, rel_type, object)"
        )

        # Source reliability ledger.
        # trust_score ∈ [0.1, 0.99]. Default 0.75.
        # Goes up when this session's beliefs are corroborated, down when contested.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS source_trust (
                source_id      TEXT PRIMARY KEY,
                trust_score    REAL NOT NULL DEFAULT 0.75,
                wins           INTEGER NOT NULL DEFAULT 0,
                losses         INTEGER NOT NULL DEFAULT 0,
                last_updated   REAL NOT NULL
            )
        """)

        # Full audit trail: what was revised, from what confidence, why.
        # Supports Genesis explaining its own epistemic history.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS belief_revisions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                subject             TEXT NOT NULL,
                revised_rel_type    TEXT NOT NULL,
                object              TEXT NOT NULL,
                old_confidence      REAL NOT NULL,
                new_confidence      REAL NOT NULL,
                outcome             TEXT NOT NULL,  -- REVISE / RESIST / TENSION
                reason              TEXT NOT NULL,
                old_strength        REAL NOT NULL,
                new_strength        REAL NOT NULL,
                opposing_rel_type   TEXT,
                revised_at          REAL NOT NULL,
                session_id          TEXT
            )
        """)

        # Add revision_status to contradiction_log if not already present.
        # Avoids re-evaluating contradictions that have already been processed.
        try:
            self._conn.execute(
                "ALTER TABLE contradiction_log ADD COLUMN revision_status TEXT DEFAULT 'pending'"
            )
        except Exception:
            pass  # column already exists

        self._conn.commit()

    # ------------------------------------------------------------------
    # Corroboration tracking
    # ------------------------------------------------------------------

    def record_source(
        self,
        subject: str,
        rel_type: str,
        obj: str,
        session_id: str,
    ) -> None:
        """
        Record that this session independently observed this relation.
        Called each time relations.add() stores a triple.
        """
        if not session_id:
            return
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO relation_sources "
                "(subject, rel_type, object, session_id, added_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (subject, rel_type, obj, session_id, time.time()),
            )
            self._conn.commit()
        except Exception:
            pass

    def corroboration_factor(self, subject: str, rel_type: str, obj: str) -> float:
        """
        How independently supported is this relation?

        Counts distinct sessions that contributed to it. Each additional
        independent session adds a bonus, capped at _CORR_CAP sessions.
        One session = 1.0. Four+ sessions = 1.0 + 4 × 0.20 = 1.80.
        """
        try:
            row = self._conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM relation_sources "
                "WHERE subject=? AND rel_type=? AND object=?",
                (subject, rel_type, obj),
            ).fetchone()
            n = row[0] if row else 0
        except Exception:
            n = 0
        bonus = min(max(0, n - 1), _CORR_CAP) * _CORR_BONUS
        return round(1.0 + bonus, 4)

    # ------------------------------------------------------------------
    # Source trust
    # ------------------------------------------------------------------

    def source_trust_score(self, session_id: str) -> float:
        """
        Trust score for a source session. Default 0.75 for unknown sources.
        """
        if not session_id:
            return _DEFAULT_SOURCE_TRUST
        try:
            row = self._conn.execute(
                "SELECT trust_score FROM source_trust WHERE source_id=?",
                (session_id,),
            ).fetchone()
            return row[0] if row else _DEFAULT_SOURCE_TRUST
        except Exception:
            return _DEFAULT_SOURCE_TRUST

    def _update_trust(self, session_id: str, won: bool) -> None:
        if not session_id:
            return
        delta = _TRUST_WIN_DELTA if won else _TRUST_LOSE_DELTA
        try:
            existing = self._conn.execute(
                "SELECT trust_score, wins, losses FROM source_trust WHERE source_id=?",
                (session_id,),
            ).fetchone()
            if existing:
                new_score = max(_TRUST_MIN, min(_TRUST_MAX, existing[0] + delta))
                wins   = existing[1] + (1 if won else 0)
                losses = existing[2] + (0 if won else 1)
                self._conn.execute(
                    "UPDATE source_trust SET trust_score=?, wins=?, losses=?, last_updated=? "
                    "WHERE source_id=?",
                    (new_score, wins, losses, time.time(), session_id),
                )
            else:
                init_score = max(_TRUST_MIN, min(_TRUST_MAX, _DEFAULT_SOURCE_TRUST + delta))
                self._conn.execute(
                    "INSERT INTO source_trust (source_id, trust_score, wins, losses, last_updated) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session_id, init_score,
                     1 if won else 0, 0 if won else 1, time.time()),
                )
            self._conn.commit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Evidence strength
    # ------------------------------------------------------------------

    def evidence_strength(
        self,
        subject: str,
        rel_type: str,
        obj: str,
        primary_session: Optional[str] = None,
    ) -> float:
        """
        How strong is the evidence for this relation?

        strength = confidence × corroboration_factor × source_trust

        A relation held at confidence 0.85, corroborated by 3 independent
        sessions (factor=1.40) from a trusted source (trust=0.80) has strength
        0.85 × 1.40 × 0.80 = 0.952. Much stronger than the same confidence
        from a single untrusted source: 0.85 × 1.0 × 0.40 = 0.34.
        """
        try:
            row = self._conn.execute(
                "SELECT confidence FROM relations "
                "WHERE subject=? AND rel_type=? AND object=?",
                (subject, rel_type, obj),
            ).fetchone()
            confidence = row[0] if row else 0.0
        except Exception:
            confidence = 0.0

        if confidence == 0.0:
            return 0.0

        corr = self.corroboration_factor(subject, rel_type, obj)

        # Use the source with highest trust among contributors if primary unknown
        trust = _DEFAULT_SOURCE_TRUST
        if primary_session:
            trust = self.source_trust_score(primary_session)
        else:
            try:
                rows = self._conn.execute(
                    "SELECT DISTINCT session_id FROM relation_sources "
                    "WHERE subject=? AND rel_type=? AND object=?",
                    (subject, rel_type, obj),
                ).fetchall()
                if rows:
                    trust = max(self.source_trust_score(r[0]) for r in rows)
            except Exception:
                pass

        return round(confidence * corr * trust, 4)

    # ------------------------------------------------------------------
    # Core revision loop
    # ------------------------------------------------------------------

    def evaluate_and_revise(self, session_id: str = "") -> int:
        """
        Process all pending contradictions and decide: REVISE, RESIST, or TENSION.

        Returns number of beliefs actually revised.
        """
        try:
            pending = self._conn.execute(
                "SELECT con_id, subject, rel_type_a, rel_type_b, object, conf_a, conf_b "
                "FROM contradiction_log "
                "WHERE revision_status = 'pending' OR revision_status IS NULL "
                "ORDER BY detected_at"
            ).fetchall()
        except Exception:
            return 0

        revised = 0
        for row in pending:
            con_id, subject, rel_a, rel_b, obj, conf_a, conf_b = row
            result = self._resolve_one(
                con_id, subject, rel_a, rel_b, obj, session_id
            )
            if result == "REVISE":
                revised += 1

        return revised

    def _resolve_one(
        self,
        con_id: int,
        subject: str,
        rel_a: str,
        rel_b: str,
        obj: str,
        session_id: str,
    ) -> str:
        """
        Evaluate one contradiction and apply the appropriate outcome.

        Returns: 'REVISE', 'RESIST', or 'TENSION'
        """
        strength_a = self.evidence_strength(subject, rel_a, obj)
        strength_b = self.evidence_strength(subject, rel_b, obj)

        if strength_a == 0.0 and strength_b == 0.0:
            self._mark_contradiction(con_id, "TENSION")
            return "TENSION"

        # Which side is stronger?
        if strength_a >= strength_b:
            winner_rel, loser_rel   = rel_a, rel_b
            winner_str, loser_str   = strength_a, strength_b
        else:
            winner_rel, loser_rel   = rel_b, rel_a
            winner_str, loser_str   = strength_b, strength_a

        ratio = winner_str / max(loser_str, 0.001)

        if ratio >= _REVISE_THRESHOLD:
            # Winner clearly stronger — revise the loser downward
            outcome = "REVISE"
            reduction = min(_MAX_REDUCTION, 0.30 * (ratio - 1.0) / ratio)
            self._apply_reduction(
                subject, loser_rel, obj, reduction,
                reason=(
                    f"Contradicts {winner_rel} on same subject-object pair. "
                    f"Evidence ratio {ratio:.2f}× favors {winner_rel} "
                    f"(strength {winner_str:.3f} vs {loser_str:.3f})."
                ),
                opposing_rel=winner_rel,
                session_id=session_id,
            )
            # Update source trust: winner's sources gain, loser's sources lose
            self._adjust_source_trust(subject, winner_rel, obj, won=True)
            self._adjust_source_trust(subject, loser_rel,  obj, won=False)

        elif ratio <= _RESIST_THRESHOLD:
            # Gap isn't decisive enough yet
            outcome = "RESIST"
            self._record_revision_audit(
                subject, loser_rel if ratio < 1.0 else winner_rel,
                obj,
                old_confidence=self._current_confidence(subject, loser_rel, obj),
                new_confidence=self._current_confidence(subject, loser_rel, obj),
                outcome="RESIST",
                reason=(
                    f"Evidence strengths too close to revise "
                    f"({winner_str:.3f} vs {loser_str:.3f}, ratio={ratio:.2f}). "
                    f"Holding in tension pending more data."
                ),
                old_strength=loser_str,
                new_strength=loser_str,
                opposing_rel=winner_rel if loser_rel == rel_a else rel_a,
                session_id=session_id,
            )
        else:
            outcome = "TENSION"

        self._mark_contradiction(con_id, outcome)
        return outcome

    # ------------------------------------------------------------------
    # Confidence reduction
    # ------------------------------------------------------------------

    def _apply_reduction(
        self,
        subject: str,
        rel_type: str,
        obj: str,
        reduction: float,
        reason: str,
        opposing_rel: str,
        session_id: str,
    ) -> None:
        """
        Reduce the confidence of the losing relation. Floor at _CONFIDENCE_FLOOR.
        Record the revision in the audit trail.
        """
        try:
            row = self._conn.execute(
                "SELECT confidence FROM relations WHERE subject=? AND rel_type=? AND object=?",
                (subject, rel_type, obj),
            ).fetchone()
            if not row:
                return
            old_conf = row[0]
            new_conf = max(_CONFIDENCE_FLOOR, old_conf * (1.0 - reduction))
            new_conf = round(new_conf, 4)

            self._conn.execute(
                "UPDATE relations SET confidence=? WHERE subject=? AND rel_type=? AND object=?",
                (new_conf, subject, rel_type, obj),
            )
            self._conn.commit()

            self._record_revision_audit(
                subject, rel_type, obj,
                old_confidence=old_conf,
                new_confidence=new_conf,
                outcome="REVISE",
                reason=reason,
                old_strength=self.evidence_strength(subject, rel_type, obj),
                new_strength=new_conf,
                opposing_rel=opposing_rel,
                session_id=session_id,
            )
        except Exception:
            pass

    def _current_confidence(self, subject: str, rel_type: str, obj: str) -> float:
        try:
            row = self._conn.execute(
                "SELECT confidence FROM relations WHERE subject=? AND rel_type=? AND object=?",
                (subject, rel_type, obj),
            ).fetchone()
            return row[0] if row else 0.0
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Trust adjustment after resolution
    # ------------------------------------------------------------------

    def _adjust_source_trust(
        self, subject: str, rel_type: str, obj: str, won: bool
    ) -> None:
        """Update trust for all sessions that contributed to this relation."""
        try:
            rows = self._conn.execute(
                "SELECT DISTINCT session_id FROM relation_sources "
                "WHERE subject=? AND rel_type=? AND object=?",
                (subject, rel_type, obj),
            ).fetchall()
            for (sid,) in rows:
                self._update_trust(sid, won=won)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cascade: when source trust drops significantly, penalize its beliefs
    # ------------------------------------------------------------------

    def cascade_trust_drop(self, session_id: str, penalty: float = 0.10) -> int:
        """
        When a source's trust drops below a threshold, proportionally reduce
        confidence on all relations that it was the PRIMARY contributor to
        (i.e., it was the only session, or the earliest session).

        This is the Wakefield mechanism: if the foundational source is
        discredited, beliefs that depended primarily on it degrade.

        Returns number of relations affected.
        """
        trust = self.source_trust_score(session_id)
        if trust > 0.35:
            return 0  # trust hasn't dropped enough to cascade yet

        try:
            # Find relations where this session is the ONLY contributor
            rows = self._conn.execute("""
                SELECT r.subject, r.rel_type, r.object, r.confidence
                FROM relations r
                WHERE EXISTS (
                    SELECT 1 FROM relation_sources rs
                    WHERE rs.subject = r.subject
                      AND rs.rel_type = r.rel_type
                      AND rs.object = r.object
                      AND rs.session_id = ?
                )
                AND (
                    SELECT COUNT(DISTINCT session_id) FROM relation_sources rs2
                    WHERE rs2.subject = r.subject
                      AND rs2.rel_type = r.rel_type
                      AND rs2.object = r.object
                ) = 1
            """, (session_id,)).fetchall()
        except Exception:
            return 0

        affected = 0
        for subj, rel_type, obj, conf in rows:
            new_conf = max(_CONFIDENCE_FLOOR, conf * (1.0 - penalty))
            try:
                self._conn.execute(
                    "UPDATE relations SET confidence=? WHERE subject=? AND rel_type=? AND object=?",
                    (round(new_conf, 4), subj, rel_type, obj),
                )
                affected += 1
            except Exception:
                pass

        if affected:
            self._conn.commit()

        return affected

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------

    def _record_revision_audit(
        self,
        subject: str,
        rel_type: str,
        obj: str,
        old_confidence: float,
        new_confidence: float,
        outcome: str,
        reason: str,
        old_strength: float,
        new_strength: float,
        opposing_rel: Optional[str],
        session_id: str,
    ) -> None:
        try:
            self._conn.execute("""
                INSERT INTO belief_revisions
                    (subject, revised_rel_type, object,
                     old_confidence, new_confidence, outcome, reason,
                     old_strength, new_strength, opposing_rel_type,
                     revised_at, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                subject, rel_type, obj,
                round(old_confidence, 4), round(new_confidence, 4),
                outcome, reason,
                round(old_strength, 4), round(new_strength, 4),
                opposing_rel, time.time(), session_id,
            ))
            self._conn.commit()
        except Exception:
            pass

    def _mark_contradiction(self, con_id: int, status: str) -> None:
        try:
            self._conn.execute(
                "UPDATE contradiction_log SET revision_status=? WHERE con_id=?",
                (status, con_id),
            )
            self._conn.commit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def revision_history(self, limit: int = 20) -> list[dict]:
        """
        What has Genesis changed its mind about, and why?
        Only returns actual revisions (not RESIST or TENSION outcomes).
        """
        try:
            rows = self._conn.execute("""
                SELECT subject, revised_rel_type, object,
                       old_confidence, new_confidence, reason,
                       opposing_rel_type, revised_at
                FROM belief_revisions
                WHERE outcome = 'REVISE'
                ORDER BY revised_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        except Exception:
            return []
        return [
            {
                "subject":        r[0],
                "relation":       r[1],
                "object":         r[2],
                "old_confidence": r[3],
                "new_confidence": r[4],
                "reason":         r[5],
                "opposed_by":     r[6],
                "revised_at":     r[7],
            }
            for r in rows
        ]

    def pending_tensions(self, limit: int = 20) -> list[dict]:
        """Beliefs held in tension — unresolved contradictions."""
        try:
            rows = self._conn.execute("""
                SELECT c.subject, c.rel_type_a, c.rel_type_b, c.object,
                       c.conf_a, c.conf_b
                FROM contradiction_log c
                WHERE c.revision_status IN ('TENSION', 'RESIST', 'pending')
                ORDER BY c.detected_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        except Exception:
            return []
        return [
            {
                "subject": r[0],
                "rel_a":   r[1],
                "rel_b":   r[2],
                "object":  r[3],
                "conf_a":  r[4],
                "conf_b":  r[5],
            }
            for r in rows
        ]

    def source_trust_report(self, limit: int = 20) -> list[dict]:
        """Which sources have been reliable? Which have been wrong?"""
        try:
            rows = self._conn.execute("""
                SELECT source_id, trust_score, wins, losses
                FROM source_trust
                ORDER BY trust_score DESC
                LIMIT ?
            """, (limit,)).fetchall()
        except Exception:
            return []
        return [
            {
                "source": r[0],
                "trust":  round(r[1], 3),
                "wins":   r[2],
                "losses": r[3],
            }
            for r in rows
        ]

    def stats(self) -> dict:
        try:
            revisions = self._conn.execute(
                "SELECT COUNT(*) FROM belief_revisions WHERE outcome='REVISE'"
            ).fetchone()[0]
            tensions = self._conn.execute(
                "SELECT COUNT(*) FROM contradiction_log "
                "WHERE revision_status IN ('TENSION', 'RESIST')"
            ).fetchone()[0]
            sources_tracked = self._conn.execute(
                "SELECT COUNT(*) FROM source_trust"
            ).fetchone()[0]
            relations_tracked = self._conn.execute(
                "SELECT COUNT(DISTINCT subject || rel_type || object) FROM relation_sources"
            ).fetchone()[0]
        except Exception:
            revisions = tensions = sources_tracked = relations_tracked = 0

        return {
            "beliefs_revised":     revisions,
            "tensions_held":       tensions,
            "sources_tracked":     sources_tracked,
            "relations_with_provenance": relations_tracked,
        }
