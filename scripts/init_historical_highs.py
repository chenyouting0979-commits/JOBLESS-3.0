"""One-time local bootstrap: fetch all-time highs for every Watchlist ticker.

Run from the repo root:

    python scripts/init_historical_highs.py

Populates data/historical_highs.json with { "2330.TW": <all-time high>, ... }.
"""
from __future__ import annotations

import os
import sys

# Make `import src...` work when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, state_manager                    # noqa: E402
from src.fetchers import yfinance_fetcher                 # noqa: E402


def main() -> None:
    highs: dict[str, float] = {}
    print(f"抓取 {len(config.WATCHLIST)} 檔股票的歷史最高價 …\n")

    for ticker in config.WATCHLIST:
        try:
            ath = yfinance_fetcher.fetch_all_time_high(ticker)
            highs[ticker] = round(ath, 2)
            print(f"  ✓ {ticker:<10} 歷史最高 {ath:,.2f}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {ticker:<10} 失敗：{exc}")

    state_manager.save_historical_highs(highs)
    print(f"\n已寫入 {config.HISTORICAL_HIGHS_PATH}（{len(highs)} 檔）")


if __name__ == "__main__":
    main()
