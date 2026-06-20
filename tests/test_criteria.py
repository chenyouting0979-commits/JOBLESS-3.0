"""Unit tests for the 7 Market Thermometer criteria (pure logic, no I/O)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config, criteria, state_manager


def _twii_df(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Adj Close": closes,
            "Volume": [1] * len(closes),
        },
        index=idx,
    )


def _stats_from(**series) -> dict[str, list]:
    stats = state_manager._empty_stats()
    n = len(next(iter(series.values())))
    for i in range(n):
        state_manager.append_market_stats(
            stats,
            trade_date=f"2026-05-{i + 1:02d}",
            up_limit=series.get("up_limit", [0] * n)[i],
            down_limit=series.get("down_limit", [0] * n)[i],
            advancing=series.get("advancing", [0] * n)[i],
            declining=series.get("declining", [1] * n)[i],
            margin_balance=series.get("margin_balance", [1] * n)[i],
            twii_close=series.get("twii_close", [1] * n)[i],
        )
    return stats


# --- Criterion 1 -----------------------------------------------------------
def test_c1_triggers_when_overheated():
    df = _twii_df(list(np.linspace(13000, 18000, 80)))  # steep run-up
    r = criteria.weighted_index_60ma_bias(df)
    assert r.value > config.BIAS_ALERT
    assert r.triggered and "過熱" in r.detail


def test_c1_calm_when_flat():
    df = _twii_df([16000.0] * 80)
    r = criteria.weighted_index_60ma_bias(df)
    assert abs(r.value) < 0.01 and not r.triggered


def test_c1_insufficient_history():
    df = _twii_df([16000.0] * 30)
    r = criteria.weighted_index_60ma_bias(df)
    assert r.value is None and not r.triggered


# --- Criteria 2 / 3 --------------------------------------------------------
def test_c2_spike_triggers():
    stats = _stats_from(up_limit=[5] * 24 + [40])
    r = criteria.up_limit_trend(stats)
    assert r.triggered and r.value == 40


def test_c2_steady_no_trigger():
    stats = _stats_from(up_limit=[5] * 25)
    assert not criteria.up_limit_trend(stats).triggered


def test_c3_uses_down_limit():
    stats = _stats_from(down_limit=[1] * 24 + [30])
    assert criteria.down_limit_trend(stats).triggered


# --- Criterion 4 -----------------------------------------------------------
def test_c4_broad_rally():
    stats = _stats_from(advancing=[900] * 5, declining=[80] * 5)
    r = criteria.ad_ratio_trend(stats)
    assert r.triggered and "普漲" in r.detail


def test_c4_broad_selloff():
    stats = _stats_from(advancing=[80] * 5, declining=[900] * 5)
    r = criteria.ad_ratio_trend(stats)
    assert r.triggered and "普跌" in r.detail


def test_c4_balanced_no_trigger():
    stats = _stats_from(advancing=[500] * 5, declining=[480] * 5)
    assert not criteria.ad_ratio_trend(stats).triggered


# --- Criterion 5 -----------------------------------------------------------
def test_c5_detects_new_high_and_updates():
    res, updated = criteria.watchlist_new_highs(
        {"2330.TW": 850.0}, {"2330.TW": 800.0}
    )
    assert res.triggered and res.value == 1.0
    assert updated["2330.TW"] == 850.0


def test_c5_no_new_high_keeps_record():
    res, updated = criteria.watchlist_new_highs(
        {"2330.TW": 790.0}, {"2330.TW": 800.0}
    )
    assert not res.triggered and updated["2330.TW"] == 800.0


def test_c5_unknown_ticker_is_recorded_not_flagged():
    # First time we see a ticker, set its record but don't call it a "new high".
    res, updated = criteria.watchlist_new_highs({"9999.TW": 100.0}, {})
    assert not res.triggered and updated["9999.TW"] == 100.0


# --- Criterion 6 -----------------------------------------------------------
def test_c6_divergence_triggers():
    # margin +20% vs index +5% -> ratio 4.0
    stats = _stats_from(margin_balance=[100, 120], twii_close=[100, 105])
    r = criteria.margin_index_growth_ratio(stats)
    assert r.triggered and r.value > config.MARGIN_RATIO_ALERT


def test_c6_caps_extreme_ratio():
    stats = _stats_from(margin_balance=[100, 200], twii_close=[100, 100.001])
    r = criteria.margin_index_growth_ratio(stats)
    assert abs(r.value) <= config.MARGIN_RATIO_CAP


def test_c6_zero_index_change_unavailable():
    stats = _stats_from(margin_balance=[100, 120], twii_close=[100, 100])
    r = criteria.margin_index_growth_ratio(stats)
    assert r.value is None and not r.triggered


# --- Criterion 7 -----------------------------------------------------------
def test_c7_upper_wick_anomaly():
    r = criteria.index_amplitude_anomaly({"high": 16800, "low": 16200, "close": 16250})
    assert r.triggered and "上影線" in r.detail


def test_c7_normal_day_no_trigger():
    r = criteria.index_amplitude_anomaly({"high": 16100, "low": 15950, "close": 16050})
    assert not r.triggered


# --- Orchestrator ----------------------------------------------------------
def test_evaluate_all_returns_seven():
    df = _twii_df(list(np.linspace(15000, 18000, 80)))
    stats = _stats_from(up_limit=[5] * 25)
    results, updated = criteria.evaluate_all(
        twii_history=df,
        twii_latest={"high": 18100, "low": 17900, "close": 18000},
        stats=stats,
        today_highs={"2330.TW": 850.0},
        historical_highs={"2330.TW": 800.0},
    )
    assert len(results) == 7
    assert updated["2330.TW"] == 850.0
