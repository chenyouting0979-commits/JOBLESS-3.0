"""Business logic for the 7 Market Thermometer criteria.

Each criterion is a pure function returning a :class:`CriterionResult`. They take
already-fetched data plus (where needed) the rolling stats history, so this module
performs no I/O and is trivially unit-testable.

Convention: criteria 2/3/4/6 expect the stats dict to ALREADY include today's row
(main.py appends today before evaluating), so "trailing window" means the last N
entries of each series.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config


@dataclass
class CriterionResult:
    key: str                 # stable id, e.g. "c1_bias"
    name: str                # Traditional Chinese label
    value: float | None      # primary numeric reading (None if unavailable)
    triggered: bool          # should the notifier highlight it?
    detail: str              # human-readable one-liner


# --------------------------------------------------------------------------- #
# Small numeric helpers
# --------------------------------------------------------------------------- #
def _slope(series: list[float]) -> float:
    """Least-squares slope of ``series`` against its index (0..n-1)."""
    n = len(series)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    y = np.asarray(series, dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def _tail(series: list, n: int) -> list:
    return series[-n:] if n > 0 else list(series)


def _pct_change(first: float, last: float) -> float:
    if first == 0:
        return 0.0
    return (last - first) / abs(first) * 100.0


# --------------------------------------------------------------------------- #
# Criterion 1 — Weighted Index 60MA bias
# --------------------------------------------------------------------------- #
def weighted_index_60ma_bias(twii_history: pd.DataFrame) -> CriterionResult:
    key, name = "c1_bias", "加權指數與60MA乖離率"
    closes = twii_history["Close"].dropna()
    if len(closes) < config.MA_60_PERIOD:
        return CriterionResult(key, name, None, False,
                               f"資料不足（需 {config.MA_60_PERIOD} 日，僅 {len(closes)} 日）")

    ma60 = closes.rolling(config.MA_60_PERIOD).mean().iloc[-1]
    close = float(closes.iloc[-1])
    bias = (close - ma60) / ma60 * 100.0
    triggered = abs(bias) >= config.BIAS_ALERT
    stance = "過熱" if bias > 0 else "過冷"
    return CriterionResult(
        key, name, round(bias, 2), triggered,
        f"收盤 {close:,.0f} / 60MA {ma60:,.0f}，乖離 {bias:+.2f}%"
        + (f"（{stance}）" if triggered else ""),
    )


# --------------------------------------------------------------------------- #
# Criteria 2 & 3 — Up/Down-limit count spike vs trailing window
# --------------------------------------------------------------------------- #
def _limit_trend(series: list[float], key: str, name: str, label: str) -> CriterionResult:
    window = _tail(series, config.MA_20_PERIOD)
    if len(window) < 2:
        return CriterionResult(key, name, None, False, "資料不足")

    current = float(window[-1])
    mean = float(np.mean(window))
    std = float(np.std(window))
    slope = _slope(window)
    threshold = mean + config.SPIKE_STD * std
    triggered = std > 0 and current > 0 and current >= threshold
    return CriterionResult(
        key, name, current, triggered,
        f"今日 {label} {current:.0f} 家，{len(window)}日均 {mean:.1f}、"
        f"斜率 {slope:+.2f}" + ("（異常放大）" if triggered else ""),
    )


def up_limit_trend(stats: dict[str, list]) -> CriterionResult:
    return _limit_trend(stats.get("up_limit", []), "c2_up_limit",
                        "20日漲停家數趨勢", "漲停")


def down_limit_trend(stats: dict[str, list]) -> CriterionResult:
    return _limit_trend(stats.get("down_limit", []), "c3_down_limit",
                        "20日跌停家數趨勢", "跌停")


# --------------------------------------------------------------------------- #
# Criterion 4 — Advancing/Declining ratio trend
# --------------------------------------------------------------------------- #
def ad_ratio_trend(stats: dict[str, list]) -> CriterionResult:
    key, name = "c4_ad_ratio", "20日漲跌家數比趨勢"
    adv = _tail(stats.get("advancing", []), config.MA_20_PERIOD)
    dec = _tail(stats.get("declining", []), config.MA_20_PERIOD)
    if not adv or not dec:
        return CriterionResult(key, name, None, False, "資料不足")

    ratios = [a / d if d else 0.0 for a, d in zip(adv, dec)]
    current = ratios[-1]
    slope = _slope(ratios)
    triggered = current >= config.AD_HIGH or (0 < current <= config.AD_LOW)
    bias_word = "普漲" if current >= config.AD_HIGH else ("普跌" if triggered else "")
    return CriterionResult(
        key, name, round(current, 2), triggered,
        f"今日漲/跌 = {adv[-1]:.0f}/{dec[-1]:.0f} = {current:.2f}，"
        f"斜率 {slope:+.3f}" + (f"（{bias_word}）" if bias_word else ""),
    )


# --------------------------------------------------------------------------- #
# Criterion 5 — Watchlist new highs (mutates a copy of historical_highs)
# --------------------------------------------------------------------------- #
def watchlist_new_highs(
    today_highs: dict[str, float],
    historical_highs: dict[str, float],
) -> tuple[CriterionResult, dict[str, float]]:
    key, name = "c5_new_highs", "Watchlist創新高家數"
    updated = dict(historical_highs)
    new_high_tickers: list[str] = []

    for ticker, today_high in today_highs.items():
        record = updated.get(ticker)
        if record is None or today_high > record:
            if record is not None and today_high > record:
                new_high_tickers.append(ticker)
            updated[ticker] = max(today_high, record or today_high)

    count = len(new_high_tickers)
    triggered = count >= 1
    listed = "、".join(t.replace(".TW", "") for t in new_high_tickers)
    detail = (f"{count} 檔創新高：{listed}" if triggered
              else f"觀察 {len(today_highs)} 檔，無創新高")
    return CriterionResult(key, name, float(count), triggered, detail), updated


# --------------------------------------------------------------------------- #
# Criterion 6 — Margin% / Index% growth ratio (capped)
# --------------------------------------------------------------------------- #
def margin_index_growth_ratio(stats: dict[str, list]) -> CriterionResult:
    key, name = "c6_margin_ratio", "融資增減比÷指數增減比"
    margin = _tail(stats.get("margin_balance", []), config.MARGIN_PERIOD)
    twii = _tail(stats.get("twii_close", []), config.MARGIN_PERIOD)
    if len(margin) < 2 or len(twii) < 2:
        return CriterionResult(key, name, None, False, "資料不足")

    margin_pct = _pct_change(margin[0], margin[-1])
    index_pct = _pct_change(twii[0], twii[-1])
    if index_pct == 0:
        return CriterionResult(key, name, None, False, "指數變動為 0，無法計算")

    ratio = margin_pct / index_pct
    cap = config.MARGIN_RATIO_CAP
    ratio = max(-cap, min(cap, ratio))
    triggered = abs(ratio) >= config.MARGIN_RATIO_ALERT
    return CriterionResult(
        key, name, round(ratio, 2), triggered,
        f"融資 {margin_pct:+.2f}% / 指數 {index_pct:+.2f}% = {ratio:+.2f}"
        + ("（資金過熱/背離）" if triggered else ""),
    )


# --------------------------------------------------------------------------- #
# Criterion 7 — Index single-day amplitude anomaly
# --------------------------------------------------------------------------- #
def index_amplitude_anomaly(twii_latest: dict[str, float]) -> CriterionResult:
    key, name = "c7_amplitude", "大盤單日震幅異常"
    high = twii_latest["high"]
    low = twii_latest["low"]
    close = twii_latest["close"]

    upper_wick = (high - close) / close if close else 0.0   # 上影
    lower_wick = (close - low) / low if low else 0.0         # 下影
    swing = max(upper_wick, lower_wick)
    triggered = swing >= config.AMPLITUDE_THRESHOLD

    which = "上影線" if upper_wick >= lower_wick else "下影線"
    return CriterionResult(
        key, name, round(swing * 100, 2), triggered,
        f"最大{which}振幅 {swing * 100:.2f}%（高 {high:,.0f}/低 {low:,.0f}/收 {close:,.0f}）"
        + ("（異常）" if triggered else ""),
    )


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def evaluate_all(
    *,
    twii_history: pd.DataFrame,
    twii_latest: dict[str, float],
    stats: dict[str, list],
    today_highs: dict[str, float],
    historical_highs: dict[str, float],
) -> tuple[list[CriterionResult], dict[str, float]]:
    """Run all 7 criteria. Returns (results, updated_historical_highs)."""
    c5, updated_highs = watchlist_new_highs(today_highs, historical_highs)
    results = [
        weighted_index_60ma_bias(twii_history),
        up_limit_trend(stats),
        down_limit_trend(stats),
        ad_ratio_trend(stats),
        c5,
        margin_index_growth_ratio(stats),
        index_amplitude_anomaly(twii_latest),
    ]
    return results, updated_highs
