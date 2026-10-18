"""Fetch a document and turn it into plain text for reading and quote verification."""
from __future__ import annotations

import io
import re
import sys
import unicodedata

from bs4 import BeautifulSoup

from .http import fetch, fetch_json, SourceError

BROWSER_HOSTS = ("justice.gov", "eeoc.gov", "ftc.gov", "ssga.com", "calcivilrights.ca.gov",
                 "courts.delaware.gov", "oag.ca.gov", "courtlistener.com", "cand.uscourts.gov")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _doj_release_via_api(url: str) -> bytes:
    """justice.gov press-release pages refuse scripted access (HTTP 401); DOJ's official
    press-release API serves the same release body. Find it by title words from the URL slug."""
    slug = url.rstrip("/").rsplit("/", 1)[-1].split("-")
    for n in (6, 4):
        words = " ".join(slug[-n:])
        data = fetch_json("https://www.justice.gov/api/v1/press_releases.json",
                          params={"parameters[title]": words, "pagesize": 20}, browser_ua=True)
        for r in data.get("results", []):
            if r.get("url", "").rstrip("/") == url.rstrip("/"):
                return ("<h1>" + r.get("title", "") + "</h1>" + r.get("body", "")).encode()
    raise SourceError(f"DOJ API: release not found for {url}")


def doc_text(url: str, ttl_hours: float = 20) -> str:
    """Plain text of a source. Default TTL is under a day so each run re-opens its sources."""
    browser = any(h in url for h in BROWSER_HOSTS)
    try:
        raw = fetch(url, ttl_hours=ttl_hours, browser_ua=browser)
    except SourceError:
        if "justice.gov" in url and "/pr/" in url:
            raw = _doj_release_via_api(url)
        else:
            raise
    if raw[:4] == b"%PDF":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return _norm(" ".join((p.extract_text() or "") for p in reader.pages))
    soup = BeautifulSoup(raw, "html.parser")
    for t in soup(["script", "style", "noscript", "ix:header"]):
        t.decompose()
    for t in soup.find_all(style=re.compile(r"display:\s*none")):
        t.decompose()
    return _norm(soup.get_text(" "))


def quote_in_doc(quote: str, text: str) -> bool:
    """True if the quote (ignoring case, whitespace, quote marks, ellipses) is in text."""
    def squash(s):
        return re.sub(r"[^a-z0-9$%.,]", "", _norm(s).lower())
    parts = [p for p in re.split(r"\.\.\.|…|\[[^\]]*\]", quote) if p.strip()]
    t = squash(text)
    return all(squash(p) in t for p in parts)


def context(url: str, term: str, width: int = 400, limit: int = 5) -> list[str]:
    text = doc_text(url)
    out = []
    for m in re.finditer(re.escape(term), text, flags=re.I):
        out.append(text[max(0, m.start() - width): m.end() + width])
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    url, term = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    w = int(sys.argv[4]) if len(sys.argv) > 4 else 500
    for c in context(url, term, width=w, limit=n):
        print("…" + c + "…\n")
