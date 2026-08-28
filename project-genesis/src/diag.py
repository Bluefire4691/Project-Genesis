#!/usr/bin/env python3
"""
Genesis diagnostic — answers "did anything actually happen?" from the DB.

Read-only.  Run after (or during) a long session and paste the output:

    python src/diag.py
    python src/diag.py --db data/genesis_memory.db --hours 12
"""

import argparse
import os
import sqlite3
import sys
import time
from collections import Counter

_DEF_DB = os.path.join(os.path.dirname(__file__), "..", "data",
                       "genesis_memory.db")


def _section(title):
    print(f"\n=== {title} " + "=" * max(1, 58 - len(title)))


def _safe(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as e:
        print(f"  (unavailable: {e})")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=_DEF_DB)
    ap.add_argument("--hours", type=int, default=12)
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"DB not found: {args.db}")
        sys.exit(1)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    now = time.time()
    since = now - args.hours * 3600

    _section("TOTALS")
    for label, sql in [
        ("memories",        "SELECT COUNT(*) FROM memories"),
        ("relations",       "SELECT COUNT(*) FROM relations"),
        ("inferred",        "SELECT COUNT(*) FROM inferred_relations"),
        ("hypotheses",      "SELECT COUNT(*) FROM hypotheses"),
        ("inference rules", "SELECT COUNT(*) FROM inference_programs"),
        ("decisions",       "SELECT COUNT(*) FROM decision_log"),
        ("goals",           "SELECT COUNT(*) FROM goals"),
        ("values held",     "SELECT COUNT(*) FROM held_values"),
        ("tastes",          "SELECT COUNT(*) FROM tastes"),
        ("web pages seen",  "SELECT COUNT(*) FROM web_page_history"),
    ]:
        rows = _safe(conn, sql)
        if rows is not None:
            print(f"  {label:16s} {rows[0][0]:,}")

    _section(f"RELATION GROWTH (last {args.hours}h, per hour)")
    rows = _safe(conn,
        "SELECT CAST((? - created_at) / 3600 AS INT) AS h, COUNT(*) "
        "FROM relations WHERE created_at >= ? GROUP BY h ORDER BY h",
        (now, since))
    if rows:
        total = sum(r[1] for r in rows)
        print(f"  NEW RELATIONS in window: {total:,}")
        for h, c in rows:
            print(f"   {h:2d}h ago  {'#' * min(60, c)} {c}")
    elif rows == []:
        print("  *** ZERO new relations in the window — Genesis learned "
              "nothing new. ***")

    _section(f"WEB ACTIVITY (last {args.hours}h)")
    rows = _safe(conn,
        "SELECT COUNT(*), SUM(paywall), SUM(text_length) "
        "FROM web_page_history WHERE fetched_at >= ?", (since,))
    if rows and rows[0][0]:
        n, pw, chars = rows[0]
        print(f"  pages fetched: {n}   paywalled: {pw or 0}   "
              f"text pulled: {(chars or 0):,} chars")
        recent = _safe(conn,
            "SELECT url, text_length FROM web_page_history "
            "WHERE fetched_at >= ? ORDER BY fetched_at DESC LIMIT 8", (since,))
        for url, ln in recent or []:
            print(f"    {ln or 0:6d} ch  {url[:70]}")
    else:
        print("  *** NO pages fetched in the window — web layer starved "
              "(search rate-limited, offline, or fetcher stalled). ***")

    _section(f"DECISIONS (last {args.hours}h)")
    rows = _safe(conn,
        "SELECT subsystem, decision FROM decision_log "
        "WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT 25", (since,))
    if rows:
        by = Counter(r[0] for r in rows)
        print(f"  by subsystem: {dict(by)}")
        for sub, dec in rows[:12]:
            print(f"    [{sub}] {dec[:70]}")
    elif rows == []:
        print("  *** ZERO decisions logged — fetch/reflect cycles produced "
              "nothing recordable. ***")

    _section("TOPIC VARIETY (learn decisions, whole DB)")
    rows = _safe(conn,
        "SELECT decision, COUNT(*) FROM decision_log "
        "WHERE decision LIKE 'learn about %' GROUP BY decision "
        "ORDER BY COUNT(*) DESC LIMIT 12")
    if rows:
        print(f"  distinct topics ever learned: {len(rows)}+")
        for dec, c in rows:
            print(f"    {c:3d}×  {dec.removeprefix('learn about ')[:60]}")
    elif rows == []:
        print("  *** No successful topic learns recorded at all. ***")

    _section("STRONGEST TASTES / VALUES / GOALS")
    rows = _safe(conn, "SELECT concept, weight, samples FROM tastes "
                       "ORDER BY ABS(weight) DESC LIMIT 6")
    for c, w, s in rows or []:
        print(f"  taste {w:+.3f} ({s}×)  {c}")
    rows = _safe(conn, "SELECT statement, confidence FROM held_values "
                       "ORDER BY confidence DESC LIMIT 4")
    for st, cf in rows or []:
        print(f"  value ({cf:.2f}) {st[:70]}")
    rows = _safe(conn, "SELECT topic, status, origin FROM goals "
                       "ORDER BY formed_at DESC LIMIT 6")
    for t, s, o in rows or []:
        print(f"  goal [{s}/{o}] {t}")

    _section("VERDICT HINTS")
    print("  - Zero new relations + zero pages  -> diet starvation: web layer")
    print("    blocked/rate-limited; offline sources exhausted. Fix the diet.")
    print("  - Relations growing but topics repeat -> curiosity ranking stuck;")
    print("    the same gaps stay top-scored. Fix the rotation.")
    print("  - Everything growing but chat repetitive -> expression layer,")
    print("    already being fixed (content-grounded expressions).")


if __name__ == "__main__":
    main()
