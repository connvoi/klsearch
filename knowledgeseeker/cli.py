"""コマンドラインインターフェース

使い方:
    python -m knowledgeseeker collect [--source NAME] [--config PATH]
    python -m knowledgeseeker search QUERY [--limit N]
    python -m knowledgeseeker list [--source NAME] [--limit N]
    python -m knowledgeseeker show ID
    python -m knowledgeseeker stats
"""

import argparse
import logging
import sys

from .collectors import collect_rss, collect_web
from .config import load_config
from .digest import write_digest
from .storage import DEFAULT_JSONL_PATH, Storage


def cmd_collect(args) -> int:
    config = load_config(args.config)
    sources = [(s, collect_rss) for s in config.rss] + [
        (s, collect_web) for s in config.web
    ]
    if args.source:
        sources = [(s, fn) for s, fn in sources if s.name == args.source]
        if not sources:
            print(f"ソース '{args.source}' が見つかりません。", file=sys.stderr)
            print(f"利用可能: {', '.join(config.all_names)}", file=sys.stderr)
            return 1

    total_saved = total_skipped = 0
    with Storage(args.db) as storage:
        # git 管理の JSONL があれば取り込む (コンテナ再作成後の DB 復元)
        imported = storage.import_jsonl(DEFAULT_JSONL_PATH)
        if imported:
            print(f"articles.jsonl から {imported} 件を復元")
        for source, collector in sources:
            saved, skipped = collector(source, storage, refresh=args.refresh)
            total_saved += saved
            total_skipped += skipped
            print(f"{source.name}: 新規 {saved} 件 / スキップ {skipped} 件")
        # 収集結果を JSONL に書き戻す (git でコミットして永続化)
        count = storage.export_jsonl(DEFAULT_JSONL_PATH)
    print(f"合計: 新規 {total_saved} 件 / スキップ {total_skipped} 件")
    print(f"articles.jsonl へ {count} 件を書き出しました")
    return 0


def cmd_digest(args) -> int:
    with Storage(args.db) as storage:
        if args.stdout:
            from .digest import build_digest

            print(build_digest(storage, hours=args.hours))
            return 0
        path = write_digest(storage, hours=args.hours, out_dir=args.out_dir)
        print(f"ダイジェストを書き出しました: {path}")
    return 0


def cmd_export(args) -> int:
    with Storage(args.db) as storage:
        count = storage.export_jsonl(args.path or DEFAULT_JSONL_PATH)
        print(f"{count} 件を書き出しました")
    return 0


def cmd_import(args) -> int:
    with Storage(args.db) as storage:
        count = storage.import_jsonl(args.path or DEFAULT_JSONL_PATH)
        print(f"{count} 件を取り込みました")
    return 0


def cmd_search(args) -> int:
    with Storage(args.db) as storage:
        rows = storage.search(args.query, limit=args.limit)
        if not rows:
            print("該当する記事はありません。")
            return 0
        for row in rows:
            print(f"[{row['id']}] {row['title']}  ({row['source']})")
            print(f"    {row['url']}")
            snippet = " ".join(row["snippet"].split())
            print(f"    {snippet}")
            print()
    return 0


def cmd_list(args) -> int:
    with Storage(args.db) as storage:
        rows = storage.list_articles(source=args.source, limit=args.limit)
        if not rows:
            print("記事がありません。まず collect を実行してください。")
            return 0
        for row in rows:
            date = (row["published"] or row["fetched_at"] or "")[:10]
            print(f"[{row['id']}] {date}  {row['title']}  ({row['source']})")
    return 0


def cmd_show(args) -> int:
    with Storage(args.db) as storage:
        row = storage.get(args.id)
        if row is None:
            print(f"ID {args.id} の記事はありません。", file=sys.stderr)
            return 1
        print(f"タイトル: {row['title']}")
        print(f"ソース  : {row['source']}")
        print(f"URL     : {row['url']}")
        print(f"公開日  : {row['published'] or '不明'}")
        print(f"取得日  : {row['fetched_at']}")
        print()
        print(row["content"])
    return 0


def cmd_stats(args) -> int:
    with Storage(args.db) as storage:
        rows = storage.stats()
        if not rows:
            print("記事がありません。")
            return 0
        total = 0
        for row in rows:
            print(f"{row['source']}: {row['count']} 件 (最終取得 {row['last_fetched']})")
            total += row["count"]
        print(f"合計: {total} 件")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="knowledgeseeker",
        description="RSS / Web ページから記事を収集して全文検索するツール",
    )
    parser.add_argument("--db", help="SQLite DB のパス (既定: data/articles.db)")
    parser.add_argument("-v", "--verbose", action="store_true", help="詳細ログを表示")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="sources.yaml の全ソースから記事を収集する")
    p.add_argument("--source", help="このソース名だけ収集する")
    p.add_argument("--config", help="設定ファイルのパス (既定: sources.yaml)")
    p.add_argument(
        "--refresh",
        action="store_true",
        help="既存の記事も再取得して上書き更新する",
    )
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("digest", help="新着記事のダイジェスト markdown を生成する")
    p.add_argument("--hours", type=int, default=24, help="過去 N 時間の新着を対象 (既定: 24)")
    p.add_argument("--out-dir", help="出力先ディレクトリ (既定: digests/)")
    p.add_argument("--stdout", action="store_true", help="ファイルに書かず標準出力へ")
    p.set_defaults(func=cmd_digest)

    p = sub.add_parser("export", help="全記事を data/articles.jsonl に書き出す")
    p.add_argument("--path", help="出力先 (既定: data/articles.jsonl)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import", help="data/articles.jsonl から記事を取り込む")
    p.add_argument("--path", help="入力元 (既定: data/articles.jsonl)")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("search", help="収集済み記事を全文検索する")
    p.add_argument("query", help="検索キーワード")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("list", help="収集済み記事を新しい順に一覧する")
    p.add_argument("--source", help="このソース名だけ表示する")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="記事の本文を表示する")
    p.add_argument("id", type=int, help="記事 ID (list / search で表示される番号)")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stats", help="ソースごとの収集状況を表示する")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    return args.func(args)
