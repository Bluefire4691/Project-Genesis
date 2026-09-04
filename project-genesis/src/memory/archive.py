"""
Archive — tagged reference memory for long-term cross-session retrieval.

Sits on top of LongTermStore and uses the same SQLite connection.

Adds three capabilities that LongTermStore doesn't have:

1. Domain tagging — every stored memory gets tagged with significance score
   and domain labels (auto-derived from processor source, manually addable).
   Tags accumulate: re-tagging a key merges tag sets rather than replacing.

2. Archive queries — retrieve memories by domain, significance threshold,
   time range, or session. The full corpus is always available for reference.

3. Named snapshots — capture the current attention state as a named reference
   point in time. Retrieve any snapshot later to reconstruct what Genesis was
   attending to at that moment. Useful for comparing developmental states.
"""

import json
import sqlite3
import time
from typing import Optional


# Domain tags automatically assigned based on processor source type.
# These can be supplemented with manually-assigned tags.
_SOURCE_TAGS: dict[str, list[str]] = {
    "text": ["language", "symbolic"],
    "numeric": ["quantitative", "measurement"],
    "pattern": ["structural", "sequential"],
}


class ArchiveStore:
    """
    Tagged reference store sharing the memory DB connection.

    Uses the same sqlite3.Connection as LongTermStore — no extra file,
    no multi-connection contention.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS archive_metadata (
                key          TEXT PRIMARY KEY,
                session_id   TEXT NOT NULL,
                significance REAL NOT NULL DEFAULT 0.5,
                domain_tags  TEXT NOT NULL DEFAULT '[]',
                archived_at  REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_archive_sig
            ON archive_metadata(significance DESC)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_archive_session
            ON archive_metadata(session_id)
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS archive_snapshots (
                snapshot_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                label        TEXT NOT NULL,
                session_id   TEXT NOT NULL,
                created_at   REAL NOT NULL,
                memory_keys  TEXT NOT NULL   -- JSON array of memory keys
            )
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Tagging
    # ------------------------------------------------------------------

    def tag(
        self,
        key: str,
        significance: float,
        session_id: str,
        domain_tags: Optional[list[str]] = None,
        source_type: Optional[str] = None,
    ) -> None:
        """
        Tag a memory with significance and domain labels.

        Auto-tags are added from source_type if provided.
        Re-tagging merges tag sets and takes the higher significance.
        """
        tags = list(domain_tags or [])

        # Auto-tag from source type
        for auto_tag in _SOURCE_TAGS.get(source_type or "", []):
            if auto_tag not in tags:
                tags.append(auto_tag)

        # Merge with existing tags if key already archived
        existing = self._conn.execute(
            "SELECT domain_tags FROM archive_metadata WHERE key = ?", (key,)
        ).fetchone()
        if existing:
            for t in json.loads(existing["domain_tags"]):
                if t not in tags:
                    tags.append(t)

        now = time.time()
        self._conn.execute("""
            INSERT INTO archive_metadata
                (key, session_id, significance, domain_tags, archived_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                significance = MAX(significance, excluded.significance),
                domain_tags  = excluded.domain_tags,
                archived_at  = excluded.archived_at
        """, (key, session_id, max(0.0, min(1.0, significance)), json.dumps(tags), now))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        domain: Optional[str] = None,
        min_significance: float = 0.0,
        since_ts: Optional[float] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Query archived memories.

        Filters: domain tag substring, minimum significance, time range,
        and/or session. Results ordered by significance DESC.

        Returns list of dicts with keys:
            key, session_id, significance, domain_tags, archived_at
        """
        conditions = ["significance >= ?"]
        params: list = [min_significance]

        if since_ts is not None:
            conditions.append("archived_at >= ?")
            params.append(since_ts)

        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)

        if domain is not None:
            # Tags stored as JSON array — check if tag string appears
            conditions.append('domain_tags LIKE ?')
            params.append(f'%"{domain}"%')

        params.append(limit)
        rows = self._conn.execute(
            f"""
            SELECT key, session_id, significance, domain_tags, archived_at
            FROM archive_metadata
            WHERE {' AND '.join(conditions)}
            ORDER BY significance DESC, archived_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        return [
            {
                "key": r["key"],
                "session_id": r["session_id"],
                "significance": r["significance"],
                "domain_tags": json.loads(r["domain_tags"]),
                "archived_at": r["archived_at"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def snapshot(
        self,
        label: str,
        memory_keys: list[str],
        session_id: str,
    ) -> int:
        """
        Save a named reference snapshot of the current attention state.

        `memory_keys` is the ordered list of working memory keys at the
        time of capture. Returns the new snapshot_id.
        """
        cursor = self._conn.execute("""
            INSERT INTO archive_snapshots
                (label, session_id, created_at, memory_keys)
            VALUES (?, ?, ?, ?)
        """, (label, session_id, time.time(), json.dumps(memory_keys)))
        self._conn.commit()
        return cursor.lastrowid

    def list_snapshots(self) -> list[dict]:
        """List all snapshots, newest first."""
        rows = self._conn.execute("""
            SELECT snapshot_id, label, session_id, created_at,
                   json_array_length(memory_keys) AS key_count
            FROM archive_snapshots
            ORDER BY created_at DESC
        """).fetchall()
        return [
            {
                "snapshot_id": r["snapshot_id"],
                "label": r["label"],
                "session_id": r["session_id"],
                "created_at": r["created_at"],
                "key_count": r["key_count"],
            }
            for r in rows
        ]

    def retrieve_snapshot(self, snapshot_id: int) -> Optional[dict]:
        """
        Retrieve a snapshot by ID.

        Returns dict with keys: snapshot_id, label, session_id, created_at,
        memory_keys (list of str). Returns None if snapshot_id not found.
        """
        row = self._conn.execute(
            "SELECT * FROM archive_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "snapshot_id": row["snapshot_id"],
            "label": row["label"],
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "memory_keys": json.loads(row["memory_keys"]),
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        total_tagged = self._conn.execute(
            "SELECT COUNT(*) FROM archive_metadata"
        ).fetchone()[0]
        total_snapshots = self._conn.execute(
            "SELECT COUNT(*) FROM archive_snapshots"
        ).fetchone()[0]
        avg_sig = self._conn.execute(
            "SELECT AVG(significance) FROM archive_metadata"
        ).fetchone()[0]
        return {
            "total_tagged": total_tagged,
            "total_snapshots": total_snapshots,
            "avg_significance": round(avg_sig or 0.0, 3),
        }
