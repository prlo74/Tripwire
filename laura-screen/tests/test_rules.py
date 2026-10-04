"""M2/M3: rule fidelity. Uses check_record without network (open_sources=False)."""
from datetime import date

import pytest

from pipeline.evidence import check_record, guard_do_not_list, load_rules, tier_of, quote_in_doc
from pipeline import financial

RULES = load_rules()
TODAY = date(2026, 9, 26)


def rec(**kw):
    base = {"id": "x", "tickers": ["ABC"], "company": "ABC Corp", "kind": "finding", "clause": "b",
            "finding_type": "jury_verdict", "event_date": "2024-01-01", "tripwire": "t",
            "sources": [{"url": "https://www.sec.gov/Archives/x.htm", "quote": "q"}]}
    base.update(kw)
    return base


def check_record_with_verified(r):
    import pipeline.evidence as ev
    orig = ev.doc_text
    ev.doc_text = lambda url: " ".join(s["quote"] for s in r["sources"])
    try:
        return check_record(r, RULES, TODAY, open_sources=True)
    finally:
        ev.doc_text = orig


def test_recent_jury_verdict_is_black():
    c = check_record_with_verified(rec())
    assert c["check"]["outcome"] == "black" and c["check"]["proposable"]
    assert "Black (b)" in c["check"]["clause_text"]


def test_finding_older_than_7_years_is_watch_not_black():
    c = check_record_with_verified(rec(event_date="2019-01-01"))
    assert c["check"]["outcome"] == "watch"
    assert "older" in c["check"]["clause_text"].lower()


def test_settlement_without_admission_never_black():
    c = check_record_with_verified(rec(kind="settlement_no_admission", event_date="2026-01-01"))
    assert c["check"]["outcome"] == "watch"


def test_tier2_only_is_a_lead_not_a_proposal():
    r = rec(sources=[{"url": "https://www.reuters.com/x", "quote": "q"}])
    c = check_record_with_verified(r)
    assert c["check"]["outcome"] == "lead" and not c["check"]["proposable"]


def test_banned_source_rejected():
    r = rec(sources=[{"url": "https://someone.substack.com/p/x", "quote": "q"},
                     {"url": "https://www.sec.gov/x", "quote": "q"}])
    c = check_record_with_verified(r)
    assert not c["check"]["proposable"]
    assert any("banned" in p for p in c["check"]["problems"])


def test_quote_over_50_words_rejected():
    long_q = " ".join(["word"] * 51)
    c = check_record_with_verified(rec(sources=[{"url": "https://www.sec.gov/x", "quote": long_q}]))
    assert not c["check"]["proposable"]


def test_quote_not_in_source_rejected():
    import pipeline.evidence as ev
    orig = ev.doc_text
    ev.doc_text = lambda url: "something else entirely"
    try:
        c = check_record(rec(), RULES, TODAY, open_sources=True)
    finally:
        ev.doc_text = orig
    assert not c["check"]["proposable"]
    assert c["check"]["outcome"] == "lead"


def test_non_qualifying_finding_type_flagged():
    c = check_record_with_verified(rec(finding_type="press_statement"))
    assert not c["check"]["proposable"]


def test_watch_needs_tripwire():
    c = check_record_with_verified(rec(kind="open_case", tripwire=None))
    assert not c["check"]["proposable"]


def test_do_not_list_needs_a_finding():
    r = check_record_with_verified(rec(tickers=["DJT"], kind="open_case"))
    out = guard_do_not_list([r], RULES)
    assert not out[0]["check"]["proposable"]
    r2 = check_record_with_verified(rec(tickers=["NWSA"], kind="settlement_no_admission"))
    assert not guard_do_not_list([r2], RULES)[0]["check"]["proposable"]


def test_values_link_must_cite_sec_filing():
    r = rec(kind="values_link", themes=["storytelling_education"],
            sources=[{"url": "https://www.courtlistener.com/x", "quote": "q"}])
    c = check_record_with_verified(r)
    assert not c["check"]["proposable"]


def test_tiers():
    assert tier_of("https://www.sec.gov/Archives/x", RULES) == 1
    assert tier_of("https://courts.delaware.gov/Opinions/x", RULES) == 1
    assert tier_of("https://apnews.com/x", RULES) == 2
    assert tier_of("https://www.reddit.com/r/x", RULES) == 0
    assert tier_of("https://randomblog.example.com", RULES) is None


def test_quote_matching_ignores_typography():
    assert quote_in_doc("Today's step - forward", "Today’s  step — forward.")
    assert quote_in_doc("alpha ... gamma", "alpha beta gamma")
    assert not quote_in_doc("alpha delta", "alpha beta gamma")


