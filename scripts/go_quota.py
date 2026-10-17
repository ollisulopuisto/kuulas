#!/usr/bin/env python3
"""OpenCode Go spend against its dollar caps.

Reads opencode's own message records (read-only) and adds up the cost of the
`opencode-go` models over rolling windows. Caps are from opencode.ai/docs/go:
$12 per 5 hours, $30 per week, $60 per month. The costs are opencode's own
estimates from list prices, and the real windows may be calendar-based, so
treat the figures as a close estimate, not as the bill.

    go_quota.py          print the table; exit 0 ok, 1 warn (70%), 2 stop (90%)
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

DB = Path.home() / ".local/share/opencode/opencode.db"
HOUR_MS = 3_600_000
WINDOWS = {"5h": 5 * HOUR_MS, "7d": 7 * 24 * HOUR_MS, "30d": 30 * 24 * HOUR_MS}
CAPS = {"5h": 12.0, "7d": 30.0, "30d": 60.0}
WARN, STOP = 0.70, 0.90


def _go(rows: list[dict]):
    for r in rows:
        if r.get("providerID") != "opencode-go":
            continue
        cost = r.get("cost")
        created = (r.get("time") or {}).get("created")
        if isinstance(cost, (int, float)) and isinstance(created, (int, float)):
            yield r, float(cost), created


def spend(rows: list[dict], now_ms: int) -> dict[str, float]:
    """Total Go cost inside each rolling window ending at ``now_ms``."""
    total = dict.fromkeys(WINDOWS, 0.0)
    for _r, cost, created in _go(rows):
        for name, span in WINDOWS.items():
            if now_ms - span <= created <= now_ms:
                total[name] += cost
    return total


def by_model(rows: list[dict], now_ms: int) -> dict[str, float]:
    """Go cost per model inside the 5-hour window."""
    out: dict[str, float] = {}
    for r, cost, created in _go(rows):
        if now_ms - WINDOWS["5h"] <= created <= now_ms:
            out[r.get("modelID", "?")] = out.get(r.get("modelID", "?"), 0.0) + cost
    return out


def level(totals: dict[str, float]) -> str:
    worst = max(totals[name] / CAPS[name] for name in CAPS)
    return "stop" if worst >= STOP else "warn" if worst >= WARN else "ok"


def _load() -> list[dict]:
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = db.execute(
        "select data from message where data like '%opencode-go%'").fetchall()
    return [json.loads(r[0]) for r in rows]


def main() -> int:
    rows = _load()
    now = int(time.time() * 1000)
    totals = spend(rows, now)
    for name, cap in CAPS.items():
        print(f"{name:>3}: ${totals[name]:6.2f} of ${cap:.0f}  "
              f"({totals[name] / cap:4.0%})")
    for model, cost in sorted(by_model(rows, now).items(), key=lambda kv: -kv[1]):
        print(f"      {model}: ${cost:.2f} in the last 5 h")
    state = level(totals)
    print(state.upper())
    return {"ok": 0, "warn": 1, "stop": 2}[state]


if __name__ == "__main__":
    sys.exit(main())
