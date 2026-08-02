"""בונה את מסד הנתונים מאפס מקבצי ה-seed.

    python scripts/build_db.py

הסקריפט הרסני בכוונה: הוא מוחק את ה-DB הקיים ובונה מחדש מ-``data/seed``.
זו הדרך היחידה להבטיח שהמספור הרץ יוצא זהה בכל סביבה. להוספת שאלות לתוך
מאגר קיים בלי למחוק — ראה ``scripts/import_questions.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db as dbmod  # noqa: E402
from app.config import RESERVED_SLUGS  # noqa: E402
from app.codes import derive_code, is_code  # noqa: E402
from app.hebrew import index_text, slugify, unique_slug  # noqa: E402

SEED = ROOT / "data" / "seed"
DB_PATH = ROOT / "data" / "sofdavar.db"


def load(name: str, default):
    path = SEED / name
    if not path.exists():
        print(f"  · {name} לא נמצא — מדלג")
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        stale = Path(str(DB_PATH) + suffix)
        if stale.exists():
            stale.unlink()

    conn = dbmod.connect(DB_PATH)
    dbmod.init_schema(conn)

    # ---- קטגוריות ----------------------------------------------------------
    categories = load("categories.json", [])
    copy = load("copy.json", {}) or {}
    blurbs = {
        item["slug"]: item
        for item in (copy.get("category_descriptions") or [])
    }

    for order, category in enumerate(categories):
        slug = category["slug"]
        if slug in RESERVED_SLUGS:
            raise SystemExit(f"הקטגוריה '{slug}' מתנגשת בנתיב קיים באתר")
        extra = blurbs.get(slug, {})
        conn.execute(
            """
            INSERT INTO categories (slug, name, blurb, meta_description, icon, color, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                category["name"],
                extra.get("blurb", ""),
                extra.get("meta_description", ""),
                category.get("icon", ""),
                category.get("color", ""),
                order,
            ),
        )
    print(f"  · {len(categories)} קטגוריות")

    category_ids = {
        row["slug"]: row["id"]
        for row in conn.execute("SELECT id, slug FROM categories")
    }

    # ---- שאלות -------------------------------------------------------------
    questions = load("questions.json", [])
    inserted = 0
    # קודי הכתובת חייבים להיות ייחודיים על פני כל המאגר, לא רק בקטגוריה.
    codes: set[str] = set()
    missing_codes: list[str] = []
    for group in questions:
        slug = group["category"]
        category_id = category_ids.get(slug)
        if category_id is None:
            # דילוג שקט כאן עלה פעם בשישים שאלות שנכתבו ולא הגיעו לאתר:
            # ההודעה נדפסה בכל בנייה ואיש לא הבחין בה. קטגוריה לא מוכרת
            # היא שגיאת נתונים, ולכן היא מפילה את הבנייה. שאלה שממתינה
            # לנושא נשמרת ב-data/seed/questions_pending.json ואינה נטענת.
            raise SystemExit(
                f"  ! קטגוריה לא מוכרת: {slug} — {len(group.get('questions', []))} שאלות\n"
                f"    הוסיפו אותה ל-data/seed/categories.json, או העבירו את השאלות\n"
                f"    ל-data/seed/questions_pending.json. אין דילוג שקט."
            )

        taken: set[str] = set()
        for order, item in enumerate(group.get("questions", [])):
            question_slug = unique_slug(slugify(item["question"]), taken)
            code = (item.get("code") or "").strip()
            if not is_code(code) or code in codes:
                # גיבוב הטקסט הוא רשת ביטחון בלבד: הוא יציב רק כל עוד
                # השאלה לא נוסחה מחדש, וזו בדיוק הבעיה שהקוד פותר.
                code = derive_code(f"{slug}/{item['question']}", codes)
                missing_codes.append(item["question"][:40])
            codes.add(code)
            conn.execute(
                """
                INSERT INTO questions (
                    category_id, code, slug, number, question, short_answer, body,
                    sources, minhag_ashkenaz, minhag_sepharad, keywords, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category_id,
                    code,
                    question_slug,
                    -(inserted + 1),  # זמני — renumber_questions קובע את הסופי
                    item["question"],
                    item["short_answer"],
                    json.dumps(item.get("body", []), ensure_ascii=False),
                    json.dumps(item.get("sources", []), ensure_ascii=False),
                    item.get("minhag_ashkenaz") or None,
                    item.get("minhag_sepharad") or None,
                    json.dumps(item.get("keywords", []), ensure_ascii=False),
                    order,
                ),
            )
            inserted += 1
    print(f"  · {inserted} שאלות")
    if missing_codes:
        print(f"  ! {len(missing_codes)} שאלות ללא code בקובץ ה-seed — נגזר קוד זמני מגיבוב הטקסט.")
        print("    הריצו scripts/assign_codes.py ושמרו את התוצאה ב-git, אחרת הכתובת")
        print("    שלהן תשתנה בפעם הבאה שהשאלה תנוסח מחדש.")

    # ---- מה נברך -----------------------------------------------------------
    foods = load("berachot.json", [])
    for food in foods:
        aliases = food.get("aliases") or []
        conn.execute(
            """
            INSERT INTO berachot (name, first, last, category, note, aliases, search)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                food["name"],
                food["first"],
                food["last"],
                food.get("category", "אחר"),
                food.get("note") or None,
                json.dumps(aliases, ensure_ascii=False),
                index_text(food["name"], *aliases),
            ),
        )
    print(f"  · {len(foods)} מאכלים")

    # ---- מטא ---------------------------------------------------------------
    meta_values = {
        "copy": copy.get("meta", {}),
        "about_html": copy.get("about_html", ""),
        "blessing_texts": load("blessing_texts.json", {}),
    }
    for key, value in meta_values.items():
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    conn.commit()

    total = dbmod.renumber_questions(conn)
    indexed = dbmod.rebuild_search_index(conn)

    # WAL מהיר לכתיבה ולכן הוא נכון לבנייה — אבל הוא תכונה של *הקובץ*, לא של
    # החיבור. כל קורא שפותח מסד במצב WAL חייב ליצור לידו ‎-shm ו-‎-wal, גם
    # לשאילתת SELECT בלבד. בפרודקשן serverless מערכת הקבצים לקריאה בלבד,
    # והפתיחה נכשלת בכל בקשה. אחרי הבנייה המסד ממילא לקריאה בלבד, ולכן
    # מחזירים אותו ל-DELETE — שם קורא לא כותב כלום.
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    mode = conn.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
    conn.close()
    if mode != "delete":
        print(f"  ⚠ journal_mode נשאר {mode} — פריסה לקריאה בלבד תיכשל")

    print(f"\nנבנה {DB_PATH}")
    print(f"  מספור רץ: 1..{total}")
    print(f"  רשומות באינדקס החיפוש: {indexed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
