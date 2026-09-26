"""M4: paste-box parser. Runs the page's own JS (site/parser.js) through Node."""
import pytest

SPEC_FIXTURE = "aapl, MSFT; brk.b $TSLA  Apple Inc.\nspy VOO\tXYZQ 123 fox foxa  Newsmax  SHOP"


def by_input(res):
    return {i["input"]: i for i in res["items"]}


@pytest.mark.parametrize("use_live_map", [False, True])
def test_spec_fixture(run_js, mini_map, use_live_map):
    payload = {"fn": "parse", "text": SPEC_FIXTURE}
    if not use_live_map:
        payload["map"] = mini_map
    res = run_js(payload)
    items = by_input(res)
    assert items["aapl"]["status"] == "stock" and items["aapl"]["ticker"] == "AAPL"
    assert items["MSFT"]["status"] == "stock"
    assert items["brk.b"]["status"] == "stock" and items["brk.b"]["ticker"] == "BRK-B"
    assert items["TSLA"]["ticker"] == "TSLA" and items["TSLA"]["status"] == "stock"
    assert items["spy"]["status"] == "etf" and items["spy"]["ticker"] == "SPY"
    assert items["VOO"]["status"] == "etf"
    assert items["Apple Inc."]["status"] == "name"
    assert items["Apple Inc."]["suggestions"][0]["ticker"] == "AAPL"
    assert items["XYZQ"]["status"] == "notfound"
    assert items["123"]["status"] == "notfound"
    fox = items["fox foxa"]
    assert fox["status"] == "ambiguous" and fox["kind"] == "classes"
    assert sorted(fox["classes"]) == ["FOX", "FOXA"]
    assert "share classes" in fox["note"]
    assert items["Newsmax"]["status"] == "name"
    assert items["Newsmax"]["suggestions"][0]["ticker"] == "NMAX"
    assert items["SHOP"]["status"] == "stock"
    # attention: Apple Inc., XYZQ, 123, fox/foxa, Newsmax
    assert res["attention"] == 5


def test_class_suffix_forms_canonicalize(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "BRK.B BRK/B BRK-B brk.b", "map": mini_map})
    stocks = [i for i in res["items"] if i["status"] == "stock"]
    assert [i["ticker"] for i in stocks] == ["BRK-B"]
    assert len(res["items"]) == 1


def test_duplicates_removed(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "aapl AAPL $aapl, AAPL;", "map": mini_map})
    assert len(res["items"]) == 1


def test_all_separators(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "AAPL,MSFT;TSLA\tSPY\nVOO$SHOP", "map": mini_map})
    assert [i.get("ticker") for i in res["items"]] == ["AAPL", "MSFT", "TSLA", "SPY", "VOO", "SHOP"]


def test_empty_input(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "  \n\t ,;$ ", "map": mini_map})
    assert res == {"items": [], "attention": 0}


def test_typo_suggests_close_ticker(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "AAPLL", "map": mini_map})
    it = res["items"][0]
    assert it["status"] == "notfound"
    assert "AAPL" in [s["ticker"] for s in it["suggestions"]]


def test_single_bare_class_prompts_for_all(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "googl", "map": mini_map})
    it = res["items"][0]
    assert it["status"] == "ambiguous"
    # Notes (GOOGM) are not a common share class and are not offered.
    assert it["classes"] == ["GOOG", "GOOGL"]


def test_resolve_all_classes(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "fox", "map": mini_map})
    item = res["items"][0]
    assert run_js({"fn": "resolve", "item": item, "choice": "all"}) == ["FOX", "FOXA"]
    assert run_js({"fn": "resolve", "item": item}) == ["FOX"]


def test_company_name_multiword(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Thomson Reuters", "map": mini_map})
    it = res["items"][0]
    assert it["status"] == "name" and it["suggestions"][0]["ticker"] == "TRI"


def test_unknown_name_not_found(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Zzyzx Widgets", "map": mini_map})
    assert res["items"][0]["status"] == "notfound"


def test_non_ticker_symbols_rejected(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "A@PL", "map": mini_map})
    assert res["items"][0]["status"] == "notfound"


def test_name_suggestion_resolves_only_on_accept(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Newsmax", "map": {**mini_map}})
    item = res["items"][0]
    assert run_js({"fn": "resolve", "item": item}) == []
    assert run_js({"fn": "resolve", "item": item, "choice": "NMAX"}) == ["NMAX"]


def test_order_preserved(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "VOO aapl SPY", "map": mini_map})
    assert [i["ticker"] for i in res["items"]] == ["VOO", "AAPL", "SPY"]


def test_numbers_and_ticker_mixed(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "123 4.5 aapl", "map": mini_map})
    st = [i["status"] for i in res["items"]]
    assert st == ["notfound", "notfound", "stock"]
