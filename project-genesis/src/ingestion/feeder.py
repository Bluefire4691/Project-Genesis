"""
Knowledge Feeder — Ingestion Pipeline.

Coordinates the full self-directed knowledge acquisition loop:

    1. CuriosityEngine identifies what Genesis most needs to learn
    2. WikipediaFetcher retrieves the article text
    3. TextChunker splits it into processor-ready segments
    4. Each chunk is processed through brain.process_input()
    5. New relations accumulate in the RelationGraph

This is the concrete implementation of M17 (Active Curiosity):
Genesis's unresolved concepts become knowledge-seeking behavior,
not just statements.

Usage:
    feeder = KnowledgeFeeder(brain)
    report = feeder.run(n_topics=3)
    print(report)  # what was learned
"""

import time
from typing import TYPE_CHECKING

from ingestion.wikipedia import WikipediaFetcher
from ingestion.chunker import chunk_text
from ingestion.curiosity import CuriosityEngine
from ingestion.dictionary import LocalDictionary

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


class KnowledgeFeeder:
    """
    Self-directed knowledge acquisition for Genesis.

    Genesis decides what to learn. The feeder goes and gets it.
    """

    def __init__(
        self,
        brain: "Orchestrator",
        sentences_per_chunk: int = 3,
        use_full_article: bool = False,
    ):
        self._brain = brain
        self._sentences_per_chunk = sentences_per_chunk
        self._use_full_article = use_full_article
        self._fetcher = WikipediaFetcher()
        self._curiosity = CuriosityEngine(brain)
        self._dictionary = LocalDictionary()

        self._total_topics_fetched: int = 0
        self._total_chunks_processed: int = 0
        self._total_relations_before: int = 0
        self._failed_topics: set[str] = set()  # never retry topics that failed everywhere

    # Maximum topics per run — prevents runaway fetching when graph is sparse.
    # Large requests (learn:200) are silently capped; quality beats quantity.
    _MAX_TOPICS_PER_RUN = 10

    def run(self, n_topics: int = 5, verbose: bool = True) -> dict:
        """
        Run one curiosity-driven knowledge acquisition cycle.

        Genesis identifies its top N curiosity targets, fetches
        Wikipedia articles for each, and processes all chunks.

        n_topics is capped at _MAX_TOPICS_PER_RUN. Use the self-directed
        loop (--self-directed) to process many topics across multiple cycles
        with knowledge integration between each batch.

        Returns a report of what was learned.
        """
        brain = self._brain
        n_topics = min(n_topics, self._MAX_TOPICS_PER_RUN)

        # What does Genesis want to know about?
        # Exclude previously failed topics so Wikipedia 404s are never retried.
        topics = [
            t for t in self._curiosity.top_topics(n=n_topics)
            if t not in self._failed_topics
        ]

        if not topics:
            return {
                "topics_attempted": [],
                "topics_succeeded": [],
                "chunks_processed": 0,
                "relations_before": 0,
                "relations_after": 0,
                "relations_added": 0,
                "note": "No curiosity targets found — process more input first.",
            }

        relations_before = brain.relations.stats().get("total_relations", 0)
        results = []

        if verbose:
            print(f"\n  [Curiosity] Genesis wants to learn about:")
            for t in topics:
                print(f"    · {t}")
            print()

        for topic in topics:
            result = self._fetch_and_process(topic, verbose=verbose)
            results.append(result)
            self._total_topics_fetched += 1

        relations_after = brain.relations.stats().get("total_relations", 0)
        chunks_total = sum(r["chunks_processed"] for r in results)
        self._total_chunks_processed += chunks_total

        succeeded = [r["topic"] for r in results if r["success"]]

        report = {
            "topics_attempted": topics,
            "topics_succeeded": succeeded,
            "chunks_processed": chunks_total,
            "relations_before": relations_before,
            "relations_after": relations_after,
            "relations_added": relations_after - relations_before,
            "per_topic": results,
        }

        if verbose:
            print(f"\n  [Curiosity] Learned from {len(succeeded)}/{len(topics)} topics.")
            print(f"  Relations: {relations_before} → {relations_after} "
                  f"(+{relations_after - relations_before})")
            print()

        return report

    def curiosity_report(self) -> list[dict]:
        """Show what Genesis is most curious about without fetching."""
        return self._curiosity.curiosity_report()

    def stats(self) -> dict:
        return {
            "total_topics_fetched":   self._total_topics_fetched,
            "total_chunks_processed": self._total_chunks_processed,
            "fetcher":                self._fetcher.stats(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_and_process(self, topic: str, verbose: bool = True) -> dict:
        """Fetch one topic and process all its chunks. Returns per-topic stats."""
        t_start = time.monotonic()

        if self._use_full_article:
            title, text = self._fetcher.fetch(topic)
        else:
            title, text = self._fetcher.fetch_summary(topic)

        if not text:
            # Try local dictionary before giving up
            definition = self._dictionary.lookup(topic)
            if definition:
                title = topic.title()
                text = definition
                if verbose:
                    print(f"  [Curiosity] ✓ '{title}' → local dictionary")
            else:
                if verbose:
                    print(f"  [Curiosity] ✗ Could not fetch '{topic}'")
                self._failed_topics.add(topic)
                return {
                    "topic": topic, "title": "", "success": False,
                    "chunks_processed": 0, "elapsed_s": 0,
                }

        chunks = chunk_text(text, sentences_per_chunk=self._sentences_per_chunk)

        if verbose:
            print(f"  [Curiosity] ✓ '{title}' → {len(chunks)} chunks")

        processed = 0
        for chunk in chunks:
            try:
                self._brain.process_input("text", chunk)
                processed += 1
            except Exception:
                pass

        elapsed = round(time.monotonic() - t_start, 2)
        return {
            "topic":            topic,
            "title":            title,
            "success":          True,
            "chunks_processed": processed,
            "elapsed_s":        elapsed,
        }
