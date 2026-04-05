#!/usr/bin/env python3
"""Claude Code status line."""

import json
import sys
import time


# ── Formatting helpers ───────────────────────────────────────────────────────


def fmt_tokens(n):
    """Format token count: 999, 125k, 1.2M."""
    if n is None:
        return "--"
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        k = n / 1000
        return f"{k:.0f}k" if k >= 10 else f"{k:.1f}k"
    m = n / 1_000_000
    return f"{m:.0f}M" if m >= 10 else f"{m:.1f}M"


def fmt_countdown(epoch):
    """Convert resets_at unix epoch to human countdown: 3h12m, 2d05h, 45m."""
    if epoch is None:
        return "--"
    remaining = epoch - time.time()
    if remaining <= 0:
        return "0m"
    total_min = int(remaining / 60)
    if total_min < 60:
        return f"{total_min}m"
    hours = total_min // 60
    mins = total_min % 60
    if hours < 24:
        return f"{hours}h{mins:02d}m"
    days = hours // 24
    hrs = hours % 24
    return f"{days}d{hrs:02d}h"


# ── ANSI helpers ────────────────────────────────────────────────────────────

BOLD = "\033[1m"
RST = "\033[0m"
BAR_BG = "\033[48;2;60;56;54m"  # gruvbox dark bg for bar track
BLOCKS = " ▏▎▍▌▋▊▉█"  # index 0=empty … 8=full


def bold(text):
    return f"{BOLD}{text}{RST}"


def progress_bar(pct, width=10):
    """Render fixed-width progress bar using Unicode block elements ▏▎▍▌▋▊▉█."""
    if pct is None:
        return f"{BAR_BG}{' ' * width}{RST}"
    pct = max(0, min(100, pct))
    eighths = round(pct / 100 * width * 8)
    full = eighths // 8
    frac = eighths % 8
    bar = "█" * full
    if frac and full < width:
        bar += BLOCKS[frac]
    return f"{BAR_BG}{bar.ljust(width)}{RST}"


# ── Data extraction ──────────────────────────────────────────────────────────


def extract_cells(data):
    """Extract cells: cwd:session, context, 5h rate."""
    cells = []

    # CWD: session
    cwd = data.get("cwd", "")
    display_cwd = cwd.rsplit("/", 1)[-1] if cwd else "--"
    session_name = data.get("session_name")
    if not session_name:
        sid = data.get("session_id", "")
        session_name = sid[:8] if sid else "--"
    cells.append(f"{bold(display_cwd)}: {session_name}")

    # Context window
    ctx = data.get("context_window", {})
    ctx_pct = ctx.get("used_percentage")
    ctx_total = ctx.get("total_input_tokens")
    ctx_max = ctx.get("context_window_size")
    if ctx_pct is not None:
        val = f"{ctx_pct:.0f}% {progress_bar(ctx_pct)} {fmt_tokens(ctx_total)}/{fmt_tokens(ctx_max)}"
    else:
        val = f"-- {progress_bar(None)} --/--"
    cells.append(f"{bold('Context:')} {val}")

    # 5h rate limit
    bucket = data.get("rate_limits", {}).get("five_hour", {})
    pct = bucket.get("used_percentage")
    resets = bucket.get("resets_at")
    if pct is not None:
        val = f"{pct:.0f}% {progress_bar(pct)} {fmt_countdown(resets)}"
    else:
        val = f"-- {progress_bar(None)}"
    cells.append(f"{bold('5h Rate:')} {val}")

    return cells


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        data = {}

    print(" | ".join(extract_cells(data)))


if __name__ == "__main__":
    main()
