"""yfinance-based fetcher for ^TWII and Taiwan stock price data."""
from __future__ import annotations

import pandas as pd
import yfinance as yf


def _download(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Download OHLC history for a single ticker, returned with a flat column index."""
    df = yf.download(
        ticker,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
    )
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no data for {ticker!r}")

    # yfinance may return a MultiIndex (column, ticker) for single tickers too.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df.dropna(how="all")


def fetch_twii_history(period: str = "1y") -> pd.DataFrame:
    """Return the ^TWII daily OHLC history.

    Columns: Open, High, Low, Close, Adj Close, Volume (index = Date).
    Used for the 60MA bias and the 3% amplitude anomaly criteria.
    """
    return _download("^TWII", period=period)


def fetch_twii_latest() -> dict[str, float]:
    """Return the most recent ^TWII bar as a dict of floats."""
    df = fetch_twii_history(period="3mo")
    last = df.iloc[-1]
    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "open": float(last["Open"]),
        "high": float(last["High"]),
        "low": float(last["Low"]),
        "close": float(last["Close"]),
    }


def fetch_stock_history(ticker: str, period: str = "max") -> pd.DataFrame:
    """Return full OHLC history for a single Taiwan stock (e.g. '2330.TW')."""
    return _download(ticker, period=period)


def fetch_stock_latest_high(ticker: str) -> dict[str, float]:
    """Return today's High/Close for a single Taiwan stock.

    Used by criterion 5 (Watchlist new highs).
    """
    df = _download(ticker, period="5d")
    last = df.iloc[-1]
    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "high": float(last["High"]),
        "close": float(last["Close"]),
    }


def fetch_all_time_high(ticker: str) -> float:
    """Return the all-time intraday high for a ticker (for bootstrapping the cache)."""
    df = fetch_stock_history(ticker, period="max")
    return float(df["High"].max())
