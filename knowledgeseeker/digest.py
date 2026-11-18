"""デイリーダイジェスト (markdown) の生成"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .storage import Storage

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "digests"

HIGHLIGHTS_PLACEHOLDER = "_(ハイライト未記入)_"


def build_digest(storage: Storage, hours: int = 24, now: datetime | None = None) -> str:
    """過去 hours 時間に取得した記事のダイジェスト markdown を組み立てる。"""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=hours)).isoformat(timespec="seconds")
    rows = storage.fetched_since(cutoff)

    date_label = now.astimezone(JST).strftime("%Y-%m-%d")
    lines = [
        f"# KnowledgeSeeker デイリーダイジェスト {date_label}",
        "",
        f"収集期間: 過去 {hours} 時間 / 新着 {len(rows)} 件",
        "",
    ]

    # ソース別件数
    by_source: dict[str, list] = {}
    for row in rows:
        by_source.setdefault(row["source"], []).append(row)

    if by_source:
        lines += ["| ソース | 新着 |", "|---|---|"]
        for source in sorted(by_source):
            lines.append(f"| {source} | {len(by_source[source])} |")
        lines.append("")

    lines += ["## ハイライト", "", HIGHLIGHTS_PLACEHOLDER, ""]

    if not rows:
        lines += ["## 新着記事", "", "新着はありませんでした。", ""]
        return "\n".join(lines)

    lines += ["## 新着記事", ""]
    for source in sorted(by_source):
        lines.append(f"### {source}")
        lines.append("")
        for row in by_source[source]:
            published = (row["published"] or "")[:10]
            date_part = f" ({published})" if published else ""
            lines.append(f"- **[{row['title']}]({row['url']})**{date_part}")
            excerpt = " ".join((row["head"] or "").split())
            if len(excerpt) > 200:
                excerpt = excerpt[:200] + "…"
            if excerpt and excerpt.lower() not in ("comments", "view in english"):
                lines.append(f"  - {excerpt}")
        lines.append("")
    return "\n".join(lines)


def write_digest(
    storage: Storage,
    hours: int = 24,
    out_dir: str | Path | None = None,
    now: datetime | None = None,
) -> Path:
    """ダイジェストを digests/YYYY-MM-DD.md (JST 日付) に書き出してパスを返す。"""
    now = now or datetime.now(timezone.utc)
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{now.astimezone(JST).strftime('%Y-%m-%d')}.md"
    path.write_text(build_digest(storage, hours=hours, now=now), encoding="utf-8")
    return path
