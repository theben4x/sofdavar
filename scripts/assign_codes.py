"""משבץ קוד קצר לכל שאלה בקובץ ה-seed, וכותב אותו חזרה.

    python scripts/assign_codes.py

הסקריפט אידמפוטנטי: שאלה שכבר יש לה ``code`` לא נגעת בה לעולם — זו כל
הנקודה. הקוד הוא הכתובת הקבועה של השאלה (``/q/k7m2``), ושינוי שלו שובר
כל קישור ישן, כולל שיתופים בוואטסאפ ותוצאות בגוגל.

הרצה נדרשת אחרי כל הוספה של שאלות ל-``data/seed/questions.json``,
והתוצאה נכנסת ל-git יחד עם השאלות עצמן.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.codes import is_code, random_code  # noqa: E402

SEED = ROOT / "data" / "seed" / "questions.json"


def main() -> int:
    if not SEED.exists():
        print(f"לא נמצא {SEED}")
        return 1

    groups = json.loads(SEED.read_text(encoding="utf-8"))

    taken: set[str] = set()
    duplicates = 0
    for group in groups:
        for item in group.get("questions", []):
            code = (item.get("code") or "").strip()
            if is_code(code) and code not in taken:
                taken.add(code)
            elif code:
                # קוד פגום או כפול — מוחלף, ומדווח. עדיף רעש עכשיו על
                # שתי שאלות שחולקות כתובת.
                duplicates += 1
                item.pop("code", None)

    added = 0
    for group in groups:
        questions = group.get("questions", [])
        for index, item in enumerate(questions):
            if item.get("code"):
                continue
            code = random_code(taken)
            taken.add(code)
            added += 1
            # הקוד נכתב ראשון באובייקט, כדי שיהיה בולט בקובץ ובדיף.
            questions[index] = {"code": code, **item}

    print(f"  · {len(taken)} קודים בסך הכול")
    if duplicates:
        print(f"  ! {duplicates} קודים פגומים או כפולים הוחלפו")
    print(f"  · {added} קודים חדשים שובצו")

    SEED.write_text(
        json.dumps(groups, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"  · נכתב {SEED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
