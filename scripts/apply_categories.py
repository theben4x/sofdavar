"""מיישם את שיוך הנושאים המאושר — ומוודא שאף מילה של תוכן לא השתנתה.

הרקע: ``data/seed/questions.json`` נכתב לפי עשרה נושאים רחבים, ואילו
``data/seed/categories.json`` הוחלף מאוחר יותר בעשרים נושאים ספציפיים.
ששה מהנושאים הרחבים אינם קטגוריות מוכרות, ו-``scripts/build_db.py``
דילג עליהם בשקט — שישים שאלות שנכתבו ואינן מגיעות לאתר.

עדות לכך ש-``berachot`` ו-``mamonot`` היו אמורים להתקיים: ``site.css``
מגדיר ``--cat-berachot`` ו-``--cat-mamonot`` ואף קטגוריה אינה משתמשת בהם.
לכן שש הקטגוריות החדשות כאן אינן דורשות שורת CSS אחת.

הסקריפט אינו משנה תוכן: הוא מזיז שאלות בין קבוצות ותו לא. נוסח השאלה,
התשובה הקצרה, גוף התשובה, המקורות, המנהגים, מילות המפתח — ובעיקר
**הקוד הקבוע שבכתובת** — נבדקים בית-בית לפני ואחרי, והכתיבה נעצרת אם
משהו מהם זז.

    python scripts/apply_categories.py            # דוח בלבד, לא כותב
    python scripts/apply_categories.py --apply    # כותב
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"

#: שדות התוכן שחייבים לצאת מכאן זהים לחלוטין למה שנכנס.
CONTENT_FIELDS = (
    "code", "question", "short_answer", "body", "sources",
    "minhag_ashkenaz", "minhag_sepharad", "keywords",
)

#: הצבעים הם שמות משתני CSS שכבר מוגדרים ב-``site.css`` (שורות 26-35),
#: והאייקון הוא קוד SVG שנכנס לתוך ``viewBox="0 0 24 24"`` בקווי מתאר
#: בלבד — ``fill: none; stroke: currentColor`` (site.css:1143).
NEW_CATEGORIES: list[dict[str, str]] = [
    {
        "after": "tefila",
        "slug": "berachot", "name": "ברכות", "color": "--cat-berachot",
        "icon": '<path d="M6.5 4h11l-1.2 6.5a4.4 4.4 0 01-8.6 0z"/>'
                '<path d="M12 14.9V20M8.5 20h7"/>',
    },
    {
        "after": "lashon-hara",
        "slug": "midot", "name": "מידות ובין אדם לחברו", "color": "--cat-bein",
        "icon": '<path d="M12 20c-4.4-2.9-7.2-5.8-7.2-9A3.7 3.7 0 0112 8.6'
                'a3.7 3.7 0 017.2 2.4c0 3.2-2.8 6.1-7.2 9z"/>',
    },
    {
        "after": "midot",
        "slug": "mamonot", "name": "ממונות", "color": "--cat-mamonot",
        "icon": '<ellipse cx="12" cy="6.5" rx="7" ry="2.8"/>'
                '<path d="M5 6.5v11c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-11"/>'
                '<path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8"/>',
    },
    {
        "after": "kibud-horim",
        "slug": "mishpacha", "name": "משפחה", "color": "--cat-mishpacha",
        "icon": '<circle cx="7.5" cy="8" r="2.2"/><circle cx="16.5" cy="8" r="2.2"/>'
                '<circle cx="12" cy="13.6" r="1.8"/>'
                '<path d="M3.6 19.6c0-2.2 1.7-3.9 3.9-3.9M20.4 19.6c0-2.2-1.7-3.9-3.9-3.9'
                'M9 20.4c0-1.7 1.3-3 3-3s3 1.3 3 3"/>',
    },
    {
        "after": "mishpacha",
        "slug": "maagal-hachaim", "name": "מעגל החיים", "color": "--cat-mishpacha",
        "icon": '<path d="M20 12a8 8 0 11-3.1-6.3"/><path d="M20 4v4.6h-4.6"/>',
    },
    {
        "after": "mezuza",
        "slug": "sifrei-kodesh", "name": "כבוד ספרי קודש", "color": "--cat-stam",
        "icon": '<path d="M6.5 3.5h11A1.5 1.5 0 0119 5v14a1.5 1.5 0 01-1.5 1.5h-11'
                'A1.5 1.5 0 015 19V5a1.5 1.5 0 011.5-1.5z"/>'
                '<path d="M8.6 3.5v17M11.6 8.2h4.8"/>',
    },
]

#: קוד השאלה -> הנושא שאליו היא עוברת. נגזר מקריאה של השאלות עצמן.
ASSIGN: dict[str, str] = {
    # --- מועדים -> החג הספציפי ---
    "e86w": "pesach", "fwqv": "pesach",
    "5m3s": "pesach",         # ספירת העומר מתחילה בפסח
    "9pk6": "rosh-hashana", "mdfc": "yom-kippur",
    "ybvy": "sukkot", "xbc5": "sukkot",
    "qaeu": "chanuka", "h3cm": "purim",
    # --- בין אדם לחברו ---
    "uptb": "lashon-hara", "8zph": "lashon-hara",
    "hjg9": "kibud-horim", "dxh4": "kibud-horim",
    "89zg": "midot", "8tet": "midot", "xqfn": "midot", "2anv": "midot",
    "nema": "mamonot",        # השבת אבידה
    "pvd5": "mamonot",        # ריבית
    # --- משפחה ---
    "th5n": "shabbat",        # שכחה להדליק נרות שבת
    "v4d4": "kashrut",        # הפרשת חלה — שאלה על בצק
    "cc3v": "mishpacha", "4bth": "mishpacha",
    "7cpb": "mishpacha", "tu55": "mishpacha",
    "jf4x": "mishpacha", "7sak": "mishpacha",
    "t7j5": "maagal-hachaim", "cgyp": "maagal-hachaim",
    # --- סת"ם ---
    "zvgc": "mezuza", "b5fd": "mezuza", "x5jk": "mezuza",
    "3f7m": "mezuza", "qrbs": "mezuza", "u55j": "mezuza",
    "snxg": "tefilin",
    "sd2p": "sifrei-kodesh", "h5rq": "sifrei-kodesh", "7w3a": "sifrei-kodesh",
    # --- ברכות וממונות במלואן ---
    **{c: "berachot" for c in
       ("qqkq", "cmtg", "vyy8", "qkwp", "gxjp", "h6x7", "uyqt", "ww8f", "jjdk", "j2gb")},
    **{c: "mamonot" for c in
       ("9ptg", "4dke", "qdzn", "v5aj", "2mxh", "6k33", "xaku", "u3wv", "gzzg", "7bdk")},
}

#: שאלה שאין לה בית באף נושא קיים או חדש. היא **אינה נמחקת** — היא עוברת
#: לקובץ המתנה שאינו נקרא בבנייה, כדי שהיא תישאר גלויה ותחזור כשיהיה לה
#: נושא. השארתה ב-questions.json הייתה מפילה את הבנייה, שכן מעכשיו
#: קטגוריה לא מוכרת היא שגיאה ולא דילוג שקט.
PENDING: dict[str, str] = {
    "fkyp": "בין המצרים ותשעת הימים — אין עדיין נושא מתאים",
}


def content_of(question: dict[str, Any]) -> str:
    """טביעת אצבע של התוכן, לצורך השוואה לפני ואחרי."""
    return json.dumps(
        {f: question.get(f) for f in CONTENT_FIELDS},
        ensure_ascii=False, sort_keys=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="כתוב לקבצים")
    args = parser.parse_args()

    categories = json.loads((SEED / "categories.json").read_text("utf-8"))
    groups = json.loads((SEED / "questions.json").read_text("utf-8"))

    before = {
        q["code"]: content_of(q)
        for g in groups for q in g["questions"]
    }
    if len(before) != sum(len(g["questions"]) for g in groups):
        raise SystemExit("יש קודים כפולים ב-questions.json — עצירה")

    # ---- הרכבת רשימת הנושאים החדשה -----------------------------------------
    known = {c["slug"] for c in categories}
    for spec in NEW_CATEGORIES:
        if spec["slug"] in known:
            continue
        entry = {k: spec[k] for k in ("slug", "name", "color", "icon")}
        anchor = next(i for i, c in enumerate(categories) if c["slug"] == spec["after"])
        categories.insert(anchor + 1, entry)
        known.add(spec["slug"])

    order = {c["slug"]: i for i, c in enumerate(categories)}

    # ---- שיוך מחדש ----------------------------------------------------------
    buckets: dict[str, list[dict[str, Any]]] = {}
    pending: list[dict[str, Any]] = []
    unknown: list[str] = []

    for group in groups:
        for question in group["questions"]:
            code = question["code"]
            if code in PENDING:
                pending.append(question)
                continue
            target = ASSIGN.get(code, group["category"])
            if target not in known:
                unknown.append(f"{code} -> {target}")
                continue
            buckets.setdefault(target, []).append(question)

    if unknown:
        raise SystemExit("שיוך לנושא שאינו קיים:\n  " + "\n  ".join(unknown))

    rebuilt = [
        {"category": slug, "questions": buckets[slug]}
        for slug in sorted(buckets, key=lambda s: order[s])
    ]

    # ---- אימות: התוכן לא זז -------------------------------------------------
    after = {q["code"]: content_of(q) for g in rebuilt for q in g["questions"]}
    after.update({q["code"]: content_of(q) for q in pending})

    if set(before) != set(after):
        lost = sorted(set(before) - set(after))
        gained = sorted(set(after) - set(before))
        raise SystemExit(f"קודים נעלמו/נוספו — עצירה. חסרים={lost} חדשים={gained}")
    changed = [c for c in before if before[c] != after[c]]
    if changed:
        raise SystemExit(f"תוכן של שאלה השתנה — עצירה. קודים={changed}")

    # ---- דוח ----------------------------------------------------------------
    empty = [c["slug"] for c in categories if c["slug"] not in buckets]
    print(f"שאלות במקור:     {len(before)}")
    print(f"שאלות שיעלו:     {sum(len(g['questions']) for g in rebuilt)}")
    print(f"ממתינות:         {len(pending)}  ({', '.join(PENDING.values())})")
    print(f"נושאים:          {len(categories)}  (מהם {len(buckets)} עם תוכן)")
    print()
    for group in rebuilt:
        name = next(c["name"] for c in categories if c["slug"] == group["category"])
        print(f"  {len(group['questions']):>3}  {group['category']:<16} {name}")
    if empty:
        print()
        print(f"  נושאים שיישארו ריקים: {', '.join(empty)}")
    print()
    print("התוכן אומת: כל הקודים נשמרו, אף שדה תוכן לא השתנה.")

    if not args.apply:
        print()
        print("דוח בלבד. להרצה אמיתית: python scripts/apply_categories.py --apply")
        return 0

    def dump(path: Path, payload: Any) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )

    dump(SEED / "categories.json", categories)
    dump(SEED / "questions.json", rebuilt)
    dump(SEED / "questions_pending.json", [
        {"category": None, "reason": PENDING[q["code"]], "questions": [q]}
        for q in pending
    ])
    print()
    print("נכתב: data/seed/categories.json, questions.json, questions_pending.json")
    print("הרץ עכשיו: python scripts/build_db.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
