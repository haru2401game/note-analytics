# note-analytics

noteアカウント（[@ha_03ru_01](https://note.com/ha_03ru_01)）の公開データを毎日自動で集めて、
グラフ付きダッシュボード・Discord通知・週次レポートにするツールです。
GitHub Actions で動くので、PCの電源がオフでも毎日記録されます。

## できること

| 機能 | 内容 |
|---|---|
| 毎日の記録 | フォロワー数・フォロー数・記事数・記事ごとのスキ数/コメント数（毎日 23:37 JST） |
| ダッシュボード | フォロワー/スキの推移と日ごとの増減、伸びている記事、カテゴリ・曜日・時間帯別の平均スキ、記事ごとのスキ推移 |
| Discord通知 | 毎晩「フォロワー前日比・新規スキ・昨日伸びた記事 TOP3」 |
| 週次レポート | 毎週日曜の夜。フォロワー増（先週比）、投稿数、1投稿あたりのフォロワー増、伸びた記事、カテゴリ比較 |

## セットアップ（15分くらい）

### 1. リポジトリを作る
1. GitHubで **public** の新しいリポジトリ `note-analytics` を作成
   （private だと GitHub Pages が有料プランになります）
2. このフォルダの中身をすべてアップロード（`.github` フォルダも忘れずに）

### 2. GitHub Pages を有効にする
`Settings` → `Pages` → Source を **Deploy from a branch**、Branch を `main` / `/docs` にして Save。
数分後に `https://haru2401game.github.io/note-analytics/` でダッシュボードが見られます。
（URLが違う場合は `config.json` の `dashboard_url` を書き換えてください）

### 3. Discord通知を設定する（任意）
1. Discordで通知用のサーバー（自分だけのサーバーでOK）を作り、チャンネルの
   `設定` → `連携サービス` → `ウェブフック` → `新しいウェブフック` → **URLをコピー**
2. GitHubの `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
   - Name: `DISCORD_WEBHOOK_URL`
   - Secret: コピーしたURL

### 4. 初回を手動で実行する
`Actions` タブ → `note daily analytics` → `Run workflow`。
緑のチェックになれば完了です。以降は毎日自動で動きます。

> 前日比や7日間の増加は、データが2日分・8日分たまってから表示されます。
> フォロワー数の過去の推移はnoteから取得できないため、記録は初回実行の日から始まります。

## カスタマイズ

- **カテゴリ分け**: `config.json` の `categories` に「カテゴリ名」と「タイトルに含まれるキーワード」を書くと、記事が自動で分類されます（上から順に判定）。
- **週次レポートの曜日**: `config.json` の `weekly_report_weekday`（0=月 … 6=日）
- **実行時刻**: `.github/workflows/daily.yml` の `cron`（UTCで指定。JST = UTC+9）
- **別アカウントを分析**: `Settings` → `Secrets and variables` → `Actions` → `Variables` に `NOTE_USER` を追加

## ファイル構成

```
scripts/collect.py   noteの公開データを取得して docs/data/ に追記
scripts/analyze.py   差分・ランキング・カテゴリ分析、週次レポート作成
scripts/notify.py    Discordへ通知
docs/index.html      ダッシュボード（GitHub Pages）
docs/data/           蓄積データ（history.json / articles.json / summary.json / weekly.json）
docs/reports/        週次レポートのMarkdown
config.json          カテゴリ・曜日などの設定
```

## ローカルで試す

```bash
pip install -r requirements.txt
python scripts/collect.py
python scripts/analyze.py
cd docs && python -m http.server 8000   # → http://localhost:8000
```

## 注意

- noteの公式に公開されたAPIではなく、Webページが内部で使っているAPIを1日1回だけ読んでいます。
  仕様が変わると取得できなくなることがあります（Actionsが赤くなったら教えてください）。
- 取得するのは誰でも見られる公開情報のみで、ログイン情報は使いません。
- PV（閲覧数）はログインが必要なため対象外です。
