"""Orchestrator: load state -> fetch today -> evaluate -> update state -> notify.

Run from the repo root as a module:

    python -m src.main
"""
from __future__ import annotations

import pandas as pd

from . import config, criteria, notifier, state_manager
from .fetchers import twse_fetcher, yfinance_fetcher

# Keep a bit more than the longest analysis window so trends stay stable.
_STATS_MAX_LEN = max(config.MA_20_PERIOD, config.MARGIN_PERIOD) * 4


def _latest_bar(twii_history: pd.DataFrame) -> dict[str, float]:
    last = twii_history.iloc[-1]
    return {
        "date": twii_history.index[-1].strftime("%Y-%m-%d"),
        "open": float(last["Open"]),
        "high": float(last["High"]),
        "low": float(last["Low"]),
        "close": float(last["Close"]),
    }


def _fetch_today_highs() -> dict[str, float]:
    """Today's intraday high per watchlist ticker (skips any that fail)."""
    highs: dict[str, float] = {}
    for ticker in config.WATCHLIST:
        try:
            highs[ticker] = yfinance_fetcher.fetch_stock_latest_high(ticker)["high"]
        except Exception as exc:  # noqa: BLE001 — one bad ticker shouldn't abort
            print(f"[main] 略過 {ticker}：{exc}")
    return highs


def run() -> None:
    print("[main] 載入本地快取 …")
    historical_highs = state_manager.load_historical_highs()
    stats = state_manager.load_market_stats()

    # --- yfinance: required (^TWII) ---
    print("[main] 抓取 ^TWII 歷史資料 …")
    twii_history = yfinance_fetcher.fetch_twii_history(period="6mo")
    twii_latest = _latest_bar(twii_history)
    trade_date = twii_latest["date"]
    print(f"[main] 最新交易日：{trade_date}（收盤 {twii_latest['close']:,.0f}）")

    # --- TWSE: optional, degrade gracefully ---
    try:
        print("[main] 抓取 TWSE 市場寬度與融資餘額 …")
        breadth = twse_fetcher.fetch_market_breadth(trade_date)
        margin_balance = twse_fetcher.fetch_margin_balance(trade_date)
        state_manager.append_market_stats(
            stats,
            trade_date=trade_date,
            up_limit=breadth["up_limit"],
            down_limit=breadth["down_limit"],
            advancing=breadth["advancing"],
            declining=breadth["declining"],
            margin_balance=margin_balance,
            twii_close=twii_latest["close"],
            max_len=_STATS_MAX_LEN,
        )
        print(f"[main] TWSE 已寫入：{breadth}, 融資 {margin_balance:,.0f}")
    except Exception as exc:  # noqa: BLE001
        print(f"[main] ⚠️ TWSE 抓取失敗，C2/C3/C4/C6 將以既有歷史評估：{exc}")

    # --- yfinance: watchlist highs ---
    print("[main] 抓取 Watchlist 當日高點 …")
    today_highs = _fetch_today_highs()

    # --- Evaluate all 7 criteria ---
    print("[main] 評估 7 項指標 …")
    results, updated_highs = criteria.evaluate_all(
        twii_history=twii_history,
        twii_latest=twii_latest,
        stats=stats,
        today_highs=today_highs,
        historical_highs=historical_highs,
    )

    # --- Persist updated state ---
    state_manager.save_market_stats(stats)
    state_manager.save_historical_highs(updated_highs)
    print("[main] 已更新本地快取（data/*.json）")

    # --- Notify ---
    for r in results:
        flag = "🔴" if r.triggered else ("⚪" if r.value is None else "🟢")
        print(f"   {flag} {r.name}: {r.detail}")
    notifier.send(results, trade_date)
    print("[main] 完成。")


if __name__ == "__main__":
    run()
