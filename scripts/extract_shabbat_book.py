"""חילוץ יחידות הלכה מתוך "השבת בהלכה ובאגדה" (שער ההלכה).

הספר בנוי בשלוש רמות טיפוגרפיות, ורק הן מבדילות בין חלקיו:
  · כותרת שער   — GuttmanDavid-Bold בגודל 13—14
  · כותרת הלכה  — GuttmanDavid-Bold בגודל 12
  · גוף ההלכה   — GuttmanDavid בגודל 8—10, והמקורות בסוגריים בגודל 7

כל כותרת בגודל 12 ומה שאחריה עד הכותרת הבאה הן יחידה אחת — וזו בדיוק
צורתה של שאלה ותשובה. הפלט הוא JSON של יחידות כאלה.

    python scripts/extract_shabbat_book.py <pdf> [-o out.json]
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import fitz

# שער ההלכה פותח בעמוד הפיזי 69 ("דיני כבוד ועונג שבת") ונמשך עד סוף החוברת.
HALACHA_FIRST_PAGE = 69

BODY_FONT = "GuttmanDavid"
BOLD_FONT = "GuttmanDavid-Bold"

# הכותרת החוזרת בראש כל עמוד, ומספר העמוד לצדה — רעש שאין לו מקום בטקסט.
RUNNING_HEADER_FONTS = {"GuttmanAdii", "TimesNewRomanPSMT", "Calibri-Bold"}

# פרטי קשר של מוקדי ההלכה בסוף החוברת, וסמלים גרפיים.
NOISE_FONTS = {"GuttmanMantova", "GuttmanMantovaBold", "Wingdings-Regular", "GuttmanLogo1"}

NIQQUD = re.compile(r"[֑-ׇ]")

def unwrap_parens(text: str) -> str:
    """‏')(שבת ב עז'‏ הוא מה שנשאר מ-'(שבת ב עז)' אחרי פריסת RTL.

    הסוגר הסוגר נגרר לראש הקטע והפותח נשאר אחריו. אין טעם להחזיר את
    הסוגריים למקומם — במקור הם רק עוטפים את הציטוט, ובשדה "מקורות" הם
    מיותרים. לכן מסירים אותם לגמרי.
    """
    return text.replace("(", " ").replace(")", " ").strip(" .,־-")


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("‏", "").replace("‎", "").replace("﻿", "")
    text = re.sub(r"[ \t ]+", " ", text)
    return text.strip()


def fix_punctuation(text: str) -> str:
    """מעביר פיסוק שנגרר לתחילת קטע אל סופו הנכון.

    ‏"‎,מי שאינו יכול"‎ הוא הפלט הגולמי של ‎"מי שאינו יכול,"‎ — הפסיק נדבק
    לקטע הבא במקום להישאר בסוף הקודם. בלי התיקון הזה כל משפט שני נראה שבור.
    """
    text = re.sub(r"(?<=\S)\s*\n\s*(?=[,.;:!?])", "", text)
    # פיסוק פותח שורה אחרי מילה עברית — שייך למילה שלפניו.
    text = re.sub(r"([֐-׿])\s+([,.;:?!])(?=\s|$)", r"\1\2", text)
    return text


def strip_niqqud(text: str) -> str:
    return NIQQUD.sub("", text)


def span_kind(span: dict) -> str:
    font = span["font"]
    size = round(span["size"])
    if font in RUNNING_HEADER_FONTS or font in NOISE_FONTS:
        return "noise"
    if font == BOLD_FONT:
        if size >= 13:
            return "section"
        if size == 12:
            return "heading"
        return "body"  # הדגשה בתוך הטקסט, לא כותרת
    if font.startswith("GuttmanStam"):
        return "body"  # פסוקים מנוקדים
    if font.startswith(BODY_FONT):
        return "source" if size <= 7 else "body"
    return "noise"


def page_stream(page: fitz.Page) -> list[tuple[str, str]]:
    """(kind, text) לפי סדר הקריאה, כשרצף מאותו סוג מתמזג לפריט אחד."""
    out: list[tuple[str, str]] = []
    for block in page.get_text("dict", sort=True)["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"]
                if not text.strip():
                    continue
                kind = span_kind(span)
                if kind == "noise":
                    continue
                if out and out[-1][0] == kind:
                    out[-1] = (kind, out[-1][1] + " " + text)
                else:
                    out.append((kind, text))
    return out


def extract(pdf_path: Path, first_page: int) -> list[dict]:
    doc = fitz.open(pdf_path)
    units: list[dict] = []
    section = ""
    current: dict | None = None

    def close() -> None:
        nonlocal current
        if current is None:
            return
        body = fix_punctuation(clean(current["body"]))
        sources = [unwrap_parens(clean(s)) for s in current["sources"]]
        sources = [s for s in sources if len(strip_niqqud(s)) > 2]
        if len(body) >= 80:  # פחות מזה אינו הלכה אלא שארית פריסה
            current["body"] = body
            current["sources"] = sources
            units.append(current)
        current = None

    for index in range(first_page, doc.page_count):
        printed = index + 1
        for kind, raw in page_stream(doc[index]):
            text = clean(raw)
            if not text:
                continue
            if kind == "section":
                close()
                section = strip_niqqud(text).strip(" .:־-")
                continue
            if kind == "heading":
                close()
                current = {
                    "page": printed,
                    "section": section,
                    "heading": strip_niqqud(text).strip(" .:־-"),
                    "body": "",
                    "sources": [],
                }
                continue
            if current is None:
                continue
            if kind == "source":
                current["sources"].append(text)
            else:
                current["body"] += " " + text
    close()
    return units


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--out", type=Path, default=Path("shabbat_book_units.json"))
    parser.add_argument("--first-page", type=int, default=HALACHA_FIRST_PAGE)
    args = parser.parse_args()

    units = extract(args.pdf, args.first_page)
    args.out.write_text(
        json.dumps({"units": units}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    sections = {u["section"] for u in units}
    chars = sum(len(u["body"]) for u in units)
    print(f"  · {len(units)} יחידות מתוך {len(sections)} שערים, {chars:,} תווים")
    print(f"  · נכתב אל {args.out}")


if __name__ == "__main__":
    main()
