"""Unit tests for the JSON cache layer (idempotency, trimming, I/O roundtrip)."""
from __future__ import annotations

import json

import pytest

from src import config, state_manager


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """Redirect cache paths to a temp dir so tests never touch real data/."""
    highs = tmp_path / "historical_highs.json"
    stats = tmp_path / "market_stats_history.json"
    monkeypatch.setattr(config, "HISTORICAL_HIGHS_PATH", str(highs))
    monkeypatch.setattr(config, "MARKET_STATS_HISTORY_PATH", str(stats))
    return highs, stats


def _append(stats, d, **kw):
    base = dict(up_limit=0, down_limit=0, advancing=0, declining=1,
               margin_balance=1, twii_close=1)
    base.update(kw)
    return state_manager.append_market_stats(stats, trade_date=d, **base)


def test_append_new_date_grows():
    stats = state_manager._empty_stats()
    _append(stats, "2026-06-01", up_limit=5)
    _append(stats, "2026-06-02", up_limit=6)
    assert stats["dates"] == ["2026-06-01", "2026-06-02"]
    assert stats["up_limit"] == [5, 6]


def test_append_same_last_date_is_idempotent():
    stats = state_manager._empty_stats()
    _append(stats, "2026-06-01", up_limit=5)
    _append(stats, "2026-06-01", up_limit=99)  # rerun same day
    assert stats["dates"] == ["2026-06-01"]
    assert stats["up_limit"] == [99]


def test_append_existing_out_of_order_overwrites_in_place():
    stats = state_manager._empty_stats()
    _append(stats, "2026-06-01", up_limit=5)
    _append(stats, "2026-06-02", up_limit=6)
    _append(stats, "2026-06-01", up_limit=50)  # touch an earlier row
    assert stats["dates"] == ["2026-06-01", "2026-06-02"]
    assert stats["up_limit"] == [50, 6]


def test_max_len_trims_oldest():
    stats = state_manager._empty_stats()
    for i in range(5):
        _append(stats, f"2026-06-0{i + 1}", up_limit=i, max_len=3)
    assert stats["dates"] == ["2026-06-03", "2026-06-04", "2026-06-05"]
    assert stats["up_limit"] == [2, 3, 4]


def test_stats_roundtrip(tmp_paths):
    stats = state_manager._empty_stats()
    _append(stats, "2026-06-01", up_limit=7)
    state_manager.save_market_stats(stats)
    loaded = state_manager.load_market_stats()
    assert loaded["dates"] == ["2026-06-01"] and loaded["up_limit"] == [7]


def test_load_missing_stats_returns_empty(tmp_paths):
    loaded = state_manager.load_market_stats()
    assert loaded["dates"] == [] and "margin_balance" in loaded


def test_load_empty_file_returns_empty(tmp_paths):
    _, stats_path = tmp_paths
    stats_path.write_text("")
    assert state_manager.load_market_stats()["dates"] == []


def test_highs_roundtrip(tmp_paths):
    state_manager.save_historical_highs({"2330.TW": 800.0})
    assert state_manager.load_historical_highs() == {"2330.TW": 800.0}


def test_load_missing_highs_returns_empty(tmp_paths):
    assert state_manager.load_historical_highs() == {}


def test_saved_json_is_utf8_readable(tmp_paths):
    highs_path, _ = tmp_paths
    state_manager.save_historical_highs({"2330.TW": 800.0})
    assert json.loads(highs_path.read_text(encoding="utf-8"))["2330.TW"] == 800.0


def test_load_stats_backfills_missing_keys(tmp_paths):
    _, stats_path = tmp_paths
    stats_path.write_text(json.dumps({"dates": ["2026-06-01"], "up_limit": [3]}))
    loaded = state_manager.load_market_stats()
    # Older/partial caches must gain the rest of the expected series.
    for key in ("down_limit", "advancing", "declining", "margin_balance", "twii_close"):
        assert key in loaded
