"""Codex collector — real quota via the Codex app-server JSON-RPC.

The Codex CLI exposes a local MCP-style server (`codex app-server --stdio`)
that answers `account/read` and `account/rateLimits/read`. The rate-limits
response carries `usedPercent` for the 5-hour and weekly windows — the same
data the herdr-agent-quota Rust plugin reads. We replicate that here in Python
so the menu bar can show real Codex consumption, not a fabricated number.

If the app-server is unavailable (not logged in, not installed) we fall back to
the honest "logged in (no live quota)" state using the local auth.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any

from .common import auth_missing, base_record, find_key, find_key_from_auth_json, print_record

CODEX_BIN = os.environ.get("CODEX_BIN_PATH", "codex")
REQUEST_TIMEOUT = 20.0

FIVE_HOUR_MINS = 5 * 60
WEEKLY_MINS = 7 * 24 * 60


# ---------------------------------------------------------------- transport
def _notify(method: str, params: dict | None = None) -> None:
    """Send a JSON-RPC notification (no id, no response expected)."""
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    proc.stdin.flush()


def _rpc(client_id: int, method: str, params: dict | None = None) -> dict:
    """Send one JSON-RPC 2.0 request and return the matching response."""
    msg = {"jsonrpc": "2.0", "id": client_id, "method": method, "params": params or {}}
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("codex app-server exited before responding")
        line = line.strip()
        if not line:
            continue
        try:
            resp = json.loads(line)
        except json.JSONDecodeError:
            continue
        if resp.get("id") != client_id:
            continue
        if "error" in resp:
            raise RuntimeError(f"codex RPC error: {resp['error']}")
        return resp


def _start_server() -> subprocess.Popen:
    return subprocess.Popen(
        [CODEX_BIN, "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )


# ---------------------------------------------------------------- parsing
def _window_kind(duration_mins: int) -> str | None:
    if duration_mins == FIVE_HOUR_MINS:
        return "fiveHour"
    if duration_mins == WEEKLY_MINS:
        return "weekly"
    return None


def _parse_rate_limits(value: dict) -> dict[str, Any]:
    result = value.get("result", value)
    limits = result.get("rateLimits") or result.get("rate_limits") or {}
    out: dict[str, Any] = {}
    for cand in (limits.get("primary"), limits.get("secondary")):
        if not isinstance(cand, dict):
            continue
        dur = cand.get("windowDurationMins") or cand.get("window_duration_mins")
        kind = _window_kind(int(dur)) if dur else None
        if not kind:
            continue
        used = cand.get("usedPercent") or cand.get("used_percent")
        # Codex omits usedPercent when the window has no usage yet -> treat as 0 used.
        if used is None:
            used = 0
        resets = cand.get("resetsAt") or cand.get("resets_at")
        out[kind] = {"usedPercent": used, "resetsAt": resets}
    if not out:
        raise RuntimeError("no supported rate-limit windows in codex response")
    return out


def _account_is_chatgpt(value: dict) -> bool:
    result = value.get("result", value)
    account = result.get("account", result)
    blob = " ".join(
        str(account.get(k, "")).lower()
        for k in ("authMode", "auth_mode", "type", "plan")
    )
    return "chatgpt" in blob


# ---------------------------------------------------------------- collector
proc: subprocess.Popen | None = None


def collect() -> dict[str, Any]:
    global proc
    record = base_record("codex", "Codex", "OpenAI / Codex")
    key = (
        find_key("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_AUTH_TOKEN")
        or find_key_from_auth_json("openai-codex")
    )
    if not key and not os.path.isfile(os.path.expanduser("~/.codex/auth.json")):
        record["ready"] = False
        record["error"] = "no_key"
        record["tierLabel"] = (
            "Codex not configured. Install: npm i -g @openai/codex && codex login"
        )
        return record

    # Try the live quota first.
    try:
        proc = _start_server()
        _rpc(1, "initialize", {
            "clientInfo": {"name": "agent-usage-collectors", "version": "1.0"},
            "capabilities": {},
        })
        _notify("initialized")
        account = _rpc(2, "account/read")
        if not _account_is_chatgpt(account):
            raise RuntimeError("Codex is using API-key auth, not a ChatGPT subscription")
        limits = _rpc(3, "account/rateLimits/read")
        quota = _parse_rate_limits(limits)
        record["ready"] = True
        record["tierLabel"] = "Codex (ChatGPT) quota"
        record["codexQuota"] = quota
        record["fetchedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # strip unused default fields
        for k in ("limits", "recentDays", "models"):
            record.pop(k, None)
        return record
    except Exception as exc:
        # Fall back to the honest local state (no live quota).
        acct = _codex_account_id()
        short = (acct or "unknown")[:8]
        turns = _codex_turns_last(7)
        record["ready"] = True
        record["tierLabel"] = f"Codex logged in - acct {short} (quota unavailable: {type(exc).__name__})"
        record["balance"] = None
        record["recentDays"] = [{"label": "codexTurns7d", "turns": turns}]
        return record
    finally:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
            proc = None


# ---------------------------------------------------------------- fallbacks
def _codex_account_id() -> str | None:
    p = os.path.expanduser("~/.codex/auth.json")
    try:
        d = json.load(open(p, encoding="utf-8"))
        return (d.get("tokens") or {}).get("account_id")
    except Exception:
        return None


def _codex_turns_last(days: int) -> int:
    log = os.path.expanduser("~/.hermes/logs/agent.log")
    if not os.path.isfile(log):
        return 0
    cutoff = time.time() - days * 86400
    try:
        with open(log, encoding="utf-8", errors="ignore") as fh:
            count = 0
            for line in fh:
                if "codex" not in line.lower() and "provider=openai" not in line:
                    continue
                # crude timestamp prefix YYYY-MM-DD
                if line[:10] < time.strftime("%Y-%m-%d", time.gmtime(cutoff)):
                    continue
                count += 1
            return count
    except Exception:
        return 0


if __name__ == "__main__":
    print_record(collect())
