"""לוח עברי: המרת תאריכים וזיהוי חגים — חישוב מקומי מלא, ללא רשת.

המימוש הוא האלגוריתם הסטנדרטי של קידוש החודש (מולד + ארבע הדחיות), אותו
אלגוריתם שמופיע ב-Calendrical Calculations ובלוח העברי של Emacs.

"תאריך מוחלט" כאן הוא מספר הימים מאז 1 בינואר שנת 1 לספירה, כשהיום הזה הוא 1.
זו בדיוק הקונבנציה של ``date.toordinal()`` בפייתון, ולכן ההמרה מלועזי היא
פונקציית ספרייה ולא קוד שלנו.

מה שלא מחושב כאן זו פרשת השבוע — סדר הפרשיות תלוי בטבלת קביעויות שקל לטעות
בה, ולכן הוא נטען מקובץ שנבנה מראש. ראה ``app/parasha.py``.
"""

from __future__ import annotations

from datetime import date

# היום המוחלט של א' תשרי שנת א' לבריאת העולם.
_HEBREW_EPOCH = -1373429

MONTH_NAMES = {
    1: "ניסן", 2: "אייר", 3: "סיוון", 4: "תמוז", 5: "אב", 6: "אלול",
    7: "תשרי", 8: "חשוון", 9: "כסלו", 10: "טבת", 11: "שבט",
    12: "אדר", 13: "אדר ב'",
}
MONTH_NAME_ADAR_I = "אדר א'"

NISAN, IYAR, SIVAN, TAMMUZ, AV, ELUL = 1, 2, 3, 4, 5, 6
TISHREI, CHESHVAN, KISLEV, TEVET, SHEVAT, ADAR_I, ADAR_II = 7, 8, 9, 10, 11, 12, 13


def gregorian_to_absolute(d: date) -> int:
    return d.toordinal()


def absolute_to_gregorian(absolute: int) -> date:
    return date.fromordinal(absolute)


def is_leap_year(year: int) -> bool:
    """שנה מעוברת במחזור י"ט השנים."""
    return ((7 * year + 1) % 19) < 7


def last_month_of_year(year: int) -> int:
    return ADAR_II if is_leap_year(year) else ADAR_I


