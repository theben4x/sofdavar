"""חילוץ חד-פעמי של תוכן ההתחלה מפלט ה-workflow אל data/seed ו-content/blog.

הסקריפט הזה רץ פעם אחת בזמן הקמת הפרויקט. הוא נשמר בעץ כדי שיהיה תיעוד
מאיפה הגיע ה-seed, ואפשר למחוק אותו בלי לשבור דבר.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
BLOG = ROOT / "content" / "blog"

VALID_FIRST = {"המוציא", "מזונות", "הגפן", "העץ", "האדמה", "שהכל"}
VALID_LAST = {"ברכת המזון", "על המחיה", "על הגפן", "על העץ", "בורא נפשות", "אין"}


def slug_ok(value: str) -> str:
    """slug לטיני בטוח לשם קובץ ולכתובת."""
    value = re.sub(r"[^a-zA-Z0-9\-]+", "-", (value or "").strip().lower())
    return re.sub(r"-{2,}", "-", value).strip("-") or "post"


def main(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload["result"]

    SEED.mkdir(parents=True, exist_ok=True)
    BLOG.mkdir(parents=True, exist_ok=True)

    # ---- שאלות ותשובות ------------------------------------------------------
    questions = []
    total = 0
    for group in result.get("qa", []):
        items = []
        for item in group.get("questions", []):
            if not (item.get("question") and item.get("short_answer")):
                continue
            items.append({
                "question": item["question"].strip(),
                "short_answer": item["short_answer"].strip(),
                "body": [p.strip() for p in item.get("body", []) if p and p.strip()],
                "sources": [s.strip() for s in item.get("sources", []) if s and s.strip()],
                "minhag_ashkenaz": (item.get("minhag_ashkenaz") or "").strip() or None,
                "minhag_sepharad": (item.get("minhag_sepharad") or "").strip() or None,
                "keywords": [k.strip() for k in item.get("keywords", []) if k and k.strip()],
            })
        if items:
            questions.append({"category": group["category"]["slug"], "questions": items})
            total += len(items)

    (SEED / "questions.json").write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"questions.json      {total} שאלות ב-{len(questions)} קטגוריות")

    # ---- מה נברך ------------------------------------------------------------
    foods, seen, rejected = [], set(), 0
    for food in result.get("berachot", []):
        name = (food.get("name") or "").strip()
        # שומרים רק ערכים שהברכות שלהם מהרשימה הסגורה — ערך שגוי בטבלה
        # הלכתית גרוע בהרבה מערך חסר.
        if (not name or name in seen
                or food.get("first") not in VALID_FIRST
                or food.get("last") not in VALID_LAST):
            rejected += 1
            continue
        seen.add(name)
        foods.append({
            "name": name,
            "first": food["first"],
            "last": food["last"],
            "category": (food.get("category") or "אחר").strip(),
            "note": (food.get("note") or "").strip() or None,
            "aliases": [a.strip() for a in (food.get("aliases") or []) if a and a.strip()],
        })
    (SEED / "berachot.json").write_text(
        json.dumps(foods, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"berachot.json       {len(foods)} מאכלים ({rejected} נדחו)")

    # ---- נוסחי הברכות -------------------------------------------------------
    texts = result.get("blessingTexts") or {}
    (SEED / "blessing_texts.json").write_text(
        json.dumps(texts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"blessing_texts.json {len(texts.get('blessings', []))} ברכות, "
          f"{len(texts.get('rules', []))} כללים")

    # ---- קופי ומטא ----------------------------------------------------------
    copy = result.get("copy") or {}
    (SEED / "copy.json").write_text(
        json.dumps(copy, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"copy.json           {len(copy.get('category_descriptions', []))} תיאורי קטגוריה")

    # ---- בלוג ---------------------------------------------------------------
    written = 0
    for post in result.get("blog", []):
        slug = slug_ok(post.get("slug"))
        tags = ", ".join(post.get("tags", []))
        front = (
            "---\n"
            f"title: {post['title']}\n"
            f"slug: {slug}\n"
            f"description: {post.get('description', '')}\n"
            f"date: {post.get('date', '2026-07-01')}\n"
            f"tags: {tags}\n"
            "---\n\n"
        )
        (BLOG / f"{slug}.md").write_text(front + post["markdown"].strip() + "\n",
                                        encoding="utf-8")
        written += 1
    print(f"content/blog/       {written} פוסטים")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
