#!/usr/bin/env bash
#
# Agent Usage Mac — one-line installer.
# Usage:  bash -c "$(curl -fsSL https://raw.githubusercontent.com/TinocoAI/agent-usage-mac/main/install.sh)"
#
# What it does:
#   1. Clone (or update) this repo into ~/agent-usage-mac
#   2. Copy the SwiftBar plugin bundle into the SwiftBar Plugins folder
#   3. Install + load a LaunchAgent that refreshes data every 5 minutes
#   4. Run the collectors once so the menu shows data immediately
#
# Requires: SwiftBar (https://swiftbar.app) and Python 3 (preinstalled on macOS).

set -euo pipefail

REPO_URL="${AGENT_USAGE_REPO_URL:-https://github.com/TinocoAI/agent-usage-mac.git}"
INSTALL_DIR="${AGENT_USAGE_INSTALL_DIR:-$HOME/agent-usage-mac}"
PLUGINS_DIR="${SWIFTBAR_PLUGINS_DIR:-$HOME/Documents/SwiftBar}"
PLUGIN_NAME="Agent Usage.1m.swiftbar"
LAUNCH_LABEL="com.hermes.agent-usage-collectors"
LAUNCH_PLIST="$HOME/Library/LaunchAgents/$LAUNCH_LABEL.plist"

echo "==> Agent Usage Mac installer"

# 1. Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "==> Updating existing install at $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "==> Cloning $REPO_URL into $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

# 2. SwiftBar plugin
echo "==> Installing SwiftBar plugin into $PLUGINS_DIR"
mkdir -p "$PLUGINS_DIR"
rm -rf "$PLUGINS_DIR/$PLUGIN_NAME"
# ditto handles spaces in the bundle name reliably (cp -R is buggy on macOS here)
ditto "$INSTALL_DIR/swiftbar/$PLUGIN_NAME" "$PLUGINS_DIR/$PLUGIN_NAME"
chmod +x "$PLUGINS_DIR/$PLUGIN_NAME/plugin.sh"

# 3. LaunchAgent
echo "==> Installing LaunchAgent ($LAUNCH_LABEL)"
# Rewrite the plist paths to this user's HOME so it works on any Mac.
python3 - "$INSTALL_DIR/com.hermes.agent-usage-collectors.plist" "$LAUNCH_PLIST" <<'PY'
import sys, plistlib, os
src, dst = sys.argv[1], sys.argv[2]
with open(src, "rb") as f:
    plist = plistlib.load(f)
args = plist.get("ProgramArguments", [])
args = [os.path.expanduser(a) if a.startswith("/Users/") else a for a in args]
plist["ProgramArguments"] = args
errp = plist.get("StandardErrorPath")
if errp:
    plist["StandardErrorPath"] = os.path.expanduser(errp)
with open(dst, "wb") as f:
    plistlib.dump(plist, f)
print("    wrote", dst)
PY

if launchctl list | grep -q "$LAUNCH_LABEL"; then
  launchctl unload "$LAUNCH_PLIST" 2>/dev/null || true
fi
launchctl load "$LAUNCH_PLIST"

# 4. First collection
echo "==> Running collectors (first refresh)"
python3 "$INSTALL_DIR/bin/agent-usage-collectors" update --write || \
  echo "    (collectors reported an issue; check provider credentials)"

echo
echo "==> Done. Restart SwiftBar (or it will pick up the plugin on next refresh)."
echo "    Menu bar: click the icon -> 'Open Dashboard' for the full panel."
