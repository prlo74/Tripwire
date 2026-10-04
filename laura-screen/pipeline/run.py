"""Run the Laura screen pipeline.

    python -m pipeline.run [--db out/db_snapshot.json] [--no-discovery] [--progress]

Inputs:  config/rules.yaml, config/baseline.yaml, evidence/*.yaml, and a snapshot of the
         Artifact database (universe, approvals) that Claude Code saves before the run.
Outputs: site/data.json (embedded in the page; no secrets), out/state.json (full detail),
         out/alerts.json (alerts to send), printed run summary.
         With --progress, stage changes and counts go to cache/progress_pipeline.json for the
         page's progress bar (see pipeline/progress.py).
"""
from __future__ import annotations

import argparse
import re
import json
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import discovery, etf, financial, newtickers, progress
from .evidence import check_record, do_not_list_tickers, guard_do_not_list, load_records, load_rules
from .http import SourceError
from .tickers import build as build_tickers, canon

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
SITE = ROOT / "site"
LABEL_RANK = {"black": 3, "watch": 2, "aligned": 1}
RANK_TO = LABEL_RANK


ABBREV = re.compile(r"(?:\b(?:[A-Z]\.)+[A-Z]|\b(?:Cal|Inc|Corp|Co|Ltd|No|v|vs|St|Mr|Ms|Dr|Jr|Sr))\.$")


def first_sentence(text: str) -> str:
    """First sentence, not fooled by abbreviations such as "N.D. Cal." or "U.S."."""
    for m in re.finditer(r"\.\s+(?=[A-Z(])", text):
        if not ABBREV.search(text[: m.start() + 1]):
            return text[: m.start() + 1]
    return text


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_db_snapshot(path: Path | None) -> dict:
    if path and path.exists():
        return json.loads(path.read_text())
    return {"universe": [], "approvals": [], "runs": []}


