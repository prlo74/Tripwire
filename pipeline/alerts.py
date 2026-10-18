"""Plan email alerts for this run.

  python -m pipeline.alerts plan <subscribers_dir> <ledger.json>

<subscribers_dir>: ArtifactData `list subscribers out_dir=cache/db` output (kept in cache/,
which is gitignored, because it holds email addresses).
<ledger.json>: the `runs/alerts_ledger` document (hashes of alerts already sent; no emails).

Writes cache/alerts_to_send.json (who gets which message) and cache/ledger_next.json (the
ledger to write back after the sends succeed). Claude Code sends each message with the Gmail
connector, then writes the new ledger to runs/alerts_ledger.

Dedup key: (ticker, from, to, evidence id, proposed|confirmed) per subscriber, so each
subscriber gets each alert once, and gets it again only when the team confirms it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
ARTIFACT_URL = "https://claude.ai/artifact/8uEh8baXjRBYo7BYLL4SHr"


def h(sub_id: str, key: str) -> str:
    return hashlib.sha256(f"{sub_id}|{key}".encode()).hexdigest()[:24]


def body(a: dict) -> str:
    lines = [
        f"Ticker: {a['ticker']}",
        f"Change: {a['from'].title()} -> Black ({a['status']})",
        f"Rule: {a['clause']}",
        f"Reason: {a['reason']}",
        f"Source: {a.get('source_url') or 'unknown'} ({a.get('source_date') or 'date unknown'})",
        f"Review it: {ARTIFACT_URL}",
        "",
        "Proposed. Awaiting team approval." if a["status"] == "proposed" else "Confirmed: the team approved this change.",
        "",
        "Tripwire is a research aid for a student competition, not investment advice.",
        "You get this because you subscribed on the Tripwire page. Unsubscribe there.",
    ]
    return "\n".join(lines)


def plan(sub_dir: Path, ledger_path: Path) -> None:
    alerts = json.loads((ROOT / "out" / "alerts.json").read_text())
    ledger = set()
    if ledger_path.exists():
        doc = json.loads(ledger_path.read_text())
        ledger = set((doc.get("data", doc)).get("sent", []))
    subs = []
    for p in sorted((sub_dir / "subscribers").glob("*.json")) if (sub_dir / "subscribers").exists() else []:
        d = json.loads(p.read_text())
        d = d.get("data", d)
        if d.get("active") and d.get("email"):
            subs.append({"id": p.stem, **d})
    sends, new = [], set(ledger)
    for s in subs:
        for a in alerts:
            if s.get("mode", "to_black") == "to_black" and not a.get("core"):
                continue
            k = h(s["id"], a["key"])
            if k in ledger:
                continue
            sends.append({"to": s["email"], "subject": a["subject"], "body": body(a), "ledger_key": k})
            new.add(k)
    CACHE.mkdir(exist_ok=True)
    (CACHE / "alerts_to_send.json").write_text(json.dumps(sends, indent=1))
    (CACHE / "ledger_next.json").write_text(json.dumps({"sent": sorted(new)}))
    print(f"{len(alerts)} alert(s) this run, {len(subs)} active subscriber(s), {len(sends)} email(s) to send")
    for x in sends:
        print(f"  -> {x['subject']}")


if __name__ == "__main__":
    if sys.argv[1] == "plan":
        plan(Path(sys.argv[2]), Path(sys.argv[3]))
