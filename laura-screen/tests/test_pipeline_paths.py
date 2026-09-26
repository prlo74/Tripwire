"""Tests for failure paths added after QA round 2: unknown-not-zero gate inputs, fiscal-year-bound
financial notes, no stale-cache fallback, approval-driven labels, alert sentence extraction."""
import json

import pytest
import requests

from pipeline import financial, http
from pipeline.evidence import load_rules
from pipeline.run import current_labels, first_sentence

RULES = load_rules()


def facts(capex=True, debt=True, sw=False):
    def flow(v):
        return {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": v, "form": "10-K"}]}}

    def inst(v):
        return {"units": {"USD": [{"end": "2025-12-31", "val": v, "form": "10-K"}]}}
    g = {"NetIncomeLoss": flow(100), "NetCashProvidedByUsedInOperatingActivities": flow(200),
         "StockholdersEquity": inst(1000)}
    if capex:
        g["PaymentsToAcquirePropertyPlantAndEquipment"] = flow(30)
        g["PaymentsToAcquireOtherPropertyPlantAndEquipment"] = flow(20)
    if sw:
        g["PaymentsToDevelopSoftware"] = flow(10)
    if debt:
        g["LongTermDebt"] = inst(100)
    return {"facts": {"dei": {"EntityPublicFloat": {"units": {"USD": [{"end": "2025-06-30", "val": 9e9, "form": "10-K"}]}}},
                      "us-gaap": g}}


def gate(monkeypatch, notes=None, **kw):
    monkeypatch.setattr(financial, "companyfacts", lambda cik: facts(**kw))
    return financial.financial_gate(1, RULES, notes)


def test_capex_tags_are_summed(monkeypatch):
    g = gate(monkeypatch)
    assert g["checks"]["fcf"]["value"] == 200 - 30 - 20


def test_missing_capex_is_unknown_not_zero(monkeypatch):
    g = gate(monkeypatch, capex=False)
    assert g["checks"]["fcf"]["pass"] is None and g["result"] == "unknown"


def test_software_only_capex_is_unknown(monkeypatch):
    g = gate(monkeypatch, capex=False, sw=True)
    assert g["checks"]["fcf"]["pass"] is None


def test_missing_debt_is_unknown_not_zero(monkeypatch):
    g = gate(monkeypatch, debt=False)
    assert g["checks"]["debt_to_equity"]["pass"] is None and g["result"] == "unknown"


def test_debt_note_fills_gap_only_for_its_fiscal_year(monkeypatch):
    note = {"debt": {"value": 0, "quote": "no borrowings", "url": "u", "fy_end": "2025-12-31"}}
    assert gate(monkeypatch, notes=note, debt=False)["checks"]["debt_to_equity"]["value"] == 0.0
    stale = {"debt": {"value": 0, "quote": "no borrowings", "url": "u", "fy_end": "2024-12-31"}}
    assert gate(monkeypatch, notes=stale, debt=False)["checks"]["debt_to_equity"]["pass"] is None


def test_capex_extra_note_added_for_matching_year(monkeypatch):
    note = {"capex_extra": {"value": 160, "label": "prepublication", "quote": "q", "url": "u", "fy_end": "2025-12-31"}}
    g = gate(monkeypatch, notes=note)
    assert g["checks"]["fcf"]["value"] == 200 - 50 - 160 and g["checks"]["fcf"]["pass"] is False


def test_fetch_raises_instead_of_serving_stale_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(http, "CACHE", tmp_path)
    monkeypatch.setattr(http, "contact_email", lambda: "test@example.com")
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    url = "https://www.sec.gov/files/example.json"
    path = http._key(url, None)
    path.write_bytes(b'{"old": true}')
    path.with_suffix(".meta").write_text(json.dumps({"url": url, "fetched": 0}))
    import os
    os.utime(path, (0, 0))  # make the cached copy very old
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise requests.ConnectionError("down")
    monkeypatch.setattr(http._session, "get", boom)
    with pytest.raises(http.SourceError):
        http.fetch(url, ttl_hours=1)
    assert len(calls) == 2  # one retry, then reported


def test_approved_label_survives_and_most_severe_wins():
    base = {"watch": ["TSLA"]}
    appr = [{"decision": "approve", "tickers": ["TSLA"], "to": "black", "decided_at": "2026-09-27", "proposal_id": "gone"},
            {"decision": "approve", "tickers": ["TSLA"], "to": "watch", "decided_at": "2026-09-28"},
            {"decision": "reject", "tickers": ["META"], "to": "black", "decided_at": "2026-09-28"}]
    lab = current_labels(base, appr)
    assert lab["TSLA"]["label"] == "black" and lab["TSLA"]["approved"]
    assert "META" not in lab


@pytest.mark.parametrize("text,want", [
    ("A federal jury (N.D. Cal., Diaz v. Tesla) returned a verdict. More.", "A federal jury (N.D. Cal., Diaz v. Tesla) returned a verdict."),
    ("DOJ sued Meta (S.D.N.Y., June 21, 2022) alleging bias. Settled.", "DOJ sued Meta (S.D.N.Y., June 21, 2022) alleging bias."),
    ("One sentence only", "One sentence only"),
])
def test_first_sentence(text, want):
    assert first_sentence(text) == want
