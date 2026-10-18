"""Tracks whether the Tripwire artifacts on claude.ai match the source in this repo.

check  : Stop-hook entry point. If watched source files changed since the last recorded
         publish, exit 2 with instructions so Claude republishes before the session ends.
mark   : record the current source hash as published (run after a successful publish).
status : print what is out of date.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # tripwire/
STATE = ROOT / ".published.json"

TARGETS = {
    "tripwire": {
        "url": "https://claude.ai/artifact/8uEh8baXjRBYo7BYLL4SHr",
        "build": "cd tripwire && python3 -m pipeline.build_page",
        "publish_file": "tripwire/site/index.html",
        # data.json is deliberately excluded: it changes every run and is only a read-only fallback.
        "watch": ["site/page.html", "site/parser.js", "site/lookthrough.js", "site/runbar.js",
                  "site/tickers.json", "site/capabilities.json", "pipeline/build_page.py"],
    },
    "analytics": {
        "url": "https://claude.ai/artifact/TjpvQ6RGKb3upULt9SBGP2",
        "build": None,
        "publish_file": "tripwire/analytics/page.html",
        "watch": ["analytics/page.html"],
    },
}

def digest(names):
    h = hashlib.sha256()
    for n in names:
        p = ROOT / n
        h.update(n.encode()); h.update(p.read_bytes() if p.exists() else b"<missing>")
    return h.hexdigest()

def load():
    try: return json.loads(STATE.read_text())
    except Exception: return {}

def stale():
    st = load()
    return [k for k, t in TARGETS.items() if st.get(k) != digest(t["watch"])]

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "mark":
        st = load()
        for k in (sys.argv[2:] or TARGETS):
            st[k] = digest(TARGETS[k]["watch"])
        STATE.write_text(json.dumps(st, indent=2) + "\n"); print("marked", sys.argv[2:] or list(TARGETS)); return 0
    if cmd == "status":
        print("out of date:", stale() or "none"); return 0
    if cmd == "check":
        try: hook = json.load(sys.stdin)
        except Exception: hook = {}
        if hook.get("stop_hook_active"): return 0          # never loop
        s = stale()
        if not s: return 0
        lines = ["Tripwire source changed since it was last published. Before ending this session:"]
        for k in s:
            t = TARGETS[k]
            if t["build"]: lines.append(f"- [{k}] run `{t['build']}`")
            lines.append(f"- [{k}] publish `{t['publish_file']}` with the Artifact tool to {t['url']} "
                         "(read it first; omit `capabilities` unless site/capabilities.json changed)")
            lines.append(f"- [{k}] then run `python3 tripwire/scripts/publish_state.py mark {k}`")
        lines.append("If this session has no Artifact tool, say so plainly and do not run `mark`.")
        print("\n".join(lines), file=sys.stderr); return 2
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main())
