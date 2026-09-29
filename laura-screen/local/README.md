# Running the Laura screen locally (macOS)

Needs: git, Python 3 + `pip install requests pyyaml beautifulsoup4 openpyxl pypdf pytest`, `node`,
and the Claude Code CLI (`claude`), logged in with your claude.ai account (uses your plan's usage).

1. `git clone` this repo to `~/CredCheck` (or set `LAURA_REPO`).
2. Create `laura-screen/config/local.yaml` containing `sec_contact_email: you@example.com` (gitignored).
3. Run `claude` once inside the repo, so it is logged in and you can approve the Artifact tool. Check that
   it can read the Artifact database and, if you want alerts, that the Gmail connector is available.
4. Test: `bash laura-screen/local/run_local.sh`, then read `~/Library/Logs/laura-screen.log`.
5. Install: `cp laura-screen/local/com.laura-screen.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.laura-screen.plist`

It starts at login and re-checks every 6 hours while the Mac is on. The script skips if it ran in the last
20 hours, and the prompt itself skips unless the interval in `settings/weekly` has passed.
Disable the cloud schedule so the two don't both run.
