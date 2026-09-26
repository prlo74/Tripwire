"""Polite, cached HTTP for all fetchers.

- Descriptive User-Agent with a contact email (SEC requires this). The email is read
  from the LAURA_SEC_CONTACT env var or config/local.yaml (gitignored), never the page.
- Per-host rate limit (SEC: < 10 req/s; others: 1 req/s).
- Disk cache under cache/http/ keyed by URL; TTL per call.
- One retry on failure, then SourceError so the run can report "X: unavailable this run".
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "http"
CACHE.mkdir(parents=True, exist_ok=True)

_last_hit: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_session = requests.Session()

# Minimum seconds between requests to the same host.
HOST_DELAY = {
    "www.sec.gov": 0.15, "data.sec.gov": 0.15, "efts.sec.gov": 0.15,
}
DEFAULT_DELAY = 1.0


class SourceError(RuntimeError):
    """A source could not be fetched after one retry."""


def contact_email() -> str:
    env = os.environ.get("LAURA_SEC_CONTACT")
    if env:
        return env
    local = ROOT / "config" / "local.yaml"
    if local.exists():
        data = yaml.safe_load(local.read_text()) or {}
        if data.get("sec_contact_email"):
            return data["sec_contact_email"]
    raise SourceError("No SEC contact email: set LAURA_SEC_CONTACT or config/local.yaml")


def user_agent() -> str:
    return f"LauraScreen/1.0 (student research, Wharton GYIC; {contact_email()})"


def _browser_ua() -> str:
    # Some agency sites (DOJ, SSGA, Delaware courts) reject non-browser agents. We send a
    # standard browser string and identify ourselves in the From header instead.
    return ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36")


def _robots_ok(url: str) -> bool:
    p = urlparse(url)
    host = p.netloc
    if host.endswith("sec.gov") or host == "www.justice.gov":
        return True  # documented public APIs / data files
    if host == "www.courtlistener.com" and p.path.startswith("/api/rest/v4/"):
        return True  # documented REST API (robots.txt governs crawling of HTML pages)
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = _session.get(f"{p.scheme}://{host}/robots.txt", timeout=15,
                             headers={"User-Agent": _browser_ua()})
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
                _robots[host] = rp
            else:
                _robots[host] = None
        except requests.RequestException:
            _robots[host] = None
    rp = _robots[host]
    return True if rp is None else rp.can_fetch("*", url)


def _is_challenge(body: bytes) -> bool:
    head = body[:4000]
    return b"bm-verify" in head or b"_Incapsula_Resource" in head or b"cf-chl" in head


def _key(url: str, params: dict | None) -> Path:
    raw = url + ("?" + json.dumps(params, sort_keys=True) if params else "")
    return CACHE / hashlib.sha256(raw.encode()).hexdigest()[:32]


def fetch(url: str, *, params: dict | None = None, ttl_hours: float = 24,
          browser_ua: bool = False, headers: dict | None = None,
          expect: bytes | None = None) -> bytes:
    """GET with disk cache. Raises SourceError after one retry.

    expect: bytes the body must start with (guards against bot-challenge pages being cached).
    """
    path = _key(url, params)
    meta = path.with_suffix(".meta")
    if path.exists() and meta.exists():
        age_h = (time.time() - path.stat().st_mtime) / 3600
        body = path.read_bytes()
        if _is_challenge(body):
            body = b""
        if body and (ttl_hours < 0 or age_h < ttl_hours) and (not expect or body.lstrip().startswith(expect)):
            return body
    if not _robots_ok(url):
        raise SourceError(f"robots.txt disallows {url}")
    host = urlparse(url).netloc
    hdrs = {"User-Agent": _browser_ua() if browser_ua else user_agent(),
            "Accept-Encoding": "gzip, deflate"}
    if host.endswith("sec.gov"):
        hdrs["From"] = contact_email()  # SEC asks for a contact; other hosts don't get the email
    if host == "www.courtlistener.com" and os.environ.get("COURTLISTENER_TOKEN"):
        hdrs["Authorization"] = f"Token {os.environ['COURTLISTENER_TOKEN']}"
    hdrs.update(headers or {})
    last_err = None
    for attempt in range(2):
        wait = HOST_DELAY.get(host, DEFAULT_DELAY) - (time.time() - _last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.time()
        try:
            r = _session.get(url, params=params, headers=hdrs, timeout=45)
            if r.status_code == 200 and _is_challenge(r.content):
                last_err = "bot challenge page"
            elif r.status_code == 200 and expect and not r.content.lstrip().startswith(expect):
                last_err = "unexpected content (bot challenge?)"
            elif r.status_code == 200:
                path.write_bytes(r.content)
                meta.write_text(json.dumps({"url": r.url, "fetched": time.time()}))
                return r.content
            else:
                last_err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last_err = type(e).__name__
        if attempt == 0:
            time.sleep(2)
    # No stale fallback: a source that fails twice is reported as unavailable this run.
    raise SourceError(f"{host}: {last_err}")


def fetch_json(url: str, **kw):
    return json.loads(fetch(url, **kw))


def fetched_at(url: str, params: dict | None = None) -> float | None:
    meta = _key(url, params).with_suffix(".meta")
    if meta.exists():
        return json.loads(meta.read_text())["fetched"]
    return None
