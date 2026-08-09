"""המרת טקסט עברי לווקטור — המנוע היחיד, לשני הצדדים.

חשוב להבין למה זה קובץ אחד ולא שניים: מספרי השאלות מחושבים בזמן בנייה
ומספר החיפוש מחושב בזמן ריצה. אם שני הצדדים היו משתמשים במימוש שונה —
למשל המודל המלא בבנייה והמודל הגזום בשרת — ההשוואה ביניהם הייתה
חסרת משמעות. לכן שניהם עוברים דרך ``encode`` שכאן.

בשרת אין ``torch``, אין ``model2vec`` ואין ``transformers``: המודל הגזום
הוא טבלת מספרים, והחישוב הוא חיפוש בטבלה וממוצע. התלויות היחידות הן
``numpy`` ו-``tokenizers`` — וזה מה שמכניס אותנו למגבלת הגודל של Vercel.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "model"

#: מזהה המתכון שלפיה נבנה הווקטור של שאלה. נכנס לחתימה ב-
#: ``scripts/build_embeddings.py``, ולכן שינוי כאן מחשב מחדש את כל המאגר —
#: וזה נכון, כי ווקטורים משתי מתכונים שונים אינם ברי-השוואה.
RECIPE = "fields-v2"

#: משקל לכל שדה בווקטור של שאלה.
#:
#: עד כאן כל השדות שורשרו לטקסט אחד יחיד, והווקטור היה ממוצע של כל
#: הטוקנים שבו. הבעיה אינה תיאורטית: לשאלה ממוצעת יש שורה אחת של שאלה
#: מול שבע עד עשר שורות של מילות מפתח, ולכן מילות המפתח קבעו את הווקטור
#: כמעט לבדן — והשאלה עצמה, שהיא הקרובה ביותר לניסוח של המשתמש, נבלעה.
#: כאן כל שדה מקודד בנפרד, **מנורמל לאורך 1**, ורק אז נכנס לצירוף. כך
#: משקל השדה נקבע במפורש ולא לפי כמה מילים יש בו.
#:
#: המספרים עצמם לא כוילו על ערכת המדידה, במכוון. מדידה על 432 צירופי
#: משקלים (``data/eval/queries.json``, 75 שאילתות עם תשובה) הראתה
#: ש**כל** אחד מהם עובר את השיטה הישנה — חציון 0.201 ב-MRR מול 0.168 —
#: כלומר הרווח בא מן ההפרדה בין השדות ולא מבחירת המספרים. יתר על כן,
#: באימות צולב בחמישה קיפולים, צירוף שנבחר בכיול על ארבע חמישיות
#: מהשאילתות יצא **גרוע יותר** על החמישית שלא נראתה (0.189) מן הצירוף
#: הקבוע שכאן (0.208). לכן אין לכייל אותם מחדש על אותה ערכה.
FIELD_WEIGHTS: dict[str, float] = {
    "question": 3.0,      # הניסוח הקרוב ביותר למה שמשתמש מקליד
    "keywords": 3.0,      # נכתבו בדיוק בשביל ניסוחים חלופיים
    "short_answer": 1.0,  # הקשר, לא זיהוי
    "body": 0.5,          # רק הפסקה הראשונה — השאר מדלל
    "topic": 0.25,        # רמז לתחום, לא יותר
}


class Encoder:
    """טבלת המילים הגזומה, בתוספת המרה של טקסט לווקטור."""

    def __init__(self, directory: Path) -> None:
        from tokenizers import Tokenizer  # מיובא כאן כדי לא לשלם עליו בלי צורך

        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.matrix: np.ndarray = np.load(directory / "matrix.npy")
        self.id_map: np.ndarray = np.load(directory / "id_map.npy")
        self.meta = json.loads((directory / "meta.json").read_text("utf-8"))
        self.dim = int(self.matrix.shape[1])

        # הטבלה נשמרת ב-int8 כדי שאף קובץ לא יעבור 100 מגה — המגבלה
        # של GitHub לקובץ בודד. לכל שורה מקדם משלה, והפענוח נעשה רק
        # על השורות שנשלפו בפועל (יחידות בכל חיפוש) ולא על הטבלה
        # כולה, שהייתה תופסת מאות מגה בזיכרון בלי צורך.
        self.scales: np.ndarray | None = None
        if self.matrix.dtype == np.int8:
            self.scales = np.load(directory / "scales.npy")

    def _rows(self, indices: np.ndarray) -> np.ndarray:
        rows = self.matrix[indices].astype(np.float32)
        if self.scales is not None:
            rows *= self.scales[indices][:, None]
        return rows

    def encode(self, text: str) -> np.ndarray:
        """ווקטור יחיד, מנורמל לאורך 1.

        הנרמול נעשה כאן ולא בצד הקורא, כדי שהשוואת דמיון תהיה מכפלה
        פשוטה של שני ווקטורים ולא תדרוש חלוקה בזמן ריצה.
        """
        return self.encode_many([text])[0]

    def encode_many(self, texts: list[str]) -> np.ndarray:
        encodings = self.tokenizer.encode_batch_fast(
            [t or "" for t in texts], add_special_tokens=False
        )
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, encoding in enumerate(encodings):
            # שורות שנגזמו מסומנות ב--1 ופשוט אינן משתתפות בממוצע. מילה
            # לא מוכרת אינה שגיאה — היא פשוט לא תורמת מידע.
            mapped = self.id_map[np.asarray(encoding.ids, dtype=np.int64)]
            kept = mapped[mapped >= 0]
            if kept.size:
                out[row] = self._rows(kept).mean(axis=0)

        norms = np.linalg.norm(out, axis=1, keepdims=True)
        np.divide(out, norms, out=out, where=norms > 0)
        return out

    # ---- ווקטור של שאלה שלמה ---------------------------------------------
    # הצד הזה רץ **רק בבנייה**. הוא יושב כאן ולא בסקריפט כדי שהמתכון
    # והמנוע יהיו באותו קובץ: אם המתכון יזוז והחתימה לא, המאגר יישאר
    # מעורבב משתי שיטות בלי שאיש ישים לב.

    def encode_documents(self, questions: Sequence[Mapping[str, Any]]) -> np.ndarray:
        """ווקטור לכל שאלה, לפי ``FIELD_WEIGHTS``.

        כל השדות של כל השאלות מקודדים בקריאה אחת ל-``encode_many``, כי
        המפרק מהיר בהרבה על אצווה מאשר על טקסט בודד.
        """
        if not questions:
            return np.zeros((0, self.dim), dtype=np.float32)

        texts: list[str] = []
        # (שורת היעד, שם השדה, טווח בתוך ``texts``)
        plan: list[tuple[int, str, int, int]] = []

        for row, item in enumerate(questions):
            for field in ("question", "short_answer", "topic"):
                value = str(item.get(field) or "").strip()
                if value:
                    plan.append((row, field, len(texts), len(texts) + 1))
                    texts.append(value)
            # רק הפסקה הראשונה: היא נושאת את ההכרעה, והשאר מדלל את
            # הווקטור עד שהוא מפסיק להבדיל בין שאלות.
            body = _as_list(item.get("body"))
            if body:
                plan.append((row, "body", len(texts), len(texts) + 1))
                texts.append(body[0])
            keywords = [k for k in (str(k).strip() for k in _as_list(item.get("keywords"))) if k]
            if keywords:
                plan.append((row, "keywords", len(texts), len(texts) + len(keywords)))
                texts.extend(keywords)

        encoded = self.encode_many(texts)  # כל שורה כבר מנורמלת לאורך 1
        out = np.zeros((len(questions), self.dim), dtype=np.float32)
        for row, field, start, stop in plan:
            block = encoded[start:stop]
            # מילות מפתח: ממוצע של ווקטורי יחידה, ואז נרמול מחדש — כך
            # שאלה עם עשר מילות מפתח אינה שוקלת יותר מאחת עם שלוש.
            vector = block[0] if stop - start == 1 else _unit(block.mean(axis=0))
            out[row] += FIELD_WEIGHTS[field] * vector

        norms = np.linalg.norm(out, axis=1, keepdims=True)
        np.divide(out, norms, out=out, where=norms > 0)
        return out


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else vector


@lru_cache(maxsize=1)
def get_encoder(directory: str | None = None) -> Encoder | None:
    """המנוע, או ``None`` אם המודל אינו קיים.

    ``None`` הוא מצב תקין ולא תקלה: האתר חייב לעבוד גם בלי החיפוש
    הסמנטי, ואז החיפוש הלקסיקלי הקיים עונה לבדו.
    """
    path = Path(directory) if directory else MODEL_DIR
    if not (path / "matrix.npy").exists():
        return None
    return Encoder(path)
