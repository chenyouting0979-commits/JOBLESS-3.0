# Taiwan Stock Screener — Market Thermometer (Phase 1 MVP)

每日抓取台股資料，評估 7 項「市場溫度計」指標，並透過 Discord Webhook 通知。
無資料庫、無 Web，狀態以 `data/*.json` 快取，由 GitHub Actions 定時執行並 git-scraping 回寫。

## 架構
```
src/
  config.py          # Watchlist、常數、觸發門檻、TWSE URL
  fetchers/
    yfinance_fetcher.py  # ^TWII 與個股價格
    twse_fetcher.py      # MI_INDEX（漲跌/漲停跌停）、MI_MARGN（融資）
  state_manager.py   # data/*.json 讀寫（冪等）
  criteria.py        # 7 項指標的純邏輯
  notifier.py        # Discord Embed（繁中）
  main.py            # 主流程
scripts/
  init_historical_highs.py  # 一次性：回補 Watchlist 歷史最高價
  init_market_stats.py      # 一次性：回補近 60 交易日市場統計
data/
  historical_highs.json
  market_stats_history.json
.github/workflows/daily_screener.yml
```

## 7 項指標
1. 加權指數與 60MA 乖離率
2. 20 日漲停家數趨勢
3. 20 日跌停家數趨勢
4. 20 日漲跌家數比趨勢
5. Watchlist 10 日內創新高家數
6. 融資增減比 ÷ 指數增減比（上限 100）
7. 大盤單日震幅異常（±3%）

## 安裝
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 首次啟動（本地各執行一次）
```bash
python scripts/init_historical_highs.py     # 填充 historical_highs.json
python scripts/init_market_stats.py 60       # 回補 60 個交易日（需數分鐘）
```

## 本地執行
```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python -m src.main
```
未設定 webhook 時會改為 console 輸出（dry-run）。

## 部署（GitHub Actions）
1. 在 repo 設定 **Settings → Secrets and variables → Actions** 新增 `DISCORD_WEBHOOK_URL`。
2. 提交全部檔案（含已 bootstrap 的 `data/*.json`）。
3. Workflow 每週一至五 09:00 UTC（台北 17:00）自動執行，並把更新後的 JSON 推回 repo。

## 觸發門檻
皆為啟發式預設值，集中於 `src/config.py`（`BIAS_ALERT`、`SPIKE_STD`、`AD_HIGH/LOW`、`MARGIN_RATIO_ALERT` …），可自行調整。

## 測試
```bash
pip install -r requirements-dev.txt
pytest
```
46 個單元測試涵蓋 7 項指標邏輯、JSON 快取冪等性，以及 TWSE 解析（用真實回傳格式的 fixture，不連網）。
