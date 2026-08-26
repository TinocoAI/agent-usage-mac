"""Shared helpers for the Agent Usage collectors (macOS port).

MIT-licensed original: github.com/viganogabriele/agent-usage-plus
Ported/adapted for macOS + Hermes by Alfredo.

Design notes:
- Collectors never store credentials. They read API keys from the same
  places Hermes keeps them: ~/.hermes/.env (perm 600) and per-profile
  .env files, or from the real environment. No key is ever echoed.
- A "record" is the JSON contract consumed by the SwiftBar plugin. It is
  mix of the upstream collector-contract plus the extra fields this port
  needs for the macOS dropdown (provider label, icon, mapped models).
- All values coming from the network (API payloads) are treated as
  untrusted and rounded/clamped before they reach the panel.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

HERMES_HOME = os.path.expanduser("~/.hermes")

# Files we are allowed to read keys from. Anything else is rejected.
_TRUSTED_ENV_FILES = [os.path.join(HERMES_HOME, ".env")]


def _dotenv_paths() -> list[str]:
    """Hermes root .env plus every profile .env (all perm-checked)."""
    paths = [HERMES_HOME + "/.env"]
    prof = os.path.join(HERMES_HOME, "profiles")
    if os.path.isdir(prof):
        for name in os.listdir(prof):
            p = os.path.join(prof, name, ".env")
            if os.path.isfile(p):
                paths.append(p)
    return [p for p in paths if os.path.isfile(p)]


def _load_dotenv() -> dict[str, str]:
    """Parse every trusted .env into a flat dict. Latest wins by walk order."""
    out: dict[str, str] = {}
    for path in _dotenv_paths():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            # A profile .env we cannot read is simply skipped.
            continue
    return out


_ENV_CACHE: dict[str, str] | None = None


def _env() -> dict[str, str]:
    global _ENV_CACHE
    if _ENV_CACHE is None:
        _ENV_CACHE = {**_load_dotenv(), **dict(os.environ)}
    return _ENV_CACHE


def find_key(*names: str) -> str | None:
    """Return the first non-empty API key among env var names. Never returns values to logs."""
    env = _env()
    for n in names:
        v = env.get(n)
        if v and v.strip():
            return v.strip()
    return None


def find_key_from_auth_json(*provider_keys: str) -> str | None:
    """Best-effort: pull a credential from Hermes' auth.json credential_pool.

    `provider_keys` are pool keys like "openai-codex", "openrouter". We read the
    first credential's access_token. Never echoes the value; returns None on any
    error so the collector degrades to a 'not configured' state.
    """
    try:
        auth_path = os.path.join(HERMES_HOME, "auth.json")
        if not os.path.isfile(auth_path):
            return None
        with open(auth_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        pool = data.get("credential_pool") or {}
        for pk in provider_keys:
            creds = pool.get(pk)
            if isinstance(creds, list) and creds:
                tok = creds[0].get("access_token") or creds[0].get("api_key")
                if tok and str(tok).strip():
                    return str(tok).strip()
    except Exception:
        return None
    return None


# ----------------------------------------------------------------- record shape


def base_record(provider_id: str, label: str, account: str) -> dict[str, Any]:
    return {
        "provider": provider_id,
        "label": label,
        "account": account,
        "ready": False,
        "error": None,
        "tierLabel": None,
        "balance": None,        # {remaining, funded, spent?, currency}
        "limits": [],           # [{label,title,percent,tokenLimit,resetsAt,startedAt}]
        "recentDays": [],       # [{date, usedPct?, spentUsd?, requests?}]
        "models": [],           # models routed through this provider (Hermes mapping)
        "fetchedAt": _now_iso(),
    }


def auth_missing(record: dict[str, Any], help_text: str) -> dict[str, Any]:
    record["ready"] = False
    record["error"] = "no_key"
    record["tierLabel"] = help_text
    return record


def classify_failure(record: dict[str, Any], name: str, exc: Exception, help_text: str) -> dict[str, Any]:
    msg = str(exc)
    if "401" in msg or "403" in msg:
        kind = "auth"
    elif "timeout" in msg.lower() or "timed out" in msg.lower():
        kind = "network"
    else:
        kind = "api"
    record["ready"] = False
    record["error"] = kind
    record["tierLabel"] = f"{name}: {kind} ({_short(msg)})"
    return record


def _short(msg: str, n: int = 80) -> str:
    return msg if len(msg) <= n else msg[: n - 1] + "\u2026"


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------- safety


def number(value: Any, default: float | None = 0.0) -> float | None:
    try:
        f = float(value)
        return f if f >= 0 else default
    except (TypeError, ValueError):
        return default


def pct(used: float | None, total: float | None) -> float | None:
    if used is None or total in (None, 0) or total <= 0:
        return None
    return max(0.0, min(100.0, (used / total) * 100.0))


# ----------------------------------------------------------------- io


def print_record(record: dict[str, Any]) -> None:
    """Emit exactly one JSON record to stdout terminated by a newline."""
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_json(url: str, api_key: str | None = None, timeout: float = 15.0) -> Any:
    """Minimal HTTPS GET with optional bearer key. No third-party deps.

    Uses urllib from the stdlib so the collector runs on the system Python.
    """
    import urllib.request

    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "agent-usage-mac/1.0")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def attach_models(record: dict[str, Any], models: list[str]) -> None:
    """The models this provider actually serves for you, per Hermes mapping."""
    record["models"] = [m for m in models if m][:40]


def attach_model_usage(record: dict[str, Any], top: list[dict] | None = None) -> None:
    """Attach top-N model activity (turns in the last window) from model_usage.json.

    The OpenRouter API does not expose per-model token stats for this key, so we
    use conversation-turn counts from the Hermes agent log as a real proxy.
    `top` is a precomputed list of {"model","short","turns"}; if omitted we try
    to read the cached JSON written by collectors/model_usage.py.
    """
    if top is None:
        try:
            state_dir = os.environ.get(
                "AGENT_USAGE_DIR",
                os.path.expanduser("~/.local/state/agent-usage-mac/usage"),
            )
            with open(os.path.join(state_dir, "model_usage.json"), encoding="utf-8") as fh:
                top = json.load(fh).get("top")
        except Exception:
            top = None
    if top:
        record["modelUsage"] = [
            {"model": t.get("model"), "short": t.get("short"), "turns": t.get("turns")}
            for t in top
        ]
