"""Codex / OpenAI usage collector.

Codex (openai-codex) bills through the OpenAI API. When an OPENAI_API_KEY (or
CODEX_API_KEY / CODEX_AUTH_TOKEN) is present we query the OpenAI usage endpoint;
otherwise we report a clear "not configured" state so the panel can show the
provider as mapped-but-unfunded rather than inventing numbers.

Ported framework from github.com/viganogabriele/agent-usage-plus (MIT).
"""

from __future__ import annotations

import json
from typing import Any

from .common import (
    auth_missing,
    base_record,
    classify_failure,
    find_key,
    find_key_from_auth_json,
    get_json,
    number,
    print_record,
)

# OpenAI usage endpoint (returns total_usage, total_tokens, etc.).
ENDPOINT = "https://api.openai.com/dashboard/billing/subscription"
USAGE_ENDPOINT = "https://api.openai.com/dashboard/billing/usage"
AUTH_HELP = (
    "Codex/OpenAI key not found. Set OPENAI_API_KEY (or CODEX_API_KEY) to "
    "enable Codex usage. It is mapped in Hermes but has no credential yet."
)


def record_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    record = base_record("codex", "Codex", "OpenAI / Codex")
    sub = payload.get("subscription") if isinstance(payload.get("subscription"), dict) else payload
    capped = sub.get("has_payment_method") if isinstance(sub.get("has_payment_method"), bool) else None
    # OpenAI subscription gives a soft limit; treat it as the funded amount.
    limit = number(sub.get("soft_limit") or sub.get("account_name") and None)
    # The subscription endpoint alone does not expose remaining; if we cannot
    # derive a balance we surface the account state and let the panel show it.
    if isinstance(capped, bool):
        record["tierLabel"] = "OpenAI account" + ("" if capped else " (no payment method)")
        record["ready"] = True
        record["balance"] = None
    else:
        record["tierLabel"] = "OpenAI account"
        record["ready"] = True
    return record


import os
import re
from collections import Counter

CODEX_AUTH = os.path.expanduser("~/.codex/auth.json")
LOG_PATH = os.path.expanduser("~/.hermes/logs/agent.log")


def _codex_token() -> str | None:
    """Read the Codex CLI OAuth token from its own auth.json (never echoed)."""
    try:
        with open(CODEX_AUTH, "r", encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return None
    if d.get("auth_mode") == "chatgpt" and isinstance(d.get("tokens"), dict):
        return d["tokens"].get("access_token") or d["tokens"].get("id_token")
    return d.get("OPENAI_API_KEY") or None


def _codex_account_id() -> str | None:
    try:
        with open(CODEX_AUTH, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d.get("tokens", {}).get("account_id")
    except Exception:
        return None


def _codex_turns_last(days: int = 7) -> int:
    """Count Codex/OpenAI conversation turns in the Hermes log (real proxy)."""
    import sys
    from datetime import datetime, timedelta

    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return 0
    ts_pat = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")
    prov_pat = re.compile(r"provider=(codex|openai)\b")
    now = None
    for ln in reversed(lines):
        m = ts_pat.match(ln)
        if m:
            try:
                now = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
                break
            except Exception:
                pass
    if now is None:
        now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    n = 0
    for ln in lines:
        tm = ts_pat.match(ln)
        if not tm:
            continue
        try:
            dt = datetime.strptime(f"{tm.group(1)} {tm.group(2)}", "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if dt < cutoff:
            continue
        if prov_pat.search(ln):
            n += 1
    return n


def collect() -> dict[str, Any]:
    record = base_record("codex", "Codex", "OpenAI / Codex")
    key = (
        find_key("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_AUTH_TOKEN")
        or _codex_token()
        or find_key_from_auth_json("openai-codex")
    )
    if not key:
        # Mapped in Hermes but no credential: honest "not configured" state.
        record["ready"] = False
        record["error"] = "no_key"
        record["tierLabel"] = AUTH_HELP
        return record
    # The Codex token authenticates (CLI works, /v1/me resolves) but OpenAI does
    # not expose per-account usage/billing through it (billing 401, codex usage
    # 404). So we show the real login state + a turn-count proxy, never fake $.
    acct = _codex_account_id()
    short = (acct or "unknown")[:8]
    turns = _codex_turns_last(7)
    record["ready"] = True
    record["tierLabel"] = f"Codex logged in - acct {short}"
    record["balance"] = None
    record["recentDays"] = [{"label": "codexTurns7d", "turns": turns}]
    return record


if __name__ == "__main__":
    print_record(collect())
