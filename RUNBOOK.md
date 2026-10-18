# Tripwire runbook

Tripwire keeps three lists of US stocks current for the Wharton GYIC Laura Gao case:
**Black** (exclude), **Watch** (serious open issue, with a tripwire) and **Aligned** (passes the
financial screen and has a documented link to Laura's values), plus a neutral fourth list,
**No finding** (まし): fully checked team stocks with nothing qualifying found. It is not a clearance.
See `no_finding` in `config/rules.yaml`. It also checks ETFs for
look-through exposure to Black-list stocks. The page is here:
https://claude.ai/artifact/8uEh8baXjRBYo7BYLL4SHr

**Claude proposes, humans decide.** Nothing is on a list until a teammate approves it on the page.
This screen is the team's assumption about Laura's wishes. It is a research aid, not investment advice.

## How to run it
1. On the public page, press **Request a check** (a GitHub issue starts a cloud run; see below). Or, locally,
   open Claude Code in this folder and say **run Tripwire**.
2. Locally, Claude asks for your go first.
3. Claude reads the team's saved tickers and approvals, runs the pipeline, reads the evidence for
   anything new, writes proposals to the page, sends email alerts, and prints a summary.
4. Open the page. Approve or reject each proposal in **Needs approval**. Every decision is logged.

A full first run takes about 4 minutes; a cached re-run takes under a minute. Alerts are only as
fast as the run schedule: a weekly run means up to 7 days of lag.

## Checking new tickers and the scheduled run
- **Paste, save, then Check now.** Saved tickers show "Waiting" in the team list. **Check now**
  (on the Paste card or the Scheduled run card) starts a full run immediately. For every new ticker
  it runs the financial gate, reads its latest 10-K for a values link, and searches its own SEC
  filings over the 7-year window for legal proceedings. Results appear in 5–10 minutes: a proposal
  in Needs approval, "Values fit, fails the financial screen", or "Checked: no values link or
  qualifying legal finding found".
- **Runs happen in the cloud (since 2026-10-19)**, on Claude credits, from `main` of
  https://github.com/prlo74/Tripwire. See `ROUTINE.md` for the routine's prompt and triggers.
  A run starts when someone opens a GitHub issue titled `Check: ...` (the public page's
  **Request a check** button does this), and daily at 07:30 Tokyo time. A Check now press on the
  team's claude.ai copy writes `requests/check` and waits for the next of those runs.
- **Public page:** https://prlo74.github.io/Tripwire/ (GitHub Pages, `site/public.html`, built by
  `pipeline.build_page`). It shows the lists from the last run, the team's decisions
  (`site/decisions.json`, no account ids or reasons) and check requests with results
  (`site/requests.json`). Visitors can't change anything; requests are GitHub issues.
- **Request handling:** `python -m pipeline.issues pending` reads open `Check:` issues, keeps
  only tickers in the ticker map (max 15 new tickers per run) and adds them to the team list;
  `record` writes results; `decisions` publishes the team's decisions.
- **Cost guard.** One run at a time (a run in progress makes the others stop), at most 15 new
  tickers per run. To stop cloud runs, disable the routine at https://claude.ai/code/routines.
  If issues are abused, lock issue creation in the repository settings.
- **Alerts.** The routine has no Gmail connector, so it lists alerts in its run summary instead
  of emailing. Attach Gmail to the routine on claude.ai to send them.
- **Local runs still work** (`/tripwire` from the wharton-gyic repo, where this repo is the
  `tripwire/` submodule). Don't start one while a cloud run is in progress: both push to `main`.
- **Only editors decide.** Approve, reject and reopen need edit access to the claude.ai copy
  (db rule `approvals: admin`).
- The old routine (`trig_01Qe7LfvthehDzsLRq1WmLGZ`, CredCheck layout) stays disabled.

## Run progress bar
While a check runs, a large bar under the summary row (visible on every tab) shows the percent done,
the current step and the elapsed time. It reads `settings/weekly` and `runs/progress` from the
database, so viewers see it too; with no live database it stays hidden. To show the `ring` or
`ledger` design instead, change `data-variant` on `#runbar` in `site/page.html`.

Steps (ids are the same in `site/runbar.js` and `pipeline/progress.py`; change both together):

| id | Shown as | Covers | Count |
|---|---|---|---|
| `starting` | Starting the run | button press until the run's first progress write (page only) | none |
| `universe` | Ticker lists and S&P 500 | reading the database, ticker lists, SPY holdings | none |
| `records` | Court and agency records | re-opening every evidence source | sources checked |
| `financials` | Financial gates and new tickers | XBRL financial gate, new team ticker checks | companies |
| `etf` | ETF holdings | issuer files / SEC N-PORT | funds |
| `discovery` | Discovery and evidence review | agency/court/10-K discovery, then Claude reading the evidence and re-running | none |
| `publish` | Writing results | export, database writes, alerts | none |

Data contract:
- `runs/progress`: `{state: "running"|"done", run_id, started_at, phase, phase_index, label,
  done, total, unit, phase_started_at, updated_at}` (UTC ISO 8601). `done`/`total`/`unit` only
  when the step has a real count; otherwise the page estimates that step from time and shows
  "About N percent". Written by Claude Code from `python -m pipeline.progress` (see CLAUDE.md).
- `runs/latest` → `run.timing`: `{total_ms, phase_ms: {starting, universe, ...}}`, written when
  the run finishes. The page weights each step by the last run's `phase_ms`; until a run has
  recorded all seven, it uses placeholder weights.
