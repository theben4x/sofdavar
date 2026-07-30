"""נרמול טקסט עברי לחיפוש, ויצירת slugים.

כל החיפוש באתר עובר דרך המודול הזה. הכלל: מה שנכנס לאינדקס ומה שנכנס
לשאילתה חייבים לעבור *בדיוק* את אותו נרמול, אחרת "בשבת" לא ימצא את "שבת".
"""

from __future__ import annotations

import re
import unicodedata

# טעמי המקרא, הניקוד, ה-dagesh וה-sin/shin dot — כולם צירופים (Mn) בטווח הזה.
_NIQQUD_RE = re.compile(r"[֑-ׇֽֿׁׂׅׄ]")

# מקף עברי, פסק, סוף פסוק, גרש וגרשיים — מפרידים או רעש, לא אותיות.
_HEB_PUNCT_RE = re.compile(r"[־׀׃׆׳״]")

_FINALS = str.maketrans("ךםןףץ", "כמנפצ")

# אותיות שימוש שאפשר להסיר מתחילת מילה. ו' ראשונה, ואז ה/ב/כ/ל/מ/ש.
_PREFIX_LETTERS = frozenset("והבכלמש")

# האורך המינימלי שנשאר אחרי הסרת תחילית. "לחם" ו"משה" לא ייחתכו.
_MIN_STEM_LEN = 3

_WORD_RE = re.compile(r"[֐-׿A-Za-z0-9]+")


def strip_niqqud(text: str) -> str:
    """מסיר ניקוד וטעמים, משאיר את האותיות."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = _NIQQUD_RE.sub("", text)
    return unicodedata.normalize("NFC", text)


def normalize(text: str) -> str:
    """צורה קנונית להשוואה: בלי ניקוד, בלי סופיות, אותיות קטנות."""
    if not text:
        return ""
    text = strip_niqqud(text)
    text = _HEB_PUNCT_RE.sub(" ", text)
    text = text.replace("'", " ").replace('"', " ").replace("`", " ")
    text = text.translate(_FINALS)
    return text.lower()


def tokenize(text: str) -> list[str]:
    """מפרק לטוקנים מנורמלים."""
    return _WORD_RE.findall(normalize(text))


def stems(word: str) -> list[str]:
    """המילה עצמה + גרסאות בלי אותיות שימוש.

    מסירים לכל היותר שתי תחיליות ("והשבת" -> "השבת" -> "שבת"), ורק כל עוד
    נשארות לפחות שלוש אותיות. הסרה שגויה מייצרת טוקן שלא קיים בשום שאילתה,
    כלומר רעש בלתי מזיק — אבל אי-הסרה שוברת חיפוש אמיתי, ולכן מעדיפים להסיר.
    """
    out = [word]
    current = word
    for _ in range(2):
        if len(current) > _MIN_STEM_LEN and current[0] in _PREFIX_LETTERS:
            current = current[1:]
            out.append(current)
        else:
            break
    return out


def index_text(*parts: str | None) -> str:
    """בונה את הטקסט שנכנס לעמודת ה-FTS.

    כל מילה נכנסת יחד עם הגְזָעים שלה, כדי שמסמך שכתוב בו "בשבת" יימצא גם
    בשאילתה "שבת" — וההפך מטופל בנרמול השאילתה.
    """
    tokens: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        for token in tokenize(part):
            for stem in stems(token):
                if stem not in seen:
                    seen.add(stem)
                    tokens.append(stem)
    return " ".join(tokens)


def fts_query(raw: str, *, prefix: bool = True) -> str:
    """הופך קלט חופשי לשאילתת FTS5 בטוחה.

    לא מעבירים קלט משתמש ל-FTS5 כמו שהוא: תווים כמו ``*``, ``:``, ``^``
    ו-``NEAR`` הם תחביר, וקלט שבור מפיל את השאילתה. לכן מפרקים לטוקנים
    בעצמנו ומרכיבים מחדש רק ממחרוזות במרכאות.
    """
    tokens = tokenize(raw)
    if not tokens:
        return ""

    clauses: list[str] = []
    for token in tokens:
        variants: list[str] = []
        seen: set[str] = set()
        for stem in stems(token):
            if stem in seen:
                continue
            seen.add(stem)
            quoted = '"' + stem.replace('"', "") + '"'
            variants.append(quoted + "*" if prefix else quoted)
        clauses.append("(" + " OR ".join(variants) + ")")
    return " AND ".join(clauses)


def slugify(text: str, *, max_words: int = 8, max_chars: int = 70) -> str:
    """slug עברי קריא.

    מאז שכתובת השאלה היא ``/q/<code>``, ה-slug אינו הכתובת אלא רק המפתח
    שמאפשר לכתובות הישנות להמשיך להפנות פנימה. הוא נשמר במסד ואינו מוצג
    לגולש. ראה ``app/codes.py``.
    """
    text = strip_niqqud(text or "")
    text = _HEB_PUNCT_RE.sub(" ", text)
    text = re.sub(r"[^֐-׿A-Za-z0-9]+", " ", text)
    words = [w for w in text.split() if w][:max_words]
    slug = "-".join(words)[:max_chars].strip("-")
    return slug or "item"


def unique_slug(base: str, taken: set[str]) -> str:
    """מוסיף סיומת מספרית רק כשצריך, ורושם את התוצאה ב-``taken``."""
    slug = base
    counter = 2
    while slug in taken:
        slug = f"{base}-{counter}"
        counter += 1
    taken.add(slug)
    return slug


_HEB_NUMERALS = [
    (400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"),
    (90, "צ"), (80, "פ"), (70, "ע"), (60, "ס"), (50, "נ"),
    (40, "מ"), (30, "ל"), (20, "כ"), (10, "י"),
    (9, "ט"), (8, "ח"), (7, "ז"), (6, "ו"), (5, "ה"),
    (4, "ד"), (3, "ג"), (2, "ב"), (1, "א"),
]


def to_hebrew_numeral(value: int, *, gershayim: bool = True) -> str:
    """מספר לגימטריה. משמש לתאריך העברי בעמוד הזמנים."""
    if value <= 0:
        return ""
    value %= 1000
    out = ""
    for amount, letter in _HEB_NUMERALS:
        while value >= amount:
            out += letter
            value -= amount
    # טו/טז ולא יה/יו, מטעמי שם.
    out = out.replace("יה", "טו").replace("יו", "טז")
    if not gershayim:
        return out
    if len(out) == 1:
        return out + "'"
    return out[:-1] + '"' + out[-1]
