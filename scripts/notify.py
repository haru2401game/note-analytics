"""
summary.json の内容を Discord に通知するスクリプト。
環境変数 DISCORD_WEBHOOK_URL が未設定なら何もしない（通知はオプション）。
"""

import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"


def fmt(n) -> str:
    return "—" if n is None else f"{n:+d}"


def daily_embed(s: dict, dashboard_url: str) -> dict:
    k = s["kpi"]
    lines = [
        f"👥 フォロワー **{k['followers']:,}**　前日比 {fmt(k['followers_1d'])} / 7日 {fmt(k['followers_7d'])}",
        f"❤️ 総スキ **{k['total_likes']:,}**　前日比 {fmt(k['likes_1d'])} / 7日 {fmt(k['likes_7d'])}",
        f"📝 記事 **{k['notes']}本**　直近7日の投稿 {k['posts_7d']}本",
    ]
    if s["top_gainers_1d"]:
        lines.append("\n**昨日スキが伸びた記事**")
        for i, a in enumerate(s["top_gainers_1d"][:3], 1):
            lines.append(f"{i}. [{a['title'][:60]}]({a['url']}) +{a['gain']}")
    return {
        "title": f"📊 note日報 {s['date']}",
        "url": dashboard_url or None,
        "description": "\n".join(lines),
        "color": 0x41C9B4,
    }


def weekly_embed(s: dict) -> dict:
    w = s["latest_weekly"]
    return {
        "title": f"🗓️ 週次レポート（{w['period']}）",
        "description": "\n".join(w["lines"])[:4000],
        "color": 0xF5A623,
    }


def main() -> None:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("DISCORD_WEBHOOK_URL 未設定のため通知をスキップ")
        return
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    s = json.loads((DATA_DIR / "summary.json").read_text(encoding="utf-8"))

    embeds = [daily_embed(s, config.get("dashboard_url", ""))]
    if s.get("weekly_generated") and s.get("latest_weekly"):
        embeds.append(weekly_embed(s))

    r = requests.post(url, json={"username": "note分析bot", "embeds": embeds}, timeout=30)
    r.raise_for_status()
    print(f"Discordに通知しました（{len(embeds)}件）")


if __name__ == "__main__":
    main()
