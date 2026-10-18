"""Check requests from the public page: GitHub issues titled "Check: AAPL, MSFT".

pending : (--dry: only count) read open issues on the public repo, keep only tickers that are in site/tickers.json,
          skip issues already answered in site/requests.json. Writes cache/requests_pending.json,
          adds new tickers to cache/db/universe/ (so `dbsync snapshot` sees them) and writes
          cache/requests_universe/manifest.json (ArtifactData batch entries that create them).
record  : after `dbsync export`, attach each requested ticker's check result and write
          site/requests.json (public) and cache/issue_comments/<n>.md (one reply per issue).
decisions: write site/decisions.json from cache/db/approvals so the public copy shows which
          proposals the team approved or rejected. No account ids and no reasons are copied.

Issue text is untrusted. Only the title after "Check:" is read, split into ticker-shaped
tokens, and a token is kept only if it is in the ticker map. Nothing else from an issue is used.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CACHE = ROOT / "cache"
REPO = os.environ.get("TRIPWIRE_REPO", "prlo74/Tripwire")
PAGE = "https://prlo74.github.io/Tripwire/"
MAX_TICKERS = 15          # new tickers checked per run, across all requests
KEEP = 100                # requests kept in site/requests.json
TITLE = re.compile(r"^\s*check\s*:\s*(.*)$", re.I)
TOKEN = re.compile(r"^\$?([A-Z]{1,6}(?:[.\-/][A-Z]{1,2})?)$")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canon(tok: str) -> str:
    return tok.strip().lstrip("$").upper().replace(".", "-").replace("/", "-")


def parse_title(title: str, tmap: dict) -> dict | None:
    """{"tickers": [...], "rejected": [...], "full": bool}, or None if not a check request."""
    m = TITLE.match(title or "")
    if not m:
        return None
    rest = m.group(1).strip()
    if re.fullmatch(r"(full( screen)?|all)\.?", rest, re.I) or not rest:
        return {"tickers": [], "rejected": [], "full": True}
    keep, bad = [], []
    for raw in re.split(r"[,;\s]+", rest):
        if not raw:
            continue
        t = canon(raw)
        if TOKEN.match(raw.strip().upper()) and t in tmap:
            if t not in keep:
                keep.append(t)
        elif len(bad) < 20:
            bad.append(raw[:12])
    return {"tickers": keep, "rejected": bad, "full": False}


def _load_requests() -> dict:
    p = SITE / "requests.json"
    return json.loads(p.read_text()) if p.exists() else {"repo": REPO, "requests": []}


def _open_issues() -> list[dict]:
    hdrs = {"Accept": "application/vnd.github+json", "User-Agent": "Tripwire-check-requests"}
    if os.environ.get("GITHUB_TOKEN"):
        hdrs["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    out, page = [], 1
    while page <= 5:
        r = requests.get(f"https://api.github.com/repos/{REPO}/issues", headers=hdrs, timeout=30,
                         params={"state": "open", "per_page": 100, "page": page, "sort": "created",
                                 "direction": "asc"})
        r.raise_for_status()
        batch = r.json()
        out += [i for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            break
        page += 1
    return out


def pending(issues: list[dict] | None = None, dry: bool = False) -> dict:
    tmap = json.loads((SITE / "tickers.json").read_text())["t"]
    done = {r["issue"] for r in _load_requests()["requests"] if r.get("checked")}
    uni_dir = CACHE / "db" / "universe"
    have = {p.stem for p in uni_dir.glob("*.json")} if uni_dir.exists() else set()
    issues = _open_issues() if issues is None else issues
    taken, budget, deferred = [], MAX_TICKERS, []
    for i in sorted(issues, key=lambda x: x["number"]):
        if i["number"] in done:
            continue
        req = parse_title(i.get("title", ""), tmap)
        if req is None:
            continue
        new = [t for t in req["tickers"] if t not in have]
        if new and len(new) > budget:
            if taken:                       # finish earlier requests first; this one waits
                deferred.append(i["number"])
                continue
            req["over_limit"] = new[budget:]
            req["tickers"] = [t for t in req["tickers"] if t not in req["over_limit"]]
            new = new[:budget]
        budget -= len(new)
        have.update(new)
        taken.append({"issue": i["number"], "url": i["html_url"], "by": (i.get("user") or {}).get("login"),
                      "opened": i.get("created_at"), "new": new, **req})
    if dry:                                 # first look before the database is read: no files
        n = sum(len(r["tickers"]) or 1 for r in taken)
        print(f"{len(taken)} pending request(s) ({n} item(s)), {len(deferred)} deferred")
        return {"requests": taken, "deferred": deferred}
    CACHE.mkdir(exist_ok=True)
    wdir = CACHE / "requests_universe"
    wdir.mkdir(exist_ok=True)
    uni_dir.mkdir(parents=True, exist_ok=True)
    writes = []
    for r in taken:
        for t in r["new"]:
            name, kind = tmap[t][0], tmap[t][1]
            doc = {"ticker": t, "type": "etf" if kind == "E" else "stock", "name": name,
                   "added_by": f"github:{r['by']}", "added_at": r["opened"] or now_iso(),
                   "request_issue": r["issue"]}
            (uni_dir / f"{t}.json").write_text(json.dumps(doc, indent=1))
            f = wdir / f"universe__{t}.json"
            f.write_text(json.dumps(doc))
            writes.append({"op": "set", "collection": "universe", "doc_id": t, "file_path": str(f)})
    (wdir / "manifest.json").write_text(json.dumps(writes, indent=1))
    res = {"requests": taken, "deferred": deferred, "new_tickers": sum(len(r["new"]) for r in taken)}
    (CACHE / "requests_pending.json").write_text(json.dumps(res, indent=1))
    print(f"{len(taken)} request(s), {res['new_tickers']} new ticker(s) to add, {len(deferred)} deferred "
          f"-> {wdir / 'manifest.json'}")
    for r in taken:
        print(f"  #{r['issue']} {r['by']}: {', '.join(r['tickers']) or 'full screen'}"
              + (f"  (not tickers: {', '.join(r['rejected'])})" if r["rejected"] else ""))
    return res


def _results() -> tuple[dict, str | None, str | None]:
    """ticker -> check result, from this run's export (falls back to the db snapshot)."""
    out = {}
    snap = ROOT / "out" / "db_snapshot.json"
    if snap.exists():
        for d in json.loads(snap.read_text()).get("universe") or []:
            if isinstance(d, dict) and d.get("check_summary"):
                out[d.get("ticker") or d.get("_id")] = d["check_summary"]
    for f in (ROOT / "out" / "db_writes").glob("universe__*.json"):
        d = json.loads(f.read_text())
        if d.get("check_summary"):
            out[f.stem.split("__", 1)[1]] = d["check_summary"]
    data = json.loads((SITE / "data.json").read_text())
    run = data.get("run") or {}
    return out, run.get("id"), run.get("finished")


