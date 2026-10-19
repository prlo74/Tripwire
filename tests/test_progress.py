"""Run progress for the page's progress bar: pipeline stage reporting, the relay CLI, the measured
stage timing, and the page's Runbar model (tests/runbar.test.js)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import progress, run
from pipeline.evidence import check_record
from pipeline.http import SourceError

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cache(tmp_path, monkeypatch):
    for name, f in [("CACHE", tmp_path), ("STATE", tmp_path / "progress.json"),
                    ("PIPELINE", tmp_path / "progress_pipeline.json"), ("DOC", tmp_path / "progress_doc.json"),
                    ("TIMING", tmp_path / "run_timing.json")]:
        monkeypatch.setattr(progress, name, f)
    return tmp_path


def test_runbar_model_js():
    r = subprocess.run(["node", str(ROOT / "tests" / "runbar.test.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().endswith("20 passed")


def test_stage_ids_match_the_page():
    src = (ROOT / "site" / "runbar.js").read_text()
    page_ids = re.findall(r'\{ id: "(\w+)"', src)
    assert page_ids == ["starting"] + progress.IDS


def test_pipeline_reports_stages_and_counts(cache, tmp_path, monkeypatch):
    """Runs the real pipeline offline (sources stubbed, outputs in a temp folder)."""
    site, out = tmp_path / "site", tmp_path / "out"
    site.mkdir()
    shutil.copy(ROOT / "site" / "tickers.json", site / "tickers.json")
    monkeypatch.setattr(run, "SITE", site)
    monkeypatch.setattr(run, "OUT", out)

    def down(*a, **k):
        raise SourceError("offline test")
    monkeypatch.setattr(run, "build_tickers", down)
    monkeypatch.setattr(run.etf, "ssga_holdings", down)
    monkeypatch.setattr(run.etf, "holdings", down)
    monkeypatch.setattr(run, "check_record", lambda r, rules, today: check_record(r, rules, today, open_sources=False))
    monkeypatch.setattr(run.financial, "financial_gate", lambda *a, **k: {"result": "unknown", "checks": {},
                                                                           "failed": [], "unknown": ["offline"]})
    saved, real_write = [], progress._write
    monkeypatch.setattr(progress, "_write", lambda path, obj: (saved.append(json.loads(json.dumps(obj))),
                                                              real_write(path, obj)))
    assert run.main(["--progress", "--no-discovery", "--db", str(tmp_path / "none.json")]) == 0

    pl = json.loads(progress.PIPELINE.read_text())
    assert [h["phase"] for h in pl["history"]] == ["records", "financials", "etf", "discovery"]
    assert pl["pipeline_done"] is True
    data = json.loads((site / "data.json").read_text())
    assert pl["run_id"] == data["run"]["id"]
    rec = [d for d in saved if d["phase"] == "records"]
    n_sources = sum(len(r.get("sources", [])) for r in run.load_records())
    assert n_sources > 0 and rec[0]["done"] == 0 and rec[-1]["done"] == rec[-1]["total"] == n_sources
    assert [d["done"] for d in rec] == sorted(d["done"] for d in rec)        # never goes backwards
    fin = [d for d in saved if d["phase"] == "financials"]
    assert fin[-1]["unit"] == "companies" and fin[-1]["done"] == fin[-1]["total"]
    assert [d for d in saved if d["phase"] == "discovery"][-1]["total"] is None   # no count -> none sent


def test_pipeline_without_progress_flag_writes_nothing(cache):
    rep = progress.Reporter(False, "run-x")
    rep.phase("records", total=3, unit="sources checked")
    rep.tick()
    rep.finished()
    assert not progress.PIPELINE.exists()


def test_failed_local_write_turns_reporting_off_without_failing(cache, monkeypatch, capsys):
    def boom(p, obj):
        raise OSError("disk full")
    monkeypatch.setattr(progress, "_write", boom)
    rep = progress.Reporter(True, "run-x")
    rep.phase("records", total=3, unit="sources checked")   # must not raise
    rep.tick()
    assert rep.enabled is False
    assert "progress reporting is off" in capsys.readouterr().err


def _cli(*args):
    return progress.main(list(args))


def test_relay_flow_start_wait_phase_finish(cache, capsys, monkeypatch):
    _cli("start", "--requested-at", "2026-10-04T12:00:00Z")
    doc = json.loads(progress.DOC.read_text())
    assert doc["state"] == "running" and doc["phase"] == "universe" and doc["phase_index"] == 2
    assert "done" not in doc and "total" not in doc    # no made-up count

    rep = progress.Reporter(True, "run-20261004T120100")
    rep.phase("records", total=28, unit="sources checked")
    _cli("wait", "--timeout", "1")
    doc = json.loads(progress.DOC.read_text())
    assert doc["phase"] == "records" and doc["phase_index"] == 3
    assert (doc["done"], doc["total"], doc["unit"]) == (0, 28, "sources checked")
    assert doc["run_id"] == "run-20261004T120100"

    # A count moves only after 5 more items AND 15 s since the last write.
    rep.tick(6)
    capsys.readouterr()
    _cli("wait", "--timeout", "1")
    assert json.loads(capsys.readouterr().out)["write"] is None
    st = json.loads(progress.STATE.read_text())
    st["last_emit"]["at"] -= 20
    progress.STATE.write_text(json.dumps(st))
    capsys.readouterr()
    _cli("wait", "--timeout", "1", "--stages-only")
    assert json.loads(capsys.readouterr().out)["write"] is None      # counts skipped on request
    _cli("wait", "--timeout", "1")
    assert json.loads(progress.DOC.read_text())["done"] == 6

    rep.phase("financials", total=4, unit="companies")
    rep.phase("etf", total=9, unit="funds")
    rep.phase("discovery")
    rep.finished()
    _cli("wait", "--timeout", "1")
    doc = json.loads(progress.DOC.read_text())
    assert doc["phase"] == "discovery" and "total" not in doc   # skipped stages still recorded below

    _cli("phase", "publish")
    assert json.loads(progress.DOC.read_text())["phase"] == "publish"
    capsys.readouterr()
    _cli("finish")
    out = capsys.readouterr().out
    summary = json.loads(out[: out.index("\n}\n") + 2])
    pm = summary["timing"]["phase_ms"]
    assert set(pm) == {"starting", *progress.IDS} and summary["missing_stages"] == []
    assert summary["timing"]["total_ms"] == sum(pm.values())
    assert json.loads(progress.DOC.read_text())["state"] == "done"


def test_phase_ms_from_history():
    h = [{"phase": "universe", "at": "2026-10-04T12:01:00Z"}, {"phase": "records", "at": "2026-10-04T12:01:10Z"},
         {"phase": "financials", "at": "2026-10-04T12:01:40Z"}, {"phase": "etf", "at": "2026-10-04T12:01:50Z"},
         {"phase": "discovery", "at": "2026-10-04T12:02:00Z"}, {"phase": "publish", "at": "2026-10-04T12:05:00Z"}]
    pm = progress.phase_ms(h, "2026-10-04T12:01:00Z", "2026-10-04T12:06:00Z", "2026-10-04T12:00:15Z", None)
    assert pm == {"starting": 45000, "universe": 10000, "records": 30000, "financials": 10000, "etf": 10000,
                  "discovery": 180000, "publish": 60000}


def test_scheduled_run_carries_starting_forward():
    h = [{"phase": "universe", "at": "2026-10-04T12:01:00Z"}]
    assert progress.phase_ms(h, "2026-10-04T12:01:00Z", "2026-10-04T12:02:00Z", None, 41000)["starting"] == 41000
    assert progress.phase_ms(h, "2026-10-04T12:01:00Z", "2026-10-04T12:02:00Z", None, None)["starting"] == 60000


def test_missing_stage_is_reported_not_invented(cache, capsys):
    _cli("start")
    _cli("phase", "publish")     # e.g. the pipeline never ran
    capsys.readouterr()
    _cli("finish")
    out = capsys.readouterr().out
    summary = json.loads(out[: out.index("\n}\n") + 2])
    assert set(summary["missing_stages"]) == {"records", "financials", "etf", "discovery"}
    assert "records" not in summary["timing"]["phase_ms"]


def test_starting_is_capped_so_a_stale_request_cannot_swamp_the_bar():
    from pipeline.progress import phase_ms, DEFAULT_STARTING_MS
    hist = [{"phase": "universe", "at": "2026-10-19T01:40:50Z"}]
    pm = phase_ms(hist, "2026-10-19T01:40:50Z", "2026-10-19T01:44:00Z", "2026-10-07T05:16:35Z", None)
    assert pm["starting"] == DEFAULT_STARTING_MS
    pm = phase_ms(hist, "2026-10-19T01:40:50Z", "2026-10-19T01:44:00Z", None, 581277006)
    assert pm["starting"] == DEFAULT_STARTING_MS
    pm = phase_ms(hist, "2026-10-19T01:40:50Z", "2026-10-19T01:44:00Z", "2026-10-19T01:40:05Z", None)
    assert pm["starting"] == 45000