# ---- financial gate with synthetic XBRL facts ----
def facts(ni=100, ocf=200, capex=50, equity=1000, debt=500, fl=6e9, eq_neg=False):
    def flow(v):
        return {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": v, "form": "10-K", "fp": "FY"}]}}

    def inst(v):
        return {"units": {"USD": [{"end": "2025-12-31", "val": v, "form": "10-K", "fp": "FY"}]}}
    return {"facts": {"dei": {"EntityPublicFloat": {"units": {"USD": [{"end": "2025-06-30", "val": fl, "form": "10-K"}]}}},
                      "us-gaap": {"NetIncomeLoss": flow(ni), "NetCashProvidedByUsedInOperatingActivities": flow(ocf),
                                  "PaymentsToAcquirePropertyPlantAndEquipment": flow(capex),
                                  "StockholdersEquity": inst(-equity if eq_neg else equity),
                                  "LongTermDebt": inst(debt)}}}


@pytest.mark.parametrize("kw,result,failed", [
    ({}, "pass", []),
    ({"fl": 4e9}, "fail", ["market_cap"]),
    ({"ni": -1}, "fail", ["net_income"]),
    ({"capex": 300}, "fail", ["fcf"]),
    ({"debt": 1600}, "fail", ["debt_to_equity"]),
    ({"eq_neg": True}, "unknown", []),
])
def test_financial_gate(monkeypatch, kw, result, failed):
    monkeypatch.setattr(financial, "companyfacts", lambda cik: facts(**kw))
    g = financial.financial_gate(1, RULES)
    assert g["result"] == result
    assert g["failed"] == failed
    if kw.get("eq_neg"):
        assert "Not meaningful" in g["checks"]["debt_to_equity"]["note"]


# ---- Rule change 2026-10-04: widened clause (b) and new clause (c) ----

def test_clause_b_text_covers_orientation_and_gender_identity():
    t = RULES["black"]["clauses"]["b"]
    assert "sexual orientation" in t and "gender identity" in t and "race" in t


def test_sexual_orientation_finding_is_black_under_b_with_clause_cited():
    c = check_record_with_verified(rec(finding_type="agency_finding", clause="b"))
    assert c["check"]["outcome"] == "black"
    assert "Black (b)" in c["check"]["clause_text"] and "sexual orientation" in c["check"]["clause_text"]


def test_widened_b_keeps_7_year_lookback_and_settlement_rules():
    assert check_record_with_verified(rec(event_date="2018-01-01"))["check"]["outcome"] == "watch"
    assert check_record_with_verified(rec(kind="settlement_no_admission", event_date="2026-01-01"))["check"]["outcome"] == "watch"


def bl(**kw):
    base = {"id": "geo-c", "tickers": ["GEO"], "company": "The GEO Group", "kind": "business_line", "clause": "c",
            "fiscal_year": 2025, "filing_date": "2026-02-20", "share_pct": 10, "tripwire": "",
            "sources": [{"url": "https://www.sec.gov/Archives/x.htm", "quote": "q"}]}
    base.update(kw)
    return base


def test_clause_c_threshold_is_in_rules_and_editable():
    assert RULES["black_business_line"]["threshold_pct"] == 10
    assert "10%" in RULES["black"]["clauses"]["c"].format(threshold_pct=10)


@pytest.mark.parametrize("share,outcome", [(10, "black"), (10.0, "black"), (45, "black"), (9.9, "below_threshold")])
def test_clause_c_at_and_around_threshold(share, outcome):
    c = check_record_with_verified(bl(share_pct=share))
    assert c["check"]["outcome"] == outcome
    assert c["check"]["proposable"] == (outcome == "black")
    if outcome == "black":
        t = c["check"]["clause_text"]
        assert t.startswith("Black (c)") and "10%" in t and "2025" in t


def test_clause_c_undisclosed_is_watch_with_tripwire_never_estimated():
    c = check_record_with_verified(bl(share_pct="unknown"))
    assert c["check"]["outcome"] == "watch" and c["check"]["proposable"]
    assert c["tripwire"] == RULES["black_business_line"]["unknown_tripwire"]
    assert "Watch (c)" in c["check"]["clause_text"]


def test_clause_c_needs_company_10k_quote_and_dates():
    c = check_record_with_verified(bl(fiscal_year=None, sources=[{"url": "https://www.reuters.com/x", "quote": "q"}]))
    assert not c["check"]["proposable"]


def test_clause_c_never_black_from_tier2():
    c = check_record_with_verified(bl(sources=[{"url": "https://www.reuters.com/x", "quote": "q"}]))
    assert c["check"]["outcome"] == "lead" and not c["check"]["proposable"]


def test_not_added_list_recorded():
    txt = " ".join(str(e) for e in RULES["do_not_list_without_finding"]).lower()
    for k in ("firearms", "social-media", "taiwan", "esg"):
        assert k in txt


def test_screen_added_tickers():
    assert set(RULES["black_business_line"]["screen_added_tickers"]) == {"GEO", "CXW"}


def test_discovery_matches_orientation_terms():
    from pipeline.discovery import RACE_OR_FALSITY
    assert RACE_OR_FALSITY.search("EEOC sues over sexual orientation discrimination")
    assert RACE_OR_FALSITY.search("transgender employee harassment settlement")
