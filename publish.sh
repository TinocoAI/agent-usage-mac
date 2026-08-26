#!/usr/bin/env bash
#
# Publish Agent Usage Mac to GitHub.
# Prereq: you already ran `gh auth login` (interactive, your account).
#
# Usage:  ./publish.sh <your-github-username>
#
set -euo pipefail

USER="${1:?Usage: ./publish.sh <your-github-username>}"
REPO="agent-usage-mac"
REMOTE="git@github.com:${USER}/${REPO}.git"

echo "==> Publishing to github.com/${USER}/${REPO}"

# 1. Replace the placeholder in README + install.sh
echo "==> Setting repo URL in docs"
sed -i '' "s|<YOUR_GH_USER>|${USER}|g" README.md install.sh
git add README.md install.sh
git commit -q -m "docs: set GitHub user to ${USER}" || echo "    (nothing to commit)"

# 2. Create the repo on GitHub (ignores if it already exists)
gh repo create "${REPO}" --public --description "SwiftBar plugin: LLM agent spend + Top-5 models in your macOS menu bar" 2>/dev/null \
  || echo "    (repo already exists or create skipped)"

# 3. Add remote + push
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE"
git branch -M main
git push -u origin main

echo
echo "==> Done: https://github.com/${USER}/${REPO}"
echo "    Others install with:"
echo "    bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/${USER}/${REPO}/main/install.sh)\""
