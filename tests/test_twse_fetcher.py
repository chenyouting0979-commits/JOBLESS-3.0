"""Tests for TWSE parsing — helpers plus fetchers driven by fixture payloads.

Payloads mirror the real 2026-06-18 TWSE responses; ``_request`` is monkeypatched
so nothing hits the network.
"""
from __future__ import annotations

import pytest

from src.fetchers import twse_fetcher as t

# --- Fixtures modeled on real TWSE responses -------------------------------
MI_INDEX_PAYLOAD = {
    "stat": "OK",
    "tables": [
        {"title": "價格指數", "fields": ["指數", "收盤指數"], "data": [["加權指數", "46,465.20"]]},
        {
            "title": "漲跌證券數合計",
            "fields": ["類型", "整體市場", "股票"],
            "data": [
                ["上漲(漲停)", "8,299(851)", "574(58)"],
                ["下跌(跌停)", "3,313(68)", "395(3)"],
                ["持平", "700", "97"],
            ],
        },
    ],
}

MI_MARGN_PAYLOAD = {
    "stat": "OK",
    "tables": [
        {
            "title": "信用交易統計",
            "fields": ["項目", "買進", "賣出", "現金(券)償還", "前日餘額", "今日餘額"],
            "data": [
                ["融資(交易單位)", "645,505", "596,232", "12,593", "9,308,567", "9,345,247"],
                ["融資金額(仟元)", "52,359,121", "43,477,739", "594,963", "584,760,128", "593,046,547"],
            ],
        }
    ],
}


# --- Numeric helpers -------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("1,234", 1234.0),
    ("593,046,547", 593046547.0),
    ("--", 0.0),
    ("", 0.0),
    ("<p style='color:red'>+</p>", 0.0),
    (58, 58.0),
])
def test_to_number(raw, expected):
    assert t._to_number(raw) == expected


@pytest.mark.parametrize("cell,expected", [
    ("574(58)", (574.0, 58.0)),
    ("3,313(68)", (3313.0, 68.0)),
    ("700", (700.0, 0.0)),
    ("8,299(851)", (8299.0, 851.0)),
])
def test_parse_count_paren(cell, expected):
    assert t._parse_count_paren(cell) == expected


def test_field_index_prefers_match():
    assert t._field_index(["類型", "整體市場", "股票"], "股票", default=1) == 2
    assert t._field_index(["a", "b"], "股票", default=99) == 99


# --- Breadth fetcher (stocks-only column) ----------------------------------
def test_fetch_market_breadth(monkeypatch):
    monkeypatch.setattr(t, "_request", lambda url, params: MI_INDEX_PAYLOAD)
    breadth = t.fetch_market_breadth("2026-06-18")
    assert breadth == {
        "advancing": 574.0, "up_limit": 58.0,
        "declining": 395.0, "down_limit": 3.0,
    }


def test_fetch_market_breadth_missing_table(monkeypatch):
    monkeypatch.setattr(t, "_request", lambda url, params: {"stat": "OK", "tables": []})
    with pytest.raises(RuntimeError):
        t.fetch_market_breadth("2026-06-18")


# --- Margin fetcher (今日餘額 of the NT$ row) -------------------------------
def test_fetch_margin_balance(monkeypatch):
    monkeypatch.setattr(t, "_request", lambda url, params: MI_MARGN_PAYLOAD)
    assert t.fetch_margin_balance("2026-06-18") == 593046547.0


def test_fetch_margin_balance_missing_row(monkeypatch):
    payload = {"stat": "OK", "tables": [{"title": "x", "fields": [], "data": []}]}
    monkeypatch.setattr(t, "_request", lambda url, params: payload)
    with pytest.raises(RuntimeError):
        t.fetch_margin_balance("2026-06-18")


# --- Date normalization ----------------------------------------------------
@pytest.mark.parametrize("value,expected", [
    ("2026-06-18", "20260618"),
    ("20260618", "20260618"),
])
def test_normalize_date(value, expected):
    assert t._normalize_date(value) == expected
