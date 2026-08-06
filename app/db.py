"""גישה ל-SQLite: סכמה, אינדקס חיפוש, ושאילתות האתר.

החיפוש בנוי על FTS5. הטקסט שנכנס לאינדקס עובר את הנרמול של ``app.hebrew``
(הסרת ניקוד, איחוד אותיות סופיות, והוספת גזעים בלי אותיות שימוש), ולכן
"בשבת" בשאילתה מוצא מסמך שכתוב בו "שבת" ולהפך.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from flask import current_app, g

from .hebrew import fts_query, index_text, normalize

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id               INTEGER PRIMARY KEY,
    slug             TEXT    NOT NULL UNIQUE,
    name             TEXT    NOT NULL,
    blurb            TEXT    NOT NULL DEFAULT '',
    meta_description TEXT    NOT NULL DEFAULT '',
    icon             TEXT    NOT NULL DEFAULT '',
    color            TEXT    NOT NULL DEFAULT '',
    sort_order       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id              INTEGER PRIMARY KEY,
    category_id     INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    -- הכתובת הקבועה של השאלה: /q/<code>. אינו נגזר מהטקסט ואינו משתנה
    -- עם ניסוח מחדש או עם מיספור מחדש. ראה app/codes.py.
    code            TEXT    NOT NULL UNIQUE,
    -- ה-slug העברי נשאר רק כדי שכתובות ישנות ימשיכו להפנות פנימה.
    slug            TEXT    NOT NULL,
    -- המספור רציף על פני כל האתר ולא מתאפס בין קטגוריות.
    number          INTEGER NOT NULL UNIQUE,
    question        TEXT    NOT NULL,
    short_answer    TEXT    NOT NULL,
    body            TEXT    NOT NULL DEFAULT '[]',
    sources         TEXT    NOT NULL DEFAULT '[]',
    minhag_ashkenaz TEXT,
    minhag_sepharad TEXT,
    keywords        TEXT    NOT NULL DEFAULT '[]',
    -- 'full' = תשובה מנוסחת; 'reference' = הפניה למקורות בלבד.
    -- מוצג אחרת בעמוד השאלה, ומדורג נמוך יותר בחיפוש.
    answer_kind     TEXT    NOT NULL DEFAULT 'full',
    -- תת-נושא בתוך הקטגוריה, לחלוקת עמוד הנושא בלבד. ריק הוא מצב תקין:
    -- קטגוריה קטנה אינה צריכה חלוקה, ואז העמוד מוצג כרשימה אחת.
    topic           TEXT    NOT NULL DEFAULT '',
    sort_order      INTEGER NOT NULL,
    UNIQUE (category_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_questions_category
    ON questions (category_id, sort_order);

CREATE TABLE IF NOT EXISTS berachot (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    first    TEXT NOT NULL,
    last     TEXT NOT NULL,
    category TEXT NOT NULL,
    note     TEXT,
    aliases  TEXT NOT NULL DEFAULT '[]',
    search   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_berachot_category ON berachot (category, name);

-- טבלת מטא לערכים בודדים: מונה השאלות המוצג, נוסחי הברכות, קופי.
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5 (
    title,
    body,
    kind   UNINDEXED,
    ref_id UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2',
    prefix  = '1 2 3 4'
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exception: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# ---------------------------------------------------------------------------
# עזרי המרה
# ---------------------------------------------------------------------------


def _row_to_question(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    for field in ("body", "sources", "keywords"):
        item[field] = json.loads(item.get(field) or "[]")
    return item


def _row_to_beracha(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["aliases"] = json.loads(item.get("aliases") or "[]")
    return item


# ---------------------------------------------------------------------------
# קריאה
# ---------------------------------------------------------------------------


def get_meta(key: str, default: Any = None) -> Any:
    row = get_db().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def question_count() -> int:
    return get_db().execute("SELECT COUNT(*) AS n FROM questions").fetchone()["n"]


def list_categories() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT c.*, COUNT(q.id) AS question_count
        FROM categories c
        LEFT JOIN questions q ON q.category_id = c.id
        GROUP BY c.id
        ORDER BY c.sort_order
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_category(slug: str) -> dict[str, Any] | None:
    row = get_db().execute("SELECT * FROM categories WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def questions_in_category(category_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        "SELECT * FROM questions WHERE category_id = ? ORDER BY sort_order, number",
        (category_id,),
    ).fetchall()
    return [_row_to_question(r) for r in rows]


def get_question(category_slug: str, question_slug: str) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT q.*, c.slug AS category_slug, c.name AS category_name, c.color AS category_color
        FROM questions q
        JOIN categories c ON c.id = q.category_id
        WHERE c.slug = ? AND q.slug = ?
        """,
        (category_slug, question_slug),
    ).fetchone()
    return _row_to_question(row) if row else None


