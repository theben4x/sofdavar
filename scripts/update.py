"""הפקודה היחידה שצריך לזכור אחרי הוספת שאלות.

    python scripts/update.py                      # אחרי עריכה ידנית של questions.json
    python scripts/update.py my-questions.csv     # אחרי הכנת קובץ חדש
    python scripts/update.py my-questions.csv --dry-run

--------------------------------------------------------------------------
למה ארבעה שלבים ולא שניים
--------------------------------------------------------------------------
1. ייבוא          — השאלות החדשות נכנסות ל-``data/seed/questions.json``
2. שיבוץ קודים    — כל שאלה חדשה מקבלת את הכתובת הקבועה שלה
3. ווקטורים       — חישוב, לחדשות ולמה שהשתנה בלבד
4. בניית המסד     — המסד שהאתר קורא ממנו נבנה מחדש מקבצי המקור

שלב 2 חייב לקדום לשלב 3: הווקטור מתויק לפי הקוד, ושאלה בלי קוד אין
לאן לשייך. שלב 4 חייב להיות אחרון: האתר קורא מהמסד ולא מקבצי המקור,
ובלעדיו עדכנת את הקבצים והאתר עדיין מציג את התוכן הישן.

--------------------------------------------------------------------------
הערה על הייבוא — שינוי מכוון מול scripts/import_questions.py
--------------------------------------------------------------------------
``import_questions.py`` כותב **למסד בלבד**, ואילו ``build_db.py`` מוחק
את המסד ובונה אותו מחדש מקבצי המקור. שרשור של השניים היה מוחק כל שאלה
שיובאה, בשקט. לכן הייבוא כאן כותב אל **קובץ המקור** — כפי ש-
``import_questions.py`` עצמו מתעד שצריך להיות ("מקור האמת לטווח ארוך
הוא data/seed/questions.json"). הפירוק של CSV/JSON נלקח משם כדי שלא
יהיו שתי גרסאות של אותו קוד.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SEED = ROOT / "data" / "seed" / "questions.json"
CATEGORIES = ROOT / "data" / "seed" / "categories.json"


def import_into_seed(path: Path, *, dry_run: bool) -> int:
    """מוסיף את השאלות שבקובץ אל ``questions.json``, לפי הקטגוריה שלהן."""
    from import_questions import normalize_row, rows_from_csv, rows_from_json

    reader = rows_from_csv if path.suffix.lower() == ".csv" else rows_from_json
    incoming = [normalize_row(row) for row in reader(path)]
    incoming = [r for r in incoming if r["question"] and r["short_answer"]]
    if not incoming:
        raise SystemExit(f"לא נמצאו שאלות תקינות ב-{path}")

    groups = json.loads(SEED.read_text("utf-8"))
    categories = json.loads(CATEGORIES.read_text("utf-8"))
    by_slug = {c["slug"]: c for c in categories}
    by_name = {c["name"]: c for c in categories}

    existing = {q["question"].strip() for g in groups for q in g["questions"]}
    bucket = {g["category"]: g for g in groups}

    added, skipped, unknown = 0, 0, {}
    for row in incoming:
        raw = row.pop("category")
        target = by_slug.get(raw) or by_name.get(raw)
        if target is None:
            unknown[raw] = unknown.get(raw, 0) + 1
            continue
        if row["question"].strip() in existing:
            skipped += 1
            continue
        group = bucket.get(target["slug"])
        if group is None:
            group = {"category": target["slug"], "questions": []}
            bucket[target["slug"]] = group
            groups.append(group)
        group["questions"].append(row)
        existing.add(row["question"].strip())
        added += 1

    print(f"  · נקראו {len(incoming)} שאלות מ-{path.name}")
    print(f"  · חדשות: {added}")
    if skipped:
        print(f"  · דילוג על {skipped} שכבר קיימות (אותו נוסח שאלה)")
    if unknown:
        detail = ", ".join(f"{k}×{v}" for k, v in unknown.items())
        raise SystemExit(
            f"  ! קטגוריות לא מוכרות: {detail}\n"
            "    הוסיפו אותן ל-data/seed/categories.json, או תקנו את הקובץ."
        )
    if dry_run:
        print("  · דוח בלבד — questions.json לא נגע")
        return added
    if added:
        SEED.write_text(
            json.dumps(groups, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        print(f"  · נכתב {SEED.relative_to(ROOT)}")
    return added


def run(step: str, script: str, *flags: str) -> None:
    print()
    print(f"-- {step} " + "-" * max(0, 58 - len(step)))
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *flags])
    if result.returncode != 0:
        raise SystemExit(f"\n!! נעצר ב\"{step}\". שום שלב הבא לא רץ.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path,
                        help="קובץ CSV או JSON להוספה (רשות)")
    parser.add_argument("--dry-run", action="store_true",
                        help="הראה מה ייובא, בלי לשנות דבר")
    args = parser.parse_args()

    if args.source and not args.source.exists():
        raise SystemExit(f"לא נמצא {args.source}")

    print("-- 1/4  ייבוא " + "-" * 45)
    if args.source:
        import_into_seed(args.source, dry_run=args.dry_run)
    else:
        print("  · אין קובץ — ממשיכים עם questions.json כמו שהוא")

    if args.dry_run:
        print()
        print("דוח בלבד. שלבים 2-4 לא רצו.")
        return 0

    run("2/4  שיבוץ קודים", "assign_codes.py")
    run("3/4  ווקטורים", "build_embeddings.py")
    # build_db.py מוחק את המסד ובונה אותו מחדש מקבצי המקור. זה מכוון:
    # קבצי ה-seed הם מקור האמת, והמסד הוא תוצר בנייה בלבד.
    run("4/4  בניית המסד", "build_db.py")

    print()
    print("-" * 60)
    print("הכול עודכן. להרצת האתר:  python run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
