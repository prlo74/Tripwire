"""Build the ticker map embedded in the page (the page cannot fetch external sites).

Sources:
- SEC company_tickers_exchange.json: ticker -> CIK, company name (stocks).
- Nasdaq Trader symbol directory (nasdaqtraded.txt): every security traded on US exchanges,
  with an ETF flag. Used as the known-ETF list and to drop delisted/OTC-only tickers.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .http import fetch

ROOT = Path(__file__).resolve().parent.parent
SEC_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"

NOT_COMMON = re.compile(r"preferred|notes? due|debenture|warrant|\bright|\bunits?\b|depositary shares? each|"
                        r"subordinated|% |perpetual|trust preferred", re.I)


def canon(t: str) -> str:
    """Canonical ticker: upper-case, class separator '-' (BRK.B, BRK/B, BRK-B -> BRK-B)."""
    t = t.strip().upper()
    return re.sub(r"[./]", "-", t)


def build() -> dict:
    sec = json.loads(fetch(SEC_URL, ttl_hours=24))
    nas_raw = [l.strip() for l in fetch(NASDAQ_URL, ttl_hours=24, expect=b"Nasdaq Traded").decode("utf-8", "replace").splitlines() if l.strip()]
    header = nas_raw[0].split("|")
    idx = {h: i for i, h in enumerate(header)}
    traded = {}
    created = nas_raw[-1]
    for line in nas_raw[1:-1]:
        f = line.split("|")
        if len(f) < len(header) or f[idx["Test Issue"]] == "Y":
            continue
        traded[canon(f[idx["Symbol"]])] = (f[idx["Security Name"]].strip(), f[idx["ETF"]] == "Y")

    out = {}
    for sym, (secname, is_etf) in traded.items():
        if is_etf:
            out[sym] = [secname, "E", None, None]
    for cik, name, t, ex in sec["data"]:
        t = canon(t)
        if t in out or t not in traded:
            continue  # ETF already, or not currently traded on a US exchange
        secname = traded[t][0]
        cls = 0 if NOT_COMMON.search(secname) else 1  # 1 = common/ordinary share class
        m = re.search(r"\bClass ([A-Z])\b", secname)
        out[t] = [name, "S", cik, cls, m.group(1) if m else None]
    m = re.search(r"(\d{2})(\d{2})(\d{4})(\d{2}):(\d{2})", created)
    as_of = f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None
    return {"asOf": as_of, "sources": [SEC_URL, NASDAQ_URL], "t": out}


if __name__ == "__main__":
    data = build()
    (ROOT / "site").mkdir(exist_ok=True)
    (ROOT / "site" / "tickers.json").write_text(json.dumps(data, separators=(",", ":")))
    etfs = sum(1 for v in data["t"].values() if v[1] == "E")
    print(f"{len(data['t'])} tickers ({etfs} ETFs), as of {data['asOf']}")