def get_question_by_code(code: str) -> dict[str, Any] | None:
    """השאילתה הראשית של עמוד השאלה — ``/q/<code>``."""
    row = get_db().execute(
        """
        SELECT q.*, c.slug AS category_slug, c.name AS category_name, c.color AS category_color
        FROM questions q
        JOIN categories c ON c.id = q.category_id
        WHERE q.code = ?
        """,
        (code,),
    ).fetchone()
    return _row_to_question(row) if row else None


def get_question_by_number(number: int) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT q.*, c.slug AS category_slug, c.name AS category_name
        FROM questions q JOIN categories c ON c.id = q.category_id
        WHERE q.number = ?
        """,
        (number,),
    ).fetchone()
    return _row_to_question(row) if row else None


def question_neighbours(number: int) -> dict[str, dict[str, Any] | None]:
    """השאלה הקודמת והבאה לפי המספור הרץ הגלובלי.

    ``ORDER BY`` ולא ``number ± 1``: המספור מכוון להשאיר חורים אחרי מחיקה
    (שאלה #2,847 נשארת #2,847 לנצח), ולכן שכן אינו בהכרח מספר צמוד.
    """
    db = get_db()
    fields = """
        q.number, q.code, q.question,
        c.slug AS category_slug, c.name AS category_name
    """
    prev_row = db.execute(
        f"""SELECT {fields} FROM questions q JOIN categories c ON c.id = q.category_id
            WHERE q.number < ? ORDER BY q.number DESC LIMIT 1""",
        (number,),
    ).fetchone()
    next_row = db.execute(
        f"""SELECT {fields} FROM questions q JOIN categories c ON c.id = q.category_id
            WHERE q.number > ? ORDER BY q.number ASC LIMIT 1""",
        (number,),
    ).fetchone()
    return {
        "prev": dict(prev_row) if prev_row else None,
        "next": dict(next_row) if next_row else None,
    }


def question_of_the_day(day: date) -> dict[str, Any] | None:
    """בחירה דטרמיניסטית לפי התאריך — אותו יום נותן תמיד את אותה שאלה."""
    total = question_count()
    if not total:
        return None
    row = get_db().execute(
        """
        SELECT q.*, c.slug AS category_slug, c.name AS category_name
        FROM questions q JOIN categories c ON c.id = q.category_id
        ORDER BY q.number LIMIT 1 OFFSET ?
        """,
        (day.toordinal() % total,),
    ).fetchone()
    return _row_to_question(row) if row else None


def related_questions(question: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    """שאלות קרובות: קודם התאמה לפי תוכן, ואם אין די — משלימים מאותה קטגוריה."""
    db = get_db()
    found: list[dict[str, Any]] = []
    seen = {question["id"]}

    match = fts_query(
        " ".join([question["question"], *question.get("keywords", [])]), prefix=False
    )
    if match:
        rows = db.execute(
            """
            SELECT q.*, c.slug AS category_slug, c.name AS category_name
            FROM search s
            JOIN questions q ON q.id = s.ref_id
            JOIN categories c ON c.id = q.category_id
            WHERE search MATCH ? AND s.kind = 'question' AND q.id != ?
            ORDER BY bm25(search, 8.0, 1.0)
            LIMIT ?
            """,
            (match, question["id"], limit),
        ).fetchall()
        for row in rows:
            found.append(_row_to_question(row))
            seen.add(row["id"])

    if len(found) < limit:
        rows = db.execute(
            f"""
            SELECT q.*, c.slug AS category_slug, c.name AS category_name
            FROM questions q JOIN categories c ON c.id = q.category_id
            WHERE q.category_id = ? AND q.id NOT IN ({",".join("?" * len(seen))})
            ORDER BY q.sort_order
            LIMIT ?
            """,
            (question["category_id"], *seen, limit - len(found)),
        ).fetchall()
        found.extend(_row_to_question(r) for r in rows)

    return found[:limit]


def list_berachot() -> list[dict[str, Any]]:
    rows = get_db().execute("SELECT * FROM berachot ORDER BY category, name").fetchall()
    return [_row_to_beracha(r) for r in rows]


def all_question_refs() -> Iterable[sqlite3.Row]:
    """לשימוש ה-sitemap: הקוד של כל שאלה."""
    return get_db().execute(
        """
        SELECT q.code
        FROM questions q JOIN categories c ON c.id = q.category_id
        ORDER BY q.number
        """
    ).fetchall()


# ---------------------------------------------------------------------------
# חיפוש
# ---------------------------------------------------------------------------

#: התאמה בתחילת הכותרת שווה יותר מהתאמה באמצע הגוף.
_PREFIX_BONUS = 6.0
_CONTAINS_BONUS = 2.5
#: נושא הוא יעד רחב יותר משאלה בודדת, ולכן מקבל דחיפה קלה בתיקו.
_CATEGORY_BONUS = 1.5

#: קנס לשאלה שאין לה תשובה מנוסחת אלא הפניה למקורות בלבד. גדול דיו כדי
#: שתשובה מלאה תמיד תקדם להפניה על אותה שאילתה, וקטן דיו כדי שהפניה
#: רלוונטית תקדים תשובה מלאה שאינה קשורה.
_REFERENCE_PENALTY = 8.0


def _search_by_number(digits: str, limit: int) -> list[tuple[float, str, int]]:
    """שאלות שמספרן מתחיל בספרות שהוקלדו.

    המספר הוא איך שמפנים לשאלה באתר ("שאלה 47"), ולכן הקלדת ספרות צריכה
    להביא אותה — ה-FTS לא מאנדקס את המספר כטקסט.
    """
    rows = get_db().execute(
        """
        SELECT id, number FROM questions
        WHERE CAST(number AS TEXT) LIKE ? || '%'
        ORDER BY LENGTH(CAST(number AS TEXT)), number
        LIMIT ?
        """,
        (digits, limit),
    ).fetchall()
    # התאמה מדויקת קופצת לראש, והשאר יורדות לפי סדר המספר.
    return [
        (1000.0 if str(row["number"]) == digits else 900.0 - index, "question", row["id"])
        for index, row in enumerate(rows)
    ]


def search(query: str, limit: int = 12) -> list[dict[str, Any]]:
    """חיפוש מאוחד שמחזיר נושאים ושאלות מסומנים לפי הסוג.

    bm25 מחזיר ציון שלילי שבו נמוך יותר הוא טוב יותר. אנחנו הופכים את הסימן
    ומוסיפים בונוסים על התאמת תחילית, כי בהשלמה אוטומטית המשתמש מצפה שמה
    שהוא מקליד יופיע בראש הרשימה ולא במקום החמישי.
    """
    numeric = _search_by_number(query.strip(), limit) if query.strip().isdigit() else []

    match = fts_query(query, join="OR")
    if not match:
        return _hydrate(numeric[:limit])

    try:
        rows = get_db().execute(
            """
            SELECT s.kind, s.ref_id, s.title, bm25(search, 10.0, 1.0) AS rank
            FROM search s
            WHERE search MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, limit * 4),
        ).fetchall()
    except sqlite3.OperationalError:
        # שאילתה שה-FTS דחה. עדיף רשימה ריקה מאשר 500 למשתמש שמקליד.
        return []

    needle = normalize(query).strip()
    scored: list[tuple[float, str, int]] = list(numeric)
    seen_numeric = {ref for _, _, ref in numeric}
    for row in rows:
        if row["kind"] == "question" and row["ref_id"] in seen_numeric:
            continue
        score = -float(row["rank"])
        title = normalize(row["title"])
        if needle:
            if title.startswith(needle):
                score += _PREFIX_BONUS
            elif needle in title:
                score += _CONTAINS_BONUS
        if row["kind"] == "category":
            score += _CATEGORY_BONUS
        scored.append((score, row["kind"], row["ref_id"]))

    # הפניות יורדות מתחת לתשובות המנוסחות. שאילתה אחת נוספת ולא עמודה
    # באינדקס ה-FTS: ``search`` היא טבלה וירטואלית שנבנית מחדש בכל בנייה,
    # והוספת שדה לה מחייבת אינדוקס מחדש של כל המאגר.
    question_ids = [i for _, k, i in scored if k == "question"]
    if question_ids:
        rows = get_db().execute(
            f"""SELECT id FROM questions
                WHERE answer_kind = 'reference'
                  AND id IN ({",".join("?" * len(question_ids))})""",
            question_ids,
        ).fetchall()
        reference = {r["id"] for r in rows}
        if reference:
            scored = [
                (score - _REFERENCE_PENALTY if kind == "question" and ref in reference else score,
                 kind, ref)
                for score, kind, ref in scored
            ]

    scored.sort(key=lambda item: -item[0])
    return _hydrate(scored[:limit])


