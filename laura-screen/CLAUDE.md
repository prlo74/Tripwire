# Laura Screen: instructions for Claude Code

When a teammate says **"run the Laura screen"** (or similar), do the steps below in order.
The rule behind everything: **Claude proposes, humans decide.** A wrong Black label on a
real company is the worst failure. Accuracy and traceability beat coverage.

Artifact: https://claude.ai/artifact/8uEh8baXjRBYo7BYLL4SHr  (page source: `site/page.html`)

## 0. Setup (once per machine)
- `pip install requests pyyaml beautifulsoup4 openpyxl pypdf pytest` and have `node` on PATH.
- SEC requires a contact email in the User-Agent. Put it in `config/local.yaml`
  (`sec_contact_email: ...`, gitignored) or the `LAURA_SEC_CONTACT` env var. Never in the page or db.
- Optional: `COURTLISTENER_TOKEN` env var (free token) for higher CourtListener limits.

## 1. Read the team's state from the Artifact database (ArtifactData tool)
`list` each of `universe`, `approvals`, `runs`, `proposals` with `out_dir: cache/db`
(use `query.limit: 1000`). The saved files hold only document data, so also write
`cache/db/versions.json` as `{"<collection>/<doc_id>": <version>}` from the versions the list
results print (needed to pin overwrites). Then:
```
python -m pipeline.dbsync snapshot cache/db
```

## 2. Run the pipeline
```
python -m pipeline.run
```
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
- Re-run `python -m pipeline.run` after editing evidence. Every record must show
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
python -m pipeline.dbsync export
```
Then one ArtifactData `batch` call with the entries in `out/db_writes/manifest.json`
(split into batches of 50). Republish the page only if `site/page.html`, the parser, the
look-through code or the ticker map changed: `python -m pipeline.build_page`, then publish
`site/index.html` to the Artifact URL above (omit `capabilities` to keep the rules).

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
If this is a scheduled run, update `settings/weekly` (pinned to its version) with `last_run_at`
and a one-line `last_run_summary`. The page's Weekly run card reads it.

## 6. Print a short run summary
What changed, what needs approval, errors/sources down, alerts sent.

## Tests
`python -m pytest -q` (parser, look-through math, rule logic, financial gate, WCAG contrast; about 6s).
`python -m pytest -m slow` runs the full pipeline end to end in a temporary copy (about 90s); it never touches the repo's outputs.
