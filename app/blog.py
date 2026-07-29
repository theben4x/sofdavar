"""טעינת פוסטים מקבצי Markdown.

כל פוסט הוא קובץ ``.md`` עם front-matter פשוט בין שתי שורות ``---``.
אין תלות ב-YAML: הפורמט מכוון, ``key: value`` בלבד, כדי שאפשר יהיה להוסיף
פוסט בעורך טקסט בלי להתקין כלום.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import markdown

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_LIST_KEYS = {"tags"}


@dataclass(frozen=True)
class Post:
    slug: str
    title: str
    description: str
    date: date
    tags: tuple[str, ...]
    html: str
    reading_minutes: int

    @property
    def display_date(self) -> str:
        return self.date.strftime("%d.%m.%Y")


def _parse(path: Path) -> Post | None:
    raw = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER_RE.match(raw)
    if not match:
        return None

    meta: dict[str, object] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip().strip('"').strip("'")
        meta[key] = (
            tuple(part.strip() for part in value.split(",") if part.strip())
            if key in _LIST_KEYS
            else value
        )

    body = raw[match.end():]
    words = len(body.split())

    try:
        published = date.fromisoformat(str(meta.get("date", "")))
    except ValueError:
        published = date.fromtimestamp(path.stat().st_mtime)

    return Post(
        slug=str(meta.get("slug") or path.stem),
        title=str(meta.get("title") or path.stem),
        description=str(meta.get("description") or ""),
        date=published,
        tags=tuple(meta.get("tags") or ()),
        html=markdown.markdown(body, extensions=["extra", "sane_lists"]),
        # קצב קריאה בעברית נמוך יותר מאנגלית; 180 מילים לדקה זו הערכה סבירה.
        reading_minutes=max(1, round(words / 180)),
    )


@lru_cache(maxsize=1)
def _load(directory: str, _stamp: float) -> tuple[Post, ...]:
    path = Path(directory)
    if not path.is_dir():
        return ()
    posts = [p for p in (_parse(f) for f in sorted(path.glob("*.md"))) if p]
    return tuple(sorted(posts, key=lambda p: p.date, reverse=True))


def _stamp_for(directory: Path) -> float:
    """חותמת שמשתנה כשמוסיפים או עורכים פוסט, כדי לפסול את המטמון."""
    if not directory.is_dir():
        return 0.0
    return max((f.stat().st_mtime for f in directory.glob("*.md")), default=0.0)


def all_posts(directory: Path) -> tuple[Post, ...]:
    return _load(str(directory), _stamp_for(directory))


def get_post(directory: Path, slug: str) -> Post | None:
    return next((p for p in all_posts(directory) if p.slug == slug), None)