def suggestions(query: str, exclude: Iterable[str] = (), limit: int = 4) -> list[dict[str, Any]]:
    """שאלות קרובות במשמעות, למדור "עוד מהמאגר".

    מסננות החוצה כל שאלה שכבר מופיעה בתוצאות הרגילות — כפילות במסך
    היא הדבר היחיד שהופך את המדור הזה למטרד במקום לעזרה. הציון של
    ``_hydrate`` אינו בשימוש כאן, כי הסדר כבר נקבע לפי הדמיון.
    """
    # הבדיקה קודמת לייבוא במכוון: כשהמדור כבוי, ``numpy`` והמודל אינם
    # נטענים בכלל, ולכן הכיבוי חוסך גם זיכרון וגם זמן עלייה.
    if not current_app.config.get("SEMANTIC_SUGGESTIONS"):
        return []

    skip = set(exclude)
    try:
        # הייבוא בתוך ה-try, ולא לפניו, וזה העיקר: ``app/semantic.py``
        # מייבא ``numpy`` ברמת המודול, ו-numpy אינו ב-requirements.txt.
        # מקומית הוא מותקן ולכן הכול עבד; ב-Vercel הוא חסר, הייבוא זרק
        # ImportError, ו-‎/api/search‎ ו-‎/search‎ החזירו 500 מאז שהמדור
        # הזה נוסף. ה-JS בצד הלקוח בולע 500 בשקט, ולכן זה נראה כמו תיבת
        # חיפוש שפשוט הפסיקה להציע — בלי שום סימן שמשהו נשבר.
        from . import semantic

        found = semantic.suggest_codes(query, limit + len(skip))
    except Exception:
        # המדור הזה הוא תוספת, והחיפוש הלקסיקלי עומד בפני עצמו — לפי
        # המדידה בראש app/semantic.py הוא גם החזק מבין השניים. עדיף
        # לאבד את "עוד מהמאגר" מאשר את החיפוש כולו.
        current_app.logger.exception("semantic suggestions unavailable")
        return []
    codes = [c for c in found if c not in skip]
    if not codes:
        return []

    rows = get_db().execute(
        f"SELECT id, code FROM questions WHERE code IN ({','.join('?' * len(codes))})",
        codes,
    ).fetchall()
    by_code = {row["code"]: row["id"] for row in rows}
    ordered = [(0.0, "question", by_code[c]) for c in codes if c in by_code]
    return _hydrate(ordered[:limit])


