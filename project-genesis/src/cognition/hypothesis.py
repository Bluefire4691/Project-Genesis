"""
Hypothesis Engine — M30: Generative Cognition (first component).

Until now Genesis only *consumes* structure: it reads text, extracts relations,
and reflects on what it already holds. Every relation in the graph traces back
to some sentence Genesis processed. Nothing in the system produces a claim that
was not in the input.

The Hypothesis Engine is the first generative organ. It produces *new* claims —
falsifiable predictions Genesis authored itself by reasoning over its own graph,
not by reading them anywhere. A hypothesis is explicitly marked as Genesis's own
conjecture (status='open'), kept separate from observed relations, and later
*tested* against evidence the graph acquires: confirmed if subsequent reading
supports it, refuted if it contradicts. That confirm/refute loop is the
scientific method in miniature — conjecture, then seek the evidence that decides.

Three generators, each grounded in a cited mechanism:

  1. Structural analogy (Gentner 1983, structure-mapping)
     If wolves PREVENTS overgrazing, and lions is a structural analog of wolves
     (same relation-type fingerprint, detected by M22 PatternTransfer), but lions
     has no PREVENTS edge yet, hypothesize: lions PREVENTS something too. The
     prediction transfers relational structure across a surface-dissimilar pair.

  2. Contradiction moderation (held tension → hidden variable)
     If X CAUSES Y and X PREVENTS Y both hold, the simplest reconciliation is a
     hidden condition: X CAUSES Y in one regime and PREVENTS it in another.
     Genesis hypothesizes that an unobserved moderating concept governs which.

  3. Chain extension (transitive frontier)
     If A CAUSES B and B CAUSES C are both held with confidence, but A→C is not,
     hypothesize A CAUSES C. Unlike the InferenceEngine (which asserts transitive
     closure as derived fact), this stays a *prediction* flagged for verification —
     Genesis commits to it only once independent evidence appears.

Hypotheses live in their own table. They never enter the relations graph unless
confirmed, so they cannot pollute fingerprinting, contradiction scans, or the
confidence that observed facts carry. Errors are data: a refuted hypothesis is
not deleted — it is marked refuted and kept, because being wrong about something
is part of Genesis's history too.
"""

import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Confidence floor for an edge to be used as the basis of a hypothesis.
# We only conjecture from relations we are reasonably sure of.
_MIN_BASIS_CONF = 0.6

# Relation types worth transferring across structural analogs.
# IS_A and CONTAINS are taxonomic and transfer poorly ("lions is a type of X"
# tells us nothing about what lions *does*); the dynamic relations do.
_TRANSFERABLE = ("CAUSES", "CONTROLS", "PREVENTS", "PREDATES", "AFFECTS", "REQUIRES")

# Max hypotheses generated per pass — keeps conjecture focused, not a firehose.
_MAX_PER_PASS = 8

# Confidence assigned to a freshly minted hypothesis, by basis. These are
# deliberately modest: a conjecture is not a fact.
_BASIS_CONF = {
    "analogy":       0.55,
    "contradiction": 0.45,
    "chain":         0.60,
}


