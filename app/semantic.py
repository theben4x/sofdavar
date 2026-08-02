"""הצעות סמנטיות — מדור "עוד מהמאגר".

התוצאות כאן מוצגות **בנפרד** מתוצאות החיפוש הרגיל, ולא מעורבבות בהן.
זו החלטה ולא נוחות: מדידה על 62 שאילתות
(``scripts/eval_retrieval.py``) הראתה שהחיפוש הסמנטי לבדו חלש
מהלקסיקלי — 16% מול 27% במקום הראשון — ולכן ערבוב שלו פנימה עלול
לדחוק תוצאה טובה. כשכבה נפרדת הוא רק מוסיף: ה-Recall@5 עלה מ-43.5%
ל-53.2%, והמשתמש רואה מאיפה כל תוצאה הגיעה.

**אין כאן סף ביטחון**, גם זה במכוון. נמדד: ציון הדמיון אינו מפריד בין
תשובה נכונה לשגויה — לשאילתה שאין לה תשובה במאגר יצא 0.750, גבוה מכל
פגיעה נכונה שנמדדה (המרבית 0.658). סף היה מסנן תשובות נכונות בלי
לחסום שגויות. הכותרת ניטרלית ואינה מבטיחה רלוונטיות: נמדד על 20
שאילתות אמיתיות שהמדור לא הציל אף אחת מארבע הפעמים שהחיפוש הראשי
נכשל, ולכן כותרת מבטיחה הייתה מטעה.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .embed import get_encoder

VECTORS = Path(__file__).resolve().parent.parent / "data" / "seed" / "embeddings.json"


@lru_cache(maxsize=1)
def _index() -> tuple[list[str], np.ndarray] | None:
    """קודי השאלות והמטריצה שלהן, או ``None`` אם אין קובץ.

    ``None`` הוא מצב תקין: האתר חייב לעבוד גם בלי הקבצים האלה, ואז
    החיפוש הלקסיקלי עונה לבדו ואין מדור "עוד מהמאגר".
    """
    if not VECTORS.exists():
        return None
    payload = json.loads(VECTORS.read_text("utf-8"))
    vectors = payload.get("vectors") or {}
    if not vectors:
        return None
    codes = list(vectors)
    matrix = np.stack([
        np.frombuffer(base64.b64decode(vectors[c]["v"]), dtype=np.float16).astype(np.float32)
        for c in codes
    ])
    return codes, matrix


def suggest_codes(query: str, limit: int = 4) -> list[str]:
    """קודי השאלות הקרובות ביותר במשמעות, מהקרוב לרחוק."""
    index = _index()
    encoder = get_encoder()
    if index is None or encoder is None or not query.strip():
        return []

    codes, matrix = index
    vector = encoder.encode(query)
    if not vector.any():
        return []
    ranked = np.argsort(-(matrix @ vector))[:limit]
    return [codes[i] for i in ranked]
