# Laura Screen runbook

Laura Screen keeps three lists of US stocks current for the Wharton GYIC Laura Gao case:
**Black** (exclude), **Watch** (serious open issue, with a tripwire) and **Aligned** (passes the
financial screen and has a documented link to Laura's values). It also checks ETFs for
look-through exposure to Black-list stocks. The page is here:
https://claude.ai/artifact/8uEh8baXjRBYo7BYLL4SHr

**Claude proposes, humans decide.** Nothing is on a list until a teammate approves it on the page.
This screen is the team's assumption about Laura's wishes. It is a research aid, not investment advice.

## How to run it
1. Open Claude Code in this folder (`laura-screen/`).
2. Say: **run the Laura screen**.
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
- **Scheduled run.** The Scheduled run card turns the automatic run on or off and sets how often
  (every 1–7 days), the weekday (7-day schedule only), time and time zone. Every 1–6 days fires
  daily and the run skips itself until the interval has passed since the last run. Alerts can be
  as late as the interval.
- Both controls drive a Claude Code Remote Routine (`trig_01Qe7LfvthehDzsLRq1WmLGZ`) owned by Leo's
  account, so only Leo can press them; other editors see the state. The settings live in the
  database (`settings/weekly`).

## How to change a rule (no code)
Edit `config/rules.yaml`, save, then run the screen again.

| To change | Edit this key |
|---|---|
| Look-back window for Black findings (7 years) | `black.lookback_years` |
| Minimum market cap ($5B) | `aligned.financial_gate.min_market_cap_usd` |
| Maximum debt/equity (1.5) | `aligned.financial_gate.max_debt_to_equity` |
| ETF exposure flag (0.5% of portfolio) | `etf_lookthrough.flag_threshold_pct_of_portfolio` |
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
- **Financial gaps**: when XBRL has no capex tag, free cash flow is "unknown"; when it has no debt
  tag, debt/equity is "unknown" unless `evidence/financial-notes.yaml` holds a verified quote from
  the company's filing (NYT, SHOP).

## Files
```
config/rules.yaml      thresholds, themes, source tiers (edit me)
config/baseline.yaml   September 2026 starting lists
evidence/*.yaml        evidence records (quotes, dates, clauses)
pipeline/              fetchers, rule engine, financial gate, look-through, run, db sync, alerts
site/page.html         the page template; build with python -m pipeline.build_page
site/parser.js         paste-box parser (runs in the page; tested with pytest via node)
site/lookthrough.js    ETF look-through math (runs in the page; tested with pytest via node)
tests/                 pytest suite
QA_LOG.md              grading rounds
```