class HypothesisEngine:
    """
    Generates and tests Genesis's own falsifiable predictions.

    Usage:
        he = HypothesisEngine(brain)
        n_new      = he.generate()          # conjecture from current graph state
        n_resolved = he.verify()            # confirm/refute open hypotheses
        open_hyps  = he.open_hypotheses()   # what Genesis currently predicts
        targets    = he.curiosity_targets() # what to read to test them
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
            CREATE TABLE IF NOT EXISTS hypotheses (
                hyp_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                subject       TEXT NOT NULL,
                rel_type      TEXT NOT NULL,
                object        TEXT,
                basis         TEXT NOT NULL,
                source        TEXT,
                rationale     TEXT,
                confidence    REAL NOT NULL,
                status        TEXT NOT NULL DEFAULT 'open',
                created_at    REAL NOT NULL,
                resolved_at   REAL,
                evidence      TEXT,
                UNIQUE(subject, rel_type, object, basis)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hyp_status ON hypotheses(status)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hyp_subject ON hypotheses(subject)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self) -> int:
        """
        Run all three generators and store any new hypotheses.
        Returns the number of new (previously unseen) hypotheses created.
        """
        created = 0
        try:
            for subject, rel_type, obj, basis, source, rationale in self._candidates():
                if created >= _MAX_PER_PASS:
                    break
                if self._record(subject, rel_type, obj, basis, source, rationale):
                    created += 1
        except Exception as exc:
            self._log("hypothesis.generate", exc)
        return created

    def _candidates(self):
        """Yield candidate hypotheses from all generators, highest-value first."""
        yield from self._from_analogy()
        yield from self._from_contradictions()
        yield from self._from_chains()

    # ── Generator 1: structural analogy ──────────────────────────────────

    def _from_analogy(self):
        """
        Transfer a relation type across a structural-analog pair.

        wolves PREVENTS overgrazing; lions ≅ wolves; lions has no PREVENTS edge
        → HYPOTHESIS: lions PREVENTS (something).
        """
        pt = getattr(self._brain, "pattern_transfer", None)
        rel = self._brain.relations
        if pt is None:
            return

        # Concepts with a known structural role are the transfer anchors.
        try:
            rows = self._conn.execute(
                "SELECT DISTINCT concept FROM concept_roles "
                "WHERE role != 'UNKNOWN' LIMIT 60"
            ).fetchall()
        except Exception:
            return

        for (concept,) in rows:
            analogs = pt.analogs_for(concept)
            if not analogs:
                continue
            # What relation types does this concept exhibit that its analogs might share?
            outgoing = rel.query_subject(concept, min_confidence=_MIN_BASIS_CONF)
            concept_rel_types = {
                r["relation"] for r in outgoing if r["relation"] in _TRANSFERABLE
            }
            if not concept_rel_types:
                continue

            for analog in analogs:
                a_name = analog["analog"]
                a_out = rel.query_subject(a_name, min_confidence=0.4)
                a_types = {r["relation"] for r in a_out}
                for rel_type in concept_rel_types:
                    if rel_type in a_types:
                        continue  # analog already has this edge — nothing to predict
                    rationale = (
                        f"{a_name} plays the same structural role as {concept} "
                        f"(analogy score {analog['match_score']}), and {concept} "
                        f"{rel_type.lower()} something — so {a_name} likely does too."
                    )
                    # object is unknown ('?') — this is an open structural prediction
                    yield (a_name, rel_type, None, "analogy", concept, rationale)

    # ── Generator 2: contradiction moderation ────────────────────────────

    def _from_contradictions(self):
        """
        A held contradiction implies a hidden moderating variable.

        X CAUSES Y and X PREVENTS Y both hold → hypothesize that some condition
        determines which, i.e. the relationship is context-dependent.
        """
        try:
            conflicts = self._brain.contradictions.query(limit=20)
        except Exception:
            return
        for c in conflicts:
            subj = c["subject"]
            obj = c["object"]
            rationale = (
                f"I hold that {subj} both {c['rel_type_a'].lower()} and "
                f"{c['rel_type_b'].lower()} {obj}. Both cannot be unconditionally "
                f"true, so some unobserved condition likely governs which holds."
            )
            # CONTROLS captures "a moderating factor governs the subject→object link"
            yield (subj, "CONTROLS", obj, "contradiction", subj, rationale)

    # ── Generator 3: chain extension ─────────────────────────────────────

    def _from_chains(self):
        """
        A CAUSES B, B CAUSES C, but A→C not held → hypothesize A CAUSES C.
        Stays a prediction (not asserted as inference) until evidence appears.

        The second hop links on B≈subject. Because the extractor emits concepts
        at inconsistent granularity ("deer populations" in one sentence, "deer"
        in the next), an exact-string join misses real chains. We bridge a single
        content word to a multi-word concept that contains it ("deer" ↔ "deer
        populations") — precise enough to avoid spurious links, loose enough to
        survive the extractor's granularity.
        """
        rel = self._brain.relations
        try:
            causes = rel.query_relation("CAUSES", min_confidence=_MIN_BASIS_CONF, limit=80)
        except Exception:
            return

        existing = {(e["subject"], e["object"]) for e in causes}
        for edge in causes:
            a, b = edge["subject"], edge["object"]
            for second in causes:
                if not _chain_linkable(b, second["subject"]):
                    continue
                c = second["object"]
                if c == a or c == b or (a, c) in existing:
                    continue
                bridge = b if b == second["subject"] else f"{b}/{second['subject']}"
                rationale = (
                    f"{a} causes {b}, and {second['subject']} causes {c}. "
                    f"If both hold, {a} may cause {c} indirectly."
                )
                yield (a, "CAUSES", c, "chain", bridge, rationale)

    # ------------------------------------------------------------------
    # Verification — the falsifiability loop
    # ------------------------------------------------------------------

    def verify(self) -> int:
        """
        Test every open hypothesis against the current relation graph.

        - If a matching observed relation now exists → status 'confirmed'.
          A confirmed analogy/chain hypothesis is promoted into the relation
          graph as a low-confidence observed edge (Genesis predicted it and
          reality agreed — that earns a place in what it knows).
        - If a *contradicting* observed relation exists → status 'refuted'.
        Returns the number of hypotheses resolved (confirmed + refuted).
        """
        resolved = 0
        try:
            open_rows = self._conn.execute(
                "SELECT hyp_id, subject, rel_type, object, basis, confidence "
                "FROM hypotheses WHERE status = 'open'"
            ).fetchall()
        except Exception as exc:
            self._log("hypothesis.verify.read", exc)
            return 0

        rel = self._brain.relations
        from cognition.contradictions import are_opposing

        for hyp_id, subject, rel_type, obj, basis, conf in open_rows:
            outgoing = rel.query_subject(subject, min_confidence=0.5)

            confirmed = False
            refuted = False
            evidence = None

            for r in outgoing:
                # Object-specified hypothesis: need an exact subject-rel-object match
                if obj:
                    if r["object"] != obj:
                        continue
                    if r["relation"] == rel_type:
                        confirmed = True
                        evidence = f"observed {subject} {rel_type} {obj}"
                        break
                    if are_opposing(r["relation"], rel_type):
                        refuted = True
                        evidence = f"observed {subject} {r['relation']} {obj} (opposes {rel_type})"
                        break
                # Open-object hypothesis (analogy): any new edge of the predicted
                # type confirms the structural prediction.
                else:
                    if r["relation"] == rel_type:
                        confirmed = True
                        evidence = f"observed {subject} {rel_type} {r['object']}"
                        break

            if confirmed:
                self._resolve(hyp_id, "confirmed", evidence)
                # Promote object-specified confirmations into the graph as a
                # modest observed edge — Genesis's prediction became knowledge.
                if obj:
                    rel.add(
                        subject=subject, rel_type=rel_type, obj=obj,
                        confidence=min(0.7, conf + 0.1),
                        source_key="hypothesis:confirmed",
                        session_id=getattr(self._brain, "session_id", None),
                    )
                resolved += 1
            elif refuted:
                self._resolve(hyp_id, "refuted", evidence)
                resolved += 1

        return resolved

    # ------------------------------------------------------------------
    # Curiosity coupling — hypotheses drive what to read next
    # ------------------------------------------------------------------

    def curiosity_targets(self, limit: int = 5) -> list[str]:
        """
        Concepts Genesis should read about to test its open hypotheses.

        A hypothesis is a reason to go looking: if Genesis predicts lions
        PREVENTS something, the way to find out is to read about lions. The
        subject of each open hypothesis is exactly such a target.
        """
        try:
            rows = self._conn.execute(
                "SELECT subject, confidence FROM hypotheses "
                "WHERE status = 'open' ORDER BY confidence DESC, created_at DESC "
                "LIMIT ?",
                (limit * 3,),
            ).fetchall()
        except Exception:
            return []
        seen: list[str] = []
        for subject, _conf in rows:
            s = (subject or "").strip().lower()
            if s and s not in seen:
                seen.append(s)
            if len(seen) >= limit:
                break
        return seen

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def open_hypotheses(self, limit: int = 20) -> list[dict]:
        """Genesis's current standing predictions, most confident first."""
        return self._query_status("open", limit)

    def resolved_hypotheses(self, limit: int = 20) -> list[dict]:
        """Hypotheses that have since been confirmed or refuted."""
        try:
            rows = self._conn.execute(
                "SELECT subject, rel_type, object, basis, rationale, confidence, "
                "status, evidence FROM hypotheses "
                "WHERE status IN ('confirmed', 'refuted') "
                "ORDER BY resolved_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:
            return []
        return [self._row_to_dict(r) for r in rows]

    def _query_status(self, status: str, limit: int) -> list[dict]:
        try:
            rows = self._conn.execute(
                "SELECT subject, rel_type, object, basis, rationale, confidence, "
                "status, evidence FROM hypotheses WHERE status = ? "
                "ORDER BY confidence DESC, created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        except Exception:
            return []
        return [self._row_to_dict(r) for r in rows]

    def stats(self) -> dict:
        try:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) FROM hypotheses GROUP BY status"
            ).fetchall()
            by_status = {r[0]: r[1] for r in rows}
            by_basis = dict(self._conn.execute(
                "SELECT basis, COUNT(*) FROM hypotheses GROUP BY basis"
            ).fetchall())
        except Exception:
            by_status, by_basis = {}, {}
        total = sum(by_status.values())
        confirmed = by_status.get("confirmed", 0)
        refuted = by_status.get("refuted", 0)
        resolved = confirmed + refuted
        return {
            "total": total,
            "open": by_status.get("open", 0),
            "confirmed": confirmed,
            "refuted": refuted,
            # How often a tested conjecture turned out right — Genesis's
            # own calibration as a hypothesizer.
            "hit_rate": round(confirmed / resolved, 3) if resolved else None,
            "by_basis": by_basis,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record(
        self,
        subject: str,
        rel_type: str,
        obj: Optional[str],
        basis: str,
        source: Optional[str],
        rationale: str,
    ) -> bool:
        """Insert a hypothesis. Returns True if newly created, False if a dup."""
        subject = (subject or "").strip().lower()
        obj = (obj or "").strip().lower() or None
        if not subject or subject == obj:
            return False
        conf = _BASIS_CONF.get(basis, 0.5)
        try:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO hypotheses "
                "(subject, rel_type, object, basis, source, rationale, "
                " confidence, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
                (subject, rel_type, obj, basis, source, rationale, conf, time.time()),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception as exc:
            self._log(f"hypothesis._record:{subject}", exc)
            return False

    def _resolve(self, hyp_id: int, status: str, evidence: Optional[str]) -> None:
        try:
            self._conn.execute(
                "UPDATE hypotheses SET status = ?, resolved_at = ?, evidence = ? "
                "WHERE hyp_id = ?",
                (status, time.time(), evidence, hyp_id),
            )
            self._conn.commit()
        except Exception as exc:
            self._log(f"hypothesis._resolve:{hyp_id}", exc)

    @staticmethod
    def _row_to_dict(r) -> dict:
        return {
            "subject":    r[0],
            "rel_type":   r[1],
            "object":     r[2],
            "basis":      r[3],
            "rationale":  r[4],
            "confidence": r[5],
            "status":     r[6],
            "evidence":   r[7],
        }

    def _log(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Chain bridging
# ---------------------------------------------------------------------------

# Words too generic to carry a chain link on their own.
_CHAIN_STOP = frozenset({
    "thing", "things", "something", "number", "numbers", "level", "levels",
    "rate", "rates", "area", "areas", "part", "parts", "form", "forms",
})


def _chain_linkable(b: str, subject: str) -> bool:
    """
    True if the object `b` of one CAUSES edge can be the cause-end `subject`
    of the next — exactly, or by single-content-word containment.

    Exact match always links. Otherwise a *single* content word (len ≥ 4, not
    a generic filler) links to a multi-word concept that contains it as a whole
    token: "deer" ↔ "deer populations", but not "soil to erode" ↔ "new growth".
    The containment must be token-level, never substring, so "ice" never links
    to "service".
    """
    b = (b or "").strip().lower()
    subject = (subject or "").strip().lower()
    if not b or not subject:
        return False
    if b == subject:
        return True

    b_tokens = b.split()
    s_tokens = subject.split()

    def _bridges(word: str, tokens: list[str]) -> bool:
        return (
            len(word) >= 4
            and word not in _CHAIN_STOP
            and word in tokens
        )

    # b is a single word contained in subject's tokens, or vice versa
    if len(b_tokens) == 1 and _bridges(b, s_tokens):
        return True
    if len(s_tokens) == 1 and _bridges(subject, b_tokens):
        return True
    return False