def _hydrate(scored: list[tuple[float, str, int]]) -> list[dict[str, Any]]:
    """הופך (ציון, סוג, מזהה) לפריטי תוצאה מוכנים לתצוגה."""
    db = get_db()
    category_ids = [i for _, k, i in scored if k == "category"]
    question_ids = [i for _, k, i in scored if k == "question"]

    categories: dict[int, sqlite3.Row] = {}
    if category_ids:
        rows = db.execute(
            f"""
            SELECT c.*, COUNT(q.id) AS question_count
            FROM categories c LEFT JOIN questions q ON q.category_id = c.id
            WHERE c.id IN ({",".join("?" * len(category_ids))})
            GROUP BY c.id
            """,
            category_ids,
        ).fetchall()
        categories = {r["id"]: r for r in rows}

    questions: dict[int, sqlite3.Row] = {}
    if question_ids:
        rows = db.execute(
            f"""
            SELECT q.*, c.slug AS category_slug, c.name AS category_name
            FROM questions q JOIN categories c ON c.id = q.category_id
            WHERE q.id IN ({",".join("?" * len(question_ids))})
            """,
            question_ids,
        ).fetchall()
        questions = {r["id"]: r for r in rows}

    results: list[dict[str, Any]] = []
    for _score, kind, ref_id in scored:
        if kind == "category" and ref_id in categories:
            row = categories[ref_id]
            results.append({
                "kind": "category",
                "kind_label": "נושא",
                "title": row["name"],
                "subtitle": f"{row['question_count']} שאלות",
                "url": f"/{row['slug']}",
                "color": row["color"],
            })
        elif kind == "question" and ref_id in questions:
            row = questions[ref_id]
            results.append({
                "kind": "question",
                "kind_label": "שאלה",
                "title": row["question"],
                "subtitle": row["category_name"],
                "number": row["number"],
                "url": f"/q/{row['code']}",
                # ``code`` משמש את ``suggestions`` כדי לא להציג פעמיים
                # שאלה שכבר מופיעה למעלה. ה-JS מתעלם ממפתחות שאינו
                # מכיר, ולכן התוספת אינה משנה את התצוגה.
                "code": row["code"],
            })
    return results


