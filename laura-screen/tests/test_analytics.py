"""Team-total analytics: counts are right and no account id ever leaves the module."""
import json
from datetime import datetime, timezone

from pipeline.analytics import build, iso_week

UID_A = "u_AAAAAAAAAAAAAAAAAAAAAA"
UID_B = "u_BBBBBBBBBBBBBBBBBBBBBB"


def _write(d, coll, doc_id, body):
    p = d / coll
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{doc_id}.json").write_text(json.dumps(body))


def _db(tmp_path):
    d = tmp_path / "db"
    _write(d, "runs", "latest", {"run": {"id": "run-2", "finished": "2026-09-30T10:05:00+00:00"},
                                  "universe": {"sp500": 503, "team": 2},
                                  "status": {"Evidence re-check": {"ok": True, "records": 5, "sources_opened": 7}}})
    _write(d, "runs", "run-1", {"id": "run-1", "finished": "2026-09-28T09:00:00+00:00", "sources_down": ["DOJ releases"],
                                "stats": {"sources_checked": 10, "sources_ok": 9}})
    _write(d, "runs", "run-2", {"id": "run-2", "finished": "2026-09-30T10:05:00+00:00", "sources_down": [],
                                "stats": {"sources_checked": 10, "sources_ok": 10}})
    _write(d, "audit_log", "a1", {"action": "check_now", "at": "2026-09-30T10:00:00Z", "by": UID_A})
    _write(d, "audit_log", "a2", {"action": "approve", "at": "2026-09-29T09:00:00Z", "by": UID_B})
    _write(d, "proposals", "p1", {"id": "p1", "evidence_hash": "new"})
    _write(d, "proposals", "p2", {"id": "p2", "evidence_hash": "h2"})
    _write(d, "approvals", "p1", {"decision": "approve", "to": "black", "decided_at": "2026-09-29T09:00:00Z", "evidence_hash": "old"})
    _write(d, "universe", "TSLA", {"ticker": "TSLA", "type": "stock"})
    _write(d, "usage", UID_A, {"weeks": {"2026-W40": {"2026-09-29": {"v": 3, "p": {"home": 3, "approvals": 1}, "a": {"approve": 1}},
                                                     "2026-09-30": {"v": 1, "p": {"home": 1}, "a": {"check_now": 1}}}}})
    _write(d, "usage", UID_B, {"weeks": {"2026-W40": {"2026-09-30": {"v": 2, "p": {"etf": 2}, "a": {}}}}})
    return d


def test_counts(tmp_path):
    history = {"first_seen": {"p1": "2026-09-28T09:00:00+00:00", "p2": "2026-09-28T09:00:00+00:00"}}
    doc, hist = build(_db(tmp_path), history, today=datetime(2026, 10, 1, tzinfo=timezone.utc))
    h = doc["headline"]
    assert h["companies_screened"] == 505
    assert h["runs_total"] == 2 and h["runs_all_sources_up"] == 1
    assert h["source_uptime_pct"] == 95.0
    assert h["decisions_total"] == 1 and h["approved"] == 1 and h["proposals_open"] == 1
    assert h["median_hours_to_decision"] == 24.0
    assert h["approvals_invalidated_by_new_evidence"] == 1
    assert h["median_minutes_check_now_to_result"] == 5.0
    assert h["people_active_ever"] == 2 and h["visits_total"] == 6
    w = {r["week"]: r for r in doc["weekly"]}["2026-W40"]
    assert w["visits"] == 6 and w["active_people"] == 2
    assert w["page_views"] == {"home": 4, "approvals": 1, "etf": 2}
    assert w["actions"] == {"approve": 1, "check_now": 1}
    assert w["runs"] == 2 and w["decisions"] == 1


def test_no_account_ids_in_outputs(tmp_path):
    doc, hist = build(_db(tmp_path), {}, today=datetime(2026, 10, 1, tzinfo=timezone.utc))
    blob = json.dumps(doc) + json.dumps(hist)
    assert "u_" not in blob


def test_pruned_weeks_keep_recorded_usage(tmp_path):
    old = {"weekly": [{"week": "2026-W30", "visits": 12, "active_people": 3, "page_views": {"home": 12},
                       "actions": {"approve": 4}, "runs": 1, "decisions": 4, "new_proposals": 0}],
           "first_seen": {}}
    doc, _ = build(_db(tmp_path), old, today=datetime(2026, 10, 1, tzinfo=timezone.utc))
    w = {r["week"]: r for r in doc["weekly"]}
    assert w["2026-W30"]["visits"] == 12 and w["2026-W30"]["actions"] == {"approve": 4}


def test_iso_week_matches_page():
    # the page's isoWeek() and Python must agree at year edges
    assert iso_week(datetime(2026, 1, 1)) == "2026-W01"
    assert iso_week(datetime(2027, 1, 1)) == "2026-W53"
    assert iso_week(datetime(2026, 9, 28)) == "2026-W40"
