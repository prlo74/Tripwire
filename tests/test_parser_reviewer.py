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


# ---------------- Round 2: tests against the rewritten parser ----------------

# R2-1. SEC-style company names contain a comma ("Tesla, Inc."). The comma must not split off
#       "Inc." as a separate not-found chip.
def test_r2_sec_style_name_with_comma(run_js):
    res = run_js({"fn": "parse", "text": "Tesla, Inc."})
    assert len(items(res)) == 1, items(res)
    assert items(res)[0]["suggestions"][0]["ticker"] == "TSLA"


# R2-2. Space-separated company names are separate companies, not one unknown phrase.
def test_r2_space_separated_company_names(run_js):
    res = run_js({"fn": "parse", "text": "Apple Microsoft Tesla"})
    got = {s["ticker"] for i in items(res) for s in i.get("suggestions", [])[:1]} | \
          {i.get("ticker") for i in items(res) if i.get("ticker")}
    assert {"AAPL", "MSFT", "TSLA"} <= got, items(res)


# R2-3. "Class A/B/C" in a name should rank that class first; non-common classes (GOOGM notes)
#       should not be offered.
def test_r2_class_word_ranks_that_class(run_js):
    a = items(run_js({"fn": "parse", "text": "Alphabet Class A"}))[0]
    b = items(run_js({"fn": "parse", "text": "Berkshire Hathaway Class B"}))[0]
    assert a["suggestions"][0]["ticker"] == "GOOGL", a
    assert "GOOGM" not in [s["ticker"] for s in a["suggestions"]], a
    assert b["suggestions"][0]["ticker"] == "BRK-B", b


# R2-4. A name pasted next to one of that company's class tickers is the same company.
def test_r2_name_plus_class_ticker_merge(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "GOOGL Alphabet Inc.", "map": mini_map})
    assert len(items(res)) == 1, items(res)


# R2-5. Slash-separated ticker lists.
def test_r2_slash_separated_list(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "AAPL/MSFT/TSLA", "map": mini_map})
    assert [i.get("ticker") for i in items(res)] == ["AAPL", "MSFT", "TSLA"], items(res)


# R2-6. Accented letters in a company name (NFKC keeps é) must still match "ESTEE LAUDER".
def test_r2_accented_company_name(run_js):
    res = run_js({"fn": "parse", "text": "Estée Lauder"})
    assert len(items(res)) == 1 and items(res)[0]["suggestions"][0]["ticker"] == "EL", items(res)


# R2-7. In an obvious sentence, everyday words that happen to be tickers (love=LOVE,
#       car=CAR) must not be silently accepted.
def test_r2_prose_words_not_silently_tickers(run_js):
    res = run_js({"fn": "parse", "text": "I really love my new car"})
    silent = [i["input"] for i in items(res) if i["status"] in ("stock", "etf")]
    assert not silent, items(res)


# R2-8. Ideographic comma (Chinese/Japanese input) is a separator.
def test_r2_ideographic_comma(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "AAPL、MSFT", "map": mini_map})
    assert [i.get("ticker") for i in items(res)] == ["AAPL", "MSFT"], items(res)


# R2-9. ETF by its fund name.
def test_r2_etf_by_name(run_js):
    res = run_js({"fn": "parse", "text": "Vanguard S&P 500 ETF"})
    assert len(items(res)) == 1, items(res)
    assert "VOO" in [s["ticker"] for s in items(res)[0].get("suggestions", [])], items(res)


# R2-10. The same company name typed twice in different forms is one item.
def test_r2_duplicate_name_forms(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Apple Inc.\nApple\nAPPLE INC", "map": mini_map})
    assert len(items(res)) == 1, items(res)


# R2-11. "AT&T" is a well-known company written with "&"; it should reach T.
def test_r2_ampersand_company(run_js):
    res = run_js({"fn": "parse", "text": "AT&T"})
    it = items(res)[0]
    got = [it.get("ticker")] + [s["ticker"] for s in it.get("suggestions", [])]
    assert "T" in got, it


# R2-12. Regression guard: things round 1 fixed must stay fixed together in one paste.
def test_r2_combined_regressions(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "Tsla, AAPL. NASDAQ:MSFT ＳＨＯＰ spy", "map": mini_map})
    assert [i.get("ticker") for i in items(res)] == ["TSLA", "AAPL", "MSFT", "SHOP", "SPY"], items(res)
    assert res["attention"] == 0


