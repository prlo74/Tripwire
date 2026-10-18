"""Bridge between the pipeline and the Artifact database (read/written by Claude Code's
ArtifactData tool, which runs as the person at the keyboard).

  python -m pipeline.dbsync snapshot <dir>   # after ArtifactData list ... out_dir=<dir>
      -> out/db_snapshot.json (universe, approvals, runs) for pipeline.run
  python -m pipeline.dbsync export
      -> out/db_writes/*.json + out/db_writes/manifest.json: the writes for one
         ArtifactData "batch" call (runs/latest, runs/<id>, proposals/<id>, and deletes of
         proposals that no longer exist)

Never writes subscriber emails or secrets anywhere in the repo.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"


def _load_dir(d: Path, coll: str) -> list[dict]:
    base = d / coll
    if not base.exists():
        return []
    rows = []
    for p in sorted(base.glob("*.json")):
        doc = json.loads(p.read_text())
        body = doc.get("data", doc) if isinstance(doc, dict) else doc
        if isinstance(body, dict):
            body = {**body, "_id": p.stem, "_version": doc.get("version") if isinstance(doc, dict) else None}
            rows.append(body)
    return rows


def snapshot(d: Path) -> Path:
    snap = {"universe": _load_dir(d, "universe"), "approvals": _load_dir(d, "approvals"),
            "runs": [r for r in _load_dir(d, "runs") if str(r.get("_id", "")).startswith("run-")],
            "proposal_ids": [r["_id"] for r in _load_dir(d, "proposals")],
            "versions": {f"{c}/{r['_id']}": r["_version"] for c in ("runs", "proposals", "universe")
                         for r in _load_dir(d, c) if r.get("_version")}}
    # Saved documents carry only their data; versions come from the ArtifactData list results,
    # recorded by Claude in <dir>/versions.json as {"collection/doc_id": version}.
    vf = d / "versions.json"
    if vf.exists():
        snap["versions"].update(json.loads(vf.read_text()))
    dest = OUT / "db_snapshot.json"
    dest.write_text(json.dumps(snap, indent=1))
    print(f"snapshot: {len(snap['universe'])} universe, {len(snap['approvals'])} approvals, "
          f"{len(snap['runs'])} runs, {len(snap['proposal_ids'])} proposals -> {dest}")
    return dest


def run_stats(data: dict) -> dict:
    """Team-level numbers for the analytics page, recorded with each run (no personal data)."""
    st = data.get("status", {})
    ev = st.get("Evidence re-check", {})
    uni = data.get("universe", {}) if isinstance(data.get("universe"), dict) else {}
    by_to = {}
    for p in data.get("proposals", []):
        by_to[p["to"]] = by_to.get(p["to"], 0) + 1
    return {"sources_checked": len(st), "sources_ok": sum(1 for v in st.values() if v.get("ok")),
            "evidence_records": ev.get("records"), "evidence_sources_opened": ev.get("sources_opened"),
            "sp500": uni.get("sp500"), "team_tickers": uni.get("team"),
            "new_tickers_checked": len(data.get("newTickerChecks", [])),
            "proposals_by_list": by_to, "values_fail": len(data.get("valuesFail", [])),
            "leads": len(data.get("leads", []))}


def export() -> Path:
    data = json.loads((ROOT / "site" / "data.json").read_text())
    snap = json.loads((OUT / "db_snapshot.json").read_text()) if (OUT / "db_snapshot.json").exists() else {}
    wdir = OUT / "db_writes"
    shutil.rmtree(wdir, ignore_errors=True)
    wdir.mkdir(parents=True)
    writes = []

    def put(coll, doc_id, body):
        f = wdir / f"{coll}__{doc_id}.json"
        f.write_text(json.dumps(body, default=str))
        w = {"op": "set", "collection": coll, "doc_id": doc_id, "file_path": str(f)}
        v = snap.get("versions", {}).get(f"{coll}/{doc_id}")
        if v:
            w["if_version"] = v  # the db refuses unpinned overwrites of existing documents
        writes.append(w)

    latest = {k: v for k, v in data.items() if k != "proposals"}
    put("runs", "latest", latest)
    run = data["run"]
    put("runs", run["id"], {"id": run["id"], "started": run["started"], "finished": run["finished"],
                            "duration_s": run["duration_s"], "errors": run["errors"],
                            "proposals": len(data["proposals"]),
                            "sources_down": [k for k, v in data["status"].items() if not v.get("ok")],
                            "stats": run_stats(data)})
    live = set()
    for p in data["proposals"]:
        put("proposals", p["id"], p)
        live.add(p["id"])
    for old in snap.get("proposal_ids", []):
        if old not in live:
            d = {"op": "delete", "collection": "proposals", "doc_id": old}
            if snap.get("versions", {}).get(f"proposals/{old}"):
                d["if_version"] = snap["versions"][f"proposals/{old}"]
            writes.append(d)
    # Mark newly checked team tickers, with a one-line outcome the page shows next to each ticker.
    by_ticker = {}
    for p in data["proposals"]:
        state = "approved" if p.get("decision") == "approve" else "rejected" if p.get("decision") == "reject" else "proposed"
        for t in p["tickers"]:
            by_ticker.setdefault(t, []).append(f"{'No finding' if p['to'] == 'nofinding' else p['to'].title()} ({state})")
    fails = {r["ticker"]: r for r in data.get("valuesFail", [])}
    # The check finishes when its results are written (after Claude reads the evidence), not when
    # the pipeline's fetch step ended, so stamp the export time.
    done_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in data.get("newTickerChecks", []):
        t = c["ticker"]
        if c.get("kind") == "etf":
            summary = "ETF: holdings added to the look-through check"
        elif t in by_ticker:
            summary = ", ".join(sorted(set(by_ticker[t])))
        elif t in fails:
            summary = "Values link found, but fails the financial screen"
        elif c.get("errors"):
            summary = "Check incomplete: " + "; ".join(c["errors"])
        else:
            g = (c.get("gate") or {}).get("result", "unknown")
            summary = "No values link or qualifying legal finding found" + (f" (financial gate: {g})" if g != "pass" else "")
        body = {"checked_at": done_at, "check_run": data["run"]["id"], "check_summary": summary}
        f = wdir / f"universe__{t}.json"
        f.write_text(json.dumps(body))
        w = {"op": "update", "collection": "universe", "doc_id": t, "file_path": str(f)}
        v = snap.get("versions", {}).get(f"universe/{t}")
        if v:
            w["if_version"] = v
        writes.append(w)
    (wdir / "manifest.json").write_text(json.dumps(writes, indent=1))
    print(f"{len(writes)} writes -> {wdir / 'manifest.json'}")
    return wdir / "manifest.json"


if __name__ == "__main__":
    if sys.argv[1] == "snapshot":
        snapshot(Path(sys.argv[2]))
    elif sys.argv[1] == "export":
        export()
