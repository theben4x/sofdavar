"""הגדרות האפליקציה."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SITE_NAME = "סוף דבר"
    SITE_TAGLINE = "מאגר שאלות ותשובות בהלכה וביהדות"

    #: משמש ל-canonical, ל-sitemap ולתגיות השיתוף. חובה לעדכן לפני עלייה לאוויר.
    SITE_URL = os.environ.get("SOFDAVAR_SITE_URL", "https://sofdavar.co.il").rstrip("/")

    DATABASE = os.environ.get("SOFDAVAR_DB", str(BASE_DIR / "data" / "sofdavar.db"))
    BLOG_DIR = BASE_DIR / "content" / "blog"
    SEED_DIR = BASE_DIR / "data" / "seed"

    #: הפסוק שממנו נגזר שם האתר. מוצג מנוקד ולכן נשמר כאן ולא בתבנית.
    VERSE = (
        "סוֹף דָּבָר הַכֹּל נִשְׁמָע אֶת הָאֱלֹהִים יְרָא "
        "וְאֶת מִצְוֺתָיו שְׁמוֹר כִּי זֶה כׇּל הָאָדָם."
    )
    VERSE_SOURCE = "קהלת יב, יג"

    #: המשפט שבלוחית, בין הפסוק לתיבת השאלה. שורה אחת קצרה: הלוחית נמדדת
    #: לפי הטקסט שבתוכה, וכל מילה נוספת פורצת אותה לשתי שורות.
    HOME_LEDE = "מאגר שאלות ותשובות מקיף בהלכה וביהדות"

    #: המילים שהודגשו בזהב בתוך הפסוק ("יְרָא", "שְׁמוֹר"). ריק במתכוון:
    #: התבקש צבע אחיד לכל הפסוק. המנגנון נשאר (המסנן ``emphasize`` והכלל
    #: ``.verse-em``), ולכן החזרת ההדגשה היא עניין של מילוי הרשימה הזאת —
    #: ובלבד שהמילים יופיעו ב-``VERSE`` בדיוק כך, כולל ניקוד.
    VERSE_EMPHASIS: tuple[str, ...] = ()

    #: הנתיבים הסטטיים נושאים ?v=<גיבוב התוכן> דרך ``static_v``, ולכן אפשר
    #: לשמור אותם במטמון לאורך זמן. שני החלקים חייבים להישאר יחד — בלי
    #: ``static_v`` מטמון של שנה יקפיא CSS ישן אצל המשתמש. החותמת הייתה
    #: mtime וזה בדיוק מה שקרה בפרודקשן, ראה את ההסבר ב-``static_v``.
    SEND_FILE_MAX_AGE_DEFAULT = 31_536_000

    JSON_AS_ASCII = False
    TEMPLATES_AUTO_RELOAD = True

    #: מספר תצוגה זמני למונה בדף הבית, שדורס את הספירה האמיתית מהמאגר.
    #: קיים כדי שהעיצוב ייראה כמו אתר מלא בזמן שהמאגר עוד נבנה.
    #: ⚠ המאגר מכיל כרגע 100 שאלות בלבד — כל עוד זה מוגדר, דף הבית מבטיח
    #: לגולשים יותר ממה שיש בו. אפסו ל-``None`` לפני עלייה לאוויר וההצגה
    #: תחזור מיד לספירה האמיתית.
    DISPLAY_TOTAL_OVERRIDE = 20_000


#: שמות שאסור שקטגוריה תתפוס, כי הם נתיבים אמיתיים באתר.
#: עמוד הכלי יושב על ``/ma-nevarech`` ולא על ``/berachot``, כדי שהקטגוריה
#: ההלכתית "ברכות" תוכל לקבל את הכתובת הטבעית שלה.
RESERVED_SLUGS = frozenset({
    "about", "blog", "zmanim", "ma-nevarech", "search", "api", "static",
    "sitemap.xml", "robots.txt", "favicon.ico", "q",
})


def rounded_floor(value: int) -> int:
    """המספר העגול הגדול ביותר שעדיין *קטן* מ-``value``.

    מוצג כ"למעלה מ-N", ולכן הוא חייב להיות קטן ממש מהמספר האמיתי — אחרת
    הכותרת בדף הבית מבטיחה יותר ממה שיש במאגר.
    """
    if value <= 1:
        return 0
    if value < 200:
        step = 10
    elif value < 1_000:
        step = 50
    elif value < 5_000:
        step = 100
    elif value < 20_000:
        step = 500
    else:
        step = 1_000
    return ((value - 1) // step) * step
