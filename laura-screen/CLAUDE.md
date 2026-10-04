# Laura Screen: instructions for Claude Code

When a teammate says **"run the Laura screen"** (or similar), do the steps below in order.
The rule behind everything: **Claude proposes, humans decide.** A wrong Black label on a
real company is the worst failure. Accuracy and traceability beat coverage.

Artifact: https://claude.ai/artifact/8uEh8baXjRBYo7BYLL4SHr  (page source: `site/page.html`)
Analytics (private, editors only): https://claude.ai/artifact/TjpvQ6RGKb3upULt9SBGP2  (page source: `analytics/page.html`)

## 0. Setup (once per machine)
- `pip install requests pyyaml beautifulsoup4 openpyxl pypdf pytest` and have `node` on PATH.
- SEC requires a contact email in the User-Agent. Put it in `config/local.yaml`
  (`sec_contact_email: ...`, gitignored) or the `LAURA_SEC_CONTACT` env var. Never in the page or db.
- Optional: `COURTLISTENER_TOKEN` env var (free token) for higher CourtListener limits.

## 0b. Progress bar: first action of every run
Before anything else, so the page's progress bar leaves "Starting" quickly:
```
python -m pipeline.progress start
```
Then ArtifactData `get runs/progress` (for its version; it may not exist yet) and `set runs/progress`
with `file_path: cache/progress_doc.json`, pinned to that version. Keep the version each write
returns and pin the next progress write to it. Rules for every progress write in this file:
- A failed progress write never fails or slows the run: retry it once at most, carry on, and list
  it in the run summary.
- At most about 15 progress writes per run. If they add more than 10% to the run's time, use
  `wait --stages-only` (stage changes only, no counts).
- Never write a made-up count or stage. The helper only prints what the pipeline reported.

## 1. Read the team's state from the Artifact database (ArtifactData tool)
`list` each of `universe`, `approvals`, `runs`, `proposals`, `audit_log`, `usage` with `out_dir: cache/db`
(use `query.limit: 1000`). The saved files hold only document data, so also write
`cache/db/versions.json` as `{"<collection>/<doc_id>": <version>}` from the versions the list
results print (needed to pin overwrites). Then:
```
python -m pipeline.dbsync snapshot cache/db
```

## 2. Run the pipeline
Run it in the background with progress reporting, and relay its stages to the page while it runs:
```
python -m pipeline.run --progress        # background (run_in_background)
python -m pipeline.progress wait         # repeat: it returns when there is something to write
```
Each time `wait` prints `"write": "runs/progress"`, `set runs/progress` from
`cache/progress_doc.json` (pinned). Stop once it says the pipeline finished (or the background
command has exited: a crashed pipeline never says so; report it), then read the
background command's output (its printed run summary) before step 3.
It fetches official data (cached under `cache/`), re-opens every evidence source and checks each
quote is really there, applies `config/rules.yaml`, and prints proposals, discovery matches and
source problems. Any source failure is retried once and reported; never route around it with
mirrors or archives.

## 3. Read the evidence for every candidate change (this is Claude's job)
- For each **discovery match** printed (agency releases, court opinions, 10-K theme matches):
  open the primary source and read it. Only if it meets a rule clause, add a record to
  `evidence/discovery-YYYY-MM.yaml` with `discovered: true`, a verbatim quote of 50 words or
  fewer, the date, the clause and a confidence (High/Medium/Low). Max 10 discovery proposals
  per run, ranked by evidence strength.
- Rules you must apply (see `config/rules.yaml`):
  - Black needs a qualifying finding (merits ruling, jury verdict, agency finding/consent order
    stating the violation, or an admitted settlement) within 7 years, on (a) knowingly false
    information to the public or (b) racial/ethnic discrimination.
  - Settlement without admission -> Watch. Finding older than 7 years -> Watch. Open case past
    a motion to dismiss -> Watch. Every Watch entry needs a tripwire.
  - Tier-2 news is a lead only (`kind: lead`). Never propose from Tier 2 alone.
  - Never add DJT, NWSA/NWS, founder/CEO-identity or China/Xinjiang screens without a finding.
  - Neutral wording. Use the source's words. No adjectives about companies.
  - Unknown values stay "unknown". Never guess a date, figure, quote or URL.
