"""M5: ETF look-through math (site/lookthrough.js, the code the page runs)."""
import pytest

BLACK = ["FOXA", "FOX", "NMAX"]
ETF = {
    "SPY": {"holdings": {"FOXA": 0.019236, "FOX": 0.011576, "TSLA": 1.6}, "asOf": "2026-09-24"},
    "VTI": {"holdings": {"FOXA": 0.02079, "NMAX": 0.000519}, "asOf": "2026-06-30"},
    "QQQ": {"holdings": {"TSLA": 3.3}, "asOf": "2026-06-30"},
    "NEWS": {"holdings": {"FOXA": 20.0, "FOX": 15.0, "NMAX": 10.0}, "asOf": "2026-09-01"},
}


def lt(run_js, rows, black=BLACK, **kw):
    return run_js({"fn": "lookthrough", "args": {"rows": rows, "etfData": ETF, "black": black, **kw}})


def test_single_etf(run_js):
    r = lt(run_js, [{"ticker": "SPY", "weightPct": 40}])
    # 40% x (0.019236 + 0.011576)% = 0.0123248% of portfolio
    assert r["mode"] == "portfolio"
    assert r["totalPct"] == pytest.approx(0.0123248, abs=1e-9)
    assert round(r["totalPct"], 4) == 0.0123
    assert r["flagged"] is False


def test_several_etfs(run_js):
    r = lt(run_js, [{"ticker": "SPY", "weightPct": 40}, {"ticker": "VTI", "weightPct": 20},
                    {"ticker": "QQQ", "weightPct": 10}])
    expected = 40 * (0.019236 + 0.011576) / 100 + 20 * (0.02079 + 0.000519) / 100 + 0
    assert r["totalPct"] == pytest.approx(expected, abs=1e-12)
    assert round(r["totalPct"], 4) == 0.0166  # hand check: 0.0123248 + 0.0042618 = 0.0165866


def test_etf_with_several_black_names_over_threshold(run_js):
    r = lt(run_js, [{"ticker": "NEWS", "weightPct": 2}])
    assert r["perEtf"][0]["blackSharePct"] == pytest.approx(45.0)
    assert r["totalPct"] == pytest.approx(0.9)
    assert r["overThreshold"] is True and r["flagged"] is True
    assert sorted(r["perEtf"][0]["blackNames"]) == ["FOX", "FOXA", "NMAX"]


def test_zero_exposure(run_js):
    r = lt(run_js, [{"ticker": "QQQ", "weightPct": 30}])
    assert r["totalPct"] == 0 and r["flagged"] is False


def test_missing_weights_fall_back_to_per_10k(run_js):
    r = lt(run_js, [{"ticker": "SPY", "weightPct": None}, {"ticker": "VTI", "weightPct": ""}])
    assert r["mode"] == "per_amount" and r["totalPct"] is None
    spy = next(e for e in r["perEtf"] if e["ticker"] == "SPY")
    assert spy["perAmountUsd"] == pytest.approx(10000 * 0.030812 / 100)  # $3.0812 per $10,000
    assert round(spy["perAmountUsd"], 4) == 3.0812


def test_direct_black_holding_flags_even_under_threshold(run_js):
    r = lt(run_js, [{"ticker": "FOXA", "weightPct": 0.1}])
    assert r["flagged"] is True and r["direct"][0]["ticker"] == "FOXA"
    assert r["totalPct"] == pytest.approx(0.1)


def test_threshold_boundary_is_strictly_greater(run_js):
    r = lt(run_js, [{"ticker": "NEWS", "weightPct": 0.5 / 45 * 100}])
    assert r["totalPct"] == pytest.approx(0.5)
    assert r["overThreshold"] is False


def test_unknown_etf_reported_missing(run_js):
    r = lt(run_js, [{"ticker": "ABCD", "weightPct": 10}])
    assert r["missingData"] == ["ABCD"]


def test_partial_weights_list_missing(run_js):
    r = lt(run_js, [{"ticker": "SPY", "weightPct": 40}, {"ticker": "VTI", "weightPct": None}])
    assert r["mode"] == "portfolio" and r["missingWeight"] == ["VTI"]


def test_approved_black_only_changes_result(run_js):
    r = lt(run_js, [{"ticker": "SPY", "weightPct": 50}], black=["FOXA"])
    assert r["totalPct"] == pytest.approx(50 * 0.019236 / 100)
