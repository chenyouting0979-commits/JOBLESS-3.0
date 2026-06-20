"""Read/update the JSON caches in data/.

Two caches:
- historical_highs.json   -> { "2330.TW": 800.0, ... }
- market_stats_history.json -> parallel arrays keyed by trading date.

The market-stats cache is kept as column arrays (dates/up_limit/...) so it maps
directly onto pandas Series for the 20-day trend calculations in criteria.py.
"""
from __future__ import annotations

import json
import os

from . import config

# Keys tracked in the rolling market-stats history.
_STATS_SERIES = (
    "up_limit",
    "down_limit",
    "advancing",
    "declining",
    "margin_balance",
    "twii_close",
)


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #
def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
    if not content:
        return default
    return json.loads(content)


def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


# --------------------------------------------------------------------------- #
# Historical highs cache
# --------------------------------------------------------------------------- #
def load_historical_highs() -> dict[str, float]:
    return _load_json(config.HISTORICAL_HIGHS_PATH, {})


def save_historical_highs(highs: dict[str, float]) -> None:
    _save_json(config.HISTORICAL_HIGHS_PATH, highs)


# --------------------------------------------------------------------------- #
# Market-stats rolling history cache
# --------------------------------------------------------------------------- #
def _empty_stats() -> dict[str, list]:
    return {"dates": [], **{k: [] for k in _STATS_SERIES}}


def load_market_stats() -> dict[str, list]:
    data = _load_json(config.MARKET_STATS_HISTORY_PATH, None)
    if not data:
        return _empty_stats()
    # Ensure every expected key exists (forward-compatible with older caches).
    data.setdefault("dates", [])
    for key in _STATS_SERIES:
        data.setdefault(key, [])
    return data


def save_market_stats(stats: dict[str, list]) -> None:
    _save_json(config.MARKET_STATS_HISTORY_PATH, stats)


def append_market_stats(
    stats: dict[str, list],
    *,
    trade_date: str,
    up_limit: float,
    down_limit: float,
    advancing: float,
    declining: float,
    margin_balance: float,
    twii_close: float,
    max_len: int | None = None,
) -> dict[str, list]:
    """Append one trading day's stats, idempotently (re-running same date overwrites).

    If ``max_len`` is given, older rows beyond that window are trimmed.
    Returns the mutated stats dict for convenience.
    """
    row = {
        "up_limit": up_limit,
        "down_limit": down_limit,
        "advancing": advancing,
        "declining": declining,
        "margin_balance": margin_balance,
        "twii_close": twii_close,
    }

    if stats["dates"] and stats["dates"][-1] == trade_date:
        # Same trading day already recorded -> overwrite the last row.
        for key, value in row.items():
            stats[key][-1] = value
    elif trade_date in stats["dates"]:
        # Out-of-order duplicate (shouldn't normally happen) -> overwrite in place.
        idx = stats["dates"].index(trade_date)
        for key, value in row.items():
            stats[key][idx] = value
    else:
        stats["dates"].append(trade_date)
        for key, value in row.items():
            stats[key].append(value)

    if max_len is not None and len(stats["dates"]) > max_len:
        trim = len(stats["dates"]) - max_len
        stats["dates"] = stats["dates"][trim:]
        for key in _STATS_SERIES:
            stats[key] = stats[key][trim:]

    return stats
