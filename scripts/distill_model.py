"""מייצר את המודל שב-``data/model`` — זיקוק סטטי ממודל עברי.

    python scripts/distill_model.py                 # בונה אל data/model
    python scripts/distill_model.py --out /tmp/m    # בונה לתיקייה אחרת
    python scripts/distill_model.py --teacher X --dims 512

רץ **פעם אחת, מקומית**. בשרת אין torch, אין transformers ואין model2vec:
שם המודל הוא טבלת מספרים, והחישוב הוא חיפוש שורות וממוצע.

--------------------------------------------------------------------------
למה מורה עברי ולא רב-לשוני
--------------------------------------------------------------------------
עד כאן המודל היה ``minishlab/potion-multilingual-128M`` — מודל סטטי
רב-לשוני ב-101 שפות, שנגזם מ-500K שורות ל-218K כדי להיכנס לתקרות של
Vercel ושל GitHub. הוא עבד, אבל הכשלים שנמדדו היו כולם מאותו סוג:
פער בין ניסוח יומיומי למונח ההלכתי — «אייפון» מול «טלפון נייד»,
«פרימור אשכוליות» מול «מיץ תפוזים», «הבגד הלבן עם החוטים» מול «טלית
קטן». זה פער של איכות המודל בעברית, לא של מתכון הווקטור.

מה שנמדד (השכבה הסמנטית לבדה, 75 שאילתות עם תשובה, מאגר של 1,790):

    ניסיונות במתכון עצמו — נרמול, חיתוך אותיות שימוש, יותר פסקאות,
    פחות שדות — נעו בין 0.132 ל-0.167 ב-MRR מול 0.160 בבסיס. כלומר רעש.

    מורה רב-לשוני חזק יותר (``intfloat/multilingual-e5-base``) ירד
    ל-0.128. potion אינו מודל גרוע — הוא מזוקק היטב.

    **חמישה מודלים עבריים שונים** — dictabert, alephbert-base ו-
    sentence-transformers-alephbert — כולם עברו את הבסיס. הכיוון הזה
    הוא הממצא, ולא מספר בודד.

    לפי ממדים: 256 → 0.177, 384 → 0.180, 512 → 0.188, 768 → 0.189.

הנבחר הוא ``dicta-il/dictabert`` ב-512 ממדים: 0.188 מול 0.160, כלומר
R@1 מ-9.3% ל-13.3% ו-R@5 מ-21.3% ל-26.7%. בהשוואה מזווגת 15 שאילתות
השתפרו ו-12 נפגעו, ורווח הסמך בבוטסטרפ הוא [-0.029, +0.085] — כלומר
על 75 שאילתות אי אפשר לקבוע מובהקות. מה שכן אפשר לקבוע: שני דפוסים
מונוטוניים בלתי תלויים (חמישה מודלים עבריים, ארבעה ממדים עולים),
ושהמודל החדש גם קטן יותר (69MB מול 77MB) וגם מייתר את שלב הגזימה.

**אזהרה מדודה:** אין להשתמש ב-``save_pretrained``/``from_pretrained``
של model2vec. נמדד שהמעגל הזה מאבד את המודל — אותו זיקוק בדיוק ירד
מ-0.188 ל-0.057, והווקטור של אותו טקסט לפני ואחרי כמעט אורתוגונלי
(קוסינוס 0.04). הזיקוק עצמו דטרמיניסטי: שתי הרצות נתנו 0.188 זהה.
לכן כאן נכתבים המטריצה והמפרק מן העצם שבזיכרון, והתוצאה נמדדת שוב
מן הקבצים שנכתבו.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEACHER = "dicta-il/dictabert"
DIMS = 512


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher", default=TEACHER)
    parser.add_argument("--dims", type=int, default=DIMS)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "model")
    args = parser.parse_args()

    try:
        import truststore

        # הרשת כאן מיירטת תעודות, ו-certifi נכשל עליהן. בלי זה כל
        # ההורדה מ-Hugging Face נופלת ב-CERTIFICATE_VERIFY_FAILED.
        truststore.inject_into_ssl()
    except ImportError:
        print("! truststore לא מותקן — ייתכן ש-SSL ייכשל.  pip install truststore")

    try:
        from model2vec.distill import distill
    except ImportError:
        raise SystemExit(
            "צריך את התוספת של הזיקוק:  pip install \"model2vec[distill]\" transformers"
        )

    print(f"מזקק {args.teacher} ל-{args.dims} ממדים…")
    model = distill(model_name=args.teacher, pca_dims=args.dims)
    embedding = np.asarray(model.embedding, dtype=np.float32)
    rows, dim = embedding.shape
    print(f"  אוצר מילים {rows}, ממדים {dim}")

    # קוונטיזציה ל-int8 עם מקדם לכל שורה. פר-שורה ולא גלובלי: זה מה
    # שמכניס את המטריצה מתחת ל-100MB, המגבלה של GitHub לקובץ בודד.
    scales = np.abs(embedding).max(axis=1) / 127.0
    scales[scales == 0] = 1.0
    quantized = np.rint(embedding / scales[:, None]).clip(-127, 127).astype(np.int8)

    # בדיקת נאמנות: הקוונטיזציה חייבת לשמר את הכיוון של כל שורה.
    decoded = quantized.astype(np.float32) * scales[:, None]
    norms = np.linalg.norm(embedding, axis=1) * np.linalg.norm(decoded, axis=1)
    live = norms > 0
    similarity = np.einsum("ij,ij->i", embedding[live], decoded[live]) / norms[live]
    worst = float(similarity.min())
    print(f"  נאמנות הקוונטיזציה: הדמיון הנמוך ביותר {worst:.4f}")
    if worst < 0.99:
        raise SystemExit(f"! הקוונטיזציה איבדה יותר מדי ({worst:.4f} < 0.99) — לא נכתב")

    args.out.mkdir(parents=True, exist_ok=True)
    np.save(args.out / "matrix.npy", quantized)
    np.save(args.out / "scales.npy", scales.astype(np.float32))
    # אין גזימה: אוצר המילים כבר עברי, וכל שורה במקומה. טבלת התרגום
    # נשמרת כזהות רק כדי ש-app/embed.py יעבוד בלי שינוי.
    np.save(args.out / "id_map.npy", np.arange(rows, dtype=np.int32))
    (args.out / "tokenizer.json").write_text(model.tokenizer.to_str(), encoding="utf-8")
    (args.out / "meta.json").write_text(
        json.dumps(
            {
                "source_model": f"distilled from {args.teacher} via model2vec",
                "dim": dim,
                "vocab_source": rows,
                "vocab_kept": rows,
                "dtype": "int8",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    total = sum(p.stat().st_size for p in args.out.iterdir())
    print(f"נכתב {args.out}  ({total / 1e6:.1f}MB)")
    print("עכשיו:  python scripts/build_embeddings.py   (החתימה השתנתה — הכול יחושב מחדש)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
