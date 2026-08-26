"""Generic "key-present" collectors for providers without a public usage API.

For these providers we can detect that a credential exists (so the panel shows
the provider as configured) but we do NOT fabricate balance/usage numbers —
OpenAI/Anthropic/DeepSeek/Gemini/xAI/Z.ai do not expose per-account spend
through a key-only endpoint we can rely on. So the record is honest:
ready=True when the key is present, with a tierLabel noting "key present".

Add a new provider by extending PROVIDERS below and registering it in
bin/agent-usage-collectors COLLECTORS.
"""

from __future__ import annotations

from typing import Any

from .common import auth_missing, base_record, find_key, print_record

# provider_id -> (display label, list of env var names that hold the key)
PROVIDERS = {
    "openai": ("OpenAI", ["OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_AUTH_TOKEN"]),
    "anthropic": ("Anthropic", ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"]),
    "deepseek": ("DeepSeek", ["DEEPSEEK_API_KEY"]),
    "gemini": ("Gemini", ["GEMINI_API_KEY", "GOOGLE_API_KEY"]),
    "xai": ("xAI", ["XAI_API_KEY"]),
    "zai": ("Z.ai", ["ZAI_API_KEY"]),
}


def make_collector(provider_id: str, label: str, env_names: list[str]):
    def collect() -> dict[str, Any]:
        record = base_record(provider_id, label, label)
        key = find_key(*env_names)
        if not key:
            record["ready"] = False
            record["error"] = "no_key"
            record["tierLabel"] = (
                f"{label} key not found. Set {' / '.join(env_names)} in env or ~/.hermes/.env."
            )
            return record
        record["ready"] = True
        record["tierLabel"] = f"{label} key present (no public usage API)"
        record["balance"] = None
        return record

    return collect


# Build and export one `collect` per provider at import time.
for _pid, (_label, _envs) in PROVIDERS.items():
    globals()[f"collect_{_pid}"] = make_collector(_pid, _label, _envs)


def collect() -> dict[str, Any]:
    """Default entrypoint (openai) so `agent-usage-collectors openai` works."""
    return collect_openai()


if __name__ == "__main__":
    print_record(collect())
