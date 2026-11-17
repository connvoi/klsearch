"""RSS / Web ページからの収集ロジック"""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .config import RssSource, WebSource
from .extract import extract_main_text, extract_title, html_to_text
from .fetch import fetch_text
from .feed import parse_feed
from .storage import Article, Storage

logger = logging.getLogger(__name__)

# RSS の要約がこれより短ければ「短い」とみなし元ページから全文を取る
FULL_CONTENT_THRESHOLD = 500
# 1ソースあたりの最大取得記事数(初回の暴走防止)
MAX_ARTICLES_PER_SOURCE = 50


def collect_rss(
    source: RssSource, storage: Storage, refresh: bool = False
) -> tuple[int, int]:
    """RSS ソースを収集。(新規保存数, スキップ数) を返す。

    refresh=True の場合、既存 URL も再取得して上書き更新する。
    """
    logger.info("[%s] フィード取得: %s", source.name, source.url)
    xml_text = fetch_text(source.url)
    if xml_text is None:
        logger.error("[%s] フィードを取得できませんでした", source.name)
        return (0, 0)

    entries = parse_feed(xml_text)
    logger.info("[%s] %d 件のエントリ", source.name, len(entries))

    saved = skipped = 0
    for entry in entries[:MAX_ARTICLES_PER_SOURCE]:
        if not refresh and storage.has_url(entry.url):
            skipped += 1
            continue
        content = html_to_text(entry.summary) if entry.summary else ""
        if source.fetch_full_content and len(content) < FULL_CONTENT_THRESHOLD:
            page = fetch_text(entry.url)
            if page:
                full = extract_main_text(page)
                if len(full) > len(content):
                    content = full
        article = Article(
            source=source.name,
            title=entry.title or entry.url,
            url=entry.url,
            published=entry.published,
            content=content,
        )
        if storage.save(article, replace=refresh):
            saved += 1
            logger.info("[%s] 保存: %s", source.name, entry.title)
        else:
            skipped += 1
    return (saved, skipped)


def collect_web(
    source: WebSource, storage: Storage, refresh: bool = False
) -> tuple[int, int]:
    """Web ページソースを収集。(新規保存数, スキップ数) を返す。

    refresh=True の場合、既存 URL も再取得して上書き更新する。
    """
    logger.info("[%s] ページ取得: %s", source.name, source.url)
    html = fetch_text(source.url)
    if html is None:
        logger.error("[%s] ページを取得できませんでした", source.name)
        return (0, 0)

    if not source.selector:
        # セレクタなし: ページ全体を1つの記事として扱う
        if not refresh and storage.has_url(source.url):
            return (0, 1)
        article = Article(
            source=source.name,
            title=extract_title(html) or source.name,
            url=source.url,
            published=None,
            content=extract_main_text(html),
        )
        return (1, 0) if storage.save(article, replace=refresh) else (0, 1)

    soup = BeautifulSoup(html, "lxml")
    elements = _select(soup, source.selector)
    if not elements:
        logger.warning(
            "[%s] セレクタ '%s' に一致する要素がありません", source.name, source.selector
        )
        return (0, 0)

    # 一致した要素内のリンクを記事候補として収集する
    links = _harvest_links(elements, base_url=source.url)
    if not links:
        # リンクがなければ要素のテキスト自体を記事として保存
        if not refresh and storage.has_url(source.url):
            return (0, 1)
        text = "\n\n".join(html_to_text(str(el)) for el in elements)
        article = Article(
            source=source.name,
            title=extract_title(html) or source.name,
            url=source.url,
            published=None,
            content=text,
        )
        return (1, 0) if storage.save(article, replace=refresh) else (0, 1)

    saved = skipped = 0
    for url, link_text in links[:MAX_ARTICLES_PER_SOURCE]:
        if not refresh and storage.has_url(url):
            skipped += 1
            continue
        page = fetch_text(url)
        if page is None:
            continue
        title = extract_title(page) or link_text or url
        article = Article(
            source=source.name,
            title=title,
            url=url,
            published=None,
            content=extract_main_text(page),
        )
        if storage.save(article, replace=refresh):
            saved += 1
            logger.info("[%s] 保存: %s", source.name, title)
        else:
            skipped += 1
    return (saved, skipped)


def _select(soup: BeautifulSoup, selector: str):
    """CSS セレクタとして解釈し、失敗・空なら class 名や id として再解釈する。"""
    try:
        elements = soup.select(selector)
        if elements:
            return elements
    except Exception:
        pass
    elements = soup.find_all(class_=selector)
    if elements:
        return elements
    el = soup.find(id=selector)
    return [el] if el else []


def _harvest_links(elements, base_url: str) -> list[tuple[str, str]]:
    """要素内のリンクを (絶対URL, リンクテキスト) で返す。同一ホストのみ。"""
    base_host = urlparse(base_url).netloc
    seen: set[str] = set()
    links: list[tuple[str, str]] = []
    for el in elements:
        for a in el.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue
            url = urljoin(base_url, href)
            url = re.sub(r"#.*$", "", url)
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                continue
            if parsed.netloc != base_host:
                continue
            if url.rstrip("/") == base_url.rstrip("/"):
                continue
            if url in seen:
                continue
            seen.add(url)
            links.append((url, a.get_text(strip=True)))
    return links
