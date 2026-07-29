"""בונה את לוח פרשות השבוע מ-Hebcal אל ``data/parasha.json``.

כלי פיתוח בלבד, בדיוק כמו ``verify_zmanim.py`` — האתר עצמו לא פונה לרשת.

למה קובץ ולא חישוב: סדר הפרשיות תלוי בטבלת קביעויות (איזה זוגות מחוברים
בכל אחד מ-14 טיפוסי השנה), ובאתר הלכה פרשה שגויה היא טעות שנראית כל שבוע.
הערת המודול ב-``app/hebcal.py`` כבר קבעה שזה יגיע מקובץ בנוי מראש.

הלוח הוא של **ארץ ישראל** (i=on). בחו״ל הסדר נבדל בשנים שבהן יום טוב נופל
בשבת, ולכן אסור להגיש את הקובץ הזה לקהל בחו״ל בלי לבנות אותו מחדש.

    python scripts/build_parasha.py                  # 2026-2050
    python scripts/build_parasha.py --from 2030 --to 2040
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

API = "https://www.hebcal.com/hebcal"
OUT = Path(__file__).resolve().parent.parent / "data" / "parasha.json"


def fetch_year(year: int) -> dict[str, str]:
    """כל שבתות השנה הלועזית → שם הפרשה בעברית."""
    response = requests.get(
        API,
        params={
            "v": "1", "cfg": "json", "year": str(year), "month": "x",
            "s": "on",    # פרשות השבוע
            "i": "on",    # לוח ארץ ישראל
            # כל השאר כבוי — אנחנו רוצים רק את הפרשות.
            "maj": "off", "min": "off", "mod": "off",
            "nx": "off", "mf": "off", "ss": "off", "c": "off",
        },
        timeout=30,
    )
    response.raise_for_status()

    out: dict[str, str] = {}
    for item in response.json().get("items", []):
        if item.get("category") != "parashat":
            continue
        # "פרשת ויקהל־פקודי" → "ויקהל־פקודי". הכותרת נשמרת בעברית כלשונה,
        # כולל המקף המחבר בזוגות.
        name = item["hebrew"].removeprefix("פרשת ").strip()
        out[item["date"]] = name
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="בניית לוח פרשות השבוע")
    parser.add_argument("--from", dest="start", type=int, default=2026)
    parser.add_argument("--to", dest="end", type=int, default=2050)
    args = parser.parse_args()

    table: dict[str, str] = {}
    for year in range(args.start, args.end + 1):
        year_table = fetch_year(year)
        if not year_table:
            raise SystemExit(f"לא התקבלו פרשות לשנת {year}")
        table.update(year_table)
        print(f"  {year}: {len(year_table)} פרשות")

    payload = {
        "source": "hebcal.com",
        "rite": "israel",
        "years": [args.start, args.end],
        "shabbatot": dict(sorted(table.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nנכתבו {len(table)} שבתות אל {OUT}")


if __name__ == "__main__":
    main()
