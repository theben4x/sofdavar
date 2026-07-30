"""קודים קצרים לכתובות של עמודי שאלה.

הכתובת של שאלה הייתה ``/<קטגוריה>/<slug עברי>``. שלוש בעיות היו בה:

* **אורך.** slug עברי באורך 70 תווים הופך ל-‎400 תווים של אחוזי-קידוד.
* **שיתוף.** כתובת כזאת נשברת ביישומונים שמזהים סוף קישור לפי רווח או
  לפי תו לא-ASCII, ובראשם וואטסאפ.
* **יציבות.** ה-slug נגזר מנוסח השאלה, ולכן כל תיקון בכותרת שינה את
  הכתובת והפיל כל קישור ישן.

הפתרון הוא קוד קצר, קבוע ואטום: ``/q/k7m2``. הוא לא נגזר מהטקסט ולא
מהמיקום, ולכן הוא שורד גם ניסוח מחדש וגם הכנסת שאלה באמצע. הוא נשמר
ב-``data/seed/questions.json`` ליד השאלה עצמה, כי המסד עצמו נבנה מחדש
בכל פריסה — ומה שלא יושב בקובץ המקור, אינו קיים.

לא ``number``: המספר הרץ ממוספר מחדש בכל ייבוא (ראה ``renumber_questions``),
ושאלה שנוספת בקטגוריה מוקדמת מזיזה את כל מי שאחריה.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable

#: בלי 0/1/i/l/o — הזוגות שמתחלפים בקריאה ובהכתבה בטלפון.
ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"

#: ארבעה תווים = 923,521 צירופים. גם ב-20,000 שאלות התפוסה היא 2%,
#: וההגרלה החוזרת במקרה של התנגשות כמעט לעולם לא נדרשת.
CODE_LENGTH = 4


def is_code(value: str) -> bool:
    """האם המחרוזת נראית כמו קוד — לשימוש הניתוב, לפני פנייה למסד."""
    return (
        len(value) == CODE_LENGTH
        and all(character in ALPHABET for character in value)
    )


def random_code(taken: Iterable[str] = ()) -> str:
    """קוד חדש שאינו תפוס. ``secrets`` ולא ``random``: אין כאן צורך
    בהצפנה, אבל גם אין סיבה לזרע צפוי שייתן את אותם קודים בכל מכונה."""
    used = set(taken)
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        if code not in used:
            return code


def derive_code(seed: str, taken: Iterable[str] = ()) -> str:
    """קוד דטרמיניסטי מטקסט — גיבוי בלבד, לשאלה שהגיעה בלי קוד.

    הבנייה חייבת להצליח גם כשמישהו הוסיף שאלה לקובץ ה-seed ושכח להריץ
    ``scripts/assign_codes.py``, ולכן נגזר כאן קוד מגיבוב הטקסט. הוא
    יציב כל עוד הטקסט לא משתנה — כלומר בדיוק הבעיה שהקוד נועד לפתור,
    ומכאן האזהרה שהבנייה מדפיסה. אין להסתמך עליו לאורך זמן.
    """
    used = set(taken)
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    for attempt in range(256):
        material = digest if attempt == 0 else hashlib.sha256(
            digest + bytes([attempt])
        ).digest()
        code = "".join(ALPHABET[byte % len(ALPHABET)] for byte in material[:CODE_LENGTH])
        if code not in used:
            return code
    return random_code(used)
