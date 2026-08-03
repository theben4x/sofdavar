"""מביא את הטקסט המלא של המקורות הקלאסיים מספריא, ושומר אותו במסד.

    python scripts/fetch_sefaria.py data/seed/citations.json

זו **שכבה 1** מתוך שלוש. רמב"ם ושולחן ערוך הם נחלת הכלל, ולכן מותר
להביא אותם בלשונם המלאה — וזה מייתר גם את הצורך לשכתב פסק וגם את
הסיכון להעתיק מספר מוגן.

הכלל היחיד שאין לעקוף: **מה שספריא לא החזירה — לא נכתב.** אין ניחוש,
אין השלמה מהזיכרון, ואין ציטוט שלא הגיע מהשרת. מקור שלא נמצא נרשם
בקובץ עם ``found: false`` ועובר לשכבה 2 כהפניה בלבד.

TLS: הרשת כאן מיירטת תעודות, ו-``certifi`` נכשל עליהן. ``truststore``
מפנה את פייתון למאגר התעודות של מערכת ההפעלה וזה עובד. בלעדיו כל
הקריאות נופלות ב-CERTIFICATE_VERIFY_FAILED.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    print("! truststore לא מותקן — ייתכן ש-SSL ייכשל.  pip install truststore")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "seed" / "sefaria.json"
API = "https://www.sefaria.org/api/v3/texts/"

#: אותיות הגימטריה. ט"ו ו-ט"ז נכתבים כך במכוון ואינם יו"ד-ה"א.
GEMATRIA = {
    "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9,
    "י": 10, "כ": 20, "ל": 30, "מ": 40, "נ": 50, "ס": 60, "ע": 70, "פ": 80,
    "צ": 90, "ק": 100, "ר": 200, "ש": 300, "ת": 400,
    "ך": 20, "ם": 40, "ן": 50, "ף": 80, "ץ": 90,
}


def to_number(word: str) -> int | None:
    """גימטריה למספר, ורק אם ההמרה חוזרת על עצמה בדיוק.

    בדיקת הלוך-חזור היא ההגנה היחידה שיש כאן: פענוח שגוי של שי"ן-יו"ד-ח
    כ-381 במקום 318 נוחת על סימן אמיתי אחר, מחזיר טקסט אמיתי, ונראה
    תקין לחלוטין. ההמרה חזרה מאמתת שהמחרוזת שנכנסה היא בדיוק זו
    שהמספר מייצר.
    """
    clean = re.sub(r'["\'׳״]', "", word).strip()
    if not clean or any(ch not in GEMATRIA for ch in clean):
        return None
    value = sum(GEMATRIA[ch] for ch in clean)
    if not value:
        return None
    # ההשוואה היא על *אוסף* האותיות ולא על סדרן: ספרים כותבים 275
    # כ"ערה" ולא כ"רעה" הקנוני, ושתיהן אותו ערך. ההשוואה עדיין תופסת
    # פענוח שקרא אות אחרת — שזה מה שהבדיקה נועדה לו — אבל אינה פוסלת
    # כתיב לגיטימי.
    return value if sorted(to_hebrew(value)) == sorted(normalise(clean)) else None


def to_hebrew(value: int) -> str:
    out, rest = "", value
    for amount, letter in (
        (400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"), (90, "צ"), (80, "פ"),
        (70, "ע"), (60, "ס"), (50, "נ"), (40, "מ"), (30, "ל"), (20, "כ"),
        (10, "י"), (9, "ט"), (8, "ח"), (7, "ז"), (6, "ו"), (5, "ה"),
        (4, "ד"), (3, "ג"), (2, "ב"), (1, "א"),
    ):
        while rest >= amount:
            out += letter
            rest -= amount
    return out.replace("יה", "טו").replace("יו", "טז")


def normalise(word: str) -> str:
    finals = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}
    return "".join(finals.get(ch, ch) for ch in word)


#: כל דפוס מחזיר (כותרת בספריא, מספרי החלקים).
PATTERNS: list[tuple[str, str, int]] = [
    # רמב"ם — פרק והלכה בהלכות שבת
    (r"רמב\"?ם.*?פ(?:רק)?[\"']?\s*([א-ת]{1,3}).*?ה(?:לכה)?[\"']?\s*([א-ת]{1,3})",
     "Mishneh_Torah,_Sabbath", 2),
    # משנה ברורה — סימן וסעיף קטן
    (r"משנה ברורה.*?סימן\s*([א-ת]{1,4}).*?ס\"ק\s*([א-ת]{1,3})",
     "Mishnah_Berurah", 2),
    # שולחן ערוך אורח חיים — סימן וסעיף. גם כשכתוב "סימן רסג ס\"ב" לבדו.
    # סימן נכתב גם "סי'" וגם "סימן"; הסעיף גם "ס\"ד", גם "סעיף ד" וגם "סעי' ד".
    (r"סי(?:מן)?[\"'׳]?\s*([א-ת]{1,4})\s*(?:ס(?:עיף|עי)?[\"'׳]?\s*([א-ת]{1,3}))?",
     "Shulchan_Arukh,_Orach_Chayim", 2),
]


def to_refs(citation: str) -> list[str]:
    """מחלץ הפניות ספריא ממחרוזת מקור אחת. עשוי להחזיר כמה."""
    refs: list[str] = []
    for pattern, book, depth in PATTERNS:
        if book.startswith("Shulchan"):
            if any(w in citation for w in NOT_SHULCHAN_ARUKH):
                continue  # "סימן" כאן שייך לחיבור אחר
            # רשימת החסימה לעולם לא תהיה שלמה — "ח\"י סימן כא" הפיל אותה
            # והחזיר את הלכות ציצית. לכן ברירת המחדל הפוכה: מקבלים רק
            # כשהמחרוזת אומרת במפורש שולחן ערוך, או שאין בה דבר מלבד
            # ההפניה עצמה. כל קיצור לא מוכר נדחה ועובר לשכבה 2.
            named = re.search(r"שלחן ערוך|שולחן ערוך|שו\"ע|מרן|רמ\"א", citation)
            # "סעי' ד, י" הוא שני סעיפים באותה הפניה — גם הזנב נוקה.
            bare = re.sub(r"סי(?:מן)?[\"'׳]?\s*[א-ת]{1,4}|ס(?:עיף|עי)?[\"'׳]?\s*[א-ת]{1,3}"
                          r"|,\s*[א-ת]{1,3}|[\s\.,()\"'׳״-]|ו?אות\s*[א-ת]{1,3}", "", citation)
            if not named and re.search(r"[א-ת]", bare):
                continue
        for match in re.finditer(pattern, citation):
            parts = [to_number(g) for g in match.groups() if g]
            if not parts or parts[0] is None:
                continue
            if len(parts) < depth or parts[1] is None:
                ref = f"{book}.{parts[0]}"
            else:
                ref = f"{book}.{parts[0]}.{parts[1]}"
            if ref not in refs:
                refs.append(ref)
        if refs:
            break  # הדפוס הראשון שתפס הוא הספציפי ביותר
    return refs


#: חיבורים שאינם שולחן ערוך אך משתמשים ב"סימן" למספור שלהם. בלעדיהם
#: "שו"ת יביע אומר ח"ב סימן יז" היה מתפרש כשולחן ערוך סימן יז — שהוא
#: הלכות ציצית — ומחזיר טקסט אמיתי לגמרי על נושא אחר. זו בדיוק הטעות
#: שהפרויקט הזה נבנה כדי למנוע, ולכן ההתאמה נחסמת ולא "מנוקה".
NOT_SHULCHAN_ARUKH = (
    "יביע אומר", "יבי\"א", "תורה לשמה", "רב פעלים", "מאורות נתן",
    "הב\"ח", "ב\"ח", "בית יוסף", "ילקוט יוסף", "ילקו\"י", "חזון עובדיה",
    "שו\"ת", "הליכות עולם", "כף החיים", "חיי אדם", "ערוך השלחן",
    "מנחת יצחק", "אגרות משה", "ציץ אליעזר", "שבט הלוי",
)


TAGS = re.compile(r"<[^>]+>")


def strip(html: str) -> str:
    text = TAGS.sub(" ", html or "")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def fetch(ref: str, *, retries: int = 2) -> dict[str, Any]:
    url = API + urllib.parse.quote(ref) + "?version=hebrew"
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "sofdavar/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            versions = data.get("versions") or []
            if not versions:
                return {"ref": ref, "found": False, "reason": "אין גרסה עברית"}
            raw = versions[0].get("text")
            text = strip(" ".join(raw) if isinstance(raw, list) else raw)
            if not text:
                return {"ref": ref, "found": False, "reason": "טקסט ריק"}
            return {
                "ref": ref, "found": True, "text": text,
                "he_ref": data.get("heRef") or "", "title": data.get("heTitle") or "",
            }
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return {"ref": ref, "found": False, "reason": "404 — ההפניה לא קיימת"}
            if attempt == retries:
                return {"ref": ref, "found": False, "reason": f"HTTP {error.code}"}
        except Exception as error:  # רשת, TLS, פענוח
            if attempt == retries:
                return {"ref": ref, "found": False, "reason": f"{type(error).__name__}"}
        time.sleep(1.5 * (attempt + 1))
    return {"ref": ref, "found": False, "reason": "נכשל"}


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("שימוש: python scripts/fetch_sefaria.py <קובץ ציטוטים.json>")
    citations = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    if isinstance(citations, dict):
        citations = citations.get("citations", [])

    cache: dict[str, Any] = {}
    if OUT.exists():
        cache = json.loads(OUT.read_text("utf-8"))

    wanted: dict[str, str] = {}
    unparsed: list[str] = []
    for citation in citations:
        refs = to_refs(citation)
        if not refs:
            unparsed.append(citation)
        for ref in refs:
            wanted.setdefault(ref, citation)

    print(f"{len(citations)} מחרוזות מקור -> {len(wanted)} הפניות ספריא")
    print(f"  לא נותחו (עוברות לשכבה 2): {len(unparsed)}")

    fresh = 0
    for ref in wanted:
        if ref in cache and cache[ref].get("found"):
            continue
        cache[ref] = fetch(ref)
        fresh += 1
        mark = "+" if cache[ref]["found"] else "-"
        print(f"  {mark} {ref}" + ("" if cache[ref]["found"] else f"  ({cache[ref]['reason']})"))
        time.sleep(0.4)  # אדיבות לשרת ציבורי וחינמי

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", "utf-8")
    found = sum(1 for v in cache.values() if v.get("found"))
    print(f"\nנשמר {OUT.relative_to(ROOT)} — {found}/{len(cache)} נמצאו, {fresh} חדשים")
    if unparsed:
        print("\nמחרוזות שלא נותחו להפניה — יופיעו כהפניה בלבד:")
        for c in unparsed[:12]:
            print(f"   {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
