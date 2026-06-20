import os

# --- Discord ---
DISCORD_WEBHOOK_URL: str = os.environ.get("DISCORD_WEBHOOK_URL", "")

# --- Watchlist (Taiwan stocks only) ---
WATCHLIST: list[str] = [
    "2330.TW",  # 台積電
    "2317.TW",  # 鴻海
    "2454.TW",  # 聯發科
    "2382.TW",  # 廣達
    "2308.TW",  # 台達電
    "2881.TW",  # 富邦金
    "2882.TW",  # 國泰金
    "2412.TW",  # 中華電
    "3008.TW",  # 大立光
    "2357.TW",  # 華碩
]

# --- Index ---
TWII_TICKER: str = "^TWII"

# --- MA periods ---
MA_60_PERIOD: int = 60       # days needed for ^TWII 60MA bias
MA_20_PERIOD: int = 20       # days kept for TWSE rolling stats
MARGIN_PERIOD: int = 20      # days for margin vs index % change

# --- Anomaly threshold ---
AMPLITUDE_THRESHOLD: float = 0.03   # 3% single-day swing (criterion 7)

# --- Criteria trigger thresholds (heuristic defaults; tune freely) ---
# C1: |60MA bias %| at/above this is flagged as overheated/oversold.
BIAS_ALERT: float = 8.0
# C2/C3: today's up/down-limit count is a "spike" if it exceeds
#        mean + SPIKE_STD * std over the trailing window.
SPIKE_STD: float = 1.0
# C4: advancing/declining ratio extremes (broad rally / broad selloff).
AD_HIGH: float = 2.0
AD_LOW: float = 0.5
# C6: |margin% / index%| at/above this flags retail over-leverage divergence.
MARGIN_RATIO_ALERT: float = 2.0
MARGIN_RATIO_CAP: float = 100.0     # hard cap on the ratio magnitude

# --- Data file paths ---
DATA_DIR: str = os.path.join(os.path.dirname(__file__), "..", "data")
HISTORICAL_HIGHS_PATH: str = os.path.join(DATA_DIR, "historical_highs.json")
MARKET_STATS_HISTORY_PATH: str = os.path.join(DATA_DIR, "market_stats_history.json")

# --- TWSE API ---
TWSE_MI_INDEX_URL: str = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TWSE_MI_MARGN_URL: str = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
TWSE_REQUEST_DELAY: float = 1.5   # seconds between requests
TWSE_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.twse.com.tw/",
}
