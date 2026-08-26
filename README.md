# Agent Usage Mac

A SwiftBar plugin that shows your LLM agent spend in the macOS menu bar:
OpenRouter balance, Codex/OpenAI activity, a Top-5 models leaderboard (by
real conversation-turn counts from your Hermes logs), and per-provider detail.

- Menu-bar click opens a dark dashboard (WebView).
- Dropdown shows a plain-text fallback summary.
- Collectors refresh every 5 minutes via a LaunchAgent.

> Honest-data note: OpenRouter shows real $ balance/usage. Codex/OpenAI (ChatGPT
> Plus / Apple-login accounts) does **not** expose a usage/credits API, so the
> panel shows login state + a turn-count proxy instead of invented dollar figures.

## Install (any Mac, one line)

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/<YOUR_GH_USER>/agent-usage-mac/main/install.sh)"
```

The installer will:
1. Clone this repo to `~/agent-usage-mac` (or update it if present).
2. Place the SwiftBar plugin bundle in your SwiftBar Plugins folder.
3. Create a LaunchAgent that runs the collectors every 5 minutes.
4. Tell you to point SwiftBar at the plugin (or restart SwiftBar).

Requires: **SwiftBar** (https://swiftbar.app — free) and **Python 3** (preinstalled on macOS).

## Manual install

```bash
git clone https://github.com/<YOUR_GH_USER>/agent-usage-mac.git ~/agent-usage-mac
cd ~/agent-usage-mac

# 1. SwiftBar plugin (copy the bundle to your SwiftBar Plugins dir)
#    In SwiftBar: Preferences -> Plugins Folder, or default ~/Documents/SwiftBar
mkdir -p ~/Documents/SwiftBar
cp -R swiftbar/Agent\ Usage.1m.swiftbar ~/Documents/SwiftBar/

# 2. LaunchAgent (refreshes data every 5 min)
cp com.hermes.agent-usage-collectors.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.hermes.agent-usage-collectors.plist

# 3. First run
python3 ~/agent-usage-mac/bin/agent-usage-collectors update --write

# 4. Restart SwiftBar
```

## Configuration

Collectors read credentials from the same places your tools already use:

| Provider   | Source                                                                 |
|------------|------------------------------------------------------------------------|
| OpenRouter | `OPENROUTER_API_KEY` in env or `~/.hermes/.env`                         |
| Codex      | `~/.codex/auth.json` (after `codex login`) or `OPENAI_API_KEY` in env   |

If a provider has no credential it shows a `not configured` / `no key` state —
never fake numbers.

### Where data lives

`~/.local/state/agent-usage-mac/usage/*.json` — generated records the plugin reads.
`~/.local/state/agent-usage-mac/usage/model_usage.json` — Top-5 models (turn counts from `~/.hermes/logs/agent.log`).

### Tuning (env vars)

| Variable              | Default | Meaning                                  |
|-----------------------|---------|------------------------------------------|
| `AGENT_USAGE_DIR`     | `~/.local/state/agent-usage-mac/usage` | Record output directory      |
| `AGENT_USAGE_STALE`   | `360`   | Seconds before a record is lazily refreshed |
| `AGENT_USAGE_WINDOW`  | `7`     | Days window for the Top-5 model leaderboard |
| `AGENT_USAGE_TOP`     | `5`     | How many models in the leaderboard        |

## How it works

- `bin/agent-usage-collectors` runs each collector and writes JSON records.
- `collectors/openrouter.py` — real balance from the OpenRouter API.
- `collectors/codex.py` — login state + turn-count proxy (no usage API exists).
- `collectors/model_usage.py` — scans `~/.hermes/logs/agent.log` for per-model turns.
- `swiftbar/Agent Usage.1m.swiftbar/` — the SwiftBar plugin (Python → HTML WebView + text dropdown).

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.hermes.agent-usage-collectors.plist
rm ~/Library/LaunchAgents/com.hermes.agent-usage-collectors.plist
rm -rf ~/Documents/SwiftBar/Agent\ Usage.1m.swiftbar
rm -rf ~/agent-usage-mac
```
