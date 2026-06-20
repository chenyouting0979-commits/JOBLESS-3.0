"""TWSE OpenAPI fetcher for market breadth (MI_INDEX) and margin (MI_MARGN).

The TWSE rwd endpoints return JSON made of several named tables. Parsing is kept
defensive (keyed by field/row labels, tolerant of fullwidth digits, comma
separators, HTML wrappers and 'A(B)' packed cells) because TWSE occasionally
adjusts table order and formatting.

Validated against real responses for 2026-06-18:
  MI_INDEX  -> table '漲跌證券數合計', row '上漲(漲停)'/'下跌(跌停)',
               cell like '574(58)' = advancing(up-limit), '股票' column.
  MI_MARGN  -> table '信用交易統計', row '融資金額(仟元)', '今日餘額' column.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime

import requests

from .. import config

_TAG_RE = re.compile(r"<[^>]+>")
_PAREN_RE = re.compile(r"^\s*([\d,\.]+)\s*(?:\(\s*([\d,\.]+)\s*\))?")


def _to_number(raw: str | int | float) -> float:
    """Convert a TWSE numeric string ('1,234', '--', '<p>+</p>') to float."""
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = _TAG_RE.sub("", str(raw)).replace(",", "").strip()
    cleaned = cleaned.replace("--", "")
    if cleaned in ("", "X", "N/A"):
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _parse_count_paren(cell: str) -> tuple[float, float]:
    """Parse a packed cell like '574(58)' -> (574.0, 58.0).

    Returns (main, paren); paren is 0.0 when absent.
    """
    text = _TAG_RE.sub("", str(cell)).strip()
    m = _PAREN_RE.match(text)
    if not m:
        return _to_number(text), 0.0
    main = _to_number(m.group(1))
    paren = _to_number(m.group(2)) if m.group(2) else 0.0
    return main, paren


def _request(url: str, params: dict) -> dict:
    """GET a TWSE rwd endpoint and return parsed JSON, with polite delay + headers."""
    time.sleep(config.TWSE_REQUEST_DELAY)
    resp = requests.get(url, params=params, headers=config.TWSE_HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if str(payload.get("stat", "")).upper() != "OK":
        raise RuntimeError(
            f"TWSE request failed ({url}): stat={payload.get('stat')!r}"
        )
    return payload


def _normalize_date(d: date | str | None) -> str:
    """Return TWSE date string 'YYYYMMDD'. Defaults to today."""
    if d is None:
        d = date.today()
    if isinstance(d, str):
        return d.replace("-", "")
    return d.strftime("%Y%m%d")


def _iter_tables(payload: dict):
    """Yield (title, fields, rows) for every embedded table.

    Supports the current 'tables': [{title, fields, data}] layout and the legacy
    flat 'fields1'/'data1' layout.
    """
    if isinstance(payload.get("tables"), list):
        for tbl in payload["tables"]:
            yield (tbl.get("title") or "", tbl.get("fields") or [],
                   tbl.get("data") or [])
        return
    for key in payload:
        if key.startswith("fields"):
            suffix = key[len("fields"):]
            yield ("", payload.get(key, []), payload.get(f"data{suffix}", []))


def _field_index(fields: list[str], *needles: str, default: int) -> int:
    """Return the index of the first field containing any needle, else default."""
    for i, f in enumerate(fields):
        if any(n in str(f) for n in needles):
            return i
    return default


def fetch_market_breadth(d: date | str | None = None) -> dict[str, float]:
    """Fetch advancing/declining and up-limit/down-limit counts from MI_INDEX.

    Uses the stocks-only ('股票') column of the '漲跌證券數合計' table, which is the
    classic individual-stock breadth (excludes ETFs/warrants/TDRs).
    Returns: { advancing, declining, up_limit, down_limit }. Supports criteria 2/3/4.
    """
    payload = _request(
        config.TWSE_MI_INDEX_URL,
        {"date": _normalize_date(d), "type": "ALL", "response": "json"},
    )

    result = {"advancing": 0.0, "declining": 0.0, "up_limit": 0.0, "down_limit": 0.0}
    found = False

    for title, fields, rows in _iter_tables(payload):
        if "漲跌證券數" not in title and not any(
            str(r[0]).startswith("上漲") for r in rows if r
        ):
            continue
        # Prefer the stocks-only column; fall back to the last available column.
        col = _field_index(fields, "股票", default=len(fields) - 1 if fields else 2)
        for row in rows:
            if not row:
                continue
            label = str(row[0])
            cell = row[col] if col < len(row) else (row[-1] if len(row) > 1 else "")
            if label.startswith("上漲"):
                result["advancing"], result["up_limit"] = _parse_count_paren(cell)
                found = True
            elif label.startswith("下跌"):
                result["declining"], result["down_limit"] = _parse_count_paren(cell)
                found = True
        if found:
            break

    if not found:
        raise RuntimeError("Could not locate breadth (漲跌證券數合計) in MI_INDEX response")
    return result


def fetch_margin_balance(d: date | str | None = None) -> float:
    """Fetch 融資金額 今日餘額 (margin balance, NT$ thousands) from MI_MARGN (MS).

    Supports criterion 6.
    """
    payload = _request(
        config.TWSE_MI_MARGN_URL,
        {"date": _normalize_date(d), "selectType": "MS", "response": "json"},
    )

    for _title, fields, rows in _iter_tables(payload):
        col = _field_index(fields, "今日餘額", default=len(fields) - 1 if fields else -1)
        for row in rows:
            if not row:
                continue
            # Match the NT$ amount row specifically, not 融資(交易單位) (lots).
            if str(row[0]).startswith("融資金額"):
                cell = row[col] if 0 <= col < len(row) else row[-1]
                return _to_number(cell)
    raise RuntimeError("Could not locate 融資金額 row in MI_MARGN response")


if __name__ == "__main__":
    # Quick manual smoke test against the most recent trading day.
    today = datetime.now().date()
    print("breadth:", fetch_market_breadth(today))
    print("margin :", fetch_margin_balance(today))
