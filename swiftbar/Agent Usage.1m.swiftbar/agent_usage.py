#!/usr/bin/env python3
# <xbar.title>Agent Usage Mac</xbar.title>
# <xbar.version>2.0</xbar.version>
# <xbar.author>Alfredo (port of agent-usage-plus, MIT)</xbar.author>
# <xbar.desc>OpenRouter / Codex / other LLM usage, balances and pace from your Hermes setup, in an Omarchy-style dark panel.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>

"""SwiftBar plugin (HTML render) for Agent Usage Mac.

Reads JSON records produced by `agent-usage-collectors update --write`
(LaunchAgent, every 5 min) from AGENT_USAGE_DIR. Renders an Omarchy-style
dark panel via inline HTML/CSS. Lazily refreshes a stale/missing record.
"""

from __future__ import annotations

import json
import os
import sys
import time

USAGE_DIR = os.environ.get(
    "AGENT_USAGE_DIR",
    os.path.expanduser("~/.local/state/agent-usage-mac/usage"),
)
COLLECTORS_BIN = os.path.expanduser("~/agent-usage-mac/bin/agent-usage-collectors")
STALE_SECS = int(os.environ.get("AGENT_USAGE_STALE", "360"))
WARN_PCT = 75.0
CRIT_PCT = 90.0

# providers we expect (order = display order). Others auto-discovered too.
PROVIDER_ORDER = ["openrouter", "codex", "openai", "anthropic", "deepseek", "gemini", "xai", "zai"]
PROVIDER_META = {
    "openrouter": ("OpenRouter", "#63B3ED", "OR"),
    "codex": ("Codex", "#A0AEC0", "CX"),
    "openai": ("OpenAI", "#10A37F", "AI"),
    "anthropic": ("Claude", "#D97757", "CL"),
    "deepseek": ("DeepSeek", "#4D6BFE", "DS"),
    "gemini": ("Gemini", "#A78BFA", "GM"),
    "xai": ("Grok", "#C7CBD1", "GK"),
    "zai": ("GLM", "#7DD3FC", "GL"),
}

ICON = "\U0001F916"


# ---------------------------------------------------------------- helpers

