"""OpenRouter current-key budget collector.

API reference: https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key

Ported from github.com/viganogabriele/agent-usage-plus (MIT). Adapted to read
the key from ~/.hermes/.env and to surface the Hermes-mapped models.
"""

from __future__ import annotations

from typing import Any

from .common import (
    auth_missing,
    base_record,
    classify_failure,
    find_key,
    get_json,
    number,
    print_record,
)

ENDPOINT = "https://openrouter.ai/api/v1/auth/key"
CREDITS_ENDPOINT = "https://openrouter.ai/api/v1/credits"
AUTH_HELP = (
    "OpenRouter key not found. Add OPENROUTER_API_KEY to ~/.hermes/.env "
    "(chmod 600) or export it, then re-run the collector."
)

# Models the Hermes config routes through OpenRouter (from config.yaml).
# Unified here so the panel can show what actually bills to this key.
ROUTED_MODELS = [
    "deepseek/deepseek-v4-flash-0731",
    "z-ai/glm-5.2",
    "qwen/qwen3.7-flash",
    "xiaomi/mimo-v2.5",
    "inclusionai/ling-3.0-flash",
    "tencent/hy3",  # active provider/model per current session
]


def record_from_payload(auth_payload: dict[str, Any], credits_payload: dict[str, Any] | None) -> dict[str, Any]:
    record = base_record("openrouter", "OpenRouter", "OpenRouter API key")
    data = auth_payload.get("data") if isinstance(auth_payload.get("data"), dict) else auth_payload

    # Real account balance comes from /credits, NOT /auth/key. The key's
    # `limit`/`limit_remaining` only describe the per-key spending cap, which
    # is smaller than the actual wallet. The user's true available credit is
    # total_credits - total_usage.
    if isinstance(credits_payload, dict):
        c = credits_payload.get("data") if isinstance(credits_payload.get("data"), dict) else credits_payload
        total_credits = number(c.get("total_credits"))
        total_usage = number(c.get("total_usage"))
        if total_credits is not None:
            remaining = total_credits - total_usage if total_usage is not None else total_credits
            record["balance"] = {
                "remaining": remaining,
                "funded": total_credits,
                "spent": total_usage,
                "currency": "USD",
            }
            record["tierLabel"] = "OpenRouter account credit"
            record["ready"] = True
            # Pace/history breakdown comes from the key payload (per-period usage).
            record["recentDays"] = [
                {"label": "daily", "spentUsd": number(data.get("usage_daily"))},
                {"label": "weekly", "spentUsd": number(data.get("usage_weekly"))},
                {"label": "monthly", "spentUsd": number(data.get("usage_monthly"))},
            ]
            from .common import attach_models, attach_model_usage

            attach_models(record, ROUTED_MODELS)
            attach_model_usage(record)
            return record

    # Fallback: if /credits is unavailable, show the per-key limit.
    limit = number(data.get("limit"))
    remaining = number(data.get("limit_remaining"))
    reset = data.get("limit_reset")
    period_spend = None
    if reset == "daily":
        period_spend = number(data.get("usage_daily"))
    elif reset == "weekly":
        period_spend = number(data.get("usage_weekly"))
    elif reset == "monthly":
        period_spend = number(data.get("usage_monthly"))
    if period_spend is None and limit is not None and remaining is not None:
        period_spend = (limit - remaining) if limit >= remaining else None
    if limit is not None and remaining is not None:
        balance = {"remaining": remaining, "funded": limit, "currency": "USD"}
        if period_spend is not None:
            balance["spent"] = period_spend
        record["balance"] = balance
        if isinstance(reset, str) and reset in {"daily", "weekly", "monthly"}:
            record["tierLabel"] = f"OpenRouter API key · {reset} budget"
    else:
        record["tierLabel"] = "OpenRouter API key · no key budget"
    record["ready"] = True
    from .common import attach_models, attach_model_usage

    attach_models(record, ROUTED_MODELS)
    attach_model_usage(record)
    return record


def collect() -> dict[str, Any]:
    record = base_record("openrouter", "OpenRouter", "OpenRouter API key")
    key = find_key("OPENROUTER_API_KEY")
    if not key:
        return auth_missing(record, AUTH_HELP)
    try:
        auth = get_json(ENDPOINT, key)
        try:
            credits = get_json(CREDITS_ENDPOINT, key)
        except Exception:
            credits = None
        return record_from_payload(auth, credits)
    except Exception as exc:  # noqa: BLE001 - converted to a display record, never leaked
        return classify_failure(record, "OpenRouter", exc, AUTH_HELP)


if __name__ == "__main__":
    print_record(collect())
