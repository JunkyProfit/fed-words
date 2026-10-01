#!/usr/bin/env bash
# Fetch new Fed Chair transcripts, rebuild index.html, and publish to GitHub Pages
# only if something actually changed. Safe to run on a schedule (e.g. weekly).
set -euo pipefail
cd "$(dirname "$0")"

git pull --ff-only --quiet          # stay in sync with GitHub; fails safely if histories diverged
python3 fetch.py
python3 build.py

if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -m "Add new transcript(s) $(date +%Y-%m-%d)"
  git push
  echo "Published. GitHub Pages updates in ~1-2 minutes."
else
  echo "No changes"
fi
