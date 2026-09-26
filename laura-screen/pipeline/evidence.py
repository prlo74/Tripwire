"""Evidence checks and rule engine.

Every run re-opens each source, confirms the quote is really in it, and applies rules.yaml.
The output is PROPOSALS only. Nothing becomes a label without a team approval in the page.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .docs import doc_text, quote_in_doc
from .http import SourceError

ROOT = Path(__file__).resolve().parent.parent


def load_rules() -> dict:
    return yaml.safe_load((ROOT / "config" / "rules.yaml").read_text())


def load_records() -> list[dict]:
    recs = []
    for p in sorted((ROOT / "evidence").glob("*.yaml")):
        recs += (yaml.safe_load(p.read_text()) or {}).get("records", [])
    return recs


def tier_of(url: str, rules: dict) -> int | None:
    """1 = primary (can trigger), 2 = lead only, 0 = banned, None = unlisted (treated as banned)."""
    host = urlparse(url).netloc.lower()
    def match(domains):
        return any(host == d or host.endswith("." + d) for d in domains)
    s = rules["sources"]
    if match(s.get("banned_domains", [])):
        return 0
    if match(s["tier1_domains"]):
        return 1
    if match(s["tier2_domains"]):
        return 2
    return None


def word_count(q: str) -> int:
    return len(re.findall(r"\S+", q))


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def years_between(a: date, b: date) -> float:
    return (b - a).days / 365.25


def check_record(rec: dict, rules: dict, today: date, open_sources: bool = True) -> dict:
    """Return the record plus a 'check' block: verified sources, problems, and the rule outcome."""
    problems, verified = [], []
    for s in rec.get("sources", []):
        t = tier_of(s["url"], rules)
        entry = {**s, "tier": t, "quote_words": word_count(s.get("quote", "")), "quote_found": None,
                 "opened_at": None, "error": None}
        entry["quote"] = re.sub(r"\s+", " ", s.get("quote", "")).strip()
        if t == 0 or t is None:
            problems.append(f"banned or unlisted source: {s['url']}")
        if entry["quote_words"] > 50:
            problems.append(f"quote over 50 words ({entry['quote_words']}): {s['url']}")
        if open_sources and entry["quote"] and t in (1, 2):
            try:
                text = doc_text(s["url"])
                entry["opened_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                entry["quote_found"] = quote_in_doc(entry["quote"], text)
                if not entry["quote_found"]:
                    problems.append(f"quote not found in source: {s['url']}")
            except SourceError as e:
                entry["error"] = str(e)
                problems.append(f"source unreachable this run: {s['url']} ({e})")
        verified.append(entry)

    ok_tier1 = [v for v in verified if v["tier"] == 1 and v["quote_found"]]
    kind = rec["kind"]
    outcome, clause_text = None, None
    b = rules["black"]
    if kind == "finding":
        if rec.get("finding_type") not in b["qualifying_findings"]:
            problems.append(f"finding_type {rec.get('finding_type')!r} is not a qualifying finding")
        age = years_between(_d(rec["event_date"]), today)
        if age <= b["lookback_years"]:
            outcome = "black"
            clause_text = (f"Black ({rec['clause']}) {b['clauses'][rec['clause']]}: "
                           f"{b['qualifying_findings'].get(rec.get('finding_type'), '?')}, "
                           f"{rec['event_date']} (within {b['lookback_years']} years)")
        else:
            outcome = "watch"
            clause_text = f"Watch: {rules['watch']['triggers']['old_finding']} ({rec['event_date']})"
    elif kind == "open_case":
        outcome = "watch"
        clause_text = f"Watch ({rec['clause']}): {rules['watch']['triggers']['open_case']}"
    elif kind == "settlement_no_admission":
        outcome = "watch"
        clause_text = f"Watch ({rec['clause']}): {rules['watch']['triggers']['settlement_no_admission']}"
    elif kind == "values_link":
        outcome = "values_link"
        labels = [rules["aligned"]["themes"][t]["label"] for t in rec.get("themes", [])]
        clause_text = "Aligned gate 2 (values link): " + ", ".join(labels)
        if not any(v["tier"] == 1 and urlparse(v["url"]).netloc.endswith("sec.gov") for v in verified):
            problems.append("values link must cite the company's own filing on sec.gov (or a primary membership list)")
    elif kind == "lead":
        outcome = "lead"
        clause_text = "Lead: needs primary source"
    else:
        problems.append(f"unknown kind {kind!r}")

    if outcome in ("black", "watch") and not ok_tier1:
        problems.append("no Tier-1 source with a verified quote: cannot be proposed")
        outcome = "lead"
        clause_text = "Lead: needs primary source"
    if outcome == "watch" and rules["watch"].get("tripwire_required") and not rec.get("tripwire") \
            and kind != "finding":
        problems.append("Watch entry has no tripwire")

    # Settlement without admission can never produce Black (belt and braces).
    if kind == "settlement_no_admission" and outcome == "black":
        outcome = "watch"

    return {**rec, "event_date": str(rec.get("event_date", "")), "sources": verified,
            "check": {"outcome": outcome, "clause_text": clause_text, "problems": problems,
                      "tier1_verified": len(ok_tier1),
                      "proposable": outcome in ("black", "watch", "values_link") and bool(ok_tier1)
                      and not [p for p in problems if not p.startswith("source unreachable")]}}


def do_not_list_tickers(rules: dict) -> dict:
    out = {}
    for e in rules.get("do_not_list_without_finding", []):
        for t in e.get("tickers", []):
            out[t] = e["reason"]
    return out


def guard_do_not_list(checked: list[dict], rules: dict) -> list[dict]:
    """Deliberately-not-listed tickers may only be proposed Black on a qualifying finding."""
    dnl = do_not_list_tickers(rules)
    for r in checked:
        hit = [t for t in r["tickers"] if t in dnl]
        if hit and r["check"]["outcome"] in ("watch", "values_link") or \
           hit and r["check"]["outcome"] == "black" and r["kind"] != "finding":
            r["check"]["problems"].append(f"{hit} are on the do-not-list-without-finding list")
            r["check"]["proposable"] = False
    return checked
