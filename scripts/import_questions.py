"""ייבוא שאלות ותשובות לתוך מאגר קיים, מ-CSV או מ-JSON.

    python scripts/import_questions.py data/my-questions.csv
    python scripts/import_questions.py data/dump.json --replace
    python scripts/import_questions.py data/big.csv --create-categories --dry-run

--------------------------------------------------------------------------
מבנה הקובץ
--------------------------------------------------------------------------
CSV — שורת כותרות בעברית או באנגלית. עמודות מזוהות:

    category / קטגוריה          slug או שם של קטגוריה קיימת          [חובה]
    question / שאלה             נוסח השאלה                          [חובה]
    short_answer / תשובה_קצרה   משפט הכרעה אחד                       [חובה]
    body / הרחבה                פסקאות, מופרדות ב-|                  [רשות]
    sources / מקורות            מקורות, מופרדים ב-|                  [רשות]
    minhag_ashkenaz / אשכנז     הבדל מנהג                            [רשות]
    minhag_sepharad / ספרד      הבדל מנהג                            [רשות]
    keywords / מילות_חיפוש      מילים, מופרדות ב-| או בפסיק           [רשות]
    topic / תת_נושא             תת-נושא בתוך הקטגוריה                 [רשות]

JSON — או רשימה שטוחה של אובייקטים עם אותם שדות, או המבנה המקובץ
``[{"category": "shabbat", "questions": [...]}]``.

הקידוד מזוהה אוטומטית: UTF-8 עם או בלי BOM, ואם לא — cp1255 (Excel בעברית).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db as dbmod  # noqa: E402
from app.codes import random_code  # noqa: E402
from app.config import RESERVED_SLUGS  # noqa: E402
from app.hebrew import as_question, slugify, unique_slug  # noqa: E402

DB_PATH = ROOT / "data" / "sofdavar.db"
ENCODINGS = ("utf-8-sig", "utf-8", "cp1255")

#: שם עמודה מנורמל -> השדה הפנימי. מאפשר כותרות בעברית או באנגלית.
COLUMNS: dict[str, str] = {
    "category": "category", "קטגוריה": "category", "נושא": "category",
    "question": "question", "שאלה": "question",
    "short_answer": "short_answer", "shortanswer": "short_answer",
    "תשובה_קצרה": "short_answer", "תשובה קצרה": "short_answer", "תשובה": "short_answer",
    "body": "body", "הרחבה": "body", "תוכן": "body",
    "sources": "sources", "מקורות": "sources", "מקור": "sources",
    "minhag_ashkenaz": "minhag_ashkenaz", "אשכנז": "minhag_ashkenaz",
    "minhag_sepharad": "minhag_sepharad", "ספרד": "minhag_sepharad",
    "keywords": "keywords", "מילות_חיפוש": "keywords", "מילות חיפוש": "keywords",
    "תגיות": "keywords",
    # "נושא" כבר תפוס לקטגוריה, ולכן תת-הנושא מקבל שם מפורש.
    "topic": "topic", "תת_נושא": "topic", "תת נושא": "topic",
}

REQUIRED = ("category", "question", "short_answer")


def read_text(path: Path) -> str:
    for encoding in ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"לא הצלחתי לפענח את הקידוד של {path}")


def split_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    separator = "|" if "|" in text else ("\n" if "\n" in text else ",")
    return [part.strip() for part in text.split(separator) if part.strip()]


def rows_from_csv(path: Path) -> Iterator[dict[str, Any]]:
    text = read_text(path)
    # ה-sniffer מזהה גם קבצים מופרדי טאב או נקודה-פסיק, שכיח בייצוא מ-Excel.
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    for raw in csv.DictReader(text.splitlines(), dialect=dialect):
        item: dict[str, Any] = {}
        for header, value in raw.items():
            field = COLUMNS.get((header or "").strip().lower())
            if field:
                item[field] = value
        if item.get("question"):
            yield item


def rows_from_json(path: Path) -> Iterator[dict[str, Any]]:
    data = json.loads(read_text(path))
    if isinstance(data, dict):
        data = data.get("questions") or data.get("data") or []

    for entry in data:
        # מבנה מקובץ: {"category": ..., "questions": [...]}
        if isinstance(entry, dict) and isinstance(entry.get("questions"), list):
            category = entry.get("category") or entry.get("slug")
            for item in entry["questions"]:
                yield {**item, "category": item.get("category", category)}
        elif isinstance(entry, dict):
            yield entry


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    item = {
        "category": str(row.get("category", "")).strip(),
        # סימן השאלה נוסף כאן ולא נסמך על מי שהכין את הקובץ: מקור חיצוני
        # כותב כותרות ("צינורית המיחם", "מותר לרסס בושם בשבת") ולא שאלות,
        # וכותרת בלי סימן שאלה נקראת כקביעה.
        "question": as_question(str(row.get("question", ""))),
        "short_answer": str(row.get("short_answer", "")).strip(),
        "body": split_list(row.get("body")),
        "sources": split_list(row.get("sources")),
        "keywords": split_list(row.get("keywords")),
        "minhag_ashkenaz": (str(row.get("minhag_ashkenaz") or "").strip() or None),
        "minhag_sepharad": (str(row.get("minhag_sepharad") or "").strip() or None),
    }
    # תת-הנושא נשמר רק כשיש בו ממש. מפתח ריק בכל שאלה מנפח את קובץ
    # המקור בלי להוסיף מידע, והוא גם נכנס לחתימת הווקטור.
    topic = str(row.get("topic") or "").strip()
    if topic:
        item["topic"] = topic
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description="ייבוא שאלות למאגר סוף דבר")
    parser.add_argument("path", type=Path, help="קובץ CSV או JSON")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--replace", action="store_true",
                        help="מוחק את כל השאלות הקיימות לפני הייבוא")
    parser.add_argument("--create-categories", action="store_true",
                        help="יוצר קטגוריה חדשה כשהיא לא קיימת במקום לדלג")
    parser.add_argument("--dry-run", action="store_true",
                        help="מנתח ומדווח בלי לכתוב למסד")
    args = parser.parse_args()

    if not args.path.exists():
        raise SystemExit(f"הקובץ לא נמצא: {args.path}")
    if not args.db.exists():
        raise SystemExit(f"המאגר לא נמצא: {args.db}\nהרץ קודם: python scripts/build_db.py")

    reader = rows_from_csv if args.path.suffix.lower() == ".csv" else rows_from_json
    rows = [normalize_row(row) for row in reader(args.path)]

    valid, skipped = [], []
    for index, row in enumerate(rows, start=1):
        missing = [field for field in REQUIRED if not row[field]]
        (skipped if missing else valid).append(
            (index, ", ".join(missing)) if missing else row
        )

    print(f"נקראו {len(rows)} שורות: {len(valid)} תקינות, {len(skipped)} דילוגים")
    for index, missing in skipped[:10]:
        print(f"  ! שורה {index}: חסר {missing}")

    if not valid:
        return 1

    conn = dbmod.connect(args.db)
    categories = {
        row["slug"]: row["id"] for row in conn.execute("SELECT id, slug FROM categories")
    }
    categories.update({
        row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM categories")
    })

    unknown = sorted({r["category"] for r in valid if r["category"] not in categories})
    if unknown and not args.create_categories:
        print(f"\n! {len(unknown)} קטגוריות לא מוכרות, השאלות שלהן לא ייובאו:")
        for name in unknown[:10]:
            print(f"    {name}")
        print("  להוספה אוטומטית הרץ שוב עם --create-categories")

    by_category: dict[str, int] = {}
    for row in valid:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1
    print("\nלפי קטגוריה:")
    for name, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
        mark = " " if name in categories else ("+" if args.create_categories else "!")
        print(f"  {mark} {name}: {count}")

    if args.dry_run:
        print("\n--dry-run: לא נכתב דבר.")
        conn.close()
        return 0

    if args.replace:
        conn.execute("DELETE FROM questions")

    if args.create_categories:
        next_order = (conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM categories"
        ).fetchone()["n"])
        for name in unknown:
            slug = slugify(name, max_words=4, max_chars=40)
            if slug in RESERVED_SLUGS:
                slug = f"{slug}-2"
            cursor = conn.execute(
                "INSERT INTO categories (slug, name, sort_order) VALUES (?, ?, ?)",
                (slug, name, next_order),
            )
            categories[name] = cursor.lastrowid
            next_order += 1

    # קוד הכתובת ייחודי על פני כל המאגר. הייבוא מגריל קוד חדש לכל שאלה,
    # ומכאן הוא נשמר במסד ולא משתנה עוד. מקור האמת לטווח ארוך הוא
    # data/seed/questions.json — ראה scripts/assign_codes.py.
    codes = {row["code"] for row in conn.execute("SELECT code FROM questions")}

    # ה-slug חייב להיות ייחודי בתוך הקטגוריה, כולל מול מה שכבר במאגר.
    taken: dict[int, set[str]] = {}
    for row in conn.execute("SELECT category_id, slug FROM questions"):
        taken.setdefault(row["category_id"], set()).add(row["slug"])

    next_order_in: dict[int, int] = {
        row["category_id"]: row["n"]
        for row in conn.execute(
            "SELECT category_id, MAX(sort_order) + 1 AS n FROM questions GROUP BY category_id"
        )
    }

    imported = 0
    for row in valid:
        category_id = categories.get(row["category"])
        if category_id is None:
            continue
        slug = unique_slug(slugify(row["question"]), taken.setdefault(category_id, set()))
        code = random_code(codes)
        codes.add(code)
        order = next_order_in.get(category_id, 0)
        next_order_in[category_id] = order + 1

        conn.execute(
            """
            INSERT INTO questions (
                category_id, code, slug, number, question, short_answer, body,
                sources, minhag_ashkenaz, minhag_sepharad, keywords, topic, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category_id, code, slug, -(imported + 1_000_000),
                row["question"], row["short_answer"],
                json.dumps(row["body"], ensure_ascii=False),
                json.dumps(row["sources"], ensure_ascii=False),
                row["minhag_ashkenaz"], row["minhag_sepharad"],
                json.dumps(row["keywords"], ensure_ascii=False),
                row.get("topic") or "",
                order,
            ),
        )
        imported += 1

    conn.commit()
    total = dbmod.renumber_questions(conn)
    indexed = dbmod.rebuild_search_index(conn)
    conn.close()

    print(f"\nיובאו {imported} שאלות.")
    print(f"  המאגר מכיל כעת {total} שאלות, ממוספרות 1..{total}")
    print(f"  אינדקס החיפוש נבנה מחדש: {indexed} רשומות")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
