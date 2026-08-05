"""מביא את הלכות שבת שברמב"ם במלואן מספריא, ומוסיף אותן ל-sefaria.json.

    python scripts/fetch_rambam_shabbat.py

``fetch_sefaria.py`` מביא הפניה אחת בכל פעם, לפי רשימה שהוכנה מראש.
כאן הצורך הפוך: אין רשימה, ורוצים את כל ההלכות כדי שאפשר יהיה לחפש
בהן את המקום שמתאים לשאלה. לכן ההבאה היא פרק שלם בכל קריאה.

הרמב"ם הוא נחלת הכלל, ולכן מותר להביאו בלשונו המלאה — וזה גם מה
שמייתר את הניחוש: מקור שהשרת לא החזיר פשוט אינו נכנס לקובץ.

TLS: הרשת כאן מיירטת תעודות ו-``certifi`` נכשל עליהן, ולכן ``truststore``.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    print("! truststore לא מותקן — ייתכן ש-SSL ייכשל.  pip install truststore")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "seed" / "sefaria.json"
API = "https://www.sefaria.org/api/v3/texts/"

BOOK = "Mishneh_Torah,_Sabbath"
TITLE = "משנה תורה, הלכות שבת"
CHAPTERS = 30

TAGS = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return " ".join(TAGS.sub(" ", text).split())


def fetch_chapter(chapter: int, *, retries: int = 3) -> list[str]:
    url = API + urllib.parse.quote(f"{BOOK}.{chapter}") + "?version=hebrew"
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=40) as response:
                data: dict[str, Any] = json.loads(response.read())
            versions = data.get("versions") or []
            if not versions:
                return []
            raw = versions[0].get("text")
            # פרק שלם חוזר כרשימת הלכות; הפניה בודדת חוזרת כמחרוזת.
            return [strip_html(t) for t in raw] if isinstance(raw, list) else [strip_html(raw)]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries:
                print(f"  ! פרק {chapter}: {exc}")
                return []
            time.sleep(1.5 * (attempt + 1))
    return []


def main() -> int:
    store: dict[str, Any] = json.loads(OUT.read_text(encoding="utf-8"))
    before = len(store)
    added = 0

    for chapter in range(1, CHAPTERS + 1):
        halachot = fetch_chapter(chapter)
        if not halachot:
            print(f"  · פרק {chapter}: ריק — לא נכתב")
            continue
        for index, text in enumerate(halachot, start=1):
            if not text:
                continue
            ref = f"{BOOK}.{chapter}.{index}"
            if ref in store:
                continue
            store[ref] = {
                "ref": ref,
                "found": True,
                "text": text,
                "he_ref": f"{TITLE} {chapter}:{index}",
                "title": "משנה תורה",
            }
            added += 1
        print(f"  · פרק {chapter}: {len(halachot)} הלכות")
        time.sleep(0.3)  # אדיבות לשרת ציבורי חינמי

    OUT.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n  · {added} הלכות חדשות. סך המקורות: {before}, ואחרי ההוספה {len(store)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
