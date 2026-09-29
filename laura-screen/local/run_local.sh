#!/bin/bash
# Runs the Laura screen locally with the Claude Code CLI. Started at login by launchd (see README.md).
# Skips itself if it already ran within the last 20 hours, and waits for internet.
set -u
REPO="${LAURA_REPO:-$HOME/CredCheck}"
BRANCH="claude/intelligent-cerf-ejxxrq"
STAMP="$HOME/.laura_screen_last_run"
LOG="$HOME/Library/Logs/laura-screen.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "=== $(date -u +%FT%TZ) start"

if [ -f "$STAMP" ] && [ $(( $(date +%s) - $(stat -f %m "$STAMP") )) -lt 72000 ]; then
  echo "ran less than 20h ago, skipping"; exit 0
fi
for i in $(seq 1 30); do curl -sfI https://www.sec.gov >/dev/null && break; sleep 10; done

cd "$REPO" || { echo "repo not found at $REPO"; exit 1; }
git checkout "$BRANCH" && git pull --ff-only || { echo "git failed"; exit 1; }
cd laura-screen
[ -f config/local.yaml ] || { echo "config/local.yaml missing (needs sec_contact_email)"; exit 1; }

claude -p "$(cat local/prompt.txt)" --permission-mode acceptEdits \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebFetch,Artifact,ArtifactData" \
  && touch "$STAMP"
echo "=== $(date -u +%FT%TZ) done"
