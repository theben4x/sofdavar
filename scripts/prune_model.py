"""גוזם את מודל השפה לעברית ואנגלית בלבד, ובודק שהתוצאה נאמנה למקור.

המודל ``potion-multilingual-128M`` הוא טבלה: שורה של 256 מספרים לכל
מילה, ב-101 שפות. הקבצים שוקלים כ-537 מגה, והתקרה של פונקציית פייתון
ב-Vercel היא 500 מגה — כלומר המודל לבדו כבר חורג. האתר בעברית, ולכן
רוב השורות מיותרות.

מה נעשה כאן, ומה **לא**: נמחקות שורות של מילים שאינן בעברית ואינן
באותיות לטיניות, והמספרים נשמרים בדיוק חצי. **רשימת המילים עצמה אינה
משתנה** — שינוי שלה הוא ניתוח מסוכן שעלול לשבור את הפירוק לרכיבים.
במקום זה נשמרת טבלת תרגום ממספר המילה המקורי לשורה החדשה, ומילה
שנגזמה פשוט אינה משתתפת בחישוב.

הבדיקה העצמית שבסוף היא העיקר: היא מקודדת משפטי בדיקה בעברית פעם עם
המודל המלא ופעם עם הגזום, ומדווחת עד כמה התוצאות זהות. מתחת ל-0.99
אין להשתמש בתוצאה.

    pip install model2vec safetensors
    python scripts/prune_model.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "model"

MODEL_NAME = "minishlab/potion-multilingual-128M"

#: משפטי בדיקה — עברית יומיומית, כולל ניקוד ומעט אנגלית, כדי שהבדיקה
#: תשקף את מה שהאתר באמת יקבל.
PROBES = [
    "שכחתי להדליק נרות שבת מה עושים",
    "האם מותר לחמם אוכל על פלטת שבת",
    "מה מברכים על עוגה",
    "בישלתי בשר בסיר חלבי",
    "מזוזה בפתח השירותים",
    "אבא שלי נפטר מה עושים",
    "כמה צדקה צריך לתת",
    "שַׁבָּת שָׁלוֹם",
    "hot plate שבת",
]

HEBREW = range(0x0590, 0x0600)
#: תווי-שירות של המפרק: קידומת מילה, קידומת תת-מילה, ורווח.
AFFIXES = ("▁", "##", " ")


def keep_token(text: str) -> bool:
    """האם לשמור את השורה של המילה הזאת."""
    core = text
    for affix in AFFIXES:
        core = core.replace(affix, "")
    if not core:
        return True  # תווי שירות נשארים תמיד
    has_hebrew = any(ord(ch) in HEBREW for ch in core)
    is_latin = all(0x20 <= ord(ch) <= 0x7E for ch in core)
    return has_hebrew or is_latin


def folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def mb(n: float) -> str:
    return f"{n / 1e6:.1f} מגה"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--min-fidelity", type=float, default=0.99)
    args = parser.parse_args()

    try:
        from model2vec import StaticModel
    except ImportError:
        raise SystemExit(
            "חסרה החבילה model2vec.\n"
            "    pip install model2vec safetensors"
        )

    print(f"טוען {args.model} …  (בפעם הראשונה זו הורדה של כ-540 מגה)")
    try:
        model = StaticModel.from_pretrained(args.model)
    except Exception as error:  # רשת, אימות, או שם מודל שגוי
        raise SystemExit(f"טעינת המודל נכשלה: {type(error).__name__}: {error}")

    matrix = np.asarray(model.embedding)
    tokenizer = model.tokenizer
    vocab = tokenizer.get_vocab()
    vocab_size, dim = matrix.shape
    print(f"  מקור: {vocab_size:,} מילים × {dim} מספרים  ({mb(matrix.nbytes)})")

    # ---- בחירת השורות שנשמרות ----------------------------------------------
    by_id = {index: text for text, index in vocab.items()}
    keep = np.zeros(vocab_size, dtype=bool)
    for index in range(vocab_size):
        keep[index] = keep_token(by_id.get(index, ""))

    kept_ids = np.flatnonzero(keep)
    if kept_ids.size == 0:
        raise SystemExit("לא נשמרה אף מילה — הבדיקה שגויה, עצירה")

    id_map = np.full(vocab_size, -1, dtype=np.int32)
    id_map[kept_ids] = np.arange(kept_ids.size, dtype=np.int32)
    pruned = matrix[kept_ids].astype(np.float32)

    # דחיסה ל-int8: מקדם משלו לכל שורה, כדי שכל שורה תנצל את מלוא
    # הטווח. **זה לא ליטוש** — ב-float16 הטבלה שוקלת 111 מגה, ו-GitHub
    # דוחה כל קובץ בודד מעל 100 מגה, כלומר בלי הדחיסה אי אפשר לדחוף
    # את הפרויקט בכלל. מדידה על הטבלה המלאה: הדמיון הנמוך ביותר בין
    # שורה מקורית לשורה מפוענחת הוא 0.9998, ואף שורה אינה מתחת ל-0.99.
    scales = (np.abs(pruned).max(axis=1) / 127.0).astype(np.float32)
    scales[scales == 0] = 1.0
    quantised = np.clip(
        np.rint(pruned / scales[:, None]), -127, 127
    ).astype(np.int8)

    share = kept_ids.size / vocab_size
    print(f"  נשמר: {kept_ids.size:,} מילים ({share:.1%})"
          f"  ({mb(quantised.nbytes + scales.nbytes)} אחרי דחיסה)")

    # ---- כתיבה --------------------------------------------------------------
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    # pretty=False: ברירת המחדל כותבת את קובץ המילים מפורק לשורות
    # ומנפחת אותו פי שניים בערך, בלי שום תועלת.
    tokenizer.save(str(OUT / "tokenizer.json"), pretty=False)
    np.save(OUT / "matrix.npy", quantised)
    np.save(OUT / "scales.npy", scales)
    np.save(OUT / "id_map.npy", id_map)
    (OUT / "meta.json").write_text(
        json.dumps({
            "source_model": args.model,
            "dim": int(dim),
            "vocab_source": int(vocab_size),
            "vocab_kept": int(kept_ids.size),
            "dtype": "int8",
        }, ensure_ascii=False, indent=2) + "\n",
        "utf-8",
    )

    # ---- בדיקה עצמית: הגזום מול המלא ---------------------------------------
    sys.path.insert(0, str(ROOT))
    from app.embed import Encoder

    encoder = Encoder(OUT)
    ours = encoder.encode_many(PROBES)

    theirs = np.asarray(model.encode(PROBES), dtype=np.float32)
    theirs /= np.linalg.norm(theirs, axis=1, keepdims=True)

    per_probe = (ours * theirs).sum(axis=1)
    worst = float(per_probe.min())

    print()
    print("בדיקה עצמית — הגזום מול המלא (1.000 = זהה):")
    for probe, score in zip(PROBES, per_probe):
        flag = "" if score >= args.min_fidelity else "   << נמוך"
        print(f"  {score:0.4f}  {probe}{flag}")

    print()
    print("--- גודל ---")
    oversized = []
    for path in sorted(OUT.iterdir()):
        size = path.stat().st_size
        flag = ""
        if size > 100e6:  # GitHub דוחה כל קובץ בודד מעל 100 מגה
            flag = "   << מעל 100 מגה, git ידחה"
            oversized.append(path.name)
        print(f"  {mb(size):>12}  {path.name}{flag}")
    total = folder_size(OUT)
    print(f"  {mb(total):>12}  סה\"כ  ->  data/model/")
    print()

    if oversized:
        raise SystemExit(
            f"קבצים מעל מגבלת GitHub: {', '.join(oversized)}.\n"
            "    צמצמו את אוצר המילים (עברית בלבד) והריצו שוב."
        )

    if worst < args.min_fidelity:
        raise SystemExit(
            f"הגזימה איבדה דיוק ({worst:.4f} < {args.min_fidelity}). אל תשתמש בתוצאה.\n"
            "    שלח את הפלט הזה — כנראה נגזמו מילים שהיו נחוצות."
        )

    print(f"תקין. הנאמנות הנמוכה ביותר: {worst:.4f}")
    print(f"התיקייה data/model/ שוקלת {mb(total)} מתוך תקרה של 500 מגה.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