- The percent never goes backwards and stays at 99 until the run records it finished. With no
  update for max(90 s, 3 × the step's usual time) the bar says "Slower than usual" and holds; a run
  that never finishes is dropped after 45 minutes, like the timer.

## Analytics (private)
https://claude.ai/artifact/TjpvQ6RGKb3upULt9SBGP2 shows team totals for the Wharton report and
college applications: runs, companies screened, sources re-opened, decisions and time to decide,
Check now waits, visits and feature use. Only people with Editor access to that page can read
the numbers. It updates at the end of each run. **Download one-page summary** gives an HTML file
you can open and print to PDF; **Download weekly CSV** gives the raw weekly counts.
The team page counts visits, tabs and feature use per person-week so people aren't double
counted, keeps only the last 8 weeks, and never collects IPs, locations or typed text. Anyone can
opt out on its Methodology tab. Tell the team before relying on the numbers.

## How to change a rule (no code)
Edit `config/rules.yaml`, save, then run the screen again.

| To change | Edit this key |
|---|---|
| Look-back window for Black findings (7 years) | `black.lookback_years` |
| Clause (c) revenue-share threshold (10%) | `black_business_line.threshold_pct` |
| Minimum market cap ($5B) | `aligned.financial_gate.min_market_cap_usd` |
| Maximum debt/equity (1.5) | `aligned.financial_gate.max_debt_to_equity` |
| ETF exposure flag (2% of portfolio) | `etf_lookthrough.flag_threshold_pct_of_portfolio` |
| Per-$ amount shown when no ETF weights | `etf_lookthrough.per_amount_fallback_usd` |
| Max discovery proposals per run (10) | `discovery.max_proposals_per_run` |
| First-run look-back for agency/court discovery (45 days) | `discovery.legal_first_run_lookback_days` |
| Theme search phrases | `aligned.themes.<theme>.discovery_phrases` |
| Companies never listed without a finding | `do_not_list_without_finding` |
| Which websites count as Tier 1 / Tier 2 / banned | `sources.tier1_domains`, `tier2_domains`, `banned_domains` |

The starting lists from September 2026 are in `config/baseline.yaml`. They are only the "from"
state for the first proposals.

## How to add a source
1. Add the domain to `sources.tier1_domains` (primary: courts, agencies, SEC) or
   `sources.tier2_domains` (news: leads only) in `config/rules.yaml`.
2. If it should be scanned automatically each run, add a function to `pipeline/discovery.py`
   that returns `{source, date, title, url, text}` items (see `eeoc_since`), and call it from
   `legal_candidates`. Be polite: `pipeline/http.py` handles caching, rate limits, robots.txt and
   one retry.
3. Run `python -m pytest -q` (and `python -m pytest -m slow` for the end-to-end check).

## How evidence works
Each finding lives in `evidence/*.yaml` with the source URL, date, and a verbatim quote of 50
words or fewer. Every run re-opens every source and checks the quote is still there. A record
with no verified Tier-1 source becomes a lead and cannot be proposed.

## What the tool cannot do yet (known limits)
- **Market cap** uses SEC's public float, which excludes insider shares and is dated to the last
  10-K cover (up to ~15 months old). For filers without a float (e.g. TRI, a 40-F filer), it
  multiplies SEC shares outstanding by the price implied in a Vanguard fund's N-PORT filing; for
  TRI the share count is from Dec 2021, which is stale.
- **ETF holdings**: only State Street (SPDR) daily files can be read by script. iShares requires
  sign-in, and Vanguard, Invesco and Schwab block scripted access, so those funds use their
  latest SEC N-PORT filing (lags ~60–90 days). The as-of date is always shown.
- **State agencies**: calcivilrights.ca.gov refuses scripted access, so the CRD v. Tesla trial
  status is read from Tesla's own 10-Q.
- **Open rule questions** for the team:
  1. An EEOC "reasonable cause" determination is not treated as an "agency finding" until the team
     decides (affects TSLA and F).
  2. Clause (a) says "knowingly", but the rule's own example (summary judgment on falsity) does
     not decide knowledge. Fox and Newsmax are proposed on falsity findings; the label says so.
- **Rule change 2026-10-04 (Leo)**: clause (b) now covers race, ethnicity, sexual orientation and gender
  identity; new clause (c) (>= `black_business_line.threshold_pct`% of latest-FY revenue from immigration
  detention, per the company's own 10-K; undisclosed = "unknown" -> Watch). GEO and CXW were added to the
  universe by the screen. Not added (decided): civilian firearms makers, social-media platforms as a
  category, China/Taiwan-politics screens, generic ESG screens. `python -m pipeline.run --full-recheck`
  re-scans the whole look-back after a rule change.
- **Financial gaps**: when XBRL has no capex tag, free cash flow is "unknown"; when it has no debt
  tag, debt/equity is "unknown" unless `evidence/financial-notes.yaml` holds a verified quote from
  the company's filing (NYT, SHOP).

## Files
```
config/rules.yaml      thresholds, themes, source tiers (edit me)
config/baseline.yaml   September 2026 starting lists
evidence/*.yaml        evidence records (quotes, dates, clauses)
pipeline/              fetchers, rule engine, financial gate, look-through, run, db sync, alerts, run progress
site/page.html         the page template; build with python -m pipeline.build_page
site/parser.js         paste-box parser (runs in the page; tested with pytest via node)
site/lookthrough.js    ETF look-through math (runs in the page; tested with pytest via node)
site/runbar.js         run progress bar model and drawing (runs in the page; tests/runbar.test.js)
tests/                 pytest suite
QA_LOG.md              grading rounds
```
