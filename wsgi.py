"""נקודת הכניסה ל-WSGI בפרודקשן — Vercel, gunicorn, uWSGI.

Vercel מחפש *מופע* Flask בשם ``app`` באחד מהשמות המוכרים (app.py, index.py,
server.py, main.py, wsgi.py, asgi.py — בשורש או תחת src/ app/ api/).
``run.py`` הוא factory ומייצר את המופע רק בתוך main(), ולכן הוא לא נמצא.
כאן המופע נוצר ברמת המודול, פעם אחת לכל תהליך.

    gunicorn wsgi:app

לפיתוח מקומי המשיכו להשתמש ב-``python run.py`` — הוא נותן --port ו--debug.

הערה: ``app.py`` בשורש היה מתנגש עם חבילת ``app/`` של הפרויקט, ולכן דווקא
השם הזה. אל תשנו אותו בלי לעדכן את vercel.json.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from app import create_app

#: רצף אחוז-קידוד תקין, למשל %D7 — הסימן שהנתיב עוד לא פוענח.
_PERCENT = re.compile(r"%[0-9A-Fa-f]{2}")


class DecodePathInfo:
    """מפענח ``PATH_INFO`` שהגיע עדיין מקודד באחוזים.

    PEP 3333 קובע ש-``PATH_INFO`` מגיע *מפוענח*, כשבתי ה-UTF-8 שלו ארוזים
    כ-latin-1. המתאם של Vercel מוסר אותו מקודד — ``/shabbat/%D7%94%D7%90…``
    במקום ``/shabbat/האם…``. Flask מתאים את הכלל ``/<category>/<slug>``
    ומקבל slug שהוא המחרוזת ``%D7%94%D7%90…`` כפשוטה, החיפוש במסד נכשל,
    והתוצאה היא 404 על *כל* דף שאלה. רק הם נפגעים: הם הנתיבים היחידים
    באתר שיש בהם עברית. שאר הנתיבים ASCII ועוברים בלי לגעת בהם.

    ההמרה חלה רק כשהנתיב כולו ASCII *וגם* מכיל רצף ‎%XX‎ תקין. אם הפלטפורמה
    תתוקן ותתחיל למסור נתיב מפוענח, הוא יגיע כ-latin-1 לא-ASCII והמחלקה
    תהיה no-op — כך שהתיקון לא יזיק על שרת תקין (gunicorn, שרת הפיתוח).
    """

    def __init__(self, wsgi_app):
        self._app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path.isascii() and _PERCENT.search(path):
            decoded = unquote(path, encoding="utf-8", errors="replace")
            environ["PATH_INFO"] = decoded.encode("utf-8").decode("latin-1")
        return self._app(environ, start_response)


app = create_app()
app.wsgi_app = DecodePathInfo(app.wsgi_app)
