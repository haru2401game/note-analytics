"""
note の公開データを取得して docs/data/ に1日分を追記するスクリプト。

取得するもの（すべてログイン不要の公開情報）:
  - フォロワー数 / フォロー数 / 記事数
  - 記事ごとのスキ数・コメント数・公開日時
  - 運営しているマガジン（config.json の tracked_magazine）の収録記事数

保存先:
  docs/data/history.json   … 日ごとのアカウント全体の数値（magazine_notes を含む）
  docs/data/articles.json  … 記事ごとのスキ数・コメント数の日次推移
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

NOTE_USER = os.environ.get("NOTE_USER", "ha_03ru_01")
API_BASE = os.environ.get("NOTE_API_BASE", "https://note.com/api/v2")
API_V1 = os.environ.get("NOTE_API_V1", "https://note.com/api/v1")
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": f"note-analytics/1.0 (personal stats for {NOTE_USER})",
    "Accept": "application/json",
}
REQUEST_INTERVAL_SEC = 1.0  # noteに負荷をかけないよう、ページ取得ごとに待つ
MAX_PAGES = 200


def today_jst() -> str:
    """実行日の日付（日本時間）。DATE_OVERRIDE があればそちらを使う（テスト用）。"""
    return os.environ.get("DATE_OVERRIDE") or datetime.now(JST).strftime("%Y-%m-%d")


def get_json(url: str, params: dict | None = None) -> dict:
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == 2:
                raise
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def pick(d: dict, *keys, default=None):
    """APIのキー名が camelCase / snake_case どちらでも拾えるようにする。"""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def fetch_creator() -> dict:
    data = get_json(f"{API_BASE}/creators/{NOTE_USER}").get("data", {})
    return {
        "followers": int(pick(data, "followerCount", "follower_count", default=0)),
        "following": int(pick(data, "followingCount", "following_count", default=0)),
        "notes": int(pick(data, "noteCount", "note_count", default=0)),
        "nickname": pick(data, "nickname", "name", default=NOTE_USER),
    }


def fetch_articles() -> list[dict]:
    articles = []
    for page in range(1, MAX_PAGES + 1):
        body = get_json(
            f"{API_BASE}/creators/{NOTE_USER}/contents",
            params={"kind": "note", "page": page},
        ).get("data", {})
        contents = body.get("contents") or []
        for c in contents:
            key = pick(c, "key")
            if not key:
                continue
            articles.append({
                "key": key,
                "title": pick(c, "name", "title", default="(無題)"),
                "url": pick(c, "noteUrl", "note_url",
                            default=f"https://note.com/{NOTE_USER}/n/{key}"),
                "published_at": pick(c, "publishAt", "publish_at", "published_at", default=""),
                "likes": int(pick(c, "likeCount", "like_count", default=0)),
                "comments": int(pick(c, "commentCount", "comment_count", default=0)),
                "hashtags": [
                    (h.get("hashtag") or {}).get("name", "").lstrip("#")
                    for h in (c.get("hashtags") or [])
                    if isinstance(h, dict)
                ],
            })
        if body.get("isLastPage", True) or not contents:
            break
        time.sleep(REQUEST_INTERVAL_SEC)
    return articles


def fetch_magazine_count(magazine_key: str):
    """マガジンの収録記事数（公開情報）。取れなければ None を返し、日次処理は止めない。"""
    try:
        data = get_json(f"{API_V1}/magazines/{magazine_key}").get("data", {})
        n = pick(data, "note_count", "noteCount")
        return int(n) if n is not None else None
    except Exception as e:  # noqa: BLE001  マガジン取得の失敗で日次の記録全体を落とさない
        print(f"  warn: magazine {magazine_key} の取得に失敗: {e}", file=sys.stderr)
        return None


def load_config() -> dict:
    path = ROOT / "config.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load(name: str, default):
    path = DATA_DIR / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save(name: str, obj) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / name).write_text(
        json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def main() -> None:
    date = today_jst()
    print(f"[{date}] collecting @{NOTE_USER}")

    config = load_config()
    creator = fetch_creator()
    articles = fetch_articles()
    print(f"  followers={creator['followers']} articles={len(articles)}")

    tracked = (config.get("tracked_magazine") or {}).get("key")
    magazine_notes = None
    if tracked:
        time.sleep(REQUEST_INTERVAL_SEC)
        magazine_notes = fetch_magazine_count(tracked)
        print(f"  magazine {tracked}: notes={magazine_notes}")

    # --- アカウント全体の推移 ---
    history = [h for h in load("history.json", []) if h["date"] != date]
    entry = {
        "date": date,
        "followers": creator["followers"],
        "following": creator["following"],
        "notes": creator["notes"] or len(articles),
        "total_likes": sum(a["likes"] for a in articles),
        "total_comments": sum(a["comments"] for a in articles),
    }
    if magazine_notes is not None:  # 取れなかった日は項目ごと省く（前日差は出さない）
        entry["magazine_notes"] = magazine_notes
    history.append(entry)
    history.sort(key=lambda h: h["date"])
    save("history.json", history)

    # --- 記事ごとの推移 ---
    store = load("articles.json", {"articles": {}})
    for a in articles:
        rec = store["articles"].setdefault(a["key"], {
            "first_seen": date, "likes": {}, "comments": {},
        })
        rec.update({
            "title": a["title"], "url": a["url"],
            "published_at": a["published_at"], "hashtags": a["hashtags"],
        })
        rec["likes"][date] = a["likes"]
        rec["comments"][date] = a["comments"]
    store["nickname"] = creator["nickname"]
    store["user"] = NOTE_USER
    save("articles.json", store)
    print("  saved.")


if __name__ == "__main__":
    main()
