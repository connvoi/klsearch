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
from .storage import Storage


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
        for source, collector in sources:
            saved, skipped = collector(source, storage)
            total_saved += saved
            total_skipped += skipped
            print(f"{source.name}: 新規 {saved} 件 / スキップ {skipped} 件")
    print(f"合計: 新規 {total_saved} 件 / スキップ {total_skipped} 件")
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
    p.set_defaults(func=cmd_collect)

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
