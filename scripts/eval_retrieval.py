"""מודד ארבע שיטות חיפוש על אותו סט שאלות, ומדפיס טבלה אחת.

    python scripts/eval_retrieval.py

השיטות:

    A  לקסיקלי AND   מה שרץ באתר היום
    B  לקסיקלי OR    שינוי של מילה אחת ב-app/hebrew.py — **זה קו הבסיס**
    C  סמנטי         ווקטורים בלבד
    D  משולב         B ו-C ביחד, במיזוג דירוגים

למה B הוא קו הבסיס ולא A: ``fts_query`` מחבר את כל הטוקנים ב-``AND``,
ולכן שאילתה טבעית בת שמונה מילים כמעט תמיד מחזירה כלום. החלפה ל-``OR``
היא תיקון של מילה אחת שקונה כמעט את כל הכיסוי בחינם. **כל טענה על
תרומת ה-AI חייבת להימדד מול B**, אחרת היא מודדת באג ולא שיפור.

מלכודת שהסקריפט מתריע עליה: ``keywords`` נמצאות באינדקס החיפוש
(db.py:476). שאילתת בדיקה שנבנתה ממילות המפתח של השאלה נמצאת בקלות
בכל שיטה, והמדידה חסרת ערך. לכן כל פריט נבדק על חפיפת שורשים נדירים
מול השאלה שלו, והחשודים מודפסים בסוף.

הם **כן נספרים** במדדים, במכוון: על 99 שאלות סף מכני טועה לשני
הכיוונים — "סיר חלבי" הוא תיאור לגיטימי של המצב, בעוד "כמה כסף לתת"
הוא הכותרת במילים אחרות — והשמטה שקטה של פריטים היא בעצמה פגיעה
ביושרה של המדידה. ההכרעה אנושית: עברו על הרשימה וערכו את הקובץ.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import db as dbmod, hebrew  # noqa: E402
from app.embed import MODEL_DIR, Encoder  # noqa: E402

EVAL = ROOT / "data" / "eval" / "queries.json"
VECTORS = ROOT / "data" / "seed" / "embeddings.json"
DB = ROOT / "data" / "sofdavar.db"

RRF_K = 60          # קבוע מקובל למיזוג דירוגים
CONTAMINATION = 2   # מילים נדירות משותפות שמעליהן הפריט מסומן לסקירה
TOP = 10


def roots(text: str) -> set[str]:
    """שורשי המילים של הטקסט, אחרי הנרמול העברי של האתר."""
    out: set[str] = set()
    for token in hebrew.tokenize(text):
        out.update(hebrew.stems(token))
    return out


def lexical(conn, query: str, *, join: str, limit: int) -> list[str]:
    """קודי השאלות לפי החיפוש הלקסיקלי, בסדר הדירוג."""
    original = hebrew.fts_query

    def patched(raw: str, *, prefix: bool = True, **_ignored: Any) -> str:
        # ``join`` של הקורא נבלע בכוונה: כאן השיטה נקבעת בלולאת המדידה
        # ולא בקוד הנמדד, אחרת אי אפשר להשוות A ל-B על אותו נתיב.
        built = original(raw, prefix=prefix, join="AND")
        return built.replace(" AND ", " OR ") if join == "OR" else built

    hebrew.fts_query = patched
    dbmod.fts_query = patched
    try:
        match = patched(query)
        if not match:
            return []
        rows = conn.execute(
            """
            SELECT q.code FROM search s
            JOIN questions q ON q.id = s.ref_id
            WHERE search MATCH ? AND s.kind = 'question'
            ORDER BY bm25(search, 8.0, 4.0, 2.0, 1.0) LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        return [row["code"] for row in rows]
    except Exception:
        return []
    finally:
        hebrew.fts_query = original
        dbmod.fts_query = original


