"""פרשת השבוע — קריאה מלוח בנוי מראש.

המודול המשלים ל-``app.hebcal``, שמחשב את הלוח העברי מקומית אבל מוסר במפורש
את סדר הפרשיות: הוא תלוי בטבלת קביעויות (אילו זוגות מחוברים בכל אחד מארבעה־
עשר טיפוסי השנה), ובאתר הלכה פרשה שגויה היא טעות שנראית כל שבוע מחדש.

הלוח נבנה פעם אחת ע"י ``scripts/build_parasha.py`` אל ``data/parasha.json``.
בזמן ריצה אין רשת ואין חישוב — רק חיפוש במילון.

הלוח הוא של **ארץ ישראל**. שבת שאין בה פרשה (יום טוב, חול המועד) פשוט
חסרה מהמילון, ולכן ``for_shabbat`` מחזיר ``None`` — ואת המקום תופס שם החג.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from . import hebcal

_DATA = Path(__file__).resolve().parent.parent / "data" / "parasha.json"


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    """הלוח, נטען פעם אחת. חסר או פגום — מחזיר ריק במקום להפיל את האתר."""
    try:
        with _DATA.open(encoding="utf-8") as handle:
            return json.load(handle)["shabbatot"]
    except (OSError, ValueError, KeyError):
        return {}


def for_shabbat(saturday: date) -> str | None:
    """שם הפרשה הנקראת בשבת הנתונה, או ``None`` אם אין בה פרשה."""
    return _table().get(saturday.isoformat())


def coming_saturday(today: date | None = None) -> date:
    """השבת הקרובה. בשבת עצמה — היום."""
    today = today or date.today()
    return today + timedelta(days=(5 - today.weekday()) % 7)


def label(saturday: date) -> str | None:
    """מה להציג לשבת הזו: שם הפרשה, ובשבת של מועד — שם המועד.

    יום טוב דוחה את הפרשה, ולכן "פרשת השבוע" ריקה בדיוק בשבתות שבהן יש
    לרוב מה להציג במקומה.
    """
    name = for_shabbat(saturday)
    if name:
        return f"פרשת {name}"

    # לא רק yomtov: שבת חול המועד גם היא בלי פרשה, והדגל שלה False.
    # נבדק על 2026-2030 — לכל שבת בלי פרשה יש בדיוק מועד אחד.
    holidays = hebcal.holidays_for(saturday)
    for holiday in holidays:
        if holiday["yomtov"]:
            return holiday["name"]
    return holidays[0]["name"] if holidays else None
