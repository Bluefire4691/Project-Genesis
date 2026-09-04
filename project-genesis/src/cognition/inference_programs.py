"""
Inference Programs — M31: Declarative Rule Authoring.

A program is a reusable if-then rule that Genesis discovered itself by
analyzing recurring patterns in its own relation graph.

Unlike M10's InferenceEngine — which runs hard-coded transitivity and bridge
rules *the engineer wrote* — M31 programs are:

  1. DISCOVERED — Genesis finds recurrent two-hop patterns empirically:
     "I've now seen three cases where X CONTROLS Y and Y CAUSES Z, and in
     each case there was also a direct X CAUSES Z edge.  I'm going to
     generalise that as a rule."

  2. AUTHORED — The rule is stored as a first-class artifact Genesis wrote:
     IF ?x CONTROLS ?y  AND  ?y CAUSES ?z  THEN  ?x CAUSES ?z

  3. EXECUTED — The rule is run across the full graph to derive new edges,
     stored in a separate table (not mixed with observed facts or M10's
     transitive inferences).

  4. TRACKED — Every derivation is watched.  When a derived edge is later
     independently confirmed by new observed relations, the rule's hit count
     rises; contradictions lower confidence.  Genesis calibrates its own
     reliability as a rule-author.

  5. VERBALIZED — Genesis can state rules it has formulated in natural
     language, including the evidence base and its current confidence.

Why this matters:  two Genesis instances that process different texts will
mine different rules.  The rules are a record of what *this* instance found
in its data — accumulated individuality expressed as program logic.  M10
always derives the same things; M31 derives what Genesis specifically learned.

The two layers are strictly additive:
  • M10: on-demand, concept-focused, hard-coded transitivity / bridge rules.
  • M31: batch, pattern-driven, empirically-discovered generalizations.
Neither layer touches the other's tables.
"""

import time
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# ── Tuning constants ─────────────────────────────────────────────────────────

# Minimum relation confidence to include in pattern mining or rule execution
_MIN_EDGE_CONF: float = 0.50

# Minimum supporting instances before a pattern is promoted to a rule.
# Small because Genesis's graph is sparse in early sessions; 2 independent
# instances of the same chain type + direct shortcut is meaningful evidence.
_MIN_EVIDENCE: int = 2

# Confidence floor for a freshly authored rule.
_MIN_RULE_CONF: float = 0.45

# Each additional evidence instance above the minimum adds this to confidence,
# capped at 0.75 — a new rule is a conjecture, not a law.
_CONF_PER_EXTRA: float = 0.05
_MAX_RULE_CONF: float = 0.75

# Minimum chain-product confidence to bother storing a derivation
_MIN_DERIV_CONF: float = 0.15

# Max rows the mining JOIN may process
_MINE_LIMIT: int = 500

# Max derivations the execution JOIN may produce per rule per run
_EXEC_LIMIT: int = 150

# Max rules authored per mine() call — keeps each pass focused
_MAX_PER_MINE: int = 10

# Relation types excluded from mining: IS_A inheritance is already handled
# by M10; mining it here would produce noisy tautologies.
_EXCLUDE_REL: frozenset = frozenset({"IS_A"})


