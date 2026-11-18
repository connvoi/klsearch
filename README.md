# KnowledgeSeeker (klsearch)

`sources.yaml` に設定した RSS フィード・Web ページから記事を収集し、
SQLite (FTS5) に保存して全文検索できるツールです。

## 必要環境

- Python 3.11+
- ライブラリ: `requests`, `beautifulsoup4`, `lxml`, `PyYAML`

```bash
pip install -r requirements.txt
```

## 使い方

```bash
# sources.yaml の全ソースから収集(URL で重複排除、2回目以降は差分のみ)
python -m knowledgeseeker collect

# 特定ソースのみ収集
python -m knowledgeseeker collect --source simonwillison

# 既存の記事も再取得して上書き(セレクタ修正後やネットワーク設定変更後に)
python -m knowledgeseeker collect --source ycombinator --refresh

# 全文検索
python -m knowledgeseeker search "prompt injection"

# 収集済み記事の一覧 / 本文表示 / 統計
python -m knowledgeseeker list --limit 30
python -m knowledgeseeker show 12
python -m knowledgeseeker stats

# 新着記事のデイリーダイジェスト (digests/YYYY-MM-DD.md) を生成
python -m knowledgeseeker digest            # 過去24時間の新着が対象
python -m knowledgeseeker digest --hours 6  # 対象期間を変更
```

## データの永続化とデイリーログ

- 記事データは `data/articles.jsonl` に書き出され、git で管理されます
  (`collect` 実行時に自動で import / export)。SQLite DB (`data/articles.db`)
  は検索用のローカルキャッシュで、JSONL から自動復元されます。
- `digest` は新着記事のまとめを `digests/YYYY-MM-DD.md` に生成します。
  「## ハイライト」節はプレースホルダになっており、定期実行時に Claude が
  テーマ別の要約を記入します。手動で `export` / `import` も実行できます。

記事は `data/articles.db` (SQLite) に保存されます。`--db PATH` で変更できます。
`-v` で収集時の詳細ログを表示します。

## sources.yaml の書き方

```yaml
rss:
  - name: "simonwillison"
    url: "https://simonwillison.net/atom/everything/"
    fetch_full_content: true   # 要約が短い場合、元ページから全文を抽出する

web:
  - name: "anthropic"
    url: "https://www.anthropic.com/news/"
    selector: "PublicationList-module-scss-module__KxYrHG__list"
```

- **rss**: RSS 2.0 / Atom / RDF に対応。`fetch_full_content: true` の場合、
  フィード内の本文が約 500 文字未満ならリンク先ページを取得して本文を抽出します。
- **web**: `selector` は CSS セレクタ(`article.post` など)。クラス名や id を
  そのまま書いても解釈されます。一致した要素内の同一ホストへのリンクを記事として
  たどり、各ページの本文を保存します。`selector` を省略するとページ全体を
  1 つの記事として保存します。

## 注意

- 1 ソースあたりの取得は最大 50 記事、リクエスト間隔は 1 秒です
  (`knowledgeseeker/collectors.py`, `knowledgeseeker/fetch.py` で調整可)。
- Hacker News などリンク先が外部サイトになるフィードは、実行環境の
  ネットワークポリシーで全ホストへのアクセスが許可されている必要があります。
  許可されていない場合や、リンク先サイトがボットアクセスを拒否 (403) する場合は、
  タイトルと URL のみ保存されます。後から `--refresh` で全文を取り直せます。
