"""ETF holdings for the look-through check.

Primary: the issuer's daily holdings file (implemented: State Street SPDR daily .xlsx).
Fallback: the ETF's latest SEC N-PORT-P filing (public filings lag the period by ~60 days;
the as-of date is always recorded and shown).

iShares serves its holdings CSV only behind a sign-in wall and Vanguard/Schwab/Invesco serve
JavaScript apps or block scripted access, so those funds use N-PORT.
"""
from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime

from .http import fetch, SourceError

SSGA = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-{t}.xlsx"
MF_URL = "https://www.sec.gov/files/company_tickers_mf.json"
NS = {"n": "http://www.sec.gov/edgar/nport"}


def _norm_name(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"/[a-z]{2,4}/?", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|plc|class [a-c]|cl [a-c]|the|new)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def ssga_holdings(ticker: str) -> dict:
    import openpyxl
    raw = fetch(SSGA.format(t=ticker.lower()), ttl_hours=20, browser_ua=True, expect=b"PK")
    ws = openpyxl.load_workbook(io.BytesIO(raw), read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    as_of = None
    for r in rows[:6]:
        if r and r[0] and str(r[0]).startswith("Holdings"):
            m = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{4})", str(r[1]))
            if m:
                as_of = datetime.strptime(m.group(1), "%d-%b-%Y").date().isoformat()
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "Name" and "Weight" in r)
    hdr = rows[hdr_i]
    ci = {h: i for i, h in enumerate(hdr) if h}
    out = []
    for r in rows[hdr_i + 1:]:
        if not r or not r[ci["Name"]] or r[ci["Weight"]] in (None, "-"):
            continue
        try:
            w = float(r[ci["Weight"]])
        except (TypeError, ValueError):
            continue
        out.append({"name": str(r[ci["Name"]]).strip(), "ticker": (r[ci["Ticker"]] or "").strip().replace(".", "-"),
                    "cusip": (r[ci.get("Identifier")] or "").strip() if ci.get("Identifier") is not None else "",
                    "pct": w})
    return {"ticker": ticker, "as_of": as_of, "source": SSGA.format(t=ticker.lower()),
            "source_kind": "Issuer daily holdings file (State Street)", "holdings": out}


def _series_for(ticker: str):
    mf = json.loads(fetch(MF_URL, ttl_hours=24 * 7))
    for cik, series, cls, sym in mf["data"]:
        if sym.upper() == ticker.upper():
            return cik, series
    return None, None


def nport_holdings(ticker: str) -> dict:
    cik, series = _series_for(ticker)
    if not series:
        raise SourceError(f"{ticker}: no SEC fund series found (a UIT or non-US fund does not file N-PORT)")
    atom = fetch("https://www.sec.gov/cgi-bin/browse-edgar", params={
        "action": "getcompany", "CIK": series, "type": "NPORT-P", "dateb": "", "owner": "include",
        "count": "10", "output": "atom"}, ttl_hours=24).decode("utf-8", "replace")
    hrefs = re.findall(r"<filing-href>([^<]+)</filing-href>", atom)
    if not hrefs:
        raise SourceError(f"{ticker}: no N-PORT-P filings found for series {series}")
    idx_url = hrefs[0]
    base = idx_url.rsplit("/", 1)[0]
    xml = fetch(base + "/primary_doc.xml", ttl_hours=24 * 30, expect=b"<?xml")
    root = ET.fromstring(xml)
    rep = root.find(".//n:genInfo/n:repPdDate", NS)
    out = []
    for inv in root.iterfind(".//n:invstOrSec", NS):
        def g(tag):
            el = inv.find(f"n:{tag}", NS)
            return el.text.strip() if el is not None and el.text else ""
        try:
            pct = float(g("pctVal"))
        except ValueError:
            continue
        tick = ""
        t_el = inv.find("n:identifiers/n:ticker", NS)
        if t_el is not None:
            tick = (t_el.get("value") or "").replace(".", "-")
        try:
            bal, val = float(g("balance") or 0), float(g("valUSD") or 0)
        except ValueError:
            bal, val = 0.0, 0.0
        out.append({"name": g("name"), "title": g("title"), "cusip": g("cusip"), "ticker": tick, "pct": pct,
                    "balance": bal, "units": g("units"), "val_usd": val})
    return {"ticker": ticker, "as_of": rep.text if rep is not None else None, "source": base + "/primary_doc.xml",
            "filing_index": idx_url, "source_kind": "SEC Form N-PORT-P (fallback; may lag ~60-90 days)",
            "holdings": out}


def holdings(ticker: str, fund_name: str = "") -> dict:
    errors = []
    if "SPDR" in fund_name.upper() or ticker.upper() in ("SPY", "DIA", "MDY"):
        try:
            return ssga_holdings(ticker)
        except (SourceError, StopIteration, KeyError, Exception) as e:  # noqa: BLE001 - report and fall back
            errors.append(f"issuer file: {e}")
    try:
        h = nport_holdings(ticker)
        if errors:
            h["note"] = "; ".join(errors)
        return h
    except SourceError as e:
        errors.append(str(e))
    raise SourceError("; ".join(errors))


def black_share(h: dict, targets: dict) -> dict:
    """targets: {TICKER: {"cusips": set, "names": set}} -> {TICKER: pct of ETF}.

    A holding matches a target by ticker, then CUSIP, then normalized issuer name. Name matches
    for multi-class companies are attributed to a class without a known CUSIP when possible;
    the company total is right either way.
    """
    out = {t: 0.0 for t in targets}
    for row in h["holdings"]:
        tick = (row.get("ticker") or "").upper()
        cus = row.get("cusip") or ""
        hit = None
        if tick in targets:
            hit = tick
        if hit is None and cus:
            hit = next((t for t, i in targets.items() if cus in i["cusips"]), None)
        if hit is None:
            nm = _norm_name(row.get("name", ""))
            cands = [t for t, i in targets.items() if nm and nm in i["names"]]
            if cands:
                hit = next((t for t in cands if not targets[t]["cusips"]), cands[0])
        if hit:
            out[hit] += row["pct"]
            if cus and tick == hit:
                targets[hit]["cusips"].add(cus)
    return {t: round(v, 6) for t, v in out.items()}


def nport_price(company_name: str, funds=("VTI", "VXUS")) -> dict | None:
    """Share price implied by a broad Vanguard fund's N-PORT (value / shares held), by issuer name."""
    target = _norm_name(company_name)
    for f in funds:
        try:
            h = nport_holdings(f)
        except SourceError:
            continue
        rows = [r for r in h["holdings"] if _norm_name(r["name"]) == target and r.get("units") == "NS"
                and r.get("balance", 0) > 0 and r.get("val_usd", 0) > 0]
        if rows:
            r = max(rows, key=lambda r: r["balance"])
            return {"price": r["val_usd"] / r["balance"], "as_of": h["as_of"], "fund": f, "source": h["source"],
                    "cusip": r["cusip"]}
    return None
