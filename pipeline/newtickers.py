"""Full check for tickers the team added since they were last checked.

Weekly discovery only scans filings published since the previous run, so a company pasted today
would be missed until its next 10-K. For each new stock this module gathers, from primary sources:
- the financial gate (SEC XBRL),
- its latest annual report (10-K / 40-F / 20-F) with theme-phrase snippets for the values link,
- SEC full-text search hits in its own filings over the look-back window for legal terms.
Claude then reads these and writes evidence records; nothing here labels anything.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .docs import doc_text
from .http import fetch_json, SourceError

ANNUAL = ("10-K", "40-F", "20-F")
LEGAL_TERMS = ['"racial discrimination"', '"race discrimination"', '"racial harassment"', '"national origin"',
               '"defamation"', '"false and defamatory"', '"Civil Rights"', '"Equal Employment Opportunity Commission"',
               '"Fair Housing Act"']


def latest_annual(cik: int) -> dict | None:
    d = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ttl_hours=24)
    r = d["filings"]["recent"]
    for i, f in enumerate(r["form"]):
        if f in ANNUAL:
            acc = r["accessionNumber"][i]
            return {"form": f, "filed": r["filingDate"][i], "accession": acc,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{r['primaryDocument'][i]}"}
    return None


def theme_snippets(url: str, themes: dict, per_theme: int = 2) -> dict:
    text = doc_text(url)
    out = {}
    for key, cfg in themes.items():
        terms = list(cfg.get("discovery_phrases", [])) + list(cfg.get("examples", []))
        snips = []
        for term in terms:
            m = re.search(r"\b" + re.escape(term) + r"\b", text, flags=re.I)
            if m:
                snips.append({"term": term, "snippet": text[max(0, m.start() - 160): m.end() + 160]})
            if len(snips) >= per_theme:
                break
        if snips:
            out[key] = snips
    return out


def legal_hits(cik: int, years: int, today: date, limit: int = 8) -> list[dict]:
    start = (today - timedelta(days=int(365.25 * years))).isoformat()
    hits, seen = [], set()
    for term in LEGAL_TERMS:
        try:
            d = fetch_json("https://efts.sec.gov/LATEST/search-index",
                           params={"q": term, "ciks": f"{cik:010d}", "forms": "10-K,10-Q,8-K,40-F,20-F,6-K",
                                   "dateRange": "custom", "startdt": start, "enddt": today.isoformat()},
                           ttl_hours=24)
        except SourceError:
            continue
        for h in d.get("hits", {}).get("hits", []):
            src = h["_source"]
            acc, doc = h["_id"].split(":", 1)
            key = (acc, term)
            if acc in {x["accession"] for x in hits} or key in seen:
                for x in hits:
                    if x["accession"] == acc and term.strip('"') not in x["terms"]:
                        x["terms"].append(term.strip('"'))
                continue
            seen.add(key)
            hits.append({"accession": acc, "form": src.get("form"), "filed": src.get("file_date"),
                         "terms": [term.strip('"')],
                         "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"})
    hits.sort(key=lambda x: (-len(x["terms"]), x["filed"] or ""), reverse=False)
    return hits[:limit]


def check(ticker: str, info: dict, tmap: dict, rules: dict, today: date, gate_fn) -> dict:
    """info: {name, cik}. gate_fn(cik) -> financial gate dict."""
    out = {"ticker": ticker, "company": info["name"], "cik": info["cik"], "errors": []}
    if tmap.get(ticker, [None, "S"])[1] == "E":
        out["kind"] = "etf"
        return out
    out["kind"] = "stock"
    try:
        out["gate"] = gate_fn(info["cik"])
    except Exception as e:  # noqa: BLE001 - reported, never fatal
        out["errors"].append(f"financial gate: {e}")
    try:
        ann = latest_annual(info["cik"])
        out["annual_report"] = ann
        if ann:
            out["theme_snippets"] = theme_snippets(ann["url"], rules["aligned"]["themes"])
    except SourceError as e:
        out["errors"].append(f"annual report: {e}")
    try:
        out["legal_hits"] = legal_hits(info["cik"], rules["black"]["lookback_years"], today)
    except SourceError as e:
        out["errors"].append(f"SEC full-text search: {e}")
    return out
