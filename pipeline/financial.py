"""Financial gate from SEC XBRL companyfacts (official, free).

Market cap: XBRL has no share price, so we use dei:EntityPublicFloat (the market value of
shares held by non-affiliates, reported on the 10-K cover) as a conservative FLOOR for market
cap. If float >= threshold, market cap is certainly >= threshold as of that date. If float is
below threshold or missing, the result is "fail" / "unknown" and the page says why.
"""
from __future__ import annotations

from datetime import date

from .http import fetch_json, SourceError

ANNUAL_FORMS = {"10-K", "10-K/A", "40-F", "40-F/A", "20-F", "20-F/A"}

TAGS = {
    "net_income": [("us-gaap", "NetIncomeLoss"), ("us-gaap", "ProfitLoss"),
                   ("ifrs-full", "ProfitLossAttributableToOwnersOfParent"), ("ifrs-full", "ProfitLoss")],
    "ocf": [("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
            ("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
            ("ifrs-full", "CashFlowsFromUsedInOperatingActivities")],
    # PP&E capex tags that are summed (they are disjoint line items):
    "capex": [("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
              ("us-gaap", "PaymentsToAcquireOtherPropertyPlantAndEquipment"),
              ("ifrs-full", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")],
    "capex_software": [("us-gaap", "PaymentsToDevelopSoftware"), ("us-gaap", "PaymentsForSoftware"),
                       ("ifrs-full", "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities")],
    "equity": [("us-gaap", "StockholdersEquity"),
               ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
               ("ifrs-full", "EquityAttributableToOwnersOfParent"), ("ifrs-full", "Equity")],
}
# Debt components; LongTermDebt (total incl. current) preferred over its pieces.
DEBT_TOTAL = [("us-gaap", "LongTermDebt"), ("us-gaap", "DebtLongtermAndShorttermCombinedAmount"),
              ("ifrs-full", "Borrowings")]
DEBT_PIECES = [("us-gaap", "LongTermDebtNoncurrent"), ("us-gaap", "LongTermDebtCurrent")]
DEBT_EXTRA = [("us-gaap", "ShortTermBorrowings"), ("us-gaap", "CommercialPaper")]


def companyfacts(cik: int) -> dict:
    return fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", ttl_hours=24 * 7)


def _units(facts, tax, tag):
    node = facts.get(tax, {}).get(tag)
    if not node:
        return []
    return node["units"].get("USD", [])


def _days(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _annual_flows(facts, tax, tag):
    """12-month values reported in annual filings, keyed by period end."""
    out = {}
    for x in _units(facts, tax, tag):
        if x.get("form") in ANNUAL_FORMS and "start" in x and 350 <= _days(x["start"], x["end"]) <= 380:
            out[x["end"]] = x  # later filings overwrite earlier (restatements)
    return out


def _instant(facts, tax, tag, end):
    vals = [x for x in _units(facts, tax, tag) if x["end"] == end and "start" not in x
            and x.get("form") in ANNUAL_FORMS]
    return vals[-1]["val"] if vals else None


def _market_cap_fallback(cf: dict, threshold: float) -> dict:
    """No public float (typical for 40-F/20-F filers): SEC shares outstanding x price implied by a
    Vanguard fund's N-PORT filing. Both numbers are SEC data; both dates are shown."""
    from .etf import nport_price
    so = cf["facts"].get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    if not so:
        return {"value": None, "pass": None, "note": "Unknown: no public float or shares outstanding in XBRL."}
    last_end = max(x["end"] for x in so)
    shares = sum(x["val"] for x in so if x["end"] == last_end and x.get("form") in ANNUAL_FORMS | {"10-Q", "6-K"}) \
        or max(x["val"] for x in so if x["end"] == last_end)
    px = nport_price(cf.get("entityName", ""))
    if not px:
        return {"value": None, "pass": None,
                "note": "Unknown: no public float in XBRL, and no N-PORT price found for this issuer."}
    mc = shares * px["price"]
    return {"value": round(mc), "pass": mc >= threshold, "as_of": px["as_of"],
            "tag": f"dei:EntityCommonStockSharesOutstanding ({last_end}) x N-PORT price ({px['fund']}, {px['as_of']})",
            "note": f"Estimate: {shares:,.0f} shares x ${px['price']:.2f} implied by {px['fund']}'s N-PORT filing.",
            "source_extra": px["source"]}


def latest_fy_end(facts) -> str | None:
    ends = set()
    for tax, tag in TAGS["net_income"] + TAGS["ocf"]:
        ends |= set(_annual_flows(facts, tax, tag))
    return max(ends) if ends else None


def _flow_sum(facts, key, end):
    """Sum every tag in TAGS[key] reported for this fiscal year."""
    total, tags = None, []
    for tax, tag in TAGS[key]:
        v = _annual_flows(facts, tax, tag).get(end)
        if v is not None:
            total = (total or 0) + v["val"]
            tags.append(f"{tax}:{tag}")
    return total, ", ".join(tags) if tags else None


def _flow(facts, key, end):
    for tax, tag in TAGS[key]:
        v = _annual_flows(facts, tax, tag).get(end)
        if v is not None:
            return v["val"], f"{tax}:{tag}"
    return None, None


def financial_gate(cik: int, rules: dict, notes: dict | None = None) -> dict:
    """notes: verified statements from the company's own filing that fill an XBRL gap,
    e.g. {"debt": {"value": 0, "url": ..., "quote": ...}}."""
    notes = notes or {}
    g = rules["aligned"]["financial_gate"]
    res = {"cik": cik, "checks": {}, "result": "unknown", "fy_end": None, "source":
           f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"}
    try:
        cf = companyfacts(cik)
    except SourceError as e:
        res["error"] = str(e)
        return res
    facts = cf["facts"]
    end = latest_fy_end(facts)
    res["fy_end"] = end
    checks = res["checks"]

    # Market cap floor: public float
    fl = [x for x in facts.get("dei", {}).get("EntityPublicFloat", {}).get("units", {}).get("USD", [])]
    if fl:
        last = sorted(fl, key=lambda x: x["end"])[-1]
        ok = last["val"] >= g["min_market_cap_usd"]
        checks["market_cap"] = {"value": last["val"], "as_of": last["end"], "tag": "dei:EntityPublicFloat",
                                "pass": True if ok else False,
                                "note": "Public float (non-affiliate shares) used as a floor for market cap."
                                        + ("" if ok else " Float excludes insider holdings, so true market cap may be higher; team should confirm.")}
    else:
        checks["market_cap"] = _market_cap_fallback(cf, g["min_market_cap_usd"])

    if end is None:
        for k in ("net_income", "fcf", "debt_to_equity"):
            checks[k] = {"value": None, "pass": None, "note": "Unknown: no annual XBRL data."}
        res["result"] = "unknown"
        return res

    ni, ni_tag = _flow(facts, "net_income", end)
    checks["net_income"] = {"value": ni, "as_of": end, "tag": ni_tag,
                            "pass": None if ni is None else ni > 0}

    ocf, ocf_tag = _flow(facts, "ocf", end)
    capex, capex_tag = _flow_sum(facts, "capex", end)
    if capex is None:  # fall back to the aggregate tag only when no PP&E line is tagged
        for tax, tag in (("us-gaap", "PaymentsToAcquireProductiveAssets"),):
            v = _annual_flows(facts, tax, tag).get(end)
            if v is not None:
                capex, capex_tag = v["val"], f"{tax}:{tag}"
    extra = notes.get("capex_extra") if notes.get("capex_extra", {}).get("fy_end") == end else None
    if extra:
        capex = (capex or 0) + extra["value"]
        capex_tag = (capex_tag + ", " if capex_tag else "") + f"company filing: {extra['label']}"
    sw, sw_tag = _flow(facts, "capex_software", end)
    if ocf is None:
        checks["fcf"] = {"value": None, "pass": None, "note": "Unknown: operating cash flow not tagged."}
    elif capex is None:
        checks["fcf"] = {"value": None, "ocf": ocf, "pass": None, "as_of": end, "tag": ocf_tag,
                         "note": "Unknown: no property-and-equipment capex tag in XBRL for this year, so free cash flow cannot be computed."}
    else:
        spent = (capex or 0) + (sw or 0)
        fcf = ocf - spent
        checks["fcf"] = {"value": fcf, "as_of": end, "ocf": ocf, "capex": capex, "capitalized_software": sw,
                         "tag": ", ".join(t for t in (ocf_tag, capex_tag, sw_tag) if t),
                         "pass": fcf > 0}

    eq = None
    eq_tag = None
    for tax, tag in TAGS["equity"]:
        eq = _instant(facts, tax, tag, end)
        if eq is not None:
            eq_tag = f"{tax}:{tag}"
            break
    debt = None
    debt_tags = []
    for tax, tag in DEBT_TOTAL:
        v = _instant(facts, tax, tag, end)
        if v is not None:
            debt, debt_tags = v, [f"{tax}:{tag}"]
            break
    if debt is None:
        pieces = [(t, _instant(facts, *t, end)) for t in DEBT_PIECES]
        if any(v is not None for _, v in pieces):
            debt = sum(v for _, v in pieces if v is not None)
            debt_tags = [f"{a}:{b}" for (a, b), v in pieces if v is not None]
    for t in DEBT_EXTRA:
        v = _instant(facts, *t, end)
        if v:
            debt = (debt or 0) + v
            debt_tags.append(f"{t[0]}:{t[1]}")
    debt_note = None
    if debt is None and notes.get("debt", {}).get("fy_end") == end:
        n = notes["debt"]
        debt = n["value"]
        debt_note = f"No debt tag in XBRL; the company's filing states it: \"{n['quote']}\""
        debt_tags.append("company filing (verified quote)")
    if debt is None:
        checks["debt_to_equity"] = {"value": None, "pass": None, "equity": eq,
                                    "note": "Unknown: no debt tags in XBRL for this year and no verified statement of zero debt."}
    if debt is None:
        pass
    elif eq is None:
        checks["debt_to_equity"] = {"value": None, "pass": None, "debt": debt,
                                    "note": "Unknown: shareholders' equity not tagged."}
    elif eq <= 0:
        checks["debt_to_equity"] = {"value": None, "debt": debt, "equity": eq, "pass": None,
                                    "note": "Not meaningful: shareholders' equity is negative (often from buybacks). Team must explain."}
    else:
        r = debt / eq
        checks["debt_to_equity"] = {"value": round(r, 3), "debt": debt, "equity": eq, "as_of": end,
                                    "tag": ", ".join(debt_tags + [eq_tag]),
                                    "pass": r <= g["max_debt_to_equity"], "note": debt_note}

    passes = [checks[k]["pass"] for k in ("market_cap", "net_income", "fcf", "debt_to_equity")]
    if any(p is False for p in passes):
        res["result"] = "fail"
    elif all(p is True for p in passes):
        res["result"] = "pass"
    else:
        res["result"] = "unknown"
    res["failed"] = [k for k in ("market_cap", "net_income", "fcf", "debt_to_equity") if checks[k]["pass"] is False]
    res["unknown"] = [k for k in ("market_cap", "net_income", "fcf", "debt_to_equity") if checks[k]["pass"] is None]
    return res
