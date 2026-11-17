"""sources.yaml の読み込み"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "sources.yaml"


@dataclass
class RssSource:
    name: str
    url: str
    fetch_full_content: bool = False


@dataclass
class WebSource:
    name: str
    url: str
    selector: str | None = None


@dataclass
class Config:
    rss: list[RssSource] = field(default_factory=list)
    web: list[WebSource] = field(default_factory=list)

    @property
    def all_names(self) -> list[str]:
        return [s.name for s in self.rss] + [s.name for s in self.web]


def load_config(path: str | Path | None = None) -> Config:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    rss = [
        RssSource(
            name=item["name"],
            url=item["url"],
            fetch_full_content=bool(item.get("fetch_full_content", False)),
        )
        for item in raw.get("rss") or []
    ]
    web = [
        WebSource(
            name=item["name"],
            url=item["url"],
            selector=item.get("selector"),
        )
        for item in raw.get("web") or []
    ]
    return Config(rss=rss, web=web)