def elapsed_days(year: int) -> int:
    """ימים מבריאת העולם עד א' תשרי של ``year``, אחרי הדחיות."""
    months_elapsed = (
        235 * ((year - 1) // 19)              # חודשים במחזורים שלמים
        + 12 * ((year - 1) % 19)              # חודשים רגילים במחזור הנוכחי
        + (7 * ((year - 1) % 19) + 1) // 19   # חודשי עיבור שכבר היו במחזור
    )
    parts_elapsed = 204 + 793 * (months_elapsed % 1080)
    hours_elapsed = (
        5 + 12 * months_elapsed
        + 793 * (months_elapsed // 1080)
        + parts_elapsed // 1080
    )
    day = 1 + 29 * months_elapsed + hours_elapsed // 24
    parts = 1080 * (hours_elapsed % 24) + parts_elapsed % 1080

    if (
        parts >= 19440                                                    # מולד זקן
        or (day % 7 == 2 and parts >= 9924 and not is_leap_year(year))    # ג"ט ר"ד
        or (day % 7 == 1 and parts >= 16789 and is_leap_year(year - 1))   # בט"ו תקפ"ט
    ):
        day += 1

    if day % 7 in (0, 3, 5):  # לא אד"ו ראש
        day += 1
    return day


def year_length(year: int) -> int:
    """353/354/355 בשנה פשוטה, 383/384/385 במעוברת."""
    return elapsed_days(year + 1) - elapsed_days(year)


def days_in_month(year: int, month: int) -> int:
    if month in (IYAR, TAMMUZ, ELUL, TEVET, ADAR_II):
        return 29
    if month == ADAR_I and not is_leap_year(year):
        return 29
    if month == CHESHVAN and year_length(year) % 10 != 5:  # מלא רק בשנה שלמה
        return 29
    if month == KISLEV and year_length(year) % 10 == 3:    # חסר בשנה חסרה
        return 29
    return 30


def hebrew_to_absolute(year: int, month: int, day: int) -> int:
    total = day
    if month < TISHREI:
        # ניסן..אדר נמצאים בחצי השני של השנה: קודם תשרי..סוף השנה.
        for m in range(TISHREI, last_month_of_year(year) + 1):
            total += days_in_month(year, m)
        for m in range(NISAN, month):
            total += days_in_month(year, m)
    else:
        for m in range(TISHREI, month):
            total += days_in_month(year, m)
    return total + elapsed_days(year) + _HEBREW_EPOCH


def absolute_to_hebrew(absolute: int) -> tuple[int, int, int]:
    """מחזיר (שנה, חודש, יום) עברי."""
    # ההערכה תמיד נמוכה מהאמת (שנה עברית קצרה מ-366 יום), ולכן מתקדמים למעלה.
    year = (absolute - _HEBREW_EPOCH) // 366
    while hebrew_to_absolute(year + 1, TISHREI, 1) <= absolute:
        year += 1

    # אם התאריך לפני א' ניסן — הוא בחצי הראשון של השנה, שמתחיל בתשרי.
    month = TISHREI if absolute < hebrew_to_absolute(year, NISAN, 1) else NISAN
    while absolute > hebrew_to_absolute(year, month, days_in_month(year, month)):
        month += 1

    day = absolute - hebrew_to_absolute(year, month, 1) + 1
    return year, month, day


def from_gregorian(d: date) -> tuple[int, int, int]:
    return absolute_to_hebrew(d.toordinal())


def to_gregorian(year: int, month: int, day: int) -> date:
    return date.fromordinal(hebrew_to_absolute(year, month, day))


def month_name(year: int, month: int) -> str:
    if month == ADAR_I and is_leap_year(year):
        return MONTH_NAME_ADAR_I
    return MONTH_NAMES[month]


def format_hebrew_date(d: date) -> str:
    """למשל: י\"ג באב ה'תשפ\"ו"""
    from .hebrew import to_hebrew_numeral

    year, month, day = from_gregorian(d)
    return (
        f"{to_hebrew_numeral(day)} ב{month_name(year, month)} "
        f"ה'{to_hebrew_numeral(year % 1000)}"
    )


# ---------------------------------------------------------------------------
# חגים ומועדים. כולם תאריכים עבריים קבועים ולכן מחושבים מקומית.
# הרשימה לפי לוח ארץ ישראל — יום טוב אחד, בלי יום טוב שני של גלויות.
# ---------------------------------------------------------------------------

#: (חודש, יום, שם, אסור במלאכה)
_FIXED_HOLIDAYS: tuple[tuple[int, int, str, bool], ...] = (
    (TISHREI, 1, "ראש השנה א'", True),
    (TISHREI, 2, "ראש השנה ב'", True),
    (TISHREI, 3, "צום גדליה", False),
    (TISHREI, 10, "יום הכיפורים", True),
    (TISHREI, 15, "סוכות", True),
    (TISHREI, 16, "חול המועד סוכות", False),
    (TISHREI, 17, "חול המועד סוכות", False),
    (TISHREI, 18, "חול המועד סוכות", False),
    (TISHREI, 19, "חול המועד סוכות", False),
    (TISHREI, 20, "חול המועד סוכות", False),
    (TISHREI, 21, "הושענא רבה", False),
    (TISHREI, 22, "שמיני עצרת ושמחת תורה", True),
    (TEVET, 10, "צום עשרה בטבת", False),
    (SHEVAT, 15, 'ט"ו בשבט', False),
    (NISAN, 15, "פסח", True),
    (NISAN, 16, "חול המועד פסח", False),
    (NISAN, 17, "חול המועד פסח", False),
    (NISAN, 18, "חול המועד פסח", False),
    (NISAN, 19, "חול המועד פסח", False),
    (NISAN, 20, "חול המועד פסח", False),
    (NISAN, 21, "שביעי של פסח", True),
    (IYAR, 18, 'ל"ג בעומר', False),
    (SIVAN, 6, "שבועות", True),
    (AV, 15, 'ט"ו באב', False),
)


def holidays_for(d: date) -> list[dict]:
    """כל המועדים שחלים בתאריך הלועזי הנתון."""
    year, month, day = from_gregorian(d)
    absolute = d.toordinal()
    found: list[dict] = []

    for h_month, h_day, name, yomtov in _FIXED_HOLIDAYS:
        if (month, day) == (h_month, h_day):
            found.append({"name": name, "yomtov": yomtov})

    # חנוכה מתחיל בכ"ה בכסלו ונמשך שמונה ימים. אורך כסלו משתנה, לכן סופרים ימים.
    offset = absolute - hebrew_to_absolute(year, KISLEV, 25)
    if 0 <= offset <= 7:
        found.append({"name": f"חנוכה — נר {offset + 1}", "yomtov": False})

    # פורים באדר, ובשנה מעוברת באדר ב'.
    purim_month = last_month_of_year(year)
    if month == purim_month:
        if day == 13:
            found.append({"name": "תענית אסתר", "yomtov": False})
        elif day == 14:
            found.append({"name": "פורים", "yomtov": False})
        elif day == 15:
            found.append({"name": "שושן פורים", "yomtov": False})

    # צומות שנדחים ליום ראשון כשהם חלים בשבת.
    for f_month, f_day, f_name in ((AV, 9, "תשעה באב"), (TAMMUZ, 17, 'צום י"ז בתמוז')):
        fast = to_gregorian(year, f_month, f_day)
        if fast.weekday() == 5:  # שבת
            fast = date.fromordinal(fast.toordinal() + 1)
        if d == fast:
            found.append({"name": f_name, "yomtov": False})

    # ראש חודש: ל' בחודש היוצא, ו-א' בחודש הנכנס. תשרי אינו ראש חודש.
    if day == 1 and month != TISHREI:
        found.append({"name": f"ראש חודש {month_name(year, month)}", "yomtov": False})
    elif day == 30:
        is_last = month == last_month_of_year(year)
        nxt_month = NISAN if is_last else month + 1
        nxt_year = year if is_last else year
        found.append(
            {"name": f"ראש חודש {month_name(nxt_year, nxt_month)}", "yomtov": False}
        )

    return found


def is_yom_tov(d: date) -> bool:
    """יום שאסור במלאכה (חוץ משבת)."""
    return any(h["yomtov"] for h in holidays_for(d))


def omer_day(d: date) -> int | None:
    """יום הספירה, או None אם לא בתקופת הספירה. הספירה בלילה שלפני היום."""
    year, _, _ = from_gregorian(d)
    day = d.toordinal() - hebrew_to_absolute(year, NISAN, 16) + 1
    return day if 1 <= day <= 49 else None
