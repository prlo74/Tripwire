"""S&P 500 rotation: each member checked once per cycle; results kept apart from the team list."""
import json
from datetime import date, timedelta

from pipeline import dbsync, newtickers
from pipeline.run import rotation_group

RULES = {"sp500_rotation": {"enabled": True, "cycle_days": 3}}
SP = {f"T{i:03d}": {"origin": "S&P 500"} for i in range(500)}


def test_every_member_once_per_cycle_in_even_thirds():
    d0 = date(2026, 10, 19)
    days = [rotation_group(SP, RULES, d0 + timedelta(days=k), set()) for k in range(3)]
    seen = [t for g in days for t in g]
    assert sorted(seen) == sorted(SP)                      # all members, no repeats
    assert all(130 <= len(g) <= 210 for g in days)          # roughly a third each day
    assert rotation_group(SP, RULES, d0 + timedelta(days=3), set()) == days[0]


def test_index_change_moves_only_that_company_and_skips_team_checks():
    d0 = date(2026, 10, 19)
    before = rotation_group(SP, RULES, d0, set())
    sp2 = {**{t: v for t, v in SP.items() if t != before[0]}, "NEW1": {"origin": "S&P 500"}}
    after = rotation_group(sp2, RULES, d0, set())
    assert set(before) - {before[0]} <= set(after)
    assert before[1] not in rotation_group(SP, RULES, d0, {before[1]})
    assert rotation_group({"X": {"origin": "team list"}}, RULES, d0, set()) == []
    assert rotation_group(SP, {"sp500_rotation": {"enabled": False}}, d0, set()) == []


def test_passages_quote_the_text_around_each_term(monkeypatch):
    text = "Intro. " + "x " * 600 + "The EEOC filed a charge alleging racial discrimination at a plant. " + "y " * 600
    monkeypatch.setattr(newtickers, "doc_text", lambda url: text)
    out = newtickers.passages("u", ["racial discrimination", "defamation"], width=40)
    assert len(out) == 1 and "racial discrimination at a plant" in out[0] and out[0].startswith("…")


def test_export_writes_rotation_results_to_sp500_checks(tmp_path, monkeypatch):
    (tmp_path / "site").mkdir(); (tmp_path / "out").mkdir()
    data = {"run": {"id": "run-1", "started": "x", "finished": "x", "duration_s": 1, "errors": []},
            "status": {}, "proposals": [], "valuesFail": [],
            "newTickerChecks": [{"ticker": "AAPL", "company": "Apple Inc.", "kind": "stock", "errors": [], "gate": {"result": "pass"}, "rotation": True},
                                {"ticker": "NFLX", "company": "NETFLIX INC", "kind": "stock", "errors": [], "gate": {"result": "pass"}, "rotation": False}]}
    (tmp_path / "site" / "data.json").write_text(json.dumps(data))
    (tmp_path / "out" / "db_snapshot.json").write_text(json.dumps({"versions": {"sp500_checks/AAPL": 4}}))
    monkeypatch.setattr(dbsync, "ROOT", tmp_path)
    monkeypatch.setattr(dbsync, "OUT", tmp_path / "out")
    writes = json.loads(dbsync.export().read_text())
    by = {(w["collection"], w["doc_id"]): w for w in writes}
    aapl = by[("sp500_checks", "AAPL")]
    assert aapl["op"] == "set" and aapl["if_version"] == 4
    assert json.loads(open(aapl["file_path"]).read())["ticker"] == "AAPL"
    assert by[("universe", "NFLX")]["op"] == "update"
    assert ("universe", "AAPL") not in by
