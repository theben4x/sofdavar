"""סוף דבר — מאגר שאלות ותשובות בהלכה וביהדות."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

from flask import Flask, request, url_for

from .config import Config

#: סוגי תוכן ששווה לדחוס. תמונות ופונטים כבר דחוסים בעצמם.
_COMPRESSIBLE = frozenset({
    "text/html", "text/css", "text/plain", "text/javascript",
    "application/javascript", "application/json",
    "application/xml", "text/xml", "image/svg+xml",
})

#: מתחת לזה התקורה של gzip גדולה מהחיסכון.
_MIN_COMPRESS_BYTES = 1024


def create_app(**overrides) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)
    app.config.update(overrides)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    from . import db
    app.teardown_appcontext(db.close_db)

    from .routes import register_routes
    register_routes(app)

    #: חותמות תוכן מחושבות. המפתח הוא שם הקובץ, הערך (זהות, חותמת).
    stamps: dict[str, tuple[tuple[float, int], str]] = {}

    @app.template_global()
    def static_v(filename: str) -> str:
        """כתובת קובץ סטטי עם חותמת שנגזרת מ*תוכן* הקובץ.

        בלי זה אי אפשר לשמור את הקבצים במטמון לאורך זמן, כי גרסה ישנה של
        ה-CSS הייתה נתקעת אצל המשתמש. ה-``?v`` משתנה עם כל עריכה.

        החותמת הייתה ``st_mtime``, וזה נשבר בפרודקשן: ה-HTML נבנה בכל
        בקשה מחדש, אבל חבילת הפריסה של Vercel לא מבטיחה שזמן השינוי של
        הקבצים ישתנה בין בנייה לבנייה (וכשה-stat נכשל החותמת הייתה 0
        קבוע). התוצאה הייתה HTML חדש עם CSS ישן במטמון הדפדפן — התבנית
        החדשה של תיבת החיפוש רונדרה בלי הכללים שלה. גיבוב של התוכן לא
        יכול להיתקע: אם הקובץ השתנה, הכתובת השתנתה.

        המדידה נשמרת לפי (זמן שינוי, גודל) כדי לא לגבב בכל בקשה. בפרודקשן
        הקובץ אינו משתנה בתוך תהליך, ובפיתוח כל שמירה מחליפה את הזוג
        ומכריחה חישוב מחדש.
        """
        path = Path(app.static_folder) / filename
        try:
            info = path.stat()
            identity = (info.st_mtime, info.st_size)
        except OSError:
            return url_for("static", filename=filename)

        cached = stamps.get(filename)
        if cached is None or cached[0] != identity:
            digest = hashlib.md5(path.read_bytes()).hexdigest()[:10]
            cached = (identity, digest)
            stamps[filename] = cached
        return url_for("static", filename=filename, v=cached[1])

    @app.after_request
    def compress(response):
        """דחיסת gzip בלי תלות חיצונית.

        ``run.py`` מריץ את Flask ישירות ואין בריפו nginx או gunicorn, ולכן
        זה לא ייפתר מעצמו. ההשפעה גדולה: עמוד "מה נברך" יורד מ-108KB ל-13KB.
        """
        if "gzip" not in request.headers.get("Accept-Encoding", ""):
            return response
        if not 200 <= response.status_code < 300:
            return response
        if "Content-Encoding" in response.headers:
            return response
        if (response.content_type or "").split(";")[0] not in _COMPRESSIBLE:
            return response

        # חובה, אחרת get_data() נכשל על תגובות שנוצרו ב-send_file.
        response.direct_passthrough = False
        data = response.get_data()
        if len(data) < _MIN_COMPRESS_BYTES:
            return response

        data = gzip.compress(data, 6)
        response.set_data(data)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(data))
        response.headers.add("Vary", "Accept-Encoding")

        # ה-ETag חושב לפני הדחיסה. בלי הסיומת פרוקסי עלול להגיש גוף דחוס
        # לבקשה שביקשה תוכן לא דחוס.
        if response.headers.get("ETag"):
            response.headers["ETag"] = response.headers["ETag"].rstrip('"') + '-gzip"'
        return response

    return app
