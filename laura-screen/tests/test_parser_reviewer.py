"""Adversarial reviewer tests for site/parser.js (QA round 1).

Each test states the behaviour a teammate would reasonably expect from the paste box.
Failures here are parser defects, not test bugs. Tests without "map" use the live
site/tickers.json (so real one-letter tickers like A, B, F and ETFs like OWN are present).
"""


def items(res):
    return res["items"]


def statuses(res):
    return [(i["status"], i.get("ticker")) for i in res["items"]]


# 1. Mixed-case ticker typed like a word ("Tsla") should still resolve to TSLA
#    (or at least suggest it), not "No US-listed company matches this name".
def test_mixed_case_ticker_resolves(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Tsla", "map": mini_map})
    it = items(res)[0]
    got = [it.get("ticker")] + [s["ticker"] for s in it.get("suggestions", [])]
    assert "TSLA" in got, it


# 2. Two mixed-case tickers must stay two items, not merge into one "company name" phrase.
def test_mixed_case_tickers_not_merged(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Aapl Msft", "map": mini_map})
    assert len(items(res)) == 2, items(res)


# 3. Sentence punctuation after a ticker ("AAPL.") must not break recognition.
def test_trailing_period_after_ticker(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "AAPL. MSFT.", "map": mini_map})
    assert statuses(res) == [("stock", "AAPL"), ("stock", "MSFT")], items(res)


# 4. A comma between company names is a separator: "Apple, Microsoft" is two names.
def test_comma_separates_company_names(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Apple, Tesla", "map": mini_map})
    ins = [i["input"] for i in items(res)]
    assert len(ins) == 2, ins
    assert items(res)[0]["suggestions"][0]["ticker"] == "AAPL"
    assert items(res)[1]["suggestions"][0]["ticker"] == "TSLA"


# 5. Full-width (IME) characters must never be silently dropped. Either normalise
#    (NFKC) to AAPL or show a flagged chip; returning nothing loses the user's input.
def test_fullwidth_input_not_silently_dropped(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "ＡＡＰＬ", "map": mini_map})
    assert len(items(res)) == 1, res
    assert items(res)[0].get("ticker") == "AAPL" or res["attention"] == 1


# 6. Zero-width space / em dash between tickers (common in copy-paste from web pages)
#    should act as separators.
def test_invisible_and_dash_separators(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "AAPL​MSFT—TSLA", "map": mini_map})
    assert [i.get("ticker") for i in items(res)] == ["AAPL", "MSFT", "TSLA"], items(res)


# 7. Exchange-prefixed / Bloomberg-suffixed forms are common pastes.
def test_exchange_prefix_and_suffix(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "NASDAQ:AAPL AAPL:US MSFT US Equity", "map": mini_map})
    tick = {i.get("ticker") for i in items(res) if i["status"] == "stock"}
    assert {"AAPL", "MSFT"} <= tick, items(res)


# 8. "Alphabet Class A": the stray "A" must not silently become Agilent (A) with no flag.
def test_class_letter_not_silently_recognized(run_js):
    res = run_js({"fn": "parse", "text": "Alphabet Class A"})
    silent = [i for i in items(res) if i["status"] == "stock" and i["ticker"] == "A"]
    assert not silent, items(res)


# 9. "BRK B" (space instead of dot) should resolve to BRK-B, not to ticker B plus a not-found BRK.
def test_space_separated_class(run_js):
    res = run_js({"fn": "parse", "text": "BRK B"})
    assert [i.get("ticker") for i in items(res)] == ["BRK-B"], items(res)


# 10. Prose words must not be silently accepted as tickers ("own" is the OWN ETF).
def test_prose_word_not_silently_an_etf(run_js):
    res = run_js({"fn": "parse", "text": "I own AAPL"})
    silent = [i for i in items(res) if i["status"] in ("stock", "etf") and i["input"] == "own"]
    assert not silent, items(res)


# 11. Duplicates across forms: name + ticker of the same company should collapse to one item.
def test_name_and_ticker_same_company_dedup(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Apple Inc. AAPL aapl $AAPL", "map": mini_map})
    assert len(items(res)) == 1 and res["attention"] == 0, items(res)


# 12. Uppercase company name with suffix ("APPLE INC") should give one name item, not
#     an extra not-found chip for "INC".
def test_uppercase_name_with_suffix(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "APPLE INC", "map": mini_map})
    assert len(items(res)) == 1 and items(res)[0]["suggestions"][0]["ticker"] == "AAPL", items(res)


# 13. ETF vs stock: an ETF typed in any case/form is an ETF, never ambiguous; repeat is deduped.
def test_etf_forms(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "spy SPY $spy (QQQ) qqq", "map": mini_map})
    assert statuses(res) == [("etf", "SPY"), ("etf", "QQQ")] and res["attention"] == 0


# 14. Explicit class (BRK.B) stays a stock; bare GOOG + GOOGL collapse into one class prompt.
def test_class_dot_then_bare(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "BRK.B goog GOOGL", "map": mini_map})
    by = {i["input"]: i for i in items(res)}
    assert by["BRK.B"]["status"] == "stock" and by["BRK.B"]["ticker"] == "BRK-B"
    g = [i for i in items(res) if i["status"] == "ambiguous"]
    assert len(g) == 1 and sorted(g[0]["classes"]) == ["GOOG", "GOOGL"]


# 15. Spec fixture with the live map: FOX/FOXA prompt lists exactly the two Fox classes.
def test_spec_fox_live_map(run_js):
    res = run_js({"fn": "parse", "text": "fox foxa"})
    it = items(res)[0]
    assert it["status"] == "ambiguous" and sorted(it["classes"]) == ["FOX", "FOXA"]


# 16. Resolve on a name item with no choice saves nothing (human must pick).
def test_resolve_name_without_choice(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Newsmax", "map": mini_map})
    assert run_js({"fn": "resolve", "item": items(res)[0]}) == []
