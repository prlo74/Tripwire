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
            "runs": [r for r in _load_dir(d, "runs") if r.get("_id") != "latest"],
            "proposal_ids": [r["_id"] for r in _load_dir(d, "proposals")],
            "versions": {f"{c}/{r['_id']}": r["_version"] for c in ("runs", "proposals", "universe")
                         for r in _load_dir(d, c) if r.get("_version")}}
    dest = OUT / "db_snapshot.json"
    dest.write_text(json.dumps(snap, indent=1))
    print(f"snapshot: {len(snap['universe'])} universe, {len(snap['approvals'])} approvals, "
          f"{len(snap['runs'])} runs, {len(snap['proposal_ids'])} proposals -> {dest}")
    return dest


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
                            "sources_down": [k for k, v in data["status"].items() if not v.get("ok")]})
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
        for t in p["tickers"]:
            by_ticker.setdefault(t, []).append(p["to"])
    fails = {r["ticker"]: r for r in data.get("valuesFail", [])}
    for c in data.get("newTickerChecks", []):
        t = c["ticker"]
        if c.get("kind") == "etf":
            summary = "ETF: holdings added to the look-through check"
        elif t in by_ticker:
            summary = "Proposed: " + ", ".join(sorted(set(by_ticker[t]))) + " (see Needs approval)"
        elif t in fails:
            summary = "Values link found, but fails the financial screen"
        elif c.get("errors"):
            summary = "Check incomplete: " + "; ".join(c["errors"])
        else:
            g = (c.get("gate") or {}).get("result", "unknown")
            summary = "No values link or qualifying legal finding found" + (f" (financial gate: {g})" if g != "pass" else "")
        body = {"checked_at": data["run"]["finished"], "check_run": data["run"]["id"], "check_summary": summary}
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
