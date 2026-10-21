"""
蓄積したデータを分析して、ダッシュボード用の summary.json と
週次レポート（weekly.json / docs/reports/YYYY-MM-DD.md）を作るスクリプト。
"""

import json
import os
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
REPORT_DIR = ROOT / "docs" / "reports"
JST = timezone(timedelta(hours=9))
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def d(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def shift(date: str, days: int) -> str:
    return (d(date) - timedelta(days=days)).strftime("%Y-%m-%d")


def value_on_or_before(series: dict, date: str):
    """{日付: 値} から、指定日以前で一番新しい値を返す。なければ None。"""
    keys = [k for k in series if k <= date]
    return series[max(keys)] if keys else None


def parse_published(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(JST)
    except ValueError:
        return None


def categorize(title: str, config: dict) -> str:
    for cat in config.get("categories", []):
        if any(k in title for k in cat["keywords"]):
            return cat["name"]
    return config.get("default_category", "その他")


# ---------------------------------------------------------------- 差分計算

def history_delta(history: list, field: str, today: str, days: int):
    series = {h["date"]: h[field] for h in history}
    now = series.get(today)
    past = value_on_or_before(series, shift(today, days))
    if now is None or past is None:
        return None
    return now - past


def article_gain(rec: dict, today: str, days: int):
    likes = rec["likes"]
    now = likes.get(today)
    if now is None:
        return None
    past = value_on_or_before(likes, shift(today, days))
    if past is not None:
        return now - past
    # 計測開始後に公開された記事は、公開からのスキ全部を「期間内の増加」とみなす
    pub = parse_published(rec.get("published_at", ""))
    if pub and pub.strftime("%Y-%m-%d") > shift(today, days):
        return now
    return None


# ---------------------------------------------------------------- 分析本体

def build_rows(store: dict, today: str, config: dict) -> list:
    rows = []
    for key, rec in store.get("articles", {}).items():
        likes = rec["likes"].get(today)
        if likes is None:  # 今日の取得で見つからなかった記事（削除・非公開など）
            continue
        pub = parse_published(rec.get("published_at", ""))
        days_live = max((d(today) - d(pub.strftime("%Y-%m-%d"))).days, 0) + 1 if pub else None
        rows.append({
            "key": key,
            "title": rec["title"],
            "url": rec["url"],
            "published_at": pub.strftime("%Y-%m-%d %H:%M") if pub else "",
            "weekday": WEEKDAYS[pub.weekday()] if pub else "",
            "hour": pub.hour if pub else None,
            "category": categorize(rec["title"], config),
            "likes": likes,
            "comments": rec["comments"].get(today, 0),
            "gain_1d": article_gain(rec, today, 1),
            "gain_7d": article_gain(rec, today, 7),
            "likes_per_day": round(likes / days_live, 2) if days_live else None,
        })
    rows.sort(key=lambda r: r["published_at"], reverse=True)
    return rows


def group_stats(rows: list, key: str, order=None) -> list:
    groups = defaultdict(list)
    for r in rows:
        if r[key] not in ("", None):
            groups[r[key]].append(r["likes"])
    names = order or sorted(groups, key=lambda k: -statistics.mean(groups[k]))
    return [
        {
            "name": n,
            "count": len(groups[n]),
            "avg_likes": round(statistics.mean(groups[n]), 1),
            "median_likes": statistics.median(groups[n]),
        }
        for n in names if groups.get(n)
    ]


def posts_per_week(rows: list, today: str, weeks: int = 12) -> list:
    end = d(today)
    monday = end - timedelta(days=end.weekday())
    result = []
    for i in range(weeks - 1, -1, -1):
        start = monday - timedelta(weeks=i)
        stop = start + timedelta(days=7)
        n = sum(
            1 for r in rows
            if r["published_at"] and start <= d(r["published_at"][:10]) < stop
        )
        result.append({"week": start.strftime("%m/%d"), "posts": n})
    return result


def hour_band(h):
    if h is None:
        return None
    for lo, hi, label in [(5, 11, "朝 5-11時"), (11, 17, "昼 11-17時"),
                          (17, 22, "夜 17-22時")]:
        if lo <= h < hi:
            return label
    return "深夜 22-5時"


# ---------------------------------------------------------------- 週次レポート

def weekly_report(history: list, rows: list, today: str, categories: list) -> dict:
    f_this = history_delta(history, "followers", today, 7)
    f_last = None
    hist_series = {h["date"]: h["followers"] for h in history}
    a = value_on_or_before(hist_series, shift(today, 7))
    b = value_on_or_before(hist_series, shift(today, 14))
    if a is not None and b is not None and shift(today, 14) >= min(hist_series):
        f_last = a - b
    likes_this = history_delta(history, "total_likes", today, 7)

    week_start = shift(today, 6)
    posted = [r for r in rows if r["published_at"][:10] >= week_start]
    gainers = sorted([r for r in rows if r["gain_7d"]], key=lambda r: -r["gain_7d"])[:3]

    lines = []
    if f_this is not None:
        diff = f"（先週 {f_last:+d}人）" if f_last is not None else ""
        lines.append(f"フォロワーは今週 {f_this:+d}人{diff}。")
    if likes_this is not None:
        lines.append(f"記事全体で新たに {likes_this} スキを獲得。")
    lines.append(f"今週の投稿は {len(posted)} 本。")
    if posted and f_this is not None and len(posted) > 0:
        lines.append(f"1投稿あたりのフォロワー増は約 {f_this / len(posted):.1f}人。")

    if gainers:
        lines.append("今週いちばん伸びた記事:")
        for i, r in enumerate(gainers, 1):
            lines.append(f"  {i}. {r['title']}（+{r['gain_7d']}スキ）")

    # 今週公開した記事のスキ数を、直近30日に公開した記事の平均と比べる
    recent = [r for r in rows if shift(today, 30) <= r["published_at"][:10] < week_start]
    if posted and recent:
        best = max(posted, key=lambda r: r["likes"])
        base = statistics.mean(r["likes"] for r in recent)
        if base:
            lines.append(
                f"今週公開の中でのトップは「{best['title']}」の {best['likes']} スキ"
                f"（公開数日で、先月公開記事の平均 {base:.0f} スキの {best['likes'] / base:.1f}倍）。"
            )

    solid = [c for c in categories if c["count"] >= 3]
    if len(solid) >= 2:
        top, low = solid[0], solid[-1]
        lines.append(
            f"カテゴリ別の平均スキは「{top['name']}」が {top['avg_likes']} で最多、"
            f"「{low['name']}」が {low['avg_likes']} で最少。"
        )

    return {"date": today, "period": f"{week_start} 〜 {today}", "lines": lines}


def write_report_md(report: dict, user: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{report['date']}.md"
    body = [f"# note 週次レポート（@{user}）", "", f"期間: {report['period']}", ""]
    body += [f"- {l}" if not l.startswith("  ") else f"  {l.strip()}" for l in report["lines"]]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- main

def main() -> dict:
    config = load_json(ROOT / "config.json", {})
    history = load_json(DATA_DIR / "history.json", [])
    store = load_json(DATA_DIR / "articles.json", {"articles": {}})
    if not history:
        raise SystemExit("history.json がありません。先に collect.py を実行してください。")

    today = history[-1]["date"]
    latest = history[-1]
    rows = build_rows(store, today, config)

    categories = group_stats(rows, "category")
    for r in rows:
        r["band"] = hour_band(r["hour"])
    weekday_stats = group_stats(rows, "weekday", order=WEEKDAYS)
    band_stats = group_stats(rows, "band", order=["朝 5-11時", "昼 11-17時", "夜 17-22時", "深夜 22-5時"])

    def top(field, n=5):
        return [
            {"title": r["title"], "url": r["url"], "gain": r[field]}
            for r in sorted([r for r in rows if r[field]], key=lambda r: -r[field])[:n]
        ]

    summary = {
        "updated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "date": today,
        "user": store.get("user", ""),
        "nickname": store.get("nickname", ""),
        "tracking_since": history[0]["date"],
        "kpi": {
            "followers": latest["followers"],
            "followers_1d": history_delta(history, "followers", today, 1),
            "followers_7d": history_delta(history, "followers", today, 7),
            "followers_30d": history_delta(history, "followers", today, 30),
            "total_likes": latest["total_likes"],
            "likes_1d": history_delta(history, "total_likes", today, 1),
            "likes_7d": history_delta(history, "total_likes", today, 7),
            "notes": latest["notes"],
            "posts_7d": sum(1 for r in rows if r["published_at"][:10] >= shift(today, 6)),
            "total_comments": latest["total_comments"],
            "avg_likes": round(statistics.mean(r["likes"] for r in rows), 1) if rows else 0,
        },
        "top_gainers_1d": top("gain_1d"),
        "top_gainers_7d": top("gain_7d"),
        "categories": categories,
        "weekday_stats": weekday_stats,
        "band_stats": band_stats,
        "posts_per_week": posts_per_week(rows, today),
        "articles": rows,
    }

    # 週次レポート（設定した曜日、または FORCE_WEEKLY=1 のとき）
    weekly = load_json(DATA_DIR / "weekly.json", [])
    want_weekly = (d(today).weekday() == config.get("weekly_report_weekday", 6)
                   or os.environ.get("FORCE_WEEKLY") == "1")
    summary["weekly_generated"] = False
    if want_weekly:
        report = weekly_report(history, rows, today, categories)
        weekly = [w for w in weekly if w["date"] != today] + [report]
        write_report_md(report, summary["user"])
        summary["weekly_generated"] = True
        (DATA_DIR / "weekly.json").write_text(
            json.dumps(weekly, ensure_ascii=False, indent=1), encoding="utf-8")
    summary["latest_weekly"] = weekly[-1] if weekly else None

    (DATA_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{today}] summary written ({len(rows)} articles, weekly={want_weekly})")
    return summary


if __name__ == "__main__":
    main()