def _read_record(name: str):
    p = os.path.join(USAGE_DIR, f"{name}.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _is_stale(rec) -> bool:
    if not rec:
        return True
    fa = rec.get("fetchedAt")
    if not fa:
        return True
    try:
        then = time.mktime(time.strptime(fa, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return True
    return (time.time() - then) > STALE_SECS


def _refresh(name):
    import subprocess

    try:
        subprocess.run([sys.executable, COLLECTORS_BIN, name, "--write"],
                        capture_output=True, timeout=20)
    except Exception:
        return None
    return _read_record(name)


def pct_of(rec) -> float | None:
    b = rec.get("balance")
    if not isinstance(b, dict):
        return None
    funded = b.get("funded")
    spent = b.get("spent")
    if funded in (None, 0) or spent is None:
        return None
    return max(0.0, min(100.0, (spent / funded) * 100.0))


def usd(v) -> str:
    try:
        return f"${float(v):.2f}"
    except Exception:
        return "\u2014"


def color_for(pct) -> str:
    if pct is None:
        return "#A0AEC0"
    if pct >= CRIT_PCT:
        return "#ED64A6"
    if pct >= WARN_PCT:
        return "#F6AD55"
    return "#63B3ED"


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------- HTML panel

def _provider_card(rec) -> str:
    pid = rec.get("provider", "?")
    name, accent, badge = PROVIDER_META.get(pid, (rec.get("label", pid), "#63B3ED", pid[:2].upper()))
    p = pct_of(rec)
    col = color_for(p)
    ready = rec.get("ready")
    b = rec.get("balance") or {}

    if ready and p is not None:
        bar_pct = max(2, min(100, int(p)))
        header_line = f"{usd(b.get('remaining'))} available"
        meter = f"""
        <div class="meter"><div class="meter-fill" style="width:{bar_pct}%;background:{col}"></div></div>
        <div class="meter-row"><span>{bar_pct}% of credit used</span><span>{usd(b.get('funded'))} total</span></div>
        """
        extra = ""
        rd = rec.get("recentDays") or []
        if rd:
            rows = "".join(
                f"<div class='kv'><span>{esc(d.get('label','?').title() if hasattr(d.get('label'),'title') else d.get('label','?'))}</span><span>{usd(d.get('spentUsd'))}</span></div>"
                for d in rd
            )
            extra += f"<div class='sub'>Usage this period</div>{rows}"
        models = rec.get("models") or []
        if models:
            chips = "".join(f"<span class='chip'>{esc(m)}</span>" for m in models[:6])
            extra += f"<div class='sub'>Routed models</div><div class='chips'>{chips}</div>"
    else:
        # ready but no balance/pct — show the honest state plus any real
        # quota data we collected (e.g. Codex 5h/weekly usage via app-server).
        msg = rec.get("tierLabel") or rec.get("error") or "not ready"
        header_line = "active"
        note = f"<div class='note'>{esc(msg)}</div>"
        # Codex live quota (real numbers from the Codex app-server)
        quota = rec.get("codexQuota") or {}
        quota_rows = ""
        if quota:
            for kind, label in (("fiveHour", "5h window"), ("weekly", "weekly")):
                w = quota.get(kind) or {}
                pct = w.get("usedPercent")
                if isinstance(pct, (int, float)):
                    avail = 100 - pct
                    pct_txt = f"{avail:.0f}% free"
                    bar = max(0, min(100, int(avail)))
                else:
                    pct_txt = "n/a"
                    bar = 0
                quota_rows += (
                    f"<div class='kv'><span>{label}</span><span>{pct_txt}</span></div>"
                    f"<div class=\"meter\"><div class=\"meter-fill\" style=\"width:{bar}%;background:#68D391\"></div></div>"
                )
        meter = note
        if quota_rows:
            meter += f"<div class='sub'>Quota (real)</div>{quota_rows}"
        extra = ""

    return f"""
    <div class="card">
      <div class="card-head">
        <span class="badge" style="background:{accent}">{esc(badge)}</span>
        <span class="pname">{esc(name)}</span>
        <span class="pval">{header_line}</span>
      </div>
      {meter}
      {extra}
    </div>
    """


def _read_model_usage():
    p = os.path.join(USAGE_DIR, "model_usage.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _model_usage_card(mu) -> str:
    if not mu or not mu.get("top"):
        return ""
    win = mu.get("windowDays", 7)
    rows = ""
    max_turns = max((t.get("turns") or 0) for t in mu["top"]) or 1
    for t in mu["top"]:
        short = esc(t.get("short") or t.get("model", "?"))
        turns = t.get("turns") or 0
        bar_pct = max(2, min(100, int(turns / max_turns * 100)))
        rows += f"""
        <div class='kv'><span>{short}</span><span>{turns:,} turns</span></div>
        <div class="meter" style="margin:1px 0 8px"><div class="meter-fill" style="width:{bar_pct}%;background:#63B3ED"></div></div>
        """
    return f"""
    <div class="card">
      <div class="card-head">
        <span class="badge" style="background:#63B3ED">#</span>
        <span class="pname">Top models</span>
        <span class="pval">last {win}d</span>
      </div>
      <div class='sub'>By activity (turns) - real from logs</div>
      {rows}
    </div>
    """


def render_html(records) -> str:
    cards = "".join(_provider_card(r) for r in records)
    mu = _read_model_usage()
    if mu and mu.get("top"):
        cards += _model_usage_card(mu)
    ts = max((r.get("fetchedAt", "") for r in records if r.get("fetchedAt")), default="")
    refresh_btn = (
        f'<a href="swiftbar://refreshPlugin?'
        f"plugin=Agent%20Usage.1m.swiftbar"
        f'&amp;terminal=false">Refresh now</a>'
    )
    import re
    html = f"""
    <html>
    <head><style>
      body {{ margin:0; padding:14px; background:#0F111A; color:#F7FAFC;
             font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text',system-ui,sans-serif; }}
      .title {{ font-size:13px; font-weight:700; letter-spacing:.5px; color:#F7FAFC; margin-bottom:2px; }}
      .title .dim {{ color:#63B3ED; font-weight:600; }}
      .sub {{ font-size:10px; text-transform:uppercase; letter-spacing:1px; color:#A0AEC0; margin:10px 0 4px; }}
      .card {{ background:#1E2130; border:1px solid #2D3748; border-radius:12px; padding:12px; margin-bottom:10px; }}
      .card-head {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
      .badge {{ width:22px; height:22px; border-radius:6px; display:inline-flex; align-items:center;
               justify-content:center; font-size:9px; font-weight:700; color:#0F111A; }}
      .pname {{ font-size:12px; font-weight:600; }}
      .pval {{ margin-left:auto; font-size:12px; font-weight:700; color:#F7FAFC; font-variant-numeric:tabular-nums; }}
      .meter {{ height:6px; background:#2D3748; border-radius:3px; overflow:hidden; }}
      .meter-fill {{ height:100%; border-radius:3px; }}
      .meter-row {{ display:flex; justify-content:space-between; font-size:10px; color:#A0AEC0; margin-top:4px; }}
      .kv {{ display:flex; justify-content:space-between; font-size:11px; color:#CBD5E0; padding:1px 0;
             font-variant-numeric:tabular-nums; }}
      .chip {{ display:inline-block; background:#2D3040; color:#A0AEC0; font-size:9px; padding:2px 6px;
              border-radius:5px; margin:2px 3px 0 0; }}
      .note {{ font-size:10px; color:#F6AD55; line-height:1.4; }}
      .chips {{ margin-top:2px; }}
      .foot {{ display:flex; justify-content:space-between; align-items:center; margin-top:6px;
              font-size:10px; color:#718096; }}
      .foot a {{ color:#63B3ED; text-decoration:none; }}
    </style></head>
    <body>
      <div class="title"><span class="dim">&#129302;</span> Agent Usage <span class="dim">Mac</span></div>
      {cards}
      <div class="foot"><span>Updated {esc(ts)}</span>{refresh_btn}</div>
    </body>
    </html>
    """
    # SwiftBar only renders HTML when the output line has NO newline in it.
    return re.sub(r"\s+", " ", html).strip()


def _write_panel(records) -> str | None:
    """Persist the full HTML panel to disk; return its file:// URL."""
    import tempfile

    path = os.path.join(tempfile.gettempdir(), "agent-usage-mac-panel.html")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_html(records))
        return "file://" + path
    except Exception:
        return None


def main() -> None:
    records = []
    seen = set()
    # ordered known providers first
    for name in PROVIDER_ORDER:
        rec = _read_record(name)
        if _is_stale(rec):
            rec = _refresh(name)
        if rec:
            records.append(rec)
            seen.add(name)
    # plus any other records on disk
    import glob

    for p in sorted(glob.glob(os.path.join(USAGE_DIR, "*.json"))):
        n = os.path.basename(p)[:-5]
        if n not in seen:
            rec = _read_record(n)
            if rec and not _is_stale(rec):
                records.append(rec)

    if not records:
        print(f"{ICON} no data")
        print("---")
        print("Agent Usage Mac")
        print("No provider records yet. Run the collectors.")
        return

    # menubar: headline = highest-used ready provider
    # Clicking the menubar icon opens the dashboard webview directly.
    panel_url = _write_panel(records)
    ready = [r for r in records if r.get("ready") and pct_of(r) is not None]
    if ready:
        head = max(ready, key=lambda r: pct_of(r))
        hp = pct_of(head)
        menubar = f"{ICON} {usd(head['balance'].get('remaining'))} {int(hp)}%"
    else:
        menubar = f"{ICON} set up"
    if panel_url:
        print(f"{menubar} | webview=true href={panel_url} webvieww=360 webviewh=540")
    else:
        print(menubar)

    print("---")

    # dropdown: simple text fallback (BitBar inline markup only)
    for rec in records:
        label = rec.get("label", rec.get("provider", "?"))
        p = pct_of(rec)
        if rec.get("ready") and p is not None:
            b = rec.get("balance", {})
            print(f"{label} | color=#63B3ED")
            print(f"  {usd(b.get('remaining'))} left | {int(p)}% used | {usd(b.get('funded'))} total")
            tl = rec.get("tierLabel")
            if tl:
                print(f"  plan: {tl} | color=#A0AEC0")
            models = rec.get("models") or []
            if models:
                print(f"  models: {', '.join(models[:4])} | color=#A0AEC0")
        else:
            msg = rec.get("tierLabel") or rec.get("error") or "not ready"
            print(f"{label} | color=#718096")
            print(f"  {msg} | color=#718096")
            quota = rec.get("codexQuota") or {}
            if quota:
                for kind, lbl in (("fiveHour", "5h"), ("weekly", "weekly")):
                    w = quota.get(kind) or {}
                    pct = w.get("usedPercent")
                    if isinstance(pct, (int, float)):
                        print(f"  {lbl}: {100 - pct:.0f}% free | color=#A0AEC0")
            for d in (rec.get("recentDays") or []):
                if "turns" in d:
                    print(f"  {d.get('label', 'activity')}: {d.get('turns', 0):,} turns | color=#A0AEC0")
        print("---")

    # (3) top models (7d) — real turn counts from the Hermes log
    mu = _read_model_usage()
    if mu and mu.get("top"):
        print(f"Top models (last {mu.get('windowDays', 7)}d) | color=#63B3ED")
        for t in mu["top"]:
            short = t.get("short") or t.get("model", "?")
            print(f"  {short}: {t.get('turns', 0):,} turns | color=#A0AEC0")
        print("---")

    ts = max((r.get("fetchedAt", "") for r in records if r.get("fetchedAt")), default="")
    if ts:
        print(f"Updated {ts} | color=#666666")

    # refresh action (valid swiftbar:// URL, opens nothing visible)
    print("Refresh now | href=swiftbar://refreshplugin?plugin=Agent%20Usage.1m.swiftbar&terminal=false")


if __name__ == "__main__":
    main()