def current_labels(baseline: dict, approvals: list[dict]) -> dict:
    """Approved labels win; otherwise the starting list (marked unapproved)."""
    labels = {}
    for t in baseline.get("black", []):
        labels[t] = {"label": "black", "approved": False, "basis": "starting list (Sept 2026), not yet approved"}
    for t in baseline.get("watch", []):
        labels[t] = {"label": "watch", "approved": False, "basis": "starting list (Sept 2026), not yet approved"}
    # Approved labels: the most severe approved label wins (black > watch > aligned), so
    # approving a Watch record after a Black one never downgrades a company.
    approved: dict[str, dict] = {}
    for a in approvals:
        if a.get("decision") != "approve":
            continue
        for t in a.get("tickers", []):
            cur = approved.get(t)
            if cur is None or LABEL_RANK.get(a["to"], 0) > LABEL_RANK.get(cur["label"], 0):
                approved[t] = {"label": a["to"], "approved": True,
                               "basis": f"approved {a.get('decided_at', '')[:10]}", "proposal_id": a.get("proposal_id")}
    labels.update(approved)
    return labels


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(OUT / "db_snapshot.json"))
    ap.add_argument("--no-discovery", action="store_true")
    ap.add_argument("--today", default=None)
    ap.add_argument("--progress", action="store_true", help="report stages for the page's progress bar")
    args = ap.parse_args(argv)

    t0 = time.time()
    started = now_iso()
    run_id = "run-" + started.replace(":", "").replace("-", "")[:15]
    prog = progress.Reporter(args.progress, run_id)
    today = date.fromisoformat(args.today) if args.today else date.today()
    OUT.mkdir(exist_ok=True)
    rules = load_rules()
    baseline = yaml.safe_load((ROOT / "config" / "baseline.yaml").read_text())
    db = load_db_snapshot(Path(args.db))
    status: dict[str, dict] = {}
    errors: list[str] = []

    def step(name, fn, *a, **kw):
        try:
            r = fn(*a, **kw)
            status.setdefault(name, {"ok": True})
            return r
        except Exception as e:  # noqa: BLE001 - every source failure is reported, never fatal
            status[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            errors.append(f"{name}: {e}")
            if not isinstance(e, SourceError):
                traceback.print_exc(file=sys.stderr)
            return None

    # 1. Ticker map (embedded in the page)
    tick = step("SEC + Nasdaq ticker lists", build_tickers)
    if tick:
        (SITE / "tickers.json").write_text(json.dumps(tick, separators=(",", ":")))
        status["SEC + Nasdaq ticker lists"].update({"as_of": tick["asOf"], "count": len(tick["t"])})
    else:
        tick = json.loads((SITE / "tickers.json").read_text()) if (SITE / "tickers.json").exists() else {"t": {}}
    tmap = tick["t"]

    # 2. Universe: S&P 500 from SPY's daily holdings file + the team's list from the page.
    spy = step("S&P 500 constituents (SPY holdings, State Street)", etf.ssga_holdings, "SPY")
    universe: dict[str, dict] = {}
    if spy:
        for h in spy["holdings"]:
            t = canon(h["ticker"]) if h.get("ticker") else None
            if t and t in tmap and tmap[t][1] == "S":
                universe[t] = {"name": tmap[t][0], "cik": tmap[t][2], "origin": "S&P 500"}
        status["S&P 500 constituents (SPY holdings, State Street)"].update(
            {"as_of": spy["as_of"], "count": len(universe), "source": spy["source"]})
    team_etfs = set()
    unchecked = []   # team tickers never checked (added since the last run)
    for u in db.get("universe", []):
        if not u.get("checked_at") and canon(u.get("ticker", "")) in tmap:
            unchecked.append(canon(u["ticker"]))
        t = canon(u.get("ticker", ""))
        if t in tmap and tmap[t][1] == "S":
            universe.setdefault(t, {"name": tmap[t][0], "cik": tmap[t][2], "origin": "team list"})
        elif t in tmap and tmap[t][1] == "E":
            team_etfs.add(t)
    labels = current_labels(baseline, db.get("approvals", []))

    # 3. Evidence: re-open every source, verify quotes, apply rules.
    raw = load_records()
    prog.phase("records", total=sum(len(r.get("sources", [])) for r in raw), unit="sources checked")
    records = []
    for r in raw:
        records.append(check_record(r, rules, today))
        prog.tick(len(r.get("sources", [])))
    records = guard_do_not_list(records, rules)
    status["Evidence re-check"] = {"ok": all(not any("unreachable" in p for p in r["check"]["problems"])
                                             for r in records),
                                   "records": len(records),
                                   "sources_opened": sum(1 for r in records for s in r["sources"] if s["opened_at"])}

    decided = {a.get("proposal_id"): a for a in db.get("approvals", [])}
    proposals, leads = [], []
    by_ticker_values = {}
    fin_notes: dict[str, dict] = {}
    for r in records:
        chk = r["check"]
        if chk["outcome"] == "lead" or not chk["proposable"]:
            if r["kind"] in ("lead", "finding", "open_case", "settlement_no_admission"):
                leads.append(r)
            continue
        if chk["outcome"] == "values_link":
            for t in r["tickers"]:
                by_ticker_values[t] = r
            continue
        if chk["outcome"] == "financial_note":
            for t in r["tickers"]:
                src = next(x for x in r["sources"] if x["quote_found"])
                fin_notes.setdefault(t, {})[r["field"]] = {"value": r["value"], "url": src["url"], "quote": src["quote"],
                                                           "fy_end": str(r.get("fy_end")), "label": r.get("label", r["field"])}
            continue
        to = chk["outcome"]
        frm = labels.get(r["tickers"][0], {}).get("label", "none")
        if frm == "none" and any(t in baseline.get("aligned_candidates", []) for t in r["tickers"]):
            frm = "aligned"
        pid = f"p-{'-'.join(r['tickers'])}-{to}-{r['id']}"
        proposals.append({"id": pid, "tickers": r["tickers"], "company": r["company"], "from": frm, "to": to,
                          "record_id": r["id"], "kind": r["kind"], "clause": r.get("clause"),
                          "clause_text": chk["clause_text"], "summary": r.get("summary", "").strip(),
                          "caveat": (r.get("caveat") or "").strip(), "tripwire": (r.get("tripwire") or "").strip(),
                          "confidence": r.get("confidence"), "event_date": r.get("event_date"),
                          "evidence": [{k: s.get(k) for k in ("publisher", "url", "doc_date", "quote", "tier",
                                                                "opened_at", "quote_found")}
                                       for s in r["sources"]],
                          "decision": decided.get(pid, {}).get("decision"),
                          "discovery": bool(r.get("discovered"))})

    # 4. Financial gate for every values-linked company (and baseline candidates).
    aligned_cands = sorted(set(by_ticker_values) | set(baseline.get("aligned_candidates", []))
                           | set(baseline.get("rejected_financial", [])))
    aligned, values_fail = [], []
    passing: dict[str, tuple] = {}
    prog.phase("financials", total=len(aligned_cands) + len(set(unchecked)), unit="companies")
    black_like = {t for p in proposals if p["to"] == "black" for t in p["tickers"]} | \
                 {t for t, l in labels.items() if l["label"] == "black"}
    for t in aligned_cands:
        if t not in tmap:
            errors.append(f"{t}: not in ticker map")
            prog.tick()
            continue
        gate = step(f"XBRL companyfacts {t}", financial.financial_gate, tmap[t][2], rules, fin_notes.get(t))
        prog.tick()
        if gate is None:
            gate = {"result": "unknown", "checks": {}, "failed": [], "unknown": ["all"]}
        rec = by_ticker_values.get(t)
        row = {"ticker": t, "company": rec["company"] if rec else tmap[t][0], "cik": tmap[t][2],
               "themes": [rules["aligned"]["themes"][th]["label"] for th in (rec or {}).get("themes", [])],
               "values_record": rec["id"] if rec else None, "values_confidence": (rec or {}).get("confidence"),
               "values_summary": (rec or {}).get("summary"), "values_caveat": (rec or {}).get("caveat"),
               "evidence": [{k: s.get(k) for k in ("publisher", "url", "doc_date", "quote", "tier", "opened_at",
                                                     "quote_found")} for s in (rec or {}).get("sources", [])],
               "gate": gate}
        if t in black_like:
            row["blocked"] = "On (or proposed for) the Black list"
            values_fail.append(row)
        elif rec is None:
            row["gate"]["note"] = "No verified values link this run."
            values_fail.append(row)
        elif gate["result"] == "pass":
            aligned.append(row)
            passing.setdefault(rec["id"], (rec, row, []))[2].append(t)
        else:
            values_fail.append(row)
    for rid, (rec, row, tks) in passing.items():
        pid = f"p-{'-'.join(tks)}-aligned-{rid}"
        proposals.append({"id": pid, "tickers": tks, "company": row["company"],
                          "from": labels.get(tks[0], {}).get("label", "none"), "to": "aligned",
                          "record_id": rid, "kind": "values_link", "clause": None,
                          "clause_text": "Aligned: passes financial gate + " + rec["check"]["clause_text"],
                          "summary": rec.get("summary", ""), "caveat": (rec.get("caveat") or ""),
                          "tripwire": "", "confidence": rec.get("confidence"), "event_date": None,
                          "evidence": row["evidence"], "gate": row["gate"],
                          "decision": decided.get(pid, {}).get("decision"),
                          "discovery": bool(rec.get("discovered"))})

    # Fingerprint the evidence behind each proposal; an approval made on different evidence
    # returns to "pending" in the page.
    import hashlib
    for p in proposals:
        basis = json.dumps([p["to"], p["clause_text"], p.get("summary"), p.get("caveat"), p.get("tripwire"),
                            [(e.get("url"), e.get("quote")) for e in p.get("evidence", [])]], sort_keys=True)
        p["evidence_hash"] = hashlib.sha256(basis.encode()).hexdigest()[:16]

    # One rule everywhere: an approval counts only if it was made on the evidence shown now.
    approvals = db.get("approvals", [])
    live = {p["id"]: p for p in proposals}

    def stale(a):
        p = live.get(a.get("proposal_id"))
        return bool(p and a.get("evidence_hash") and a["evidence_hash"] != p["evidence_hash"])
    valid = [a for a in approvals if not stale(a)]
    labels = current_labels(baseline, valid)
    by_pid = {a.get("proposal_id"): a for a in approvals}
    for p in proposals:
        a = by_pid.get(p["id"])
        p["evidence_changed"] = bool(a and stale(a))
        p["decision"] = a.get("decision") if a and not p["evidence_changed"] else None
        if a and not p["evidence_changed"] and a.get("from"):
            p["from"] = a["from"]          # the state the team approved the move from
        else:
            cur = labels.get(p["tickers"][0], {}).get("label")
            if cur:
                p["from"] = cur
        cur = labels.get(p["tickers"][0], {})
        if not p["decision"] and cur.get("approved") and RANK_TO.get(cur["label"], 0) > RANK_TO.get(p["to"], 0):
            p["context"] = f"{p['tickers'][0]} is already approved {cur['label'].title()}; this record is context."

    # Cap discovery proposals per run; the rest wait in the collapsed "more" list.
    cap = rules["discovery"].get("max_proposals_per_run", 10)
    conf_rank = {"High": 0, "Medium": 1, "Low": 2}
    disc_props = sorted([p for p in proposals if p.get("discovery")],
                        key=lambda p: (conf_rank.get(p.get("confidence"), 3), -RANK_TO.get(p["to"], 0)))
    overflow = {p["id"] for p in disc_props[cap:]}
    held_back = [p for p in proposals if p["id"] in overflow]
    proposals = [p for p in proposals if p["id"] not in overflow]

    # 4b. Full check for team tickers added since they were last checked.
    new_checks = []
    for t in sorted(set(unchecked)):
        info = universe.get(t) or {"name": tmap[t][0], "cik": tmap[t][2]}
        r = step(f"New ticker check {t}", newtickers.check, t, info, tmap, rules, today,
                 lambda cik, t=t: financial.financial_gate(cik, rules, fin_notes.get(t)))
        prog.tick()
        if r:
            new_checks.append(r)

    # 5. ETF look-through data.
    etf_list = sorted(set(baseline.get("default_etfs", [])) | team_etfs)
    targets = {}
    for t in sorted({t for r in records if r["kind"] in ("finding", "open_case", "settlement_no_admission")
                     for t in r["tickers"]} | set(labels)):
        if t in tmap:
            targets[t] = {"cusips": set(), "names": {etf._norm_name(tmap[t][0])}}
    etf_data = {}
    prog.phase("etf", total=len(etf_list), unit="funds")
    for e in (["SPY"] if "SPY" in etf_list else []) + [x for x in etf_list if x != "SPY"]:
        h = spy if (e == "SPY" and spy) else step(f"ETF holdings {e}", etf.holdings, e, tmap.get(e, [""])[0])
        prog.tick()
        if not h:
            etf_data[e] = {"asOf": None, "error": status.get(f"ETF holdings {e}", {}).get("error", "unavailable")}
            continue
        if h.get("note"):
            status[f"ETF holdings {e}"] = {"ok": False, "error": f"issuer file unavailable, used SEC N-PORT instead ({h['note']})"}
        shares = etf.black_share(h, targets)
        etf_data[e] = {"asOf": h["as_of"], "source": h["source"], "sourceKind": h["source_kind"],
                       "holdings": {k: v for k, v in shares.items() if v}, "positions": len(h["holdings"]),
                       "name": tmap.get(e, [e])[0]}

    # 6. Discovery (legal candidates + Aligned theme candidates).
    prog.phase("discovery")
    disc = {"legal": [], "themes": [], "status": {}}
    last_runs = sorted((r.get("finished") for r in db.get("runs", []) if r.get("finished")), reverse=True)
    if last_runs:
        since = date.fromisoformat(last_runs[0][:10]) - timedelta(days=1)
    else:
        since = today - timedelta(days=rules["discovery"].get("first_run_lookback_days", 365))
    if not args.no_discovery:
        legal_since = since if last_runs else \
            today - timedelta(days=rules["discovery"].get("legal_first_run_lookback_days", 45))
        res = step("Discovery: agencies and courts", discovery.legal_candidates, universe, legal_since)
        if res:
            known = {t for p in proposals for t in p["tickers"]} | set(labels)
            disc["legal"] = [c for c in res["candidates"] if not set(c["tickers"]) <= known]
            disc["legal_known"] = [c for c in res["candidates"] if set(c["tickers"]) <= known]
            disc["status"].update(res["status"])
            disc["legal_since"] = legal_since.isoformat()
            for k, v in res["status"].items():
                status[f"{k} releases"] = {"ok": v["ok"], "error": v.get("error"), "items": v["items_scanned"],
                                            "since": legal_since.isoformat()}
        ucik = {v["cik"]: t for t, v in universe.items()}
        th = step("Discovery: SEC full-text search (themes)", discovery.theme_candidates, ucik,
                  rules["aligned"]["themes"], since)
        if th:
            cands, err = th
            if err:
                status["Discovery: SEC full-text search (themes)"] = {"ok": False, "error": err}
            known = set(aligned_cands) | black_like
            rows = []
            for t, v in cands.items():
                if t in known:
                    continue
                sic, sic_desc = discovery.sic_of(universe[t]["cik"])
                rows.append({"ticker": t, "company": universe[t]["name"], "themes": v, "sic": sic,
                             "sic_desc": sic_desc, "industry_fit": sic in discovery.THEME_SIC,
                             "score": len(v) * 2 + sum(len(p) for p in v.values()) + (3 if sic in discovery.THEME_SIC else 0)})
            rows.sort(key=lambda r: (-r["industry_fit"], -r["score"], r["ticker"]))
            disc["themes"] = rows

    # 7. Alerts: Aligned/Watch -> Black proposals (and confirmations after approval).
    alerts = []
    for p in proposals:
        if p["to"] == "black" and p["from"] != "black":
            status_word = "confirmed" if p.get("decision") == "approve" else "proposed"
            if p.get("decision") == "reject":
                continue
            ev = p["evidence"][0] if p["evidence"] else {}
            for t in p["tickers"]:
                alerts.append({"key": f"{t}|{p['from']}|black|{p['record_id']}|{status_word}", "ticker": t,
                               "core": p["from"] in ("aligned", "watch"),
                               "from": p["from"], "to": "black", "status": status_word, "proposal_id": p["id"],
                               "subject": f"[Laura Screen] {t} {status_word}: {p['from'].title()} → Black",
                               "clause": p["clause_text"], "reason": first_sentence(p["summary"]),
                               "source_url": ev.get("url"), "source_date": ev.get("doc_date")})

    finished = now_iso()
    run = {"id": run_id, "started": started, "finished": finished,
           "duration_s": round(time.time() - t0, 1), "today": today.isoformat(), "errors": errors,
           "discovery_since": since.isoformat(),
           "legal_discovery_since": (disc.get("legal_since") or since.isoformat())}
    dnl = do_not_list_tickers(rules)
    data = {
        "run": run, "status": status, "tickersAsOf": tick.get("asOf"),
        "labels": labels, "proposals": proposals,
        "aligned": aligned, "valuesFail": values_fail,
        "leads": [{"id": r["id"], "tickers": r["tickers"], "company": r["company"], "summary": r.get("summary", "").strip(),
                   "problems": r["check"]["problems"], "event_date": r.get("event_date"),
                   "sources": [{k: s.get(k) for k in ("publisher", "url", "doc_date", "tier")} for s in r["sources"]]}
                  for r in leads],
        "newTickerChecks": new_checks,
        "etf": etf_data, "etfDefaults": baseline.get("default_etfs", []),
        "blackCandidates": sorted(targets),
        "discovery": {"heldBack": [{"id": p["id"], "tickers": p["tickers"], "to": p["to"], "confidence": p["confidence"]} for p in held_back],
                      "legal": disc["legal"], "legalKnown": disc.get("legal_known", []),
                      "themes": disc["themes"][:40], "since": disc.get("legal_since")},
        "universe": {"sp500": sum(1 for v in universe.values() if v["origin"] == "S&P 500"),
                     "team": sum(1 for v in universe.values() if v["origin"] == "team list"),
                     "teamEtfs": sorted(team_etfs)},
        "doNotList": dnl,
        "rules": {"lookback_years": rules["black"]["lookback_years"], "gate": rules["aligned"]["financial_gate"],
                  "threshold_pct": rules["etf_lookthrough"]["flag_threshold_pct_of_portfolio"],
                  "per_amount": rules["etf_lookthrough"]["per_amount_fallback_usd"],
                  "sizing": rules["aligned"]["sizing_display_only"],
                  "themes": {k: v["label"] for k, v in rules["aligned"]["themes"].items()}},
    }
    (SITE / "data.json").write_text(json.dumps(data, indent=1, default=str))
    (OUT / "state.json").write_text(json.dumps({**data, "records": records}, indent=1, default=str))
    (OUT / "alerts.json").write_text(json.dumps(alerts, indent=1, default=str))
    prog.finished()

    # Summary
    print(f"Laura screen run {run['id']} finished in {run['duration_s']}s")
    print(f"Universe: {data['universe']['sp500']} S&P 500 + {data['universe']['team']} team stocks; "
          f"ETFs checked: {', '.join(etf_data)}")
    for p in proposals:
        print(f"  PROPOSAL {'+'.join(p['tickers']):10s} {p['from']:>8s} -> {p['to']:<8s} [{p['confidence']}] {p['clause_text'][:90]}")
    for r in values_fail:
        g = r["gate"]
        why = r.get("blocked") or ", ".join(g.get("failed", []) + [f"unknown:{u}" for u in g.get("unknown", [])])
        print(f"  VALUES FIT, NOT ALIGNED {r['ticker']:6s} gate={g['result']} ({why})")
    print(f"Leads needing a primary source: {len(leads)}")
    print(f"Discovery: {len(disc['legal'])} new legal matches since {disc.get('legal_since')}, "
          f"{len(disc['themes'])} theme matches (unreviewed)")
    print(f"Alerts to send: {len(alerts)}")
    for c in new_checks:
        g = (c.get("gate") or {}).get("result", "n/a")
        print(f"  NEW TICKER {c['ticker']:6s} gate={g} themes={list((c.get('theme_snippets') or {}).keys())} "
              f"legal_hits={len(c.get('legal_hits') or [])} annual={((c.get('annual_report') or {}).get('url'))}")
    for k, v in status.items():
        if not v.get("ok"):
            print(f"  SOURCE PROBLEM {k}: {v.get('error')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
