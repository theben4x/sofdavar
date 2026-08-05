"""מוצא שאלות שאומרות את אותו דבר בניסוח שונה.

    python scripts/find_near_duplicates.py
    python scripts/find_near_duplicates.py --threshold 0.93 --category shabbat

בדיקת כפילות לפי נוסח מדויק תופסת רק את המקרה הקל. "מותר לפתוח בקבוק
בשבת" ו"פתיחת בקבוקים בשבת" הן אותה שאלה ואף אחת מהן אינה מחרוזת של
השנייה — ואחרי הוספה של מאות שאלות ממקור אחד, זה בדיוק סוג הכפילות
שנוצר.

המנוע כאן הוא אותו ``app.embed`` שמשמש את החיפוש באתר. זה מכוון: אם
שתי שאלות קרובות מספיק כדי שהמנוע יבלבל ביניהן בחיפוש, הן קרובות
מספיק כדי שהמבקר יראה כפילות.

הסקריפט **מדווח בלבד** ואינו מוחק. איחוד שתי שאלות הוא החלטת תוכן.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.embed import MODEL_DIR, Encoder  # noqa: E402

SEED = ROOT / "data" / "seed" / "questions.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.94)
    parser.add_argument("--category", default="shabbat")
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()

    if not (MODEL_DIR / "matrix.npy").exists():
        print("המודל אינו קיים — הריצו scripts/prune_model.py")
        return 1

    groups = json.loads(SEED.read_text(encoding="utf-8"))
    items = [
        q
        for g in groups
        if g["category"] == args.category
        for q in g["questions"]
        if (q.get("status") or "published") != "draft"
    ]
    if len(items) < 2:
        print("אין מספיק שאלות להשוואה")
        return 0

    encoder = Encoder(MODEL_DIR)
    # השאלה והתשובה הקצרה יחד: שתי שאלות שנוסחו אחרת אך נענות אותו
    # דבר הן כפילות, ושתי שאלות דומות בלשונן שנענות אחרת אינן.
    vectors = encoder.encode_many(
        [f"{q['question']} {q.get('short_answer', '')}" for q in items]
    )
    similarity = vectors @ vectors.T
    np.fill_diagonal(similarity, -1.0)

    rows, cols = np.where(np.triu(similarity) >= args.threshold)
    pairs = sorted(
        ((float(similarity[r, c]), int(r), int(c)) for r, c in zip(rows, cols)),
        reverse=True,
    )

    print(f"{len(items)} שאלות ב-{args.category}, סף {args.threshold}")
    print(f"{len(pairs)} זוגות חשודים\n")
    for score, first, second in pairs[: args.limit]:
        a, b = items[first], items[second]
        print(f"  {score:.3f}  [{a.get('code')}] {a['question']}")
        print(f"         [{b.get('code')}] {b['question']}")
    if len(pairs) > args.limit:
        print(f"\n  · ועוד {len(pairs) - args.limit} זוגות")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
