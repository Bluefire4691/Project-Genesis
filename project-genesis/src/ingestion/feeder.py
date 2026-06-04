"""
Knowledge Feeder — Ingestion Pipeline.

Coordinates the full self-directed knowledge acquisition loop:

    1. CuriosityEngine identifies what Genesis most needs to learn
    2. WordNet provides the base definition of the concept (always, offline)
    3. GutenbergFetcher finds a relevant book and reads the next passage
       — Genesis tracks where it left off and continues next session
    4. OfflineCorpusFetcher searches the NLTK corpus when Gutenberg is offline
    5. Each text chunk is processed through brain.process_input()
    6. New relations accumulate in the RelationGraph

Sources in priority order:
    WordNet      — word definitions, always available offline
    Gutenberg    — complete public domain books, requires network
    NLTK corpus  — Brown + Gutenberg corpora already on disk, offline fallback

Genesis reads books, not encyclopedia stubs. The same book is returned to
across multiple sessions — understanding builds the way a reader's does.
"""

import time
from typing import TYPE_CHECKING

from ingestion.chunker import chunk_text
from ingestion.curiosity import CuriosityEngine
from ingestion.wordnet_dict import WordNetDictionary
from ingestion.gutenberg import GutenbergFetcher
from ingestion.corpus import OfflineCorpusFetcher

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


class KnowledgeFeeder:
    """
    Self-directed knowledge acquisition for Genesis.

    Genesis decides what to learn. The feeder finds the right source and
    reads it — returning to the same books across sessions.
    """

    def __init__(
        self,
        brain: "Orchestrator",
        sentences_per_chunk: int = 3,
    ):
        self._brain = brain
        self._sentences_per_chunk = sentences_per_chunk
        self._curiosity = CuriosityEngine(brain)
        self._wordnet = WordNetDictionary()
        self._gutenberg = GutenbergFetcher()
        self._corpus = OfflineCorpusFetcher()

        self._total_topics_fetched: int = 0
        self._total_chunks_processed: int = 0
        self._failed_topics: set[str] = set()
        # Concepts whose lookup produced no new relations, with a strike count.
        # After _MAX_STRIKES unproductive fetches a concept is set aside so the
        # feeder stops wasting cycles re-reading what it already fully knows.
        self._unproductive: dict[str, int] = {}

    _MAX_TOPICS_PER_RUN = 10
    _MAX_STRIKES = 2          # unproductive fetches before a topic is set aside

    def run(self, n_topics: int = 5, verbose: bool = True) -> dict:
        """
        Run one curiosity-driven knowledge acquisition cycle.

        Returns a report of what was learned.
        """
        n_topics = min(n_topics, self._MAX_TOPICS_PER_RUN)

        # Ask the curiosity engine for a generous candidate pool, then pick the
        # first n that aren't known dead-ends. The curiosity engine no longer
        # excludes anything itself (that starved it), so the filtering for
        # already-exhausted concepts happens here against live graph state.
        candidates = self._curiosity.top_topics(n=n_topics * 6)
        topics: list[str] = []
        for t in candidates:
            if t in self._failed_topics:
                continue
            if self._unproductive.get(t, 0) >= self._MAX_STRIKES:
                continue
            topics.append(t)
            if len(topics) >= n_topics:
                break

        if not topics:
            return {
                "topics_attempted": [],
                "topics_succeeded": [],
                "chunks_processed": 0,
                "relations_before": 0,
                "relations_after": 0,
                "relations_added": 0,
                "note": "No fresh curiosity targets — frontier exhausted for now.",
            }

        relations_before = self._brain.relations.stats().get("total_relations", 0)
        results = []

        if verbose:
            print(f"\n  [Curiosity] Genesis wants to learn about:")
            for t in topics:
                print(f"    · {t}")
            print()

        for topic in topics:
            rel_before_topic = self._brain.relations.stats().get("total_relations", 0)
            result = self._fetch_and_process(topic, verbose=verbose)
            rel_after_topic = self._brain.relations.stats().get("total_relations", 0)

            # Track productivity: a topic that adds nothing new earns a strike.
            if rel_after_topic > rel_before_topic:
                self._unproductive[topic] = 0
            else:
                self._unproductive[topic] = self._unproductive.get(topic, 0) + 1

            results.append(result)
            self._total_topics_fetched += 1

        relations_after = self._brain.relations.stats().get("total_relations", 0)
        chunks_total = sum(r["chunks_processed"] for r in results)
        self._total_chunks_processed += chunks_total
        succeeded = [r["topic"] for r in results if r["success"]]

        if verbose:
            print(f"\n  [Curiosity] Learned from {len(succeeded)}/{len(topics)} topics.")
            print(f"  Relations: {relations_before} → {relations_after} "
                  f"(+{relations_after - relations_before})")
            print()

        return {
            "topics_attempted": topics,
            "topics_succeeded": succeeded,
            "chunks_processed": chunks_total,
            "relations_before": relations_before,
            "relations_after": relations_after,
            "relations_added": relations_after - relations_before,
            "per_topic": results,
        }

    def curiosity_report(self) -> list[dict]:
        """Show what Genesis is most curious about without fetching."""
        return self._curiosity.curiosity_report()

    def reading_status(self) -> dict:
        """Report Genesis's reading progress through Gutenberg books."""
        return self._gutenberg.reading_status()

    def stats(self) -> dict:
        return {
            "total_topics_fetched":   self._total_topics_fetched,
            "total_chunks_processed": self._total_chunks_processed,
            "gutenberg_online":       self._gutenberg.available,
            "corpus_available":       self._corpus.available,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_and_process(self, topic: str, verbose: bool = True) -> dict:
        """Gather text about a topic from all available sources and process it."""
        t_start = time.monotonic()
        all_chunks: list[str] = []
        sources: list[str] = []
        title = topic.title()

        # --- WordNet: base definition, always available ---
        # Fed whole, NOT through the chunker. WordNet emits short, clean
        # declarative sentences ("Animal contains face.", "Kill causes die.")
        # that the chunker's 60-char minimum would discard — exactly the
        # structured sentences that yield the cleanest relation triples.
        # The TextProcessor splits them into sentences itself, no length floor.
        definition = self._wordnet.lookup(topic)
        if definition:
            all_chunks.append(definition)
            sources.append("WordNet")

        # --- Gutenberg: read the next passage from a relevant book ---
        book_title, passage = self._gutenberg.fetch_for_topic(topic)
        if passage:
            all_chunks.extend(
                chunk_text(passage, sentences_per_chunk=self._sentences_per_chunk)
            )
            sources.append(f"Gutenberg: {book_title}")
            title = book_title or title

        # --- Offline corpus: NLTK texts when Gutenberg is unreachable ---
        elif self._corpus.available:
            corpus_passage = self._corpus.find_passages(topic)
            if corpus_passage:
                all_chunks.extend(
                    chunk_text(corpus_passage,
                               sentences_per_chunk=self._sentences_per_chunk)
                )
                sources.append("NLTK corpus")

        if not all_chunks:
            if verbose:
                print(f"  [Curiosity] ✗ No sources found for '{topic}'")
            self._failed_topics.add(topic)
            return {
                "topic": topic, "title": "", "success": False,
                "chunks_processed": 0, "elapsed_s": 0,
            }

        source_label = " + ".join(sources)
        if verbose:
            print(f"  [Curiosity] ✓ '{title}' → {source_label} "
                  f"({len(all_chunks)} chunks)")

        processed = 0
        for chunk in all_chunks:
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
