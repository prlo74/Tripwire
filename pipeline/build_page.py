"""Assemble site/index.html: the page template with the ticker map, the last run's data
(read-only fallback when the live database is unavailable) and the JS modules inlined.
The page cannot fetch external sites, so everything it needs ships inside it."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def safe_json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str).replace("</", "<\\/")


def build() -> Path:
    tpl = (SITE / "page.html").read_text()
    data = json.loads((SITE / "data.json").read_text())
    tickers = json.loads((SITE / "tickers.json").read_text())
    out = (tpl.replace("/*__DATA__*/", safe_json(data))
              .replace("/*__TICKERS__*/", safe_json(tickers))
              .replace("/*__PARSER__*/", (SITE / "parser.js").read_text())
              .replace("/*__LOOKTHROUGH__*/", (SITE / "lookthrough.js").read_text())
              .replace("/*__RUNBAR__*/", (SITE / "runbar.js").read_text()))
    assert "/*__" not in out, "unfilled placeholder"
    dest = SITE / "index.html"
    dest.write_text(out)
    # GitHub Pages copy: claude.ai wraps index.html in a document skeleton; a static host doesn't,
    # so public.html carries its own (the UTF-8 declaration matters for the parser's regexes).
    (SITE / "public.html").write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                                      '<meta name="viewport" content="width=device-width,initial-scale=1">'
                                      '</head><body>\n' + out + '\n</body></html>\n')
    return dest


if __name__ == "__main__":
    p = build()
    print(f"{p} ({p.stat().st_size / 1024:.0f} KB)")
