"""מוודא שכל שאלה בקובץ ה-seed מסתיימת בסימן שאלה.

    python scripts/fix_question_marks.py [--dry-run]

השאלות שנכתבו מתוך ספר ירשו את סגנון הכותרות שלו — "מותר לרסס בושם
בשבת", "צינורית המיחם" — ולידן, באותה רשימה, יושבות שאלות שנכתבו כשאלות
ומסתיימות בסימן שאלה. ההבדל נראה כמו חוסר עקביות ולא כמו סגנון.

``scripts/import_questions.py`` כבר מוסיף את הסימן בייבוא, ולכן הסקריפט
הזה נחוץ רק לתיקון מה שנכנס לפניו. הוא אידמפוטנטי ואפשר להריצו שוב.

``slugify`` מסירה פיסוק, ולכן ה-slug אינו משתנה ואין כתובת שנשברת.
הווקטורים כן מחושבים מחדש, כי הם נגזרים מלשון השאלה — הריצו אחר כך
``python scripts/update.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hebrew import as_question  # noqa: E402

SEED = ROOT / "data" / "seed" / "questions.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    groups = json.loads(SEED.read_text(encoding="utf-8"))
    changed = []
    for group in groups:
        for item in group.get("questions", []):
            before = item.get("question", "")
            after = as_question(before)
            if after != before:
                changed.append((before, after))
                item["question"] = after

    total = sum(len(g.get("questions", [])) for g in groups)
    print(f"  · {total} שאלות, {len(changed)} תוקנו")
    for before, after in changed[:8]:
        print(f"      {before}  ←  {after}")
    if len(changed) > 8:
        print(f"      ועוד {len(changed) - 8}")

    if args.dry_run:
        print("\nדוח בלבד.")
        return 0
    if changed:
        SEED.write_text(
            json.dumps(groups, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  · נכתב {SEED.relative_to(ROOT)}")
        print("\nהשלב הבא:  python scripts/update.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
