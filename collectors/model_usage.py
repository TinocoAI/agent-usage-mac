"""Extract the top-N most-used models from the Hermes agent log.

The OpenRouter API does not expose per-model token stats for this key
(endpoints return 404), and Hermes only logs token counts on API-error
lines. So we count conversation *turns* per model from the agent log,
which is a real, extractable proxy for model activity in the last window.

Output: JSON written to AGENT_USAGE_DIR/model_usage.json
{
  "windowDays": 7,
  "generatedAt": "...",
  "top": [ {"model": "tencent/hy3", "short": "hy3", "turns": 1087}, ... ]
}
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta

LOG_PATH = os.path.expanduser("~/.hermes/logs/agent.log")
STATE_DIR = os.environ.get(
    "AGENT_USAGE_DIR",
    os.path.expanduser("~/.local/state/agent-usage-mac/usage"),
)
OUT_PATH = os.path.join(STATE_DIR, "model_usage.json")
WINDOW_DAYS = int(os.environ.get("AGENT_USAGE_WINDOW", "7"))
TOP_N = int(os.environ.get("AGENT_USAGE_TOP", "5"))

TS_PAT = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")
MODEL_PAT = re.compile(r"model=([\w\-./:]+)")


def short_name(model: str) -> str:
    # tencent/hy3 -> hy3 ; deepseek/deepseek-v4-flash-0731 -> deepseek-v4-flash-0731
    return model.split("/", 1)[-1]


def collect(window_days: int = WINDOW_DAYS, top_n: int = TOP_N) -> dict:
    counts: Counter = Counter()
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        lines = []

    # "now" = most recent timestamp found in the log, else system now.
    now = None
    for ln in reversed(lines):
        m = TS_PAT.match(ln)
        if m:
            try:
                now = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
                break
            except Exception:
                pass
    if now is None:
        now = datetime.utcnow()
    cutoff = now - timedelta(days=window_days)

    for ln in lines:
        tm = TS_PAT.match(ln)
        if not tm:
            continue
        try:
            dt = datetime.strptime(f"{tm.group(1)} {tm.group(2)}", "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if dt < cutoff:
            continue
        mm = MODEL_PAT.search(ln)
        if not mm:
            continue
        counts[mm.group(1)] += 1

    top = [
        {"model": m, "short": short_name(m), "turns": c}
        for m, c in counts.most_common(top_n)
    ]
    return {
        "windowDays": window_days,
        "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "top": top,
    }


def main() -> None:
    rec = collect()
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2)
    if "--write" not in sys.argv:
        print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
