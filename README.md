# Tripwire

A values screen for US stocks and ETFs, built by a high-school team for the
[Wharton Global Youth Investment Competition](https://globalyouth.wharton.upenn.edu/competitions/investment-competition/)
(2026, Laura Gao client case).

**Open the page:** https://prlo74.github.io/Tripwire/

Tripwire keeps three lists current from primary sources:

- **Black list (exclude):** a court, jury or agency made a qualifying finding within 7 years
  (knowingly false information to the public, or discrimination), or a company earns a set
  share of revenue from immigration detention per its own 10-K.
- **Watch list (monitor):** a serious open issue with no qualifying finding yet, such as a
  settlement without admission or a case past a motion to dismiss. Every entry has a tripwire.
- **Aligned list (include):** passes a financial screen (market cap, profit, free cash flow,
  debt/equity) and has a documented link to the client's values in the company's own filings.
- **No finding list (neutral):** team stocks checked in full with nothing qualifying found.
  It is not a clearance.

It also looks through ETFs to show how much of a portfolio sits in Black-list stocks.

## Try it

1. Open https://prlo74.github.io/Tripwire/. No claude.ai account is needed.
2. On **Home**, paste tickers or company names into **Paste tickers** (for example
   `AAPL, Microsoft, brk.b`), fix any flagged chips, and press **Request a check**.
3. GitHub opens with an issue titled `Check: AAPL, MSFT, BRK-B`. Submit it (a free GitHub account
   is needed). The issue starts a Claude Code run in the cloud right away.
4. In about 10 to 20 minutes the result shows under **Check requests** on the page. Each ticker is
   either a proposal (open **Needs approval** to see the quote and source), "Values link found, but
   fails the financial screen", or "No values link or qualifying legal finding found". If the run
   can post on GitHub, it also replies on the issue.

A request can hold up to 15 tickers. Visitors can't approve anything: a run only proposes, and a
team member decides on the team's private copy. Approved decisions appear here after the next run.

## How it works

**Claude proposes, humans decide.** Claude Code runs a Python pipeline that reads official
sources (SEC filings, DOJ, EEOC and FTC releases, court opinions), re-opens every source on
every run to check each quoted passage is still there, and applies the rules in
[`config/rules.yaml`](config/rules.yaml). It only *proposes* changes, each with a verbatim
quote of 50 words or fewer and a link to the primary source. Nothing is on a list until a team
member approves it on the page, and every decision is logged.

- How to run it and change the rules: [`RUNBOOK.md`](RUNBOOK.md)
- What Claude does on each run: [`CLAUDE.md`](CLAUDE.md)
- Evidence records: [`evidence/`](evidence/)
- Quality review rounds: [`QA_LOG.md`](QA_LOG.md)
- The cloud run: [`ROUTINE.md`](ROUTINE.md) and [`pipeline/issues.py`](pipeline/issues.py)
- Tests: `python -m pytest -q`

## Important

This is a research aid for a student competition, **not investment advice**. The lists are the
team's assumption about the client's wishes, applied to public records. A listing reflects the
rules in `config/rules.yaml` and the cited source, not an opinion about any company. If a
source is wrong or out of date, open an issue with the correction and a link.
