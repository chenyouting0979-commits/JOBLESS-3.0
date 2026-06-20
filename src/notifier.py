"""Discord webhook integration — formats the 7 criteria as a Traditional Chinese embed."""
from __future__ import annotations

import requests

from . import config
from .criteria import CriterionResult

# Discord embed colors
_COLOR_ALERT = 0xE74C3C    # red — at least one criterion triggered
_COLOR_CALM = 0x2ECC71     # green — all quiet
_COLOR_INFO = 0x95A5A6     # grey — degraded / insufficient data


def build_embed(results: list[CriterionResult], trade_date: str) -> dict:
    triggered = [r for r in results if r.triggered]
    has_data = any(r.value is not None for r in results)

    if triggered:
        color = _COLOR_ALERT
    elif has_data:
        color = _COLOR_CALM
    else:
        color = _COLOR_INFO

    fields = []
    for r in results:
        mark = "🔴" if r.triggered else ("⚪" if r.value is None else "🟢")
        fields.append({
            "name": f"{mark} {r.name}",
            "value": r.detail or "—",
            "inline": False,
        })

    summary = (
        f"⚠️ 觸發 {len(triggered)} 項指標：" + "、".join(r.name for r in triggered)
        if triggered else "✅ 今日各項指標均處於正常區間"
    )

    return {
        "title": f"📊 台股市場溫度計 — {trade_date}",
        "description": summary,
        "color": color,
        "fields": fields,
        "footer": {"text": "Taiwan Stock Screener · Market Thermometer"},
    }


def send(results: list[CriterionResult], trade_date: str) -> bool:
    """POST the embed to the Discord webhook.

    Returns True on success. If no webhook is configured, prints the summary to
    stdout (handy for local dry-runs) and returns False.
    """
    embed = build_embed(results, trade_date)

    if not config.DISCORD_WEBHOOK_URL:
        print("[notifier] DISCORD_WEBHOOK_URL 未設定，改為輸出至 console：")
        print(f"  {embed['title']}")
        print(f"  {embed['description']}")
        for f in embed["fields"]:
            print(f"  {f['name']}: {f['value']}")
        return False

    resp = requests.post(
        config.DISCORD_WEBHOOK_URL,
        json={"embeds": [embed]},
        timeout=30,
    )
    resp.raise_for_status()
    print(f"[notifier] Discord 通知已送出（HTTP {resp.status_code}）")
    return True
