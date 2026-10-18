"""Run progress for the page's progress bar (runs/progress in the Artifact database).

The pipeline cannot write to the database; Claude Code does, with ArtifactData. So this module
keeps the progress locally and prints the document for Claude to write:

    python -m pipeline.progress start [--requested-at ISO]   # first action of every run
    python -m pipeline.progress wait [--timeout 120] [--stages-only]   # while pipeline.run --progress runs
    python -m pipeline.progress phase <stage> [--done N --total M --unit U]
    python -m pipeline.progress finish [--requested-at ISO]   # after the results are written

Each command saves the document to write as cache/progress_doc.json and prints it. `finish` also
saves cache/run_timing.json ({"run": {... "timing": {total_ms, phase_ms}}}) for runs/latest.

`python -m pipeline.run --progress` records its own stage changes and counts in
cache/progress_pipeline.json (only the pipeline writes that file; only this CLI writes
cache/progress.json, so the two never overwrite each other).

Stage ids must equal Runbar.PHASES ids in site/runbar.js ("starting" is the page's own first step).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
STATE = CACHE / "progress.json"
PIPELINE = CACHE / "progress_pipeline.json"
DOC = CACHE / "progress_doc.json"
TIMING = CACHE / "run_timing.json"

# (id, label). phase_index counts the page's "starting" step as 1, so universe is 2.
STAGES = [
    ("universe", "Ticker lists and S&P 500"),
    ("records", "Court and agency records"),
    ("financials", "Financial gates and new tickers"),
    ("etf", "ETF holdings"),
    ("discovery", "Discovery and evidence review"),
    ("publish", "Writing results"),
]
IDS = [s[0] for s in STAGES]
LABELS = dict(STAGES)
DEFAULT_STARTING_MS = 60000
COUNT_STEP = 5          # relay a count after this many more items...
COUNT_MIN_GAP_S = 15    # ...and not more often than this


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms(s: str | None) -> int:
    if not s:
        return 0
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


def _read(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _write(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, p)  # atomic: a reader never sees a half-written file


class Reporter:
    """Used by pipeline.run --progress. A failed local write disables reporting and says so;
    it never fails the run."""

    def __init__(self, enabled: bool, run_id: str | None = None):
        self.enabled = enabled
        self.doc = {"run_id": run_id, "phase": None, "done": None, "total": None, "unit": None,
                    "history": [], "pipeline_done": False}

    def _save(self) -> None:
        if not self.enabled:
            return
        self.doc["updated_at"] = now_iso()
        try:
            _write(PIPELINE, self.doc)
        except OSError as e:
            print(f"progress: could not write {PIPELINE} ({e}); progress reporting is off for this run",
                  file=sys.stderr)
            self.enabled = False

    def phase(self, stage: str, total: int | None = None, unit: str | None = None) -> None:
        assert stage in IDS, stage
        at = now_iso()
        self.doc.update(phase=stage, done=0 if total else None, total=total or None, unit=unit if total else None)
        self.doc["history"].append({"phase": stage, "at": at})
        self._save()

    def tick(self, n: int = 1) -> None:
        if self.doc["total"]:
            self.doc["done"] = min(self.doc["total"], (self.doc["done"] or 0) + n)
            self._save()

    def finished(self) -> None:
        self.doc["pipeline_done"] = True
        self._save()


def _doc(st: dict) -> dict:
    """The runs/progress document. Counts only when the stage has a real count."""
    d = {"state": st["state"], "started_at": st["started_at"], "phase": st["phase"],
         "phase_index": IDS.index(st["phase"]) + 2, "label": LABELS[st["phase"]],
         "phase_started_at": st["phase_started_at"], "updated_at": now_iso()}
    if st.get("run_id"):
        d["run_id"] = st["run_id"]
    if st.get("total"):
        d.update(done=st["done"] or 0, total=st["total"], unit=st["unit"])
    return d


def _emit(st: dict, reason: str) -> dict:
    doc = _doc(st)
    st["writes"] = st.get("writes", 0) + 1
    st["last_emit"] = {"at": time.time(), "phase": st["phase"], "done": st.get("done")}
    _write(STATE, st)
    _write(DOC, doc)
    print(json.dumps({"write": "runs/progress", "file_path": str(DOC), "reason": reason, "doc": doc}, indent=1))
    return doc


def _set_phase(st: dict, stage: str, at: str) -> None:
    if st["phase"] != stage:
        st["history"].append({"phase": stage, "at": at})
    st.update(phase=stage, phase_started_at=at, done=None, total=None, unit=None)


def cmd_start(a) -> int:
    at = now_iso()
    st = {"state": "running", "started_at": at, "requested_at": a.requested_at, "phase": "universe",
          "phase_started_at": at, "history": [{"phase": "universe", "at": at}], "writes": 0}
    for p in (PIPELINE, TIMING):
        p.unlink(missing_ok=True)  # leftovers from an earlier run must not leak into this one
    _emit(st, "run started")
    return 0


def _load_state() -> dict:
    st = _read(STATE)
    if not st:
        sys.exit("progress: no run started (run `python -m pipeline.progress start` first)")
    return st


def _merge_pipeline(st: dict) -> dict | None:
    """Fold the pipeline's stage changes and counts into the CLI state."""
    pl = _read(PIPELINE)
    if not pl:
        return None
    if pl.get("run_id"):
        st["run_id"] = pl["run_id"]
    known = {(h["phase"], h["at"]) for h in st["history"]}
    for h in pl.get("history", []):
        if (h["phase"], h["at"]) not in known and h["phase"] != st["phase"]:
            _set_phase(st, h["phase"], h["at"])
    if pl.get("phase") == st["phase"] and pl.get("total"):
        st.update(done=pl["done"], total=pl["total"], unit=pl["unit"])
    return pl