# ---------------- Round 3: greedy name matching and prose detection ----------------

# R3-1. One lowercase typo must not turn every lowercase ticker in the same line into an
#       "ordinary word" that is dropped on save unless clicked.
def test_r3_lowercase_list_with_typo_keeps_tickers(run_js, mini_map):
    res = run_js({"fn": "parse", "text": "aapl msft tsla xyzq", "map": mini_map})
    st = [(i["status"], i.get("ticker")) for i in items(res)]
    assert st[:3] == [("stock", "AAPL"), ("stock", "MSFT"), ("stock", "TSLA")], items(res)
    assert items(res)[3]["status"] == "notfound"


# R3-2. Spec fixture with the typo in lowercase: FOX/FOXA must still get the share-class prompt,
#       and spy/VOO must still be ETFs.
def test_r3_spec_fixture_lowercase_typo(run_js):
    text = "aapl, MSFT; brk.b $TSLA  Apple Inc.\nspy VOO\txyzq 123 fox foxa  Newsmax  SHOP"
    res = run_js({"fn": "parse", "text": text})
    fox = [i for i in items(res) if i.get("kind") == "classes"]
    assert len(fox) == 1 and sorted(fox[0]["classes"]) == ["FOX", "FOXA"], items(res)
    assert not [i for i in items(res) if i.get("kind") == "word"], items(res)


# R3-3. "Fox News" is Fox Corp's network; it must not suggest News Corp (NWS/NWSA), which is
#       a different company on the do-not-list.
def test_r3_fox_news_does_not_suggest_news_corp(run_js):
    res = run_js({"fn": "parse", "text": "Fox News"})
    sugg = {s["ticker"] for i in items(res) for s in i.get("suggestions", [])}
    assert not ({"NWS", "NWSA"} & sugg), items(res)


# R3-4. A two-word company name whose SEC name has extra words ("WELLS FARGO & COMPANY/MN")
#       is one item, not "Wells" + a not-found "Fargo".
def test_r3_wells_fargo_one_item(run_js):
    res = run_js({"fn": "parse", "text": "Wells Fargo"})
    assert len(items(res)) == 1 and items(res)[0]["suggestions"][0]["ticker"] == "WFC", items(res)


# R3-5. Regression: "The New York Times" worked in round 2; it must not produce a stray "The" chip.
def test_r3_the_new_york_times(run_js):
    res = run_js({"fn": "parse", "text": "The New York Times"})
    assert len(items(res)) == 1 and items(res)[0]["suggestions"][0]["ticker"] == "NYT", items(res)


# R3-6. Title-case heading words that happen to be tickers must not be silently accepted.
def test_r3_heading_word_not_silent_ticker(run_js):
    res = run_js({"fn": "parse", "text": "Top Picks"})
    silent = [i["input"] for i in items(res) if i["status"] in ("stock", "etf")]
    assert not silent, items(res)


# R3-7. List headings pasted from the page itself ("Black List", "Watch List") must not
#       suggest unrelated companies (Black Hills, etc.).
def test_r3_list_headings_no_company_suggestions(run_js):
    for text in ("Black List", "Watch List"):
        res = run_js({"fn": "parse", "text": text})
        sugg = [s["ticker"] for i in items(res) for s in i.get("suggestions", [])]
        assert not sugg and not [i for i in items(res) if i["status"] in ("stock", "etf")], (text, items(res))


# R3-8. Fund names for the page's own default ETFs.
def test_r3_default_etf_names(run_js):
    for text, want in (("Vanguard Total Stock Market ETF", "VTI"), ("SPDR S&P 500 ETF Trust", "SPY")):
        res = run_js({"fn": "parse", "text": text})
        assert len(items(res)) == 1, (text, items(res))
        assert want in [s["ticker"] for s in items(res)[0].get("suggestions", [])], (text, items(res))


# ---------------- Round 4: realistic team pastes ----------------

# R4-1 (realistic). A typed, space-separated uppercase ticker list with one-letter tickers
#       (F = Ford, a current Watch proposal; T = AT&T). Comma/tab lists already work.
def test_r4_space_list_with_single_letter_tickers(run_js):
    res = run_js({"fn": "parse", "text": "AAPL MSFT F GM T"})
    assert [(i["status"], i.get("ticker")) for i in items(res)] == [
        ("stock", "AAPL"), ("stock", "MSFT"), ("stock", "F"), ("stock", "GM"), ("stock", "T")], items(res)


