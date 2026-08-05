"""מיזוג התוצרים של הכתיבה אל קבצי המקור.

    python scripts/merge_book_import.py <scratch-dir> [--apply]

בלי ``--apply`` הסקריפט מדווח בלבד ואינו נוגע בקובץ. הבדיקות שלמטה הן
שער אחד לשני סוגי פגמים שאין להם דרך אחרת להתגלות: שאריות של פריסת
ה-PDF (ניקוד, מילה שנשברה באמצע), וכפילות מול מה שכבר במאגר.

שלושה תוצרים נכנסים, ולכל אחד יעד אחר:

``expand_out_*.json``  — הרחבה לשאלה שכבר באתר. נכתבת ל-body בלבד.
``ref_out_*.json``     — תשובה לשאלה שכל תשובתה עד כה היתה הפניה לספר
                         ("לפסק למעשה ראה..."). כתיבת התשובה היא מה
                         שהופך אותה לראויה לפרסום, ולכן **כאן בלבד**
                         מוסר ה-``status: draft``. שאלה שלא נכתבה לה
                         תשובה נשארת טיוטה, וזה מכוון.
``out_*.json``         — שאלות חדשות לגמרי.

שני הראשונים נכתבים ישירות ל-``data/seed/questions.json`` לפי ה-``code``,
שהוא הכתובת הקבועה של השאלה. השאלות החדשות נכתבות לקובץ ייבוא נפרד, כי
``scripts/update.py`` הוא שמכניס אותן — הוא גם משבץ קודים, גם מחשב
ווקטורים וגם בונה את המסד, ועקיפה שלו משאירה את השלושה לא מסונכרנים.

סדר הפעולות אינו שרירותי: התשובות מוחלות **לפני** שנבנית רשימת
הכפילויות. שאלה שנוסחה מחדש בשלב התשובות חייבת להיבדק בנוסח החדש שלה,
אחרת שאלה חדשה שזהה לה תיכנס בשקט.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed" / "questions.json"

NIQQUD = re.compile(r"[֑-ׇ]")
# אות עברית בודדת בין רווחים היא כמעט תמיד מילה שנשברה בפריסה ("מלב ן").
# אותיות השימוש דבוקות תמיד למילה שאחריהן, ולכן אין להן מופע לגיטימי כזה.
ORPHAN_LETTER = re.compile(r"(?<![֐-׿])\s[א-ת]\s(?![֐-׿])")
REQUIRED = ("category", "question", "short_answer")
TEXT_FIELDS = ("question", "short_answer")


def norm(text: str) -> str:
    """נוסח שאלה מנורמל, לבדיקת כפילות בלבד."""
    text = NIQQUD.sub("", unicodedata.normalize("NFC", text))
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def texts(item: dict) -> list[str]:
    out = [str(item.get(f, "")) for f in TEXT_FIELDS]
    out += [str(p) for p in item.get("body", [])]
    for field in ("minhag_ashkenaz", "minhag_sepharad"):
        if item.get(field):
            out.append(str(item[field]))
    return out


def check(item: dict, where: str, problems: list[str]) -> bool:
    ok = True
    for field in REQUIRED:
        if not str(item.get(field, "")).strip():
            problems.append(f"{where}: חסר {field}")
            ok = False
    if item.get("category") not in (None, "shabbat"):
        problems.append(f"{where}: קטגוריה {item['category']}")
        ok = False
    for blob in texts(item):
        if NIQQUD.search(blob):
            problems.append(f"{where}: ניקוד — {blob[:60]}")
            ok = False
            break
        if ORPHAN_LETTER.search(blob):
            problems.append(f"{where}: מילה שבורה — {blob[:60]}")
            ok = False
            break
    if len(str(item.get("short_answer", ""))) < 25:
        problems.append(f"{where}: תשובה קצרה מדי")
        ok = False
    return ok


def load_many(paths: list[Path], key: str) -> list[dict]:
    out: list[dict] = []
    for path in sorted(paths):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ! {path.name}: {exc}")
            continue
        items = data.get(key, []) if isinstance(data, dict) else data
        for item in items:
            item["_from"] = path.name
        out.extend(items)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "book_import.json")
    args = parser.parse_args()

    groups = json.loads(SEED.read_text(encoding="utf-8"))
    by_code = {q["code"]: q for g in groups for q in g["questions"] if q.get("code")}

    # ---- הרחבות -----------------------------------------------------------
    problems: list[str] = []
    expansions = load_many(list(args.scratch.glob("expand_out_*.json")), "items")
    applied, misses = 0, 0
    for item in expansions:
        code = (item.get("code") or "").strip()
        body = [str(p).strip() for p in item.get("body", []) if str(p).strip()]
        target = by_code.get(code)
        if target is None or not body:
            misses += 1
            continue
        if any(NIQQUD.search(p) or ORPHAN_LETTER.search(p) for p in body):
            problems.append(f"הרחבה {code}: טקסט פגום")
            continue
        target["body"] = body
        applied += 1

    # ---- תשובות במקום הפניה -----------------------------------------------
    answers = load_many(list(args.scratch.glob("ref_out_*.json")), "items")
    answered, refused = 0, 0
    for item in answers:
        code = (item.get("code") or "").strip()
        target = by_code.get(code)
        short = str(item.get("short_answer") or "").strip()
        if target is None or len(short) < 25:
            refused += 1
            continue
        if "לפסק למעשה ראה" in short:
            # פיגום העריכה דלף לתוכן. ערך כזה גרוע מטיוטה, כי הוא נראה
            # תשובה ואינו תשובה.
            problems.append(f"תשובה {code}: נשאר נוסח ההפניה")
            continue
        candidate = dict(target)
        candidate["short_answer"] = short
        for field in ("body", "sources", "keywords"):
            if item.get(field):
                candidate[field] = [str(v).strip() for v in item[field] if str(v).strip()]
        for field in ("minhag_ashkenaz", "minhag_sepharad"):
            if item.get(field):
                candidate[field] = str(item[field]).strip()
        if item.get("question"):
            candidate["question"] = str(item["question"]).strip()
        if not check(candidate, f"תשובה {code}", problems):
            continue
        # הפרסום קורה כאן ורק כאן: יש תשובה, ולכן אין עוד מה להמתין לו.
        candidate.pop("status", None)
        candidate["draft_kind"] = "from_book"
        target.clear()
        target.update(candidate)
        answered += 1

    # ---- שאלות חדשות ------------------------------------------------------
    existing = {norm(q["question"]) for g in groups for q in g["questions"]}
    incoming = load_many(list(args.scratch.glob("out_*.json")), "questions")
    seen: dict[str, str] = {}
    clean, dupes = [], Counter()
    for item in incoming:
        where = f"{item.pop('_from', '?')}/{str(item.get('question'))[:30]}"
        if not check(item, where, problems):
            continue
        key = norm(item["question"])
        if key in existing:
            dupes["מול המאגר"] += 1
            continue
        if key in seen:
            dupes["בתוך החדשות"] += 1
            continue
        seen[key] = where
        item.setdefault("category", "shabbat")
        clean.append(item)

    still_draft = sum(
        1 for g in groups for q in g["questions"] if q.get("status") == "draft"
    )
    print(f"  · הרחבות: {applied} שובצו, {misses} בלי התאמה")
    print(f"  · תשובות במקום הפניה: {answered} נכתבו ופורסמו, {refused} נותרו בלי")
    print(f"  · נשארו טיוטות: {still_draft}")
    print(f"  · שאלות חדשות: {len(incoming)} נקראו, {len(clean)} תקינות")
    for reason, count in dupes.items():
        print(f"    · {count} כפולות {reason}")
    if problems:
        print(f"  ! {len(problems)} פגמים:")
        for line in problems[:25]:
            print(f"    · {line}")
        if len(problems) > 25:
            print(f"    · ועוד {len(problems) - 25}")

    if not args.apply:
        print("\nדוח בלבד. הרץ עם --apply כדי לכתוב.")
        return 0

    SEED.write_text(
        json.dumps(groups, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  · נכתב {SEED.relative_to(ROOT)}")
    args.out.write_text(
        json.dumps(clean, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"  · נכתב {args.out}")
    print(f"\nהשלב הבא:  python scripts/update.py {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
