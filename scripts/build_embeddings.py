"""מחשב את הווקטור של כל שאלה — ורק למה שחדש או השתנה.

הווקטורים נשמרים ב-``data/seed/embeddings.json`` ונכנסים ל-git יחד עם
השאלות. בשרת אין חישוב ואין הורדה: הקובץ הזה כבר מוכן.

הווקטור נבנה **שדה-שדה** ולא מטקסט אחד משורשר. המתכון והמשקלים יושבים
ב-``app/embed.py`` (``FIELD_WEIGHTS``), יחד עם המדידה שהצדיקה אותם.

למה חישוב מצטבר, אם ממילא הכול לוקח שנייה: הרווח אינו מהירות אלא
יציבות ב-git. הוספת שאלה אחת משנה שורה אחת בקובץ, ולכן רואים בדיוק מה
זז ואי אפשר לקלקל בטעות ווקטורים של שאלות ישנות.

החתימה שלפיה מחליטים אם לחשב מחדש מכסה גם את **זהות המודל**. החלפת
המודל, או גזימה מחדש בהיקף אחר, משנה את החתימה של כל השאלות וגורמת
לחישוב מלא — וזה נכון: ווקטורים משני מודלים שונים אינם ברי-השוואה.

    python scripts/build_embeddings.py
    python scripts/build_embeddings.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.embed import FIELD_WEIGHTS, MODEL_DIR, RECIPE, Encoder  # noqa: E402

SEED = ROOT / "data" / "seed" / "questions.json"
OUT = ROOT / "data" / "seed" / "embeddings.json"

#: השדות שמשתתפים בווקטור. כל שדה אחר בשאלה יכול להשתנות בלי לגרור
#: חישוב מחדש — וזה מכוון, כי תיקון פסיק בפסקה שלישית אינו מזיז ווקטור.
FIELDS = ("question", "keywords", "short_answer", "body", "topic")


def text_of(question: dict[str, Any]) -> str:
    """הטקסט שהחתימה נגזרת ממנו — לא הטקסט שמקודד.

    הקידוד עצמו נעשה ב-``Encoder.encode_documents``, שדה-שדה. כאן רק
    צריך מחרוזת יציבה שמשתנה בדיוק כשאחד השדות המשתתפים משתנה. גוף
    התשובה נחתך לפסקה הראשונה בלבד, כי רק היא נכנסת לווקטור.
    """
    snapshot = {
        field: (question.get("body") or [])[:1] if field == "body" else question.get(field)
        for field in FIELDS
    }
    return json.dumps(snapshot, sort_keys=True, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="דווח בלי לכתוב")
    args = parser.parse_args()

    encoder = Encoder(MODEL_DIR) if (MODEL_DIR / "matrix.npy").exists() else None
    if encoder is None:
        raise SystemExit(
            f"לא נמצא מודל ב-{MODEL_DIR.relative_to(ROOT)}\n"
            "    הריצו קודם: python scripts/prune_model.py"
        )

    # החתימה מכסה גם את **המתכון** ולא רק את המודל: שינוי במשקלי השדות
    # משנה כל ווקטור במאגר, ובלי זה היה נשאר חצי מאגר בשיטה הישנה.
    fingerprint = json.dumps(
        {"model": encoder.meta, "recipe": RECIPE, "weights": FIELD_WEIGHTS},
        sort_keys=True, ensure_ascii=False,
    )
    groups = json.loads(SEED.read_text("utf-8"))

    previous: dict[str, Any] = {}
    if OUT.exists():
        previous = json.loads(OUT.read_text("utf-8")).get("vectors", {})

    questions = [q for g in groups for q in g["questions"]]
    missing = [q["question"][:40] for q in questions if not q.get("code")]
    if missing:
        raise SystemExit(
            f"{len(missing)} שאלות בלי code — הריצו scripts/assign_codes.py קודם.\n"
            "    הווקטור מתויק לפי הקוד, ולכן שאלה בלי קוד אין לאן לשייך."
        )

    vectors: dict[str, Any] = {}
    stale: list[dict[str, Any]] = []
    unchanged = 0

    for question in questions:
        code = question["code"]
        digest = hashlib.sha256(
            (fingerprint + "\x00" + text_of(question)).encode("utf-8")
        ).hexdigest()[:16]
        known = previous.get(code)
        if known and known.get("hash") == digest:
            vectors[code] = known
            unchanged += 1
        else:
            stale.append({"code": code, "hash": digest, "question": question})

    removed = sorted(set(previous) - {q["code"] for q in questions})

    print(f"שאלות:      {len(questions)}")
    print(f"  ללא שינוי: {unchanged}")
    print(f"  לחישוב:    {len(stale)}")
    if removed:
        print(f"  נמחקות:    {len(removed)}  ({', '.join(removed[:8])}"
              f"{'…' if len(removed) > 8 else ''})")

    if stale:
        computed = encoder.encode_documents([s["question"] for s in stale])
        for entry, vector in zip(stale, computed):
            vectors[entry["code"]] = {
                "hash": entry["hash"],
                "v": base64.b64encode(
                    vector.astype(np.float16).tobytes()
                ).decode("ascii"),
            }
        for entry in stale[:6]:
            print(f"    · {entry['question']['question'][:56]}")
        if len(stale) > 6:
            print(f"    · ועוד {len(stale) - 6}")

    if args.dry_run:
        print()
        print("דוח בלבד — לא נכתב דבר.")
        return 0

    if not stale and not removed and OUT.exists():
        print()
        print("אין שינוי. הקובץ לא נגע.")
        return 0

    OUT.write_text(
        json.dumps(
            {"model": encoder.meta, "recipe": RECIPE, "weights": FIELD_WEIGHTS,
             "dim": encoder.dim, "vectors": dict(sorted(vectors.items()))},
            ensure_ascii=False, indent=1,
        ) + "\n",
        "utf-8",
    )
    print()
    print(f"נכתב {OUT.relative_to(ROOT)} — {len(vectors)} ווקטורים, "
          f"{OUT.stat().st_size / 1024:.0f} קילו")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
