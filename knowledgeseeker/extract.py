"""HTML からの本文抽出(簡易 readability)

trafilatura 等の外部ライブラリに依存せず、BeautifulSoup で
「それらしい本文ブロック」を選んでプレーンテキスト化する。
"""

import re

from bs4 import BeautifulSoup

# 本文に含めないタグ
_STRIP_TAGS = [
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "iframe",
    "svg",
    "button",
]

# 広告・ナビっぽい class/id
_NOISE_RE = re.compile(
    r"(comment|sidebar|share|social|related|breadcrumb|menu|banner|cookie|promo|subscribe)",
    re.I,
)


def html_to_text(html: str) -> str:
    """HTML 断片をプレーンテキストにする。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return _normalize(text)


def extract_main_text(html: str) -> str:
    """ページ全体の HTML から本文らしきテキストを抽出する。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"class": _NOISE_RE}):
        tag.decompose()
    for tag in soup.find_all(attrs={"id": _NOISE_RE}):
        tag.decompose()

    # 1. <article> / <main> / role=main を優先
    for selector in ("article", "main", '[role="main"]'):
        candidates = soup.select(selector)
        if candidates:
            best = max(candidates, key=lambda el: len(el.get_text()))
            text = _normalize(best.get_text(separator="\n"))
            if len(text) > 200:
                return text

    # 2. テキスト量が最大の <div> を探す
    best_text = ""
    for div in soup.find_all("div"):
        # 直下にテキストの多い段落を持つものを優先
        own = "\n".join(
            p.get_text(separator="\n") for p in div.find_all("p", recursive=False)
        )
        if len(own) > len(best_text):
            best_text = own
    if len(best_text) > 200:
        return _normalize(best_text)

    # 3. フォールバック: body 全体
    body = soup.body or soup
    return _normalize(body.get_text(separator="\n"))


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def _normalize(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    out: list[str] = []
    blank = 0
    for line in lines:
        if line:
            out.append(line)
            blank = 0
        else:
            blank += 1
            if blank == 1 and out:
                out.append("")
    return "\n".join(out).strip()