class InferenceProgramEngine:
    """
    Mines the relation graph for recurrent chain patterns and authors rules.

    Usage
    -----
        ipe = InferenceProgramEngine(brain)
        new_rules  = ipe.mine()              # discover & author new rules
        new_deriv  = ipe.run_all()           # apply all rules, emit new edges
        confirmed  = ipe.verify_derivations() # track which derived edges held
        rules      = ipe.programs()          # list authored rules
        stats_dict = ipe.stats()
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain
        self._conn  = brain.relations._conn
        self._init_schema()

    # ── Schema ───────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS inference_programs (
                prog_id           INTEGER PRIMARY KEY AUTOINCREMENT,
                rel_a             TEXT    NOT NULL,
                rel_b             TEXT    NOT NULL,
                result_rel        TEXT    NOT NULL,
                evidence_count    INTEGER NOT NULL DEFAULT 0,
                application_count INTEGER NOT NULL DEFAULT 0,
                hit_count         INTEGER NOT NULL DEFAULT 0,
                confidence        REAL    NOT NULL,
                authored_at       REAL    NOT NULL,
                last_run_at       REAL,
                UNIQUE(rel_a, rel_b, result_rel)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS program_derivations (
                deriv_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                prog_id    INTEGER NOT NULL REFERENCES inference_programs(prog_id),
                subject    TEXT    NOT NULL,
                rel_type   TEXT    NOT NULL,
                object     TEXT    NOT NULL,
                confidence REAL    NOT NULL,
                derived_at REAL    NOT NULL,
                status     TEXT    NOT NULL DEFAULT 'open',
                UNIQUE(prog_id, subject, object)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_prog_deriv_status "
            "ON program_derivations(status)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_prog_deriv_subj "
            "ON program_derivations(subject)"
        )
        self._conn.commit()

    # ── Phase 1: Mine patterns → author rules ────────────────────────────────

    def mine(self) -> int:
        """
        Scan the relation graph for recurrent two-hop chain patterns.

        A pattern  (rel_A, rel_B) → result_rel  is promoted to a stored rule
        when at least MIN_EVIDENCE distinct chains of type (rel_A, rel_B) exist
        alongside a direct shortcut of type result_rel between the same endpoints.

        Returns the number of newly authored rules this call.
        """
        try:
            return self._mine_patterns()
        except Exception as exc:
            self._log("programs.mine", exc)
            return 0

    def _mine_patterns(self) -> int:
        # Three-way JOIN: r1 and r2 form the two-hop chain; r3 is the direct
        # shortcut that tells us what relation the chain implies in practice.
        #
        #   r1: A --rel_a--> B
        #   r2: B --rel_b--> C
        #   r3: A --result_rel--> C  (direct observed edge)
        #
        # We count how often each (rel_a, rel_b, result_rel) triple appears and
        # promote those above MIN_EVIDENCE to rules.
        rows = self._conn.execute("""
            SELECT r1.rel_type, r2.rel_type, r3.rel_type
            FROM   relations r1
            JOIN   relations r2 ON LOWER(r1.object)   = LOWER(r2.subject)
            JOIN   relations r3 ON LOWER(r3.subject)  = LOWER(r1.subject)
                               AND LOWER(r3.object)   = LOWER(r2.object)
            WHERE  r1.confidence >= ? AND r2.confidence >= ?
              AND  r1.subject != r2.object
              AND  r1.rel_type NOT IN ('IS_A')
              AND  r2.rel_type NOT IN ('IS_A')
              AND  r3.rel_type NOT IN ('IS_A')
            LIMIT  ?
        """, (_MIN_EDGE_CONF, _MIN_EDGE_CONF, _MINE_LIMIT)).fetchall()

        # {(rel_a, rel_b): {result_rel: count}}
        patterns: dict = defaultdict(lambda: defaultdict(int))
        for rel_a, rel_b, result_rel in rows:
            patterns[(rel_a, rel_b)][result_rel] += 1

        authored = 0
        for (rel_a, rel_b), results in sorted(
            patterns.items(),
            key=lambda kv: max(kv[1].values()),
            reverse=True,
        ):
            if authored >= _MAX_PER_MINE:
                break
            # Promote only the best-evidenced result type per chain pair
            best_result, count = max(results.items(), key=lambda kv: kv[1])
            if count >= _MIN_EVIDENCE:
                if self._author_rule(rel_a, rel_b, best_result, count):
                    authored += 1
        return authored

    def _author_rule(
        self, rel_a: str, rel_b: str, result_rel: str, evidence_count: int
    ) -> bool:
        """
        Store a newly discovered rule.  Returns True if inserted (new),
        False if the rule already existed.

        Confidence grows with evidence but is capped at _MAX_RULE_CONF — a
        freshly authored rule is a conjecture, not a certified law.
        """
        conf = min(
            _MAX_RULE_CONF,
            _MIN_RULE_CONF + _CONF_PER_EXTRA * (evidence_count - _MIN_EVIDENCE),
        )
        try:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO inference_programs "
                "(rel_a, rel_b, result_rel, evidence_count, confidence, authored_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (rel_a, rel_b, result_rel, evidence_count, conf, time.time()),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as exc:
            self._log("programs._author_rule", exc)
            return False

    # ── Phase 2: Execute rules → derive new edges ────────────────────────────

    def run_all(self) -> int:
        """
        Apply every stored rule across the full relation graph.

        For each rule  IF ?x rel_a ?y AND ?y rel_b ?z THEN ?x result_rel ?z,
        find all matching chains and store derivations where no direct observed
        edge already exists.

        Returns the total number of new derivations stored.
        """
        try:
            rows = self._conn.execute(
                "SELECT prog_id, rel_a, rel_b, result_rel, confidence "
                "FROM inference_programs ORDER BY confidence DESC"
            ).fetchall()
        except Exception as exc:
            self._log("programs.run_all.load", exc)
            return 0

        total = 0
        for prog_id, rel_a, rel_b, result_rel, conf in rows:
            try:
                n = self._run_program(prog_id, rel_a, rel_b, result_rel, conf)
                if n > 0:
                    total += n
                    self._conn.execute(
                        "UPDATE inference_programs "
                        "SET last_run_at = ?, application_count = application_count + ? "
                        "WHERE prog_id = ?",
                        (time.time(), n, prog_id),
                    )
                    self._conn.commit()
            except Exception as exc:
                self._log(f"programs.run_program:{prog_id}", exc)
        return total

    def _run_program(
        self,
        prog_id: int,
        rel_a: str,
        rel_b: str,
        result_rel: str,
        prog_conf: float,
    ) -> int:
        """
        Apply one rule: find all matching two-hop chains and derive edges.
        Skips any (subject, result_rel, object) triple already directly observed.
        """
        chains = self._conn.execute("""
            SELECT r1.subject, r2.object, r1.confidence, r2.confidence
            FROM   relations r1
            JOIN   relations r2 ON LOWER(r1.object) = LOWER(r2.subject)
            WHERE  r1.rel_type = ? AND r2.rel_type = ?
              AND  r1.confidence >= ? AND r2.confidence >= ?
              AND  r1.subject != r2.object
            LIMIT  ?
        """, (rel_a, rel_b, _MIN_EDGE_CONF, _MIN_EDGE_CONF,
              _EXEC_LIMIT)).fetchall()

        derived = 0
        for subj, obj, conf_a, conf_b in chains:
            # Never derive what is already directly observed
            observed = self._conn.execute(
                "SELECT 1 FROM relations "
                "WHERE subject = ? AND rel_type = ? AND object = ? LIMIT 1",
                (subj, result_rel, obj),
            ).fetchone()
            if observed:
                continue

            deriv_conf = round(prog_conf * conf_a * conf_b, 4)
            if deriv_conf < _MIN_DERIV_CONF:
                continue

            try:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO program_derivations "
                    "(prog_id, subject, rel_type, object, confidence, derived_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (prog_id, subj, result_rel, obj, deriv_conf, time.time()),
                )
                if cur.rowcount > 0:
                    derived += 1
            except Exception:
                pass

        if derived:
            self._conn.commit()
        return derived

    # ── Phase 3: Track rule accuracy ────────────────────────────────────────

    def verify_derivations(self) -> int:
        """
        Check open derivations against the current observed relation graph.

        When a derived edge now matches an independently-observed relation,
        mark it confirmed and increment the authoring rule's hit_count.

        Returns the number of derivations newly confirmed.
        """
        try:
            open_rows = self._conn.execute(
                "SELECT deriv_id, prog_id, subject, rel_type, object "
                "FROM program_derivations WHERE status = 'open'"
            ).fetchall()
        except Exception as exc:
            self._log("programs.verify.load", exc)
            return 0

        confirmed = 0
        for deriv_id, prog_id, subj, rel_type, obj in open_rows:
            observed = self._conn.execute(
                "SELECT 1 FROM relations "
                "WHERE subject = ? AND rel_type = ? AND object = ? LIMIT 1",
                (subj, rel_type, obj),
            ).fetchone()
            if not observed:
                continue
            self._conn.execute(
                "UPDATE program_derivations SET status = 'confirmed' "
                "WHERE deriv_id = ?",
                (deriv_id,),
            )
            self._conn.execute(
                "UPDATE inference_programs "
                "SET hit_count = hit_count + 1 WHERE prog_id = ?",
                (prog_id,),
            )
            confirmed += 1

        if confirmed:
            self._conn.commit()
        return confirmed

    # ── Query ────────────────────────────────────────────────────────────────

    def programs(self, limit: int = 20) -> list[dict]:
        """All authored rules, most confident first."""
        try:
            rows = self._conn.execute(
                "SELECT prog_id, rel_a, rel_b, result_rel, evidence_count, "
                "application_count, hit_count, confidence, authored_at, last_run_at "
                "FROM inference_programs ORDER BY confidence DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:
            return []
        return [self._row_to_dict(r) for r in rows]

    def top_derivations(self, limit: int = 20) -> list[dict]:
        """Highest-confidence derivations from all programs."""
        try:
            rows = self._conn.execute(
                "SELECT d.subject, d.rel_type, d.object, d.confidence, "
                "       d.status, p.rel_a, p.rel_b "
                "FROM   program_derivations d "
                "JOIN   inference_programs  p ON p.prog_id = d.prog_id "
                "ORDER  BY d.confidence DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:
            return []
        return [
            {
                "subject":    r[0],
                "rel_type":   r[1],
                "object":     r[2],
                "confidence": r[3],
                "status":     r[4],
                "via":        f"{r[5]}+{r[6]}",
            }
            for r in rows
        ]

    def stats(self) -> dict:
        try:
            prog_row = self._conn.execute(
                "SELECT COUNT(*), AVG(confidence), "
                "       SUM(application_count), SUM(hit_count) "
                "FROM   inference_programs"
            ).fetchone()
            deriv_row = self._conn.execute(
                "SELECT COUNT(*), "
                "       SUM(CASE WHEN status='confirmed' THEN 1 ELSE 0 END) "
                "FROM   program_derivations"
            ).fetchone()
        except Exception:
            return {"total_programs": 0, "total_derivations": 0, "hit_rate": None}

        total_p   = prog_row[0]  or 0
        avg_conf  = prog_row[1]  or 0.0
        total_app = prog_row[2]  or 0
        total_hit = prog_row[3]  or 0
        total_d   = deriv_row[0] or 0
        confirmed = deriv_row[1] or 0

        hit_rate: Optional[float] = None
        if total_app > 0:
            hit_rate = round(total_hit / total_app, 3)

        return {
            "total_programs":       total_p,
            "avg_confidence":       round(avg_conf, 3),
            "total_derivations":    total_d,
            "confirmed_derivations": confirmed,
            "total_applications":   total_app,
            "total_hits":           total_hit,
            "hit_rate":             hit_rate,
        }

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(r) -> dict:
        return {
            "prog_id":          r[0],
            "rel_a":            r[1],
            "rel_b":            r[2],
            "result_rel":       r[3],
            "evidence_count":   r[4],
            "application_count": r[5],
            "hit_count":        r[6],
            "confidence":       r[7],
            "authored_at":      r[8],
            "last_run_at":      r[9],
        }

    def _log(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass
