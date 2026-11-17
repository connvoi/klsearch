"""RSS 2.0 / Atom / RDF フィードのパーサ(lxml ベース、外部依存なし)"""

from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from lxml import etree

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss1": "http://purl.org/rss/1.0/",
}


@dataclass
class FeedEntry:
    title: str
    url: str
    published: str | None  # ISO 8601
    summary: str  # HTML のままの要約/本文


def _text(el) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip() if len(el) else (el.text or "").strip()


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    # RFC 822 (RSS)
    try:
        return parsedate_to_datetime(value).isoformat()
    except (ValueError, TypeError):
        pass
    # ISO 8601 (Atom)
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def parse_feed(xml_text: str) -> list[FeedEntry]:
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
    root = etree.fromstring(xml_text.encode("utf-8"), parser=parser)
    if root is None:
        return []
    tag = etree.QName(root).localname.lower()
    if tag == "feed":
        return _parse_atom(root)
    if tag == "rss":
        return _parse_rss2(root)
    if tag == "rdf":
        return _parse_rss1(root)
    return []


def _parse_atom(root) -> list[FeedEntry]:
    entries = []
    for entry in root.findall("atom:entry", NS):
        link = ""
        for l in entry.findall("atom:link", NS):
            rel = l.get("rel", "alternate")
            if rel == "alternate":
                link = l.get("href", "")
                break
        if not link:
            first = entry.find("atom:link", NS)
            link = first.get("href", "") if first is not None else ""
        content = entry.find("atom:content", NS)
        summary = entry.find("atom:summary", NS)
        body_el = content if content is not None else summary
        body = (body_el.text or _text(body_el)) if body_el is not None else ""
        published = entry.find("atom:published", NS)
        updated = entry.find("atom:updated", NS)
        date_el = published if published is not None else updated
        entries.append(
            FeedEntry(
                title=_text(entry.find("atom:title", NS)),
                url=link,
                published=_parse_date(date_el.text if date_el is not None else None),
                summary=body or "",
            )
        )
    return [e for e in entries if e.url]


def _parse_rss2(root) -> list[FeedEntry]:
    entries = []
    for item in root.findall(".//item"):
        encoded = item.find("content:encoded", NS)
        description = item.find("description")
        body = ""
        if encoded is not None and encoded.text:
            body = encoded.text
        elif description is not None and description.text:
            body = description.text
        pub = item.find("pubDate")
        dc_date = item.find("dc:date", NS)
        date_text = pub.text if pub is not None else (dc_date.text if dc_date is not None else None)
        link = item.find("link")
        entries.append(
            FeedEntry(
                title=_text(item.find("title")),
                url=(link.text or "").strip() if link is not None else "",
                published=_parse_date(date_text),
                summary=body,
            )
        )
    return [e for e in entries if e.url]


def _parse_rss1(root) -> list[FeedEntry]:
    entries = []
    for item in root.findall("rss1:item", NS):
        description = item.find("rss1:description", NS)
        link = item.find("rss1:link", NS)
        dc_date = item.find("dc:date", NS)
        entries.append(
            FeedEntry(
                title=_text(item.find("rss1:title", NS)),
                url=(link.text or "").strip() if link is not None else "",
                published=_parse_date(dc_date.text if dc_date is not None else None),
                summary=_text(description),
            )
        )
    return [e for e in entries if e.url]