# R4-2 (realistic). Broker CSV export: tickers found, and header words must not suggest
#       companies ("Price" -> T. Rowe Price).
def test_r4_broker_export_headers(run_js):
    text = ("Symbol,Description,Quantity,Price\nAAPL,APPLE INC,10,227.50\n"
            "VOO,VANGUARD S&P 500 ETF,5,510.12\nBRK/B,BERKSHIRE HATHAWAY INC CL B,2,480.00")
    res = run_js({"fn": "parse", "text": text})
    got = {i.get("ticker") for i in items(res) if i["status"] in ("stock", "etf")}
    assert {"AAPL", "VOO", "BRK-B"} <= got, items(res)
    sugg = {s["ticker"] for i in items(res) for s in i.get("suggestions", [])}
    assert "TROW" not in sugg, items(res)


# R4-3 (realistic, design judgment). In a multi-column broker export, prices and quantities
#       are not tickers and should not each need a "Skip" click.
def test_r4_broker_export_numbers_not_attention(run_js):
    text = "AAPL,APPLE INC,10,227.50\nVOO,VANGUARD S&P 500 ETF,5,510.12"
    res = run_js({"fn": "parse", "text": text})
    nums = [i["input"] for i in items(res) if __import__("re").fullmatch(r"[\d.,]+", i["input"])]
    assert not nums, items(res)


# R4-4 (realistic). Apostrophes in everyday company names.
def test_r4_apostrophe_names(run_js):
    res = run_js({"fn": "parse", "text": "Lowe's, McDonald's"})
    top = [i["suggestions"][0]["ticker"] if i.get("suggestions") else None for i in items(res)]
    assert top == ["LOW", "MCD"], items(res)


# R4-5 (realistic). "Exxon Mobil" (SEC now lists "ExxonMobil Holdings Corp").
def test_r4_exxon_mobil(run_js):
    res = run_js({"fn": "parse", "text": "Exxon Mobil"})
    assert len(items(res)) == 1 and items(res)[0]["suggestions"][0]["ticker"] == "XOM", items(res)


# R4-6 (realistic). "Name (TICKER)" with a short name: the name is an alias, not a
#       separate not-found chip.
def test_r4_short_name_with_ticker_in_parens(run_js):
    res = run_js({"fn": "parse", "text": "Berkshire (BRK.B), Alphabet (GOOGL)"})
    assert not [i for i in items(res) if i["status"] == "notfound"], items(res)
    assert len(items(res)) == 2, items(res)


# R4-7 (guard). Newline company-name lists the team actually uses resolve with the right
#       first suggestion.
def test_r4_company_name_list_guard(run_js):
    text = "Apple\nMicrosoft\nNvidia\nMeta Platforms\nTesla\nJPMorgan Chase\nAdobe\nThomson Reuters\nNew York Times\nShopify\nWells Fargo\nThe Walt Disney Company"
    res = run_js({"fn": "parse", "text": text})
    top = [i.get("ticker") or i["suggestions"][0]["ticker"] for i in items(res)]
    assert top == ["AAPL", "MSFT", "NVDA", "META", "TSLA", "JPM", "ADBE", "TRI", "NYT", "SHOP", "WFC", "DIS"], items(res)


# R4-8 (guard). Spec fixture exactly as written in the build prompt, live map: exactly the
#       expected items and nothing else.
def test_r4_spec_fixture_exact_live(run_js):
    text = "aapl, MSFT; brk.b $TSLA  Apple Inc.\nspy VOO\tXYZQ 123 fox foxa  Newsmax  SHOP"
    res = run_js({"fn": "parse", "text": text})
    summary = [(i["status"], i["input"] if i["status"] == "notfound" else
                i.get("ticker") or (i.get("suggestions") or [{}])[0].get("ticker") or
                "+".join(sorted(i.get("classes", [])))) for i in items(res)]
    assert summary == [("stock", "AAPL"), ("stock", "MSFT"), ("stock", "BRK-B"), ("stock", "TSLA"),
                       ("etf", "SPY"), ("etf", "VOO"), ("notfound", "XYZQ"), ("notfound", "123"),
                       ("ambiguous", "FOX+FOXA"), ("name", "NMAX"), ("stock", "SHOP")], summary
    aapl = items(res)[0]
    assert "Apple Inc." in aapl.get("aliases", []), aapl
    assert res["attention"] == 4
