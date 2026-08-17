"""מתקן כיווניות ב-PPTX שנוצר ב-pptxgenjs, ברמת הריצה ולא רק ברמת הפסקה.

הבעיה: pptxgenjs כותב rtl="1" על <a:pPr> בלבד, וכל מחרוזת נכנסת לריצה אחת.
PowerPoint מרנדר אז שני פגמים, ששניהם נמדדו מול PowerPoint עצמו:

  1. אסימון שמערב אותיות לטיניות וספרות מתהפך: «512MB» מודפס «MB512»,
     «int8» מודפס «8int», «Recall@5» מודפס «5Recall@».
     סימני כיווניות אינם עוזרים: LRM ו-LRE נבדקו ולא שינו דבר, ו-LRI/FSI
     (U+2066‑2069) מצוירים כריבועים גלויים — בדיוק כמו ב-Word.
  2. רווח שצמוד לגבול בין קטע לטיני לעברי נגזם: «Model2Vec היא» מודפס
     «Model2Vecהיא».

התיקון, לכל פסקה שסומנה rtl="1":

  * הריצה מפוצלת לפי כתב — קטע עברי מול קטע לטיני/ספרתי, וניטרלים
    (רווח, פסיק, נקודתיים) נדבקים לקטע שלפניהם;
  * קטע עברי מקבל rtl="1" ו-lang="he-IL", קטע לטיני מקבל rtl="0"
    ו-lang="en-US". הסימון המפורש הוא מה שמונע את ההיפוך;
  * רווח בסוף קטע לטיני שלפני קטע עברי מועבר לתחילת הקטע העברי, כי
    PowerPoint גוזם רווח בסוף ריצה בגבול כיוון אך לא בתחילתה.

הרצה:  python fix_pptx_bidi.py deck.pptx
"""

from __future__ import annotations

import html
import re
import shutil
import sys
import zipfile
from pathlib import Path

HEB = re.compile(r"[֐-׿יִ-ﭏ]")

RUN = re.compile(r"<a:r>(.*?)</a:r>", re.S)
PARA = re.compile(r"<a:p>(.*?)</a:p>", re.S)
RPR = re.compile(r"<a:rPr\b[^>]*?(?:/>|>.*?</a:rPr>)", re.S)
TEXT = re.compile(r"<a:t>(.*?)</a:t>", re.S)
PPR_RTL = re.compile(r'<a:pPr\b[^>]*\brtl="1"')


def _strong(ch: str):
    """עברית → True, לטינית או ספרה → False, ניטרלי → None."""
    if HEB.match(ch):
        return True
    if ch.isascii() and ch.isalnum():
        return False
    return None


def split_by_script(text: str):
    default_rtl = next((s for s in (_strong(c) for c in text) if s is not None), True)
    segments, buf, buf_rtl = [], "", None
    for ch in text:
        s = _strong(ch)
        kind = s if s is not None else (buf_rtl if buf_rtl is not None else default_rtl)
        if buf_rtl is None or kind == buf_rtl:
            buf, buf_rtl = buf + ch, kind
        else:
            segments.append((buf, buf_rtl))
            buf, buf_rtl = ch, kind
    if buf:
        segments.append((buf, buf_rtl))
    return segments


OPENERS = "/([{<"


def fix_boundaries(segments):
    out = [[s, r] for s, r in segments]

    # רווח בסוף קטע לטיני שלפני קטע עברי עובר לתחילת הקטע העברי: PowerPoint
    # גוזם רווח בסוף ריצה בגבול כיוון, אך רווח בתחילת ריצה שורד.
    for i in range(len(out) - 1):
        seg, rtl = out[i]
        nseg, nrtl = out[i + 1]
        if rtl is False and nrtl is True and seg.endswith(" "):
            stripped = seg.rstrip(" ")
            out[i][0] = stripped
            out[i + 1][0] = seg[len(stripped):] + nseg

    # פיסוק פותח שנשאר בזנב של קטע עברי — הלוכסן של «/q/k7m2» — עובר לקטע
    # הלטיני, אחרת הוא מצויר בצדו השני של האסימון. רק אם לפניו רווח, כדי
    # שלא לתלוש פיסוק מתוך מילה עברית.
    for i in range(len(out) - 1):
        seg, rtl = out[i]
        nseg, nrtl = out[i + 1]
        if rtl is True and nrtl is False and seg and seg[-1] in OPENERS:
            j = len(seg)
            while j > 0 and seg[j - 1] in OPENERS:
                j -= 1
            if j == 0 or seg[j - 1] == " ":
                out[i][0], out[i + 1][0] = seg[:j], seg[j:] + nseg

    return [(s, r) for s, r in out if s]


def _set_attrs(rpr_xml: str, *, rtl: str, lang: str) -> str:
    """מחליף (או מוסיף) את lang, altLang ו-rtl בתגית הפתיחה של a:rPr."""
    m = re.match(r"<a:rPr\b([^>]*?)(/>|>)", rpr_xml, re.S)
    attrs, close = m.group(1), m.group(2)
    for name in ("lang", "altLang", "rtl"):
        attrs = re.sub(r'\s%s="[^"]*"' % name, "", attrs)
    attrs = f' lang="{lang}" altLang="en-US" rtl="{rtl}"' + attrs
    return "<a:rPr" + attrs + close + rpr_xml[m.end():]


def _escape(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fix_paragraph(para_body: str) -> str:
    if not PPR_RTL.search(para_body):
        return para_body

    def fix_run(m):
        run = m.group(1)
        m_rpr, m_t = RPR.search(run), TEXT.search(run)
        if not m_rpr or not m_t:
            return m.group(0)
        rpr, text = m_rpr.group(0), html.unescape(m_t.group(1))
        if not text:
            return m.group(0)
        segments = fix_boundaries(split_by_script(text))
        if len(segments) == 1 and segments[0][1] is None:
            return m.group(0)
        out = []
        for seg, is_rtl in segments:
            attrs = ({"rtl": "1", "lang": "he-IL"} if is_rtl
                     else {"rtl": "0", "lang": "en-US"})
            out.append("<a:r>" + _set_attrs(rpr, **attrs)
                       + "<a:t>" + _escape(seg) + "</a:t></a:r>")
        return "".join(out)

    return RUN.sub(fix_run, para_body)


def fix_xml(xml: str) -> str:
    return PARA.sub(lambda m: "<a:p>" + fix_paragraph(m.group(1)) + "</a:p>", xml)


def fix_pptx(path: Path) -> tuple[int, int]:
    src = path.with_suffix(".pptx.orig")
    shutil.copy2(path, src)
    touched = runs_before = 0
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
            path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if re.fullmatch(r"ppt/(slides|notesSlides)/\w+\.xml", item.filename):
                xml = data.decode("utf-8")
                runs_before += len(RUN.findall(xml))
                new = fix_xml(xml)
                if new != xml:
                    touched += 1
                data = new.encode("utf-8")
            zout.writestr(item, data)
    src.unlink()
    return touched, runs_before


if __name__ == "__main__":
    p = Path(sys.argv[1])
    n, runs = fix_pptx(p)
    print(f"תוקנו {n} שקפים ({runs} ריצות נסרקו): {p}")