def record() -> Path:
    pend = json.loads((CACHE / "requests_pending.json").read_text())
    tmap = json.loads((SITE / "tickers.json").read_text())["t"]
    results, run_id, finished = _results()
    store = _load_requests()
    cdir = CACHE / "issue_comments"
    cdir.mkdir(parents=True, exist_ok=True)
    for r in pend["requests"]:
        rows = [{"ticker": t, "name": tmap.get(t, [""])[0], "type": "etf" if tmap.get(t, ["", ""])[1] == "E" else "stock",
                 "result": results.get(t, "Not checked in this run")} for t in r["tickers"]]
        entry = {"issue": r["issue"], "url": r["url"], "by": r["by"], "opened": r["opened"],
                 "checked": finished or now_iso(), "run": run_id, "full": r["full"], "tickers": rows,
                 "rejected": r["rejected"], "over_limit": r.get("over_limit", [])}
        store["requests"] = [x for x in store["requests"] if x["issue"] != r["issue"]] + [entry]
        lines = [f"Checked in run `{run_id}`." if run_id else "Checked.", ""]
        if rows:
            lines += ["| Ticker | Result |", "|---|---|"] + [f"| {x['ticker']} | {x['result']} |" for x in rows]
        else:
            lines += ["Full screen run. The lists on the page are now up to date."]
        if r["rejected"]:
            lines += ["", "Not recognised as US tickers: " + ", ".join(r["rejected"])]
        if r.get("over_limit"):
            lines += ["", f"Over the {MAX_TICKERS}-ticker limit per run, not checked: " + ", ".join(r["over_limit"])]
        lines += ["", f"Proposals still need a team member's approval before anything is on a list. Page: {PAGE}"]
        (cdir / f"{r['issue']}.md").write_text("\n".join(lines) + "\n")
    store["repo"] = REPO
    store["updated"] = now_iso()
    store["requests"] = sorted(store["requests"], key=lambda x: x["issue"])[-KEEP:]
    p = SITE / "requests.json"
    p.write_text(json.dumps(store, indent=1))
    print(f"recorded {len(pend['requests'])} request(s) -> {p}; replies in {cdir}")
    return p


PUBLIC_DECISION_FIELDS = ("proposal_id", "decision", "decided_at", "tickers", "from", "to", "company",
                          "clause", "tripwire", "event_date", "evidence", "evidence_hash")


def decisions(src: Path | None = None) -> Path:
    src = src or CACHE / "db" / "approvals"
    out = {}
    for f in sorted(src.glob("*.json")):
        d = json.loads(f.read_text())
        d = d.get("data", d)
        if d.get("decision") in ("approve", "reject"):
            out[d.get("proposal_id") or f.stem] = {k: d[k] for k in PUBLIC_DECISION_FIELDS if k in d}
    p = SITE / "decisions.json"
    p.write_text(json.dumps({"updated": now_iso(), "approvals": out}, indent=1))
    print(f"{len(out)} decisions -> {p}")
    return p


if __name__ == "__main__":
    if sys.argv[1] == "pending":
        pending(dry="--dry" in sys.argv)
    else:
        {"record": record, "decisions": decisions}[sys.argv[1]]()
