"""One-time local bootstrap: backfill the rolling market-stats history.

Run from the repo root:

    python scripts/init_market_stats.py [num_trading_days]   # default 60

Strategy:
  1. Pull ^TWII history once (yfinance) -> use its dates as the trading-day filter
     and as the source of daily closes (avoids one TWSE call per weekend/holiday).
  2. For each of the most recent N trading days, fetch TWSE MI_INDEX breadth and
     MI_MARGN margin balance, then append chronologically to the JSON cache.

This makes ~2 polite TWSE requests per trading day, so it takes a few minutes.
"""
from __future__ import annotations

import os
import sys

# Make `import src...` work when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, state_manager                    # noqa: E402
from src.fetchers import twse_fetcher, yfinance_fetcher  # noqa: E402


def main(num_days: int) -> None:
    print(f"目標：回補最近 {num_days} 個交易日的市場統計\n")

    # 1) ^TWII closes keyed by trading date (also our trading-day calendar).
    print("抓取 ^TWII 歷史 …")
    twii = yfinance_fetcher.fetch_twii_history(period="1y")
    twii_close = {idx.strftime("%Y-%m-%d"): float(row["Close"])
                  for idx, row in twii.iterrows()}
    trading_dates = sorted(twii_close)[-num_days:]
    print(f"  取得 {len(trading_dates)} 個交易日：{trading_dates[0]} ~ {trading_dates[-1]}\n")

    # 2) Fetch TWSE breadth + margin per trading day, chronologically.
    stats = state_manager._empty_stats()
    ok, fail = 0, 0
    for i, d in enumerate(trading_dates, 1):
        try:
            breadth = twse_fetcher.fetch_market_breadth(d)
            margin = twse_fetcher.fetch_margin_balance(d)
            state_manager.append_market_stats(
                stats,
                trade_date=d,
                up_limit=breadth["up_limit"],
                down_limit=breadth["down_limit"],
                advancing=breadth["advancing"],
                declining=breadth["declining"],
                margin_balance=margin,
                twii_close=twii_close[d],
            )
            ok += 1
            print(f"  [{i:>2}/{len(trading_dates)}] ✓ {d}  "
                  f"漲停 {breadth['up_limit']:.0f} 跌停 {breadth['down_limit']:.0f} "
                  f"漲 {breadth['advancing']:.0f} 跌 {breadth['declining']:.0f} "
                  f"融資 {margin:,.0f}")
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"  [{i:>2}/{len(trading_dates)}] ✗ {d}  跳過：{exc}")

    state_manager.save_market_stats(stats)
    print(f"\n已寫入 {config.MARKET_STATS_HISTORY_PATH}"
          f"（成功 {ok}、失敗 {fail}）")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else config.MA_60_PERIOD
    main(days)