- Re-run `python -m pipeline.run` after editing evidence (no `--progress`: the page stays on
  "Discovery and evidence review" until step 4). Every record must show
  `proposable: True` with verified quotes.

## 3b. Full check of new team tickers
The run prints `NEW TICKER` lines and saves details in `site/data.json` → `newTickerChecks`
(tickers the team pasted that were never checked). For each stock:
- Read Item 1 (Business) of its latest annual report (`annual_report.url`), starting from the
  `theme_snippets`. If it documents a link to one of the three themes in the company's own words,
  add a `values_link` record (`discovered: true`). Marketing adjectives don't count.
- Open each `legal_hits` filing (SEC full-text hits in its own filings over the look-back window)
  and read the legal-proceedings passage. Most hits are boilerplate; write a `finding`,
  `open_case` or `settlement_no_admission` record only when a primary source meets a rule clause.
- If nothing qualifies, write nothing. The export records "No values link or qualifying legal
  finding found" on the ticker, and the page shows it.
Re-run `python -m pipeline.run` after writing records; `dbsync export` then marks each checked
ticker (`universe/<T>.checked_at`, `check_summary`). New-ticker proposals count toward the 10
discovery proposals per run.

## 4. Write results to the Artifact
```
python -m pipeline.progress phase publish     # then set runs/progress from cache/progress_doc.json
python -m pipeline.dbsync export
```
Then one ArtifactData `batch` call with the entries in `out/db_writes/manifest.json`
(split into batches of 50). Republish the page only if `site/page.html`, the parser, the
look-through code or the ticker map changed: `python -m pipeline.build_page`, then publish
`site/index.html` to the Artifact URL above (omit `capabilities` to keep the rules; if the rules
must change, pass the whole of `site/capabilities.json`, since a declaration replaces the old one).

## 5. Email alerts
`list subscribers` with `out_dir: cache/db` (cache is gitignored: it holds emails) and `get
runs/alerts_ledger` (save as `cache/ledger.json`; may not exist yet), then
```
python -m pipeline.alerts plan cache/db cache/ledger.json
```
Send each item in `cache/alerts_to_send.json` with the Gmail connector (`send_message`), then
`set runs/alerts_ledger` from `cache/ledger_next.json`. If Gmail is not connected, say so and
list the alerts in the run summary instead. Before the first real alert ever, send one test
email to Leo only, and only after he says yes. (Done: Leo approved and received the test on 2026-09-26.)

## 5b. Weekly run bookkeeping
First close the progress bar and record how long each stage took:
```
python -m pipeline.progress finish [--requested-at <settings/weekly.check_requested_at>]
```
Pass `--requested-at` only for a Check now run (a scheduled run has no button press; the helper
carries the previous "starting" time forward). Then, in this order: `update runs/latest` from
`cache/run_timing.json` (it holds the whole `run` object with `timing` added; pin to the version
the step 4 batch returned), `set runs/progress` from `cache/progress_doc.json` (state `done`),
and finally `settings/weekly` below. The page uses `run.timing.phase_ms` to weight its bar.

After every run (scheduled or Check now), update `settings/weekly` (pinned to its version) with
`last_run_at`, a one-line `last_run_summary`, and `check_completed_at` (the current UTC time, as the
last write of the run). The page's elapsed timer stops at `check_completed_at` and shows how long
the check took; a request with no completion after 45 minutes is shown as unfinished.

## 5c. Analytics (team totals only)
```
python -m pipeline.analytics cache/db
```
Then `set metrics/latest` on the analytics Artifact (URL above) from `out/analytics.json`
(`file_path`; pin `if_version` to the version a `get` shows). Commit `analytics/history.json`:
it keeps weekly totals after the page deletes raw usage older than 8 weeks. Never write account
ids, names or per-person numbers to the analytics page, the repo or the run summary.

## 6. Print a short run summary
What changed, what needs approval, errors/sources down, alerts sent. Also: the number of progress
writes, any that failed, roughly how many seconds they added (only the writes outside the
background pipeline add time), and the recorded `phase_ms` (printed by `progress finish`).

## Tests
`python -m pytest -q` (parser, look-through math, rule logic, financial gate, WCAG contrast, run
progress; about 8s). `node tests/runbar.test.js` runs the progress bar's model on its own.
`python -m pytest -m slow` runs the full pipeline end to end in a temporary copy (about 90s); it never touches the repo's outputs.
