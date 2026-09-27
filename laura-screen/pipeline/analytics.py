"""Team-total analytics for the private Laura Screen Analytics page.

  python -m pipeline.analytics <db_dir>
      reads <db_dir>/{runs,audit_log,approvals,proposals,universe,usage}/*.json (saved by
      ArtifactData list ... out_dir=<db_dir>), merges analytics/history.json, and writes
      out/analytics.json (the metrics/latest document for the analytics page) and an updated
      analytics/history.json.

Only team totals leave this module: no account ids, names or emails are written anywhere.
Raw usage documents (one per viewer, last 8 weeks) are read here and reduced to counts.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "analytics" / "history.json"
OUT = ROOT / "out" / "analytics.json"
PAGES = ["home", "approvals", "etf", "records", "method"]
ACTIONS = ["save_tickers", "remove_ticker", "check_now", "approve", "reject", "comment", "reopen",
           "csv_download", "alerts_on", "alerts_off", "schedule", "etf_add", "etf_weight", "open_list"]


def _load(d: Path, coll: str) -> list[dict]:
    base = d / coll
    if not base.exists():
        return []
    out = []
    for p in sorted(base.glob("*.json")):
        doc = json.loads(p.read_text())
        doc["_id"] = p.stem
        out.append(doc)
    return out


def _ts(s) -> datetime | None:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def iso_week(t: datetime | date) -> str:
    y, w, _ = t.isocalendar()
    return f"{y}-W{w:02d}"


def _median(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 1) if xs else None


def backfill_first_seen() -> dict:
    """When each proposal id first appeared, read from the committed site/data.json history.

    Uses the run.finished time stored in the first commit whose data.json lists the proposal,
    so it is a real observation, not a guess. Returns {} outside a git checkout.
    """
    try:
        revs = subprocess.run(["git", "-C", str(ROOT), "log", "--reverse", "--format=%H", "--", "site/data.json"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return {}
    seen = {}
    for rev in revs:
        try:
            raw = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:laura-screen/site/data.json"],
                                 capture_output=True, text=True, check=True).stdout
            data = json.loads(raw)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        when = (data.get("run") or {}).get("finished")
        for p in data.get("proposals", []):
            seen.setdefault(p["id"], when)
    return seen


def build(db: Path, history: dict, today: datetime | None = None) -> tuple[dict, dict]:
    now = today or datetime.now(timezone.utc)
    runs = [r for r in _load(db, "runs") if r["_id"] != "latest"]
    latest = next((r for r in _load(db, "runs") if r["_id"] == "latest"), {})
    audit = _load(db, "audit_log")
    approvals = _load(db, "approvals")
    proposals = _load(db, "proposals")
    universe = _load(db, "universe")
    usage = _load(db, "usage")

    # --- when each proposal was first seen (for time-to-decision) ---
    first_seen = dict(history.get("first_seen") or {})
    if not first_seen:
        first_seen = backfill_first_seen()
    run_now = (latest.get("run") or {}).get("finished")
    for p in proposals:
        first_seen.setdefault(p["_id"], run_now)

    # --- decisions ---
    decided = [a for a in approvals if a.get("decision") in ("approve", "reject")]
    hours = []
    for a in decided:
        t0, t1 = _ts(first_seen.get(a["_id"])), _ts(a.get("decided_at"))
        if t0 and t1 and t1 >= t0:
            hours.append((t1 - t0).total_seconds() / 3600)
    live_hash = {p["_id"]: p.get("evidence_hash") for p in proposals}
    evidence_changed = sum(1 for a in decided if a["_id"] in live_hash and a.get("evidence_hash")
                           and live_hash[a["_id"]] and a["evidence_hash"] != live_hash[a["_id"]])
    pending = sum(1 for p in proposals if p["_id"] not in {a["_id"] for a in decided})
    by_list = {}
    for a in decided:
        if a["decision"] == "approve":
            by_list[a.get("to", "?")] = by_list.get(a.get("to", "?"), 0) + 1

    # --- Check now -> results (first run that finished after each request) ---
    run_ends = sorted(t for t in (_ts(r.get("finished")) for r in runs) if t)
    waits = []
    for e in audit:
        if e.get("action") != "check_now":
            continue
        t = _ts(e.get("at"))
        nxt = next((f for f in run_ends if t and f >= t), None)
        if t and nxt and nxt - t < timedelta(hours=3):
            waits.append((nxt - t).total_seconds() / 60)

    # --- run health ---
    with_stats = [r for r in runs if r.get("stats")]
    checked = sum(r["stats"].get("sources_checked") or 0 for r in with_stats)
    ok = sum(r["stats"].get("sources_ok") or 0 for r in with_stats)
    clean = sum(1 for r in runs if not r.get("sources_down"))
    stats = (sorted(with_stats, key=lambda r: r.get("finished", ""))[-1]["stats"] if with_stats else {})
    uni = latest.get("universe") if isinstance(latest.get("universe"), dict) else {}
    status = latest.get("status") or {}
    ev = status.get("Evidence re-check", {})

    # --- weekly series ---
    weeks: dict[str, dict] = {}

    def wk(w: str) -> dict:
        return weeks.setdefault(w, {"week": w, "visits": 0, "active_people": 0, "page_views": {}, "actions": {},
                                    "runs": 0, "decisions": 0, "new_proposals": 0, "_people": set()})

    for u in usage:
        for w, days in (u.get("weeks") or {}).items():
            row = wk(w)
            active = False
            for day in days.values():
                row["visits"] += int(day.get("v") or 0)
                for k, n in (day.get("p") or {}).items():
                    row["page_views"][k] = row["page_views"].get(k, 0) + int(n)
                for k, n in (day.get("a") or {}).items():
                    row["actions"][k] = row["actions"].get(k, 0) + int(n)
                active = active or bool(day.get("v") or day.get("p") or day.get("a"))
            if active:
                row["_people"].add(u["_id"])
    raw_usage_weeks = set(weeks)
    for e in audit:
        t = _ts(e.get("at"))
        if t and e.get("by"):
            wk(iso_week(t))["_people"].add(e["by"])
    for r in runs:
        t = _ts(r.get("finished"))
        if t:
            wk(iso_week(t))["runs"] += 1
    for a in decided:
        t = _ts(a.get("decided_at"))
        if t:
            wk(iso_week(t))["decisions"] += 1
    for pid, when in first_seen.items():
        t = _ts(when)
        if t:
            wk(iso_week(t))["new_proposals"] += 1

    old = {w["week"]: w for w in history.get("weekly", [])}
    series = []
    for w in sorted(set(weeks) | set(old)):
        row = weeks.get(w)
        if row is None:
            series.append(old[w])
            continue
        row["active_people"] = len(row.pop("_people"))
        if w not in raw_usage_weeks and w in old:
            # raw usage for this week was pruned (8-week retention): keep the counts recorded earlier
            for k in ("visits", "page_views", "actions"):
                row[k] = old[w].get(k, row[k])
            row["active_people"] = max(row["active_people"], old[w].get("active_people", 0))
        series.append(row)

    headline = {
        # uni["team"] counts team stocks outside the S&P 500, so the sum has no double counting
        "companies_screened": (uni.get("sp500") or 0) + (uni.get("team") or 0),
        "sp500_companies": uni.get("sp500"),
        "team_tickers": len(universe),
        "runs_total": len(runs),
        "runs_last_30_days": sum(1 for t in run_ends if now - t <= timedelta(days=30)),
        "runs_all_sources_up": clean,
        "source_checks": checked, "source_checks_ok": ok,
        "source_uptime_pct": round(100 * ok / checked, 1) if checked else None,
        "evidence_records": ev.get("records", stats.get("evidence_records")),
        "evidence_sources_opened_per_run": ev.get("sources_opened", stats.get("evidence_sources_opened")),
        "proposals_open": pending,
        "decisions_total": len(decided),
        "approved": sum(1 for a in decided if a["decision"] == "approve"),
        "rejected": sum(1 for a in decided if a["decision"] == "reject"),
        "approved_by_list": by_list,
        "median_hours_to_decision": _median(hours), "decisions_timed": len(hours),
        "approvals_invalidated_by_new_evidence": evidence_changed,
        "check_now_requests": sum(1 for e in audit if e.get("action") == "check_now"),
        "median_minutes_check_now_to_result": _median(waits), "check_now_timed": len(waits),
        "people_active_ever": len({e["by"] for e in audit if e.get("by")} | {u["_id"] for u in usage}),
        "visits_total": sum(r.get("visits", 0) for r in series),
        "first_activity": min((e.get("at") for e in audit if e.get("at")), default=None),
    }
    doc = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of_run": (latest.get("run") or {}).get("id"),
        "headline": headline,
        "weekly": series,
        "pages": PAGES, "actions": ACTIONS,
        "notes": [
            "Usage counting started when the tracker was added; earlier weeks show runs and decisions only.",
            "Active people counts anyone who visited or acted that week (usage counts plus the audit log).",
            "Time to decision runs from the first run that proposed a change to the team's decision.",
            "Check now wait runs from the request to the end of the next pipeline run (before Claude reads new evidence).",
        ],
    }
    new_history = {"first_seen": first_seen, "weekly": series}
    return doc, new_history


def main(argv: list[str]) -> None:
    db = Path(argv[1]) if len(argv) > 1 else ROOT / "cache" / "db"
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    doc, hist = build(db, history)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(hist, indent=1, sort_keys=True))
    h = doc["headline"]
    print(f"analytics: {h['runs_total']} runs, {h['decisions_total']} decisions, {h['visits_total']} visits, "
          f"{len(doc['weekly'])} weeks -> {OUT}")


if __name__ == "__main__":
    main(sys.argv)
