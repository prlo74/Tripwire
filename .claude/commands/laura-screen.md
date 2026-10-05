---
description: Run Tripwire locally (on-demand)
---
Run Tripwire now, in the laura-screen/ folder of this repo. This is an on-demand run: ignore the schedule switch and interval.
0. Read the db doc settings/weekly on https://claude.ai/artifact/8uEh8baXjRBYo7BYLL4SHr. If check_requested_at is newer than check_completed_at, tell me who/when asked (and which new tickers are waiting) and wait for my go. If there is no pending request, say so and ask whether to run anyway. Do nothing else until I say go.
1. `git pull`. If config/local.yaml is missing, ask me for the SEC contact email and create it (gitignored; never commit it). Install packages if needed: `pip install requests pyyaml beautifulsoup4 openpyxl pypdf pytest`.
2. Follow laura-screen/CLAUDE.md steps 1 to 6 exactly, including step 3b. If no Gmail connector is available, list the alerts in the summary instead of sending.
3. Update settings/weekly, pinned to its version: last_run_at, a one-line last_run_summary and check_completed_at (the current UTC time, as the last write of the run; pass `--requested-at` to `progress finish` if a request was pending).
4. Run `python -m pytest -q`, then commit and push run outputs and any new evidence records to the current branch.
Never label anything yourself; only propose. If a source is down, report it; never route around it.