def cmd_wait(a) -> int:
    """Block until there is something worth writing: a new stage, the count moved by COUNT_STEP
    (at most every COUNT_MIN_GAP_S), or the pipeline finished. Prints the document to write."""
    st = _load_state()
    deadline = time.time() + a.timeout
    while True:
        pl = _merge_pipeline(st)
        last = st.get("last_emit") or {}
        done_flag = bool(pl and pl.get("pipeline_done"))
        if st["phase"] != last.get("phase"):
            _emit(st, "new stage" + (" (pipeline finished)" if done_flag else ""))
            return 0
        if done_flag:
            _write(STATE, st)
            print(json.dumps({"write": None, "reason": "pipeline finished; no new stage to write"}))
            return 0
        moved = (st.get("done") or 0) - (last.get("done") or 0)
        if not a.stages_only and st.get("total") and moved >= COUNT_STEP and time.time() - last.get("at", 0) >= COUNT_MIN_GAP_S:
            _emit(st, "count")
            return 0
        if time.time() >= deadline:
            _write(STATE, st)
            print(json.dumps({"write": None, "reason": f"nothing new in {a.timeout}s"}))
            return 0
        time.sleep(1)


def cmd_phase(a) -> int:
    st = _load_state()
    _merge_pipeline(st)
    _set_phase(st, a.stage, now_iso())
    if a.total:
        st.update(done=a.done or 0, total=a.total, unit=a.unit)
    _emit(st, f"stage {a.stage}")
    return 0


def phase_ms(history: list[dict], started_at: str, ended_at: str, requested_at: str | None,
             prev_starting: int | None) -> dict:
    """Duration of each stage from its first start to the next stage's start. "starting" is the
    time from the button press to the first progress write; a scheduled run has no press, so the
    previous run's value (or 60 s) is carried forward."""
    req = ms(requested_at)
    starting = ms(started_at) - req if req and req <= ms(started_at) else (prev_starting or DEFAULT_STARTING_MS)
    first: dict[str, int] = {}
    for h in history:
        first.setdefault(h["phase"], ms(h["at"]))
    out = {"starting": starting}
    order = [p for p in IDS if p in first]
    for i, p in enumerate(order):
        nxt = first[order[i + 1]] if i + 1 < len(order) else ms(ended_at)
        out[p] = max(0, nxt - first[p])
    return out


def _prev_starting() -> int | None:
    latest = _read(CACHE / "db" / "runs" / "latest.json") or {}
    body = latest.get("data", latest)
    v = (((body.get("run") or {}).get("timing") or {}).get("phase_ms") or {}).get("starting")
    return v if isinstance(v, int) and v > 0 else None


def cmd_finish(a) -> int:
    st = _load_state()
    _merge_pipeline(st)
    end = now_iso()
    pm = phase_ms(st["history"], st["started_at"], end, a.requested_at or st.get("requested_at"), _prev_starting())
    timing = {"total_ms": sum(pm.values()), "phase_ms": pm}
    missing = [p for p in IDS if p not in pm]
    data = _read(ROOT / "site" / "data.json") or {}
    if data.get("run"):
        _write(TIMING, {"run": {**data["run"], "timing": timing}})
    st["state"] = "done"
    st["phase_started_at"] = st.get("phase_started_at") or end
    print(json.dumps({"timing": timing, "missing_stages": missing,
                      "runs_latest_update": str(TIMING) if data.get("run") else None,
                      "progress_writes_before_this": st.get("writes", 0)}, indent=1))
    _emit(st, "run finished")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.progress")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--requested-at", default=None, help="settings/weekly.check_requested_at for a Check now run")
    w = sub.add_parser("wait")
    w.add_argument("--timeout", type=int, default=120)
    w.add_argument("--stages-only", action="store_true", help="skip count updates (if writes slow the run)")
    p = sub.add_parser("phase")
    p.add_argument("stage", choices=IDS)
    p.add_argument("--done", type=int)
    p.add_argument("--total", type=int)
    p.add_argument("--unit")
    f = sub.add_parser("finish")
    f.add_argument("--requested-at", default=None)
    a = ap.parse_args(argv)
    return {"start": cmd_start, "wait": cmd_wait, "phase": cmd_phase, "finish": cmd_finish}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
