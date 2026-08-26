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
#   5. Detect any provider that is not yet configured and print setup steps
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

# 5. Detect unconfigured providers and print setup steps
echo
echo "==> Checking provider configuration..."
python3 - "$INSTALL_DIR" <<'PY'
import sys, os, json, glob
base = sys.argv[1]
usage_dir = os.path.expanduser("~/.local/state/agent-usage-mac/usage")
records = []
for p in sorted(glob.glob(os.path.join(usage_dir, "*.json"))):
    try:
        records.append(json.load(open(p, encoding="utf-8")))
    except Exception:
        pass

# Which providers we know how to guide. Keys are the provider ids used by the
# plugin (PROVIDER_ORDER). Each entry: (display title, multi-line setup steps).
GUIDE = {
    "openrouter": (
        "OpenRouter",
        "1) Get a key: https://openrouter.ai/keys\n"
        "2) Add it to ~/.hermes/.env (chmod 600):\n"
        "     OPENROUTER_API_KEY=sk-or-...\n"
        "   or export it in your shell profile. Then re-run:\n"
        "     python3 ~/agent-usage-mac/bin/agent-usage-collectors update --write"
    ),
    "codex": (
        "Codex / OpenAI (ChatGPT login)",
        "1) Install the Codex CLI:  npm install -g @openai/codex\n"
        "2) Log in (opens a browser with your OpenAI account):  codex login\n"
        "   The panel then shows login state + a turn-count proxy.\n"
        "   (A paid OpenAI API key also works: set OPENAI_API_KEY in env.)"
    ),
    "openai": (
        "OpenAI (API key)",
        "1) Get a key: https://platform.openai.com/api-keys\n"
        "2) Add to ~/.hermes/.env or shell profile:\n"
        "     OPENAI_API_KEY=sk-...\n"
        "   Then re-run the collectors."
    ),
    "anthropic": (
        "Anthropic (Claude)",
        "1) Get a key: https://console.anthropic.com/settings/keys\n"
        "2) Add to ~/.hermes/.env or shell profile:\n"
        "     ANTHROPIC_API_KEY=sk-ant-...\n"
        "   Then re-run the collectors."
    ),
    "deepseek": (
        "DeepSeek",
        "1) Get a key: https://platform.deepseek.com/api_keys\n"
        "2) Add to ~/.hermes/.env or shell profile:\n"
        "     DEEPSEEK_API_KEY=sk-...\n"
        "   Then re-run the collectors."
    ),
    "gemini": (
        "Google Gemini",
        "1) Get a key: https://aistudio.google.com/apikey\n"
        "2) Add to ~/.hermes/.env or shell profile:\n"
        "     GEMINI_API_KEY=...  (or GOOGLE_API_KEY)\n"
        "   Then re-run the collectors."
    ),
    "xai": (
        "xAI (Grok)",
        "1) Get a key: https://console.x.ai/\n"
        "2) Add to ~/.hermes/.env or shell profile:\n"
        "     XAI_API_KEY=xai-...\n"
        "   Then re-run the collectors."
    ),
    "zai": (
        "Z.ai (GLM)",
        "1) Get a key: https://z.ai/api\n"
        "2) Add to ~/.hermes/.env or shell profile:\n"
        "     ZAI_API_KEY=...\n"
        "   Then re-run the collectors."
    ),
}

unconfigured = []
for r in records:
    if r.get("error") == "no_key" or (not r.get("ready") and r.get("error") == "no_key"):
        unconfigured.append(r.get("provider"))

if not unconfigured:
    print("    All detected providers are configured. Nothing to do.")
else:
    print("    The following providers are NOT configured yet:")
    for prov in unconfigured:
        title, steps = GUIDE.get(prov, (prov, "See the project README for setup."))
        print()
        print(f"    ### {title}")
        print("    " + steps.replace("\n", "\n    "))
    print()
    print("    After setting up a key, the LaunchAgent refreshes every 5 min,")
    print("    or refresh now from the menu (Refresh now) / run the collectors.")
PY

echo
echo "==> Done. Restart SwiftBar (or it will pick up the plugin on next refresh)."
echo "    Menu bar: click the icon -> 'Open Dashboard' for the full panel."