def gated(conn, query: str, *, limit: int, floor: float) -> list[str]:
    """לקסיקלי OR, אבל תוצאה שאין בה מספיק מן המידע שבשאילתה נפסלת.

    זו השיטה שרצה באתר (``app.db.search``). היא נמדדת כאן כדי שהסף
    ייקבע מן המספרים ולא מן התחושה — במיוחד "נמנע כראוי", שהוא כל
    מטרתה: 27 מן השאילתות בערכה הן שאלות שאין להן תשובה במאגר.
    """
    match = hebrew.fts_query(query, join="OR")
    if not match:
        return []
    try:
        rows = conn.execute(
            """
            SELECT q.code, s.body FROM search s
            JOIN questions q ON q.id = s.ref_id
            WHERE search MATCH ? AND s.kind = 'question'
            ORDER BY bm25(search, 8.0, 4.0, 2.0, 1.0) LIMIT ?
            """,
            (match, limit),
        ).fetchall()
    except Exception:
        return []
    terms = dbmod.query_terms(query, conn=conn)
    return [
        row["code"]
        for row in rows
        if terms.evidence_ratio(set((row["body"] or "").split())) >= floor
    ]


def fuse(*rankings: list[str], limit: int) -> list[str]:
    """מיזוג דירוגים — כל שיטה תורמת 1/(k+מקום), והסכום קובע."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for position, code in enumerate(ranking):
            score[code] = score.get(code, 0.0) + 1.0 / (RRF_K + position + 1)
    return [c for c, _ in sorted(score.items(), key=lambda kv: -kv[1])][:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor", type=float, default=0.0,
                        help="סף דמיון סמנטי; מתחתיו נחשב 'אין תשובה'")
    parser.add_argument("--evidence", type=float, default=dbmod.MIN_EVIDENCE,
                        help="איזה חלק מן המידע שבשאילתה חייב להימצא בתוצאה")
    parser.add_argument("--queries", type=Path, default=EVAL,
                        help="קובץ שאילתות אחר (ברירת מחדל: data/eval/queries.json)")
    parser.add_argument("--source", choices=("all", "owner", "agent"), default="all",
                        help="מי כתב את השאילתות. השאילתות של בעל האתר קלות "
                             "יותר כי הן משתמשות במונח ההלכתי; אלה של הסוכנים "
                             "נכתבו בהוראה להימנע ממנו. האמת בין השתיים.")
    args = parser.parse_args()

    if not args.queries.exists():
        raise SystemExit(f"לא נמצא {args.queries}")
    items = json.loads(args.queries.read_text("utf-8"))
    if args.source != "all":
        items = [i for i in items if i.get("source", "agent") == args.source]
        if not items:
            raise SystemExit(f"אין פריטים מסוג {args.source}")

    encoder = Encoder(MODEL_DIR) if (MODEL_DIR / "matrix.npy").exists() else None
    if encoder is None:
        raise SystemExit("לא נמצא מודל — הריצו scripts/prune_model.py")

    payload = json.loads(VECTORS.read_text("utf-8"))
    codes = list(payload["vectors"])
    matrix = np.stack([
        np.frombuffer(base64.b64decode(payload["vectors"][c]["v"]), dtype=np.float16)
        .astype(np.float32)
        for c in codes
    ])

    conn = dbmod.connect(DB)
    questions = {
        row["code"]: {"question": row["question"], "category": row["category_id"],
                      "keywords": json.loads(row["keywords"] or "[]")}
        for row in conn.execute("SELECT code, question, category_id, keywords FROM questions")
    }

    # ---- בדיקת זיהום -------------------------------------------------------
    # ספירת מילים משותפות לבדה נותנת תוצאה שגויה: "כמה", "מה", "מותר"
    # ו"לתת" מופיעות כמעט בכל שאלה, וחפיפה בהן אינה אומרת דבר. לעומתן
    # "חלבי" או "מזוזה" מופיעות במעט שאלות, וחפיפה בהן היא בדיוק
    # הזיהום שאנחנו מחפשים. לכן נספרות רק מילים **נדירות** במאגר.
    frequency: dict[str, int] = {}
    for data in questions.values():
        for root in roots(" ".join([data["question"], *data["keywords"]])):
            frequency[root] = frequency.get(root, 0) + 1
    rare_below = max(2, len(questions) // 10)

    suspect = []
    for item in items:
        gold = item.get("gold")
        if not gold or gold not in questions:
            continue
        source = questions[gold]
        overlap = roots(item["query"]) & roots(
            " ".join([source["question"], *source["keywords"]])
        )
        rare = sorted(r for r in overlap if frequency.get(r, 0) <= rare_below)
        if len(rare) >= CONTAMINATION:
            suspect.append((item["query"], gold, rare))

    def semantic(query: str, limit: int) -> list[str]:
        sims = matrix @ encoder.encode(query)
        order = np.argsort(-sims)[:limit]
        return [codes[i] for i in order if sims[i] >= args.floor]

    systems: dict[str, Callable[[str, int], list[str]]] = {
        "A  לקסיקלי AND": lambda q, n: lexical(conn, q, join="AND", limit=n),
        "B  לקסיקלי OR ": lambda q, n: lexical(conn, q, join="OR", limit=n),
        "C  סמנטי      ": semantic,
        "D  משולב      ": lambda q, n: fuse(
            lexical(conn, q, join="OR", limit=n), semantic(q, n), limit=n
        ),
        "E  OR + סף    ": lambda q, n: gated(conn, q, limit=n, floor=args.evidence),
    }

    graded = [i for i in items if i.get("gold")]
    absent = [i for i in items if not i.get("gold")]

    print(f"פריטים: {len(items)}  |  עם תשובה: {len(graded)}  |  בלי תשובה: {len(absent)}")
    if suspect:
        # מכוון: הפריטים **נספרים**. סף מכני על 99 שאלות טועה לשני
        # הכיוונים — "סיר חלבי" הוא תיאור לגיטימי של המצב, ואילו
        # "כמה כסף לתת" הוא הכותרת במילים אחרות — ולכן ההכרעה אנושית.
        # השמטה שקטה של פריטים היא בעצמה פגיעה ביושרה של המדידה.
        print(f"  ! {len(suspect)} פריטים חשודים בחפיפה — נספרו, אך דורשים סקירה שלך")
    print()
    print(f"{'שיטה':<16}{'Recall@1':>10}{'Recall@5':>10}{'MRR@10':>9}"
          f"{'אפס תוצאות':>13}{'טעות בטוחה':>13}{'נמנע כראוי':>13}")
    print("-" * 84)

    results: dict[str, dict[str, float]] = {}
    for name, search in systems.items():
        hit1 = hit5 = mrr = empty = wrong = 0
        for item in graded:
            ranking = search(item["query"], TOP)
            if not ranking:
                empty += 1
                continue
            gold = item["gold"]
            if ranking[0] == gold:
                hit1 += 1
            elif questions.get(ranking[0], {}).get("category") != \
                    questions.get(gold, {}).get("category"):
                # תוצאה ראשונה מנושא אחר לגמרי — זו הטעות שמזיקה באמת
                wrong += 1
            if gold in ranking[:5]:
                hit5 += 1
            if gold in ranking:
                mrr += 1.0 / (ranking.index(gold) + 1)

        abstained = sum(1 for item in absent if not search(item["query"], TOP))
        n = max(len(graded), 1)
        results[name] = {
            "recall@1": hit1 / n, "recall@5": hit5 / n, "mrr": mrr / n,
            "empty": empty / n, "wrong": wrong / n,
            "abstain": abstained / max(len(absent), 1),
        }
        r = results[name]
        print(f"{name:<16}{r['recall@1']:>9.1%}{r['recall@5']:>10.1%}{r['mrr']:>9.3f}"
              f"{r['empty']:>12.1%}{r['wrong']:>12.1%}{r['abstain']:>12.1%}")

    print()
    best = max(results, key=lambda k: results[k]["mrr"])
    baseline = results["B  לקסיקלי OR "]
    print(f"הטוב ביותר: {best.strip()}")
    delta = results[best]["mrr"] - baseline["mrr"]
    print(f"מול קו הבסיס (B): {delta:+.3f} ב-MRR, "
          f"{results[best]['wrong'] - baseline['wrong']:+.1%} בטעות בטוחה")

    if suspect:
        print()
        print("--- פריטים חשודים בזיהום (לא נספרו) ---")
        for query, gold, overlap in suspect[:12]:
            print(f"  {query}")
            print(f"      חופף ל-{gold}: {', '.join(overlap)}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