# ---------------------------------------------------------------------------
# בנייה מחדש של האינדקס (בשימוש הייבוא בלבד)
# ---------------------------------------------------------------------------


def rebuild_search_index(conn: sqlite3.Connection) -> int:
    """בונה מאפס את טבלת ה-FTS מתוך הטבלאות הרגילות."""
    conn.execute("DELETE FROM search")

    rows = conn.execute("SELECT id, name, slug, blurb FROM categories").fetchall()
    conn.executemany(
        "INSERT INTO search (title, body, kind, ref_id) VALUES (?, ?, 'category', ?)",
        [
            (index_text(r["name"]), index_text(r["name"], r["slug"], r["blurb"]), r["id"])
            for r in rows
        ],
    )

    rows = conn.execute(
        "SELECT id, question, short_answer, body, keywords FROM questions"
    ).fetchall()
    payload = []
    for r in rows:
        body_parts = json.loads(r["body"] or "[]")
        keywords = json.loads(r["keywords"] or "[]")
        payload.append((
            index_text(r["question"]),
            index_text(r["question"], r["short_answer"], *body_parts, *keywords),
            r["id"],
        ))
    conn.executemany(
        "INSERT INTO search (title, body, kind, ref_id) VALUES (?, ?, 'question', ?)",
        payload,
    )

    conn.commit()
    return conn.execute("SELECT COUNT(*) AS n FROM search").fetchone()["n"]


def renumber_questions(conn: sqlite3.Connection) -> int:
    """ממספר מחדש ברצף על פני כל הקטגוריות.

    זו הדרישה המרכזית של המיספור באתר: קטגוריה עם שלוש שאלות ואחריה קטגוריה
    נוספת ממשיכות 1,2,3 ואז 4,5 — בלי איפוס. הסדר נקבע לפי סדר הקטגוריות
    ובתוכן לפי סדר השאלות, כדי שהמספרים יישארו יציבים בין ריצות.
    """
    rows = conn.execute(
        """
        SELECT q.id FROM questions q JOIN categories c ON c.id = q.category_id
        ORDER BY c.sort_order, q.sort_order, q.id
        """
    ).fetchall()

    # המספר הוא UNIQUE, ולכן מזיזים קודם לטווח זמני כדי לא להתנגש באמצע.
    conn.execute("UPDATE questions SET number = -id")
    conn.executemany(
        "UPDATE questions SET number = ? WHERE id = ?",
        [(index + 1, row["id"]) for index, row in enumerate(rows)],
    )
    conn.commit()
    return len(rows)
