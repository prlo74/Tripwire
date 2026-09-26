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
            body = {**body, "_id": p.stem}
            rows.append(body)
    return rows


def snapshot(d: Path) -> Path:
    snap = {"universe": _load_dir(d, "universe"), "approvals": _load_dir(d, "approvals"),
            "runs": [r for r in _load_dir(d, "runs") if r.get("_id") != "latest"],
            "proposal_ids": [r["_id"] for r in _load_dir(d, "proposals")]}
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
        writes.append({"op": "set", "collection": coll, "doc_id": doc_id, "file_path": str(f)})

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
            writes.append({"op": "delete", "collection": "proposals", "doc_id": old})
    (wdir / "manifest.json").write_text(json.dumps(writes, indent=1))
    print(f"{len(writes)} writes -> {wdir / 'manifest.json'}")
    return wdir / "manifest.json"


if __name__ == "__main__":
    if sys.argv[1] == "snapshot":
        snapshot(Path(sys.argv[2]))
    elif sys.argv[1] == "export":
        export()
