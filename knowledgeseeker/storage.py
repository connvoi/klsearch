"""SQLite + FTS5 による記事の保存と全文検索"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "articles.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    published   TEXT,
    fetched_at  TEXT NOT NULL,
    content     TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title,
    content,
    content='articles',
    content_rowid='id',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;

CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO articles_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;
"""


@dataclass
class Article:
    source: str
    title: str
    url: str
    published: str | None
    content: str


class Storage:
    def __init__(self, db_path: str | Path | None = None):
        path = Path(db_path) if db_path else DEFAULT_DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def has_url(self, url: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM articles WHERE url = ?", (url,)
        ).fetchone()
        return row is not None

    def save(self, article: Article, replace: bool = False) -> bool:
        """保存する。URL が既存なら False(スキップ)。replace=True なら上書き更新。"""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        params = (
            article.source,
            article.title,
            article.url,
            article.published,
            now,
            article.content,
        )
        if replace:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO articles (source, title, url, published, fetched_at, content)"
                    " VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(url) DO UPDATE SET"
                    "   source = excluded.source,"
                    "   title = excluded.title,"
                    "   published = COALESCE(excluded.published, articles.published),"
                    "   fetched_at = excluded.fetched_at,"
                    "   content = excluded.content",
                    params,
                )
            return True
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO articles (source, title, url, published, fetched_at, content)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    params,
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def search(self, query: str, limit: int = 20) -> list[sqlite3.Row]:
        # trigram トークナイザはクエリをそのままフレーズとして扱えるよう引用符で囲む
        fts_query = " ".join(f'"{term}"' for term in query.split())
        return self.conn.execute(
            """
            SELECT a.id, a.source, a.title, a.url, a.published,
                   snippet(articles_fts, 1, '[', ']', '…', 24) AS snippet
            FROM articles_fts
            JOIN articles a ON a.id = articles_fts.rowid
            WHERE articles_fts MATCH ?
            ORDER BY bm25(articles_fts)
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()

    def list_articles(
        self, source: str | None = None, limit: int = 20
    ) -> list[sqlite3.Row]:
        if source:
            return self.conn.execute(
                "SELECT id, source, title, url, published, fetched_at"
                " FROM articles WHERE source = ?"
                " ORDER BY COALESCE(published, fetched_at) DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        return self.conn.execute(
            "SELECT id, source, title, url, published, fetched_at"
            " FROM articles ORDER BY COALESCE(published, fetched_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def get(self, article_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ).fetchone()

    def stats(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT source, COUNT(*) AS count, MAX(fetched_at) AS last_fetched"
            " FROM articles GROUP BY source ORDER BY source"
        ).fetchall()
