"""
Long-Term Memory Store — SQLite backend.

Every memory is written here immediately on store(). This is the source
of truth. Working memory (attention.py) is a fast read-cache on top.

Design: write-through, never-delete.
- Write-through:   every store() call writes to SQLite immediately.
                   A process crash can't lose a memory.
- Never-delete:    no row is ever removed. Relevance can decay, but
                   the record stays. Total retention is non-negotiable.

Search uses SQLite FTS5 (full-text search, part of stdlib sqlite3).
FTS5 gives proper tokenization and BM25 ranking at no extra cost.
Falls back to LIKE-based search on platforms where FTS5 is unavailable.
"""

import os
import re
import sqlite3
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.types import Memory


class LongTermStore:
    """
    SQLite-backed persistent memory store.

    All reads/writes go through a single persistent connection (single-
    threaded — Genesis doesn't need multi-thread memory access yet).
    FTS5 index is maintained manually in upsert() so behaviour is
    predictable and there's no trigger complexity.
    """

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")   # safer concurrent reads
        self._conn.execute("PRAGMA synchronous=NORMAL") # performance/durability balance
        self._fts_available = False
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                key          TEXT PRIMARY KEY,
                content      TEXT NOT NULL,
                context      TEXT NOT NULL,
                source_type  TEXT NOT NULL,
                relevance    REAL NOT NULL DEFAULT 0.5,
                created_at   REAL NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed REAL
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_relevance
            ON memories(relevance DESC)
        """)

        # FTS5 for full-text search — try to create, fall back to LIKE
        try:
            c.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(key UNINDEXED, content, context, tokenize='porter ascii')
            """)
            self._fts_available = True
        except sqlite3.OperationalError:
            # FTS5 not compiled in — LIKE fallback will be used
            self._fts_available = False

        c.execute("""
            CREATE TABLE IF NOT EXISTS associations (
                key_a      TEXT NOT NULL,
                key_b      TEXT NOT NULL,
                strength   REAL NOT NULL DEFAULT 0.5,
                kind       TEXT NOT NULL DEFAULT 'co_occurrence',
                created_at REAL NOT NULL,
                PRIMARY KEY (key_a, key_b)
            )
        """)
        c.commit()

    # ------------------------------------------------------------------
    # Memory CRUD
    # ------------------------------------------------------------------

    def upsert(self, key: str, memory: Memory) -> None:
        """
        Insert or update a memory. Updates merge content and take the
        higher relevance score (a memory becoming more relevant is
        never reversed by a new write at lower relevance).
        """
        now = time.time()
        self._conn.execute("""
            INSERT INTO memories
                (key, content, context, source_type, relevance, created_at,
                 access_count, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                content      = excluded.content,
                context      = excluded.context,
                relevance    = MAX(relevance, excluded.relevance),
                access_count = excluded.access_count,
                last_accessed = ?
        """, (
            key, memory.content, memory.context, memory.source_type,
            memory.relevance, memory.created_at, memory.access_count, now,
            now,
        ))

        if self._fts_available:
            # Maintain FTS index: delete old entry, insert fresh
            self._conn.execute("DELETE FROM memories_fts WHERE key = ?", (key,))
            self._conn.execute(
                "INSERT INTO memories_fts(key, content, context) VALUES (?, ?, ?)",
                (key, memory.content, memory.context),
            )

        self._conn.commit()

    def get(self, key: str) -> Optional[Memory]:
        """Retrieve a memory by exact key. Returns None if not found."""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE key = ?", (key,)
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def update_access(self, key: str, access_count: int) -> None:
        """Record an access — updates access_count and last_accessed timestamp."""
        self._conn.execute(
            "UPDATE memories SET access_count = ?, last_accessed = ? WHERE key = ?",
            (access_count, time.time(), key),
        )
        self._conn.commit()

    def update_relevance(self, key: str, relevance: float) -> None:
        """Update the relevance score for a memory."""
        self._conn.execute(
            "UPDATE memories SET relevance = ? WHERE key = ?",
            (max(0.0, min(1.0, relevance)), key),
        )
        self._conn.commit()

    def all_keys(self) -> list[str]:
        """Return all memory keys (may be large — use sparingly)."""
        rows = self._conn.execute("SELECT key FROM memories").fetchall()
        return [r["key"] for r in rows]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 20) -> list[tuple[str, Memory]]:
        """
        Full-text search using FTS5 (BM25 ranking) with LIKE fallback.

        Returns at most `limit` results ordered by relevance * fts_rank.
        """
        if self._fts_available:
            return self._search_fts(query, limit)
        return self._search_like(query, limit)

    def _search_fts(self, query: str, limit: int) -> list[tuple[str, Memory]]:
        """FTS5 search with BM25 ranking blended with stored relevance."""
        # Clean query for FTS5: remove punctuation, wrap in quotes for phrase
        clean = re.sub(r"[^\w\s]", " ", query).strip()
        if not clean:
            return []
        try:
            rows = self._conn.execute("""
                SELECT m.*, -rank AS fts_score
                FROM memories_fts fts
                JOIN memories m ON m.key = fts.key
                WHERE memories_fts MATCH ?
                ORDER BY (m.relevance * 0.4 + (-rank) * 0.6) DESC
                LIMIT ?
            """, (clean, limit)).fetchall()
            return [(r["key"], self._row_to_memory(r)) for r in rows]
        except sqlite3.OperationalError:
            # Query parse error (e.g. special chars) — fall through to LIKE
            return self._search_like(query, limit)

    def _search_like(self, query: str, limit: int) -> list[tuple[str, Memory]]:
        """LIKE-based fallback search. Slower, no stemming."""
        words = re.findall(r"\b\w{2,}\b", query.lower())
        if not words:
            return []
        conditions = " OR ".join(
            "LOWER(content) LIKE ? OR LOWER(context) LIKE ? OR LOWER(key) LIKE ?"
            for _ in words
        )
        params = []
        for w in words:
            params.extend([f"%{w}%", f"%{w}%", f"%{w}%"])
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM memories WHERE {conditions} ORDER BY relevance DESC LIMIT ?",
            params,
        ).fetchall()
        return [(r["key"], self._row_to_memory(r)) for r in rows]

    # ------------------------------------------------------------------
    # Associations
    # ------------------------------------------------------------------

    def add_association(
        self, key_a: str, key_b: str, strength: float, kind: str = "co_occurrence"
    ) -> None:
        """
        Create or strengthen an association between two memories.
        Associations are bidirectional: both (a→b) and (b→a) are stored.
        """
        now = time.time()
        for ka, kb in [(key_a, key_b), (key_b, key_a)]:
            self._conn.execute("""
                INSERT INTO associations (key_a, key_b, strength, kind, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key_a, key_b) DO UPDATE SET
                    strength = MAX(strength, excluded.strength)
            """, (ka, kb, strength, kind, now))
        self._conn.commit()

    def get_associations(self, key: str, min_strength: float = 0.1) -> list[tuple[str, float, str]]:
        """
        Return associated keys for `key` with strength >= min_strength.
        Returns list of (neighbor_key, strength, kind).
        """
        rows = self._conn.execute(
            "SELECT key_b, strength, kind FROM associations WHERE key_a = ? AND strength >= ?",
            (key, min_strength),
        ).fetchall()
        return [(r["key_b"], r["strength"], r["kind"]) for r in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        assocs = self._conn.execute("SELECT COUNT(*) FROM associations").fetchone()[0]
        avg_rel = self._conn.execute("SELECT AVG(relevance) FROM memories").fetchone()[0]
        return {
            "total_memories": total,
            "total_associations": assocs // 2,  # stored bidirectionally
            "avg_relevance": round(avg_rel or 0.0, 3),
            "fts_available": self._fts_available,
            "db_path": self._db_path,
        }

    def close(self) -> None:
        """Close the database connection cleanly."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_memory(row) -> Memory:
        return Memory(
            content=row["content"],
            context=row["context"],
            source_type=row["source_type"],
            relevance=row["relevance"],
            created_at=row["created_at"],
            access_count=row["access_count"],
            associations=[],  # populated on demand via get_associations()
        )
