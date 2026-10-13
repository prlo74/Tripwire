# Tripwire

A values screen for US stocks and ETFs, built by a high-school team for the
[Wharton Global Youth Investment Competition](https://globalyouth.wharton.upenn.edu/competitions/investment-competition/)
(2026, Laura Gao client case).

**Open the live page:** https://claude.ai/artifact/8uEh8baXjRBYo7BYLL4SHr

Tripwire keeps three lists current from primary sources:

- **Black list (exclude):** a court, jury or agency made a qualifying finding within 7 years
  (knowingly false information to the public, or discrimination), or a company earns a set
  share of revenue from immigration detention per its own 10-K.
- **Watch list (monitor):** a serious open issue with no qualifying finding yet, such as a
  settlement without admission or a case past a motion to dismiss. Every entry has a tripwire.
- **Aligned list (include):** passes a financial screen (market cap, profit, free cash flow,
  debt/equity) and has a documented link to the client's values in the company's own filings.

It also looks through ETFs to show how much of a portfolio sits in Black-list stocks.

## How it works

**Claude proposes, humans decide.** Claude Code runs a Python pipeline that reads official
sources (SEC filings, DOJ, EEOC and FTC releases, court opinions), re-opens every source on
every run to check each quoted passage is still there, and applies the rules in
[`laura-screen/config/rules.yaml`](laura-screen/config/rules.yaml). It only *proposes* changes,
each with a verbatim quote of 50 words or fewer and a link to the primary source. Nothing is
on a list until a team member approves it on the page, and every decision is logged.

- How to run it and change the rules: [`laura-screen/RUNBOOK.md`](laura-screen/RUNBOOK.md)
- What Claude does on each run: [`laura-screen/CLAUDE.md`](laura-screen/CLAUDE.md)
- Evidence records: [`laura-screen/evidence/`](laura-screen/evidence/)
- Quality review rounds: [`laura-screen/QA_LOG.md`](laura-screen/QA_LOG.md)
- Tests: `cd laura-screen && python -m pytest -q`

## Important

This is a research aid for a student competition, **not investment advice**. The lists are the
team's assumption about the client's wishes, applied to public records. A listing reflects the
rules in `config/rules.yaml` and the cited source, not an opinion about any company. If a
source is wrong or out of date, open an issue with the correction and a link.
