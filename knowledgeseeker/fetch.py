"""HTTP 取得まわり(リトライ・待機つき)"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

USER_AGENT = "KnowledgeSeeker/0.1 (+https://github.com/connvoi/klsearch)"
TIMEOUT = 30
RETRIES = 2
RETRY_WAIT = 3.0

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})

# サイトへの連続アクセスを避けるための最小間隔(秒)
REQUEST_INTERVAL = 1.0
_last_request_at = 0.0


def fetch(url: str) -> requests.Response | None:
    """URL を取得する。失敗したら None を返す(例外は投げない)。"""
    global _last_request_at
    for attempt in range(RETRIES + 1):
        wait = REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()
        try:
            resp = _session.get(url, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp
            # 4xx はリトライしても無駄
            if 400 <= resp.status_code < 500:
                logger.warning("%s -> HTTP %s (スキップ)", url, resp.status_code)
                return None
            logger.warning("%s -> HTTP %s", url, resp.status_code)
        except requests.RequestException as e:
            logger.warning("%s -> %s", url, e)
        if attempt < RETRIES:
            time.sleep(RETRY_WAIT * (attempt + 1))
    return None


def fetch_text(url: str) -> str | None:
    """URL からテキスト (HTML/XML) を取得する。バイナリ等は None。"""
    resp = fetch(url)
    if resp is None:
        return None
    ctype = resp.headers.get("Content-Type", "").lower()
    if ctype and not ("html" in ctype or "xml" in ctype or ctype.startswith("text/")):
        logger.warning("%s -> テキストでない Content-Type: %s (スキップ)", url, ctype)
        return None
    if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp.text
