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

import numpy as np

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "model"


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
