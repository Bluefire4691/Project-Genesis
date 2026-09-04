"""
Regression tests for the paywall domain blocklist (pre-fetch gate).

Covers the review findings:
  - lstrip("www.") stripped a character set, not the prefix, so blocklist
    domains starting with 'w' (wiley.com) never matched
  - _detect_paywall substring matching flagged '*group.com' via 'oup.com'
  - the pre-fetch block must keep the M25 escalation flow alive: a skipped
    domain queues an access request, and resolving it exempts the domain
"""

import sqlite3
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ingestion.browser import (
    GenesisBrowser, _is_blocked_domain, _domain_matches,
)


# ── _is_blocked_domain: suffix matching, www handling ─────────────────────────

def test_www_prefix_stripped_as_prefix_not_charset():
    # The lstrip bug: 'www.wiley.com'.lstrip('www.') == 'iley.com'
    assert _is_blocked_domain("https://www.wiley.com/doi/10.1002/x")
    assert _is_blocked_domain("https://wiley.com/anything")


def test_w_domains_blocked():
    # Every blocklist entry starting with 'w' was previously unmatchable
    assert _is_blocked_domain("https://www.wiley.com/")
    assert _is_blocked_domain("http://wiley.com/")


def test_subdomains_blocked():
    assert _is_blocked_domain("https://link.springer.com/article/10.1007/x")
    assert _is_blocked_domain("https://wayf.springernature.com/login")
    assert _is_blocked_domain("https://www.nature.com/articles/x")
    assert _is_blocked_domain("https://academic.oup.com/journal")


def test_unrelated_domains_not_blocked():
    # Substring traps: 'group.com' contains 'oup.com'; 'w3.org' starts with w
    assert not _is_blocked_domain("https://researchgroup.com/page")
    assert not _is_blocked_domain("https://group.com/")
    assert not _is_blocked_domain("https://www.w3.org/standards")
    assert not _is_blocked_domain("https://en.wikipedia.org/wiki/Wolf")
    assert not _is_blocked_domain("https://mynature.company.org/")


def test_malformed_url_not_blocked():
    assert not _is_blocked_domain("not a url at all")
    assert not _is_blocked_domain("")


# ── _domain_matches shared helper ─────────────────────────────────────────────

def test_domain_matches_is_suffix_not_substring():
    domains = {"oup.com", "bmj.com"}
    assert _domain_matches("academic.oup.com", domains)
    assert _domain_matches("oup.com", domains)
    assert _domain_matches("www.oup.com", domains)
    assert not _domain_matches("group.com", domains)
    assert not _domain_matches("researchgroup.com", domains)
    assert not _domain_matches("thebmj.company.com", domains)


# ── _detect_paywall: no more substring false positives ────────────────────────

def test_detect_paywall_short_text_on_group_dot_com_is_not_paywall():
    b = GenesisBrowser(db_conn=None)
    assert not b._detect_paywall("Short page.", "https://researchgroup.com/x")
    assert not b._detect_paywall("Short page.", "https://group.com/x")


def test_detect_paywall_short_text_on_real_paywall_domain():
    b = GenesisBrowser(db_conn=None)
    assert b._detect_paywall("Abstract only.", "https://academic.oup.com/article")
    assert b._detect_paywall("Abstract only.", "https://www.wiley.com/doi/x")


# ── Escalation flow survives the pre-fetch block ──────────────────────────────

def _mem_browser() -> GenesisBrowser:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    return GenesisBrowser(db_conn=conn)


def test_blocked_fetch_queues_access_request():
    b = _mem_browser()
    result = b.fetch("https://www.nature.com/articles/s41586-x")
    assert result is None
    pending = b.pending_access_requests()
    assert any("nature.com" in r["domain"] for r in pending), (
        "Skipping a blocked domain must still queue an access request "
        "so the user can grant access"
    )


def test_resolved_access_request_exempts_domain():
    b = _mem_browser()
    b.fetch("https://www.nature.com/articles/x")          # queues request
    pending = b.pending_access_requests()
    assert pending
    b.resolve_access_request(pending[0]["id"])            # user grants access
    assert not b.is_blocked("https://www.nature.com/articles/y"), (
        "A granted access request must exempt the domain from the block"
    )
    # Other blocked domains remain blocked
    assert b.is_blocked("https://link.springer.com/article/z")


def test_is_blocked_without_grant():
    b = _mem_browser()
    assert b.is_blocked("https://www.wiley.com/doi/x")
    assert not b.is_blocked("https://en.wikipedia.org/wiki/Wolf")
