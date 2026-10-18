"""Discovery: find NEW names outside the current lists.

Black/Watch: agency releases and court opinions since the last run, matched to universe
companies by name. These are CANDIDATES for Claude to read; only a candidate whose primary
source Claude reads and records in evidence/*.yaml becomes a proposal.

Aligned: universe companies whose latest 10-K contains theme phrases (SEC full-text search),
then the financial gate.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from .http import fetch, fetch_json, SourceError

# Clause (b): race, ethnicity, sexual orientation and gender identity terms. Clause (a): falsity to the public. Plain "discrimination"
# (disability, religion, age, sex) is outside the rule and is not matched.
RACE_OR_FALSITY = re.compile(
    r"\b(race|racial|racially|national origin|ethnic|ethnicity|black employees|black workers|hispanic|"
    r"latino|asian american|african american|fair housing|redlining|sexual orientation|gender identity|"
    r"transgender|gay|lesbian|lgbt\w*|homophob\w*|transphob\w*|defam\w*|disinformation|misinformation|"
    r"misled the public|misleading the public|false information)\b", re.I)

GENERIC_SINGLE = {"visa", "southern", "apple", "oracle", "intel", "salesforce", "cisco", "chubb", "target","target", "block", "apple", "visa", "ford", "gap", "match", "fox", "news", "general",
                  "southern", "united", "american", "first", "public", "global", "national", "best",
                  "entergy", "ball", "crown", "dover", "masco", "corning", "progressive", "equity"}


def _norm(s: str) -> str:
    s = html.unescape(s).lower().replace("&", " and ").replace("’", "'")
    s = re.sub(r"/[a-z]{2,4}/?", " ", s)
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    s = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|plc|holdings?|group|the|class [a-c]|new|de|del)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def name_patterns(universe: dict) -> list[tuple[re.Pattern, str, bool]]:
    """universe: {ticker: {name, cik}} -> [(regex, ticker, case_sensitive)]"""
    pats, seen = [], set()
    for t, info in universe.items():
        n = _norm(info["name"])
        if not n or len(n) < 3 or (info.get("cik"), n) in seen:
            continue
        seen.add((info.get("cik"), n))
        single = " " not in n
        if single and (n in GENERIC_SINGLE or len(n) <= 4):
            # Common words: require the capitalized name followed by a corporate cue
            # ("Target Corp", "Apple Inc", "Ford Motor", "Visa to Pay"), never a bare word.
            word = n.capitalize()
            cue = r"(?:,?\s+(?:Inc|Corp|Corporation|Co|Company|Motor|Stores|Brands|Holdings|LLC|L\.P)\b|\s+(?:to|agrees|will|settles|resolves|pays)\b)"
            pats.append((re.compile(r"(?<![A-Za-z])" + re.escape(word) + cue), t, True))
        else:
            pats.append((re.compile(r"\b" + r"\s+".join(map(re.escape, n.split())) + r"\b", re.I), t, False))
    return pats


def match_universe(text: str, pats) -> list[str]:
    hits = []
    for rx, t, _ in pats:
        if rx.search(text):
            hits.append(t)
    return sorted(set(hits))


def doj_since(since: date, max_pages: int = 60) -> tuple[list[dict], str | None]:
    out = []
    for page in range(max_pages):
        try:
            d = fetch_json("https://www.justice.gov/api/v1/press_releases.json",
                           params={"pagesize": 50, "page": page, "sort": "date", "direction": "DESC"},
                           browser_ua=True, ttl_hours=12)
        except SourceError as e:
            return out, f"DOJ: {e}"
        stop = False
        for r in d.get("results", []):
            try:
                dt = datetime.fromtimestamp(int(r["date"])).date()
            except (ValueError, TypeError, KeyError):
                continue   # a release without a date cannot be placed in the window
            if dt < since:
                stop = True
                break
            comps = [c.get("name", "") for c in (r.get("component") or []) if isinstance(c, dict)]
            out.append({"source": "DOJ", "date": dt.isoformat(), "title": html.unescape(r["title"]),
                        "url": r["url"], "components": comps,
                        "text": r["title"] + " " + re.sub("<[^>]+>", " ", r.get("body") or "")[:3000]})
        if stop or not d.get("results"):
            break
    return out, None


def eeoc_since(since: date, max_pages: int = 25) -> tuple[list[dict], str | None]:
    out = []
    for page in range(max_pages):
        try:
            b = fetch("https://www.eeoc.gov/newsroom/search", params={"page": page} if page else None,
                      browser_ua=True, ttl_hours=12)
        except SourceError as e:
            return out, f"EEOC: {e}"
        s = BeautifulSoup(b, "html.parser")
        rows = s.select("article.press_release")
        found_old = False
        n = 0
        for row in rows:
            a = row.select_one('a[href*="/newsroom/"]')
            tm = row.select_one(".field--name-field-published-date")
            if not a or not tm:
                continue
            try:
                dt = datetime.strptime(tm.get_text(strip=True), "%B %d, %Y").date()
            except ValueError:
                continue
            n += 1
            if dt < since:
                found_old = True
                continue
            out.append({"source": "EEOC", "date": dt.isoformat(), "title": a.get_text(" ", strip=True),
                        "url": "https://www.eeoc.gov" + a["href"] if a["href"].startswith("/") else a["href"],
                        "text": row.get_text(" ", strip=True)})
        if found_old or n == 0:
            break
    return out, None


def ftc_since(since: date, max_pages: int = 15) -> tuple[list[dict], str | None]:
    out = []
    for page in range(max_pages):
        try:
            b = fetch("https://www.ftc.gov/news-events/news/press-releases",
                      params={"page": page} if page else None, browser_ua=True, ttl_hours=12)
        except SourceError as e:
            return out, f"FTC: {e}"
        s = BeautifulSoup(b, "html.parser")
        n, found_old = 0, False
        seen = {x["url"] for x in out}
        for row in s.select("article"):
            a = row.select_one('a[href*="/news-events/news/press-releases/"]')
            tm = row.select_one("time")
            if not a or not tm:
                continue
            try:
                dt = date.fromisoformat((tm.get("datetime") or "")[:10])
            except ValueError:
                continue
            n += 1
            if dt < since:
                found_old = True
                continue
            href = a["href"]
            if ("https://www.ftc.gov" + href) in seen or href in seen:
                continue
            seen.add("https://www.ftc.gov" + href if href.startswith("/") else href)
            out.append({"source": "FTC", "date": dt.isoformat(), "title": a.get_text(" ", strip=True),
                        "url": "https://www.ftc.gov" + href if href.startswith("/") else href,
                        "text": row.get_text(" ", strip=True)})
        if found_old or n == 0:
            break
    return out, None


def courtlistener_since(since: date) -> tuple[list[dict], str | None]:
    q = ('("race discrimination" OR "racial discrimination" OR "racial harassment" OR "sexual orientation discrimination" '
         'OR "gender identity discrimination" OR defamation) '
         'AND (jury OR verdict OR "summary judgment")')
    try:
        d = fetch_json("https://www.courtlistener.com/api/rest/v4/search/",
                       params={"q": q, "type": "o", "order_by": "dateFiled desc",
                               "filed_after": since.isoformat()}, browser_ua=True, ttl_hours=12)
    except SourceError as e:
        return [], f"CourtListener: {e}"
    out = []
    for r in d.get("results", []):
        ops = r.get("opinions") or [{}]
        out.append({"source": "CourtListener", "date": r.get("dateFiled"), "title": r.get("caseName", ""),
                    "url": ops[0].get("download_url") or "https://www.courtlistener.com" + r.get("absolute_url", ""),
                    "court": r.get("court"), "text": r.get("caseName", "")})
    return out, None


def legal_candidates(universe: dict, since: date, deep: bool = False) -> dict:
    """deep=True (full re-check after a rule change) lifts the page caps so the whole window is scanned."""
    pats = name_patterns(universe)
    status, cands = {}, []
    caps = {doj_since: 600, eeoc_since: 200, ftc_since: 150}
    for fn in (doj_since, eeoc_since, ftc_since, courtlistener_since):
        items, err = fn(since, caps[fn]) if (deep and fn in caps) else fn(since)
        name = fn.__name__.split("_")[0].upper().replace("COURTLISTENER", "CourtListener")
        status[name] = {"ok": err is None, "items_scanned": len(items), "error": err}
        for it in items:
            if not RACE_OR_FALSITY.search(it["text"]):
                continue
            hits = match_universe(it["title"], pats) or (
                match_universe(it["text"], pats) if it["source"] == "CourtListener" else [])
            if hits:
                it = {k: v for k, v in it.items() if k != "text"}
                it["tickers"] = hits
                cands.append(it)
    return {"candidates": cands, "status": status}


def theme_candidates(universe_ciks: dict, themes: dict, since: date) -> tuple[dict, str | None]:
    """SEC full-text search for theme phrases in 10-K filings since `since`.
    universe_ciks: {cik: ticker}. Returns {ticker: {theme: [phrases]}}."""
    out: dict[str, dict] = {}
    err = None
    for theme, cfg in themes.items():
        for ph in cfg.get("discovery_phrases", []):
            for start in (0, 100):
                try:
                    d = fetch_json("https://efts.sec.gov/LATEST/search-index",
                                   params={"q": f'"{ph}"', "forms": "10-K,40-F,20-F", "dateRange": "custom",
                                           "startdt": since.isoformat(), "enddt": date.today().isoformat(),
                                           "from": start}, ttl_hours=24 * 3)
                except SourceError as e:
                    err = f"SEC full-text search: {e}"
                    break
                hits = d.get("hits", {}).get("hits", [])
                for h in hits:
                    for c in h["_source"].get("ciks", []):
                        t = universe_ciks.get(int(c))
                        if t:
                            out.setdefault(t, {}).setdefault(theme, set()).add(ph)
                if len(hits) < 100:
                    break
    return {t: {th: sorted(p) for th, p in v.items()} for t, v in out.items()}, err


# SEC Standard Industrial Classification codes where the three themes plausibly live:
# publishing, news, education, software/creative tools, internet marketplaces, media.
THEME_SIC = {2711, 2721, 2731, 2741, 2750, 7370, 7371, 7372, 7374, 7379, 5961, 5990, 7812, 7819, 4833,
             4841, 8200, 8211, 8220, 8290, 7900, 7990, 5731, 5945, 3861}


def sic_of(cik: int) -> tuple[int | None, str | None]:
    try:
        d = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", ttl_hours=24 * 30)
        return (int(d["sic"]) if d.get("sic") else None), d.get("sicDescription")
    except (SourceError, ValueError):
        return None, None


def sec_phrase_hits(universe_ciks: dict, phrases: list[str], forms: str, since: date,
                    max_pages: int = 5) -> tuple[dict, str | None]:
    """SEC full-text search for exact phrases in the given forms since `since`.
    Returns ({ticker: [{phrase, form, filed, url}]}, error). Hits are leads for Claude to read."""
    out: dict[str, list] = {}
    err = None
    for ph in phrases:
        for page in range(max_pages):
            try:
                d = fetch_json("https://efts.sec.gov/LATEST/search-index",
                               params={"q": f'"{ph}"', "forms": forms, "dateRange": "custom",
                                       "startdt": since.isoformat(), "enddt": date.today().isoformat(),
                                       "from": page * 100}, ttl_hours=24 * 3)
            except SourceError as e:
                err = f"SEC full-text search: {e}"
                break
            hits = d.get("hits", {}).get("hits", [])
            for h in hits:
                src = h["_source"]
                for c in src.get("ciks", []):
                    t = universe_ciks.get(int(c))
                    if not t:
                        continue
                    acc, _, fname = h["_id"].partition(":")
                    url = f"https://www.sec.gov/Archives/edgar/data/{int(c)}/{acc.replace('-', '')}/{fname}"
                    row = {"phrase": ph, "form": src.get("form"), "filed": src.get("file_date"), "url": url}
                    if row not in out.setdefault(t, []):
                        out[t].append(row)
            if len(hits) < 100:
                break
    return out, err
