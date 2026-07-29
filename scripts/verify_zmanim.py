"""משווה את מנוע הזמנים המקומי מול Hebcal.

כלי פיתוח בלבד. האתר עצמו לא פונה לרשת — הסקריפט הזה קיים כדי לוודא שהחישוב
המקומי לא סטה, ולהריץ אותו מחדש אחרי כל שינוי ב-``app/zmanim.py``.

    python scripts/verify_zmanim.py            # דגימה של השנה הקרובה
    python scripts/verify_zmanim.py --days 60  # בדיקה צפופה יותר
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from app import zmanim  # noqa: E402

API = "https://www.hebcal.com/zmanim"

#: המפתח שלנו -> המפתח אצל Hebcal. רק זמנים שמוגדרים באותה שיטה בשני הצדדים.
KEY_MAP = {
    "alot": "alotHaShachar",
    "misheyakir": "misheyakir",
    "sunrise": "sunrise",
    "shema_gra": "sofZmanShma",
    "shema_mga": "sofZmanShmaMGA",
    "tefila_gra": "sofZmanTfilla",
    "tefila_mga": "sofZmanTfillaMGA",
    "chatzot": "chatzot",
    "mincha_gedola": "minchaGedola",
    "mincha_ketana": "minchaKetana",
    "plag": "plagHaMincha",
    "sunset": "sunset",
    "tzeit": "tzeit85deg",
    "tzeit72": "tzeit72min",
}

TOLERANCE_MINUTES = 1.0


def fetch(city: zmanim.City, day: date) -> dict:
    response = requests.get(
        API,
        params={
            "cfg": "json",
            "latitude": city.lat,
            "longitude": city.lon,
            "tzid": "Asia/Jerusalem",
            "date": day.isoformat(),
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("times", {})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=12, help="כמה תאריכים לדגום")
    parser.add_argument("--start", default=date.today().isoformat())
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    step = max(1, 365 // args.days)
    cities = [zmanim.get_city(s) for s in ("jerusalem", "tel-aviv", "haifa", "eilat")]

    worst: dict[str, float] = {}
    failures: list[str] = []
    checks = 0

    for city in cities:
        for i in range(args.days):
            day = start + timedelta(days=i * step)
            try:
                remote = fetch(city, day)
            except Exception as exc:  # רשת לא זמינה — לא כישלון של החישוב
                print(f"  ! לא ניתן להשוות {city.name} {day}: {exc}")
                continue

            local = zmanim.compute(day, city)["by_key"]

            for our_key, their_key in KEY_MAP.items():
                theirs_raw = remote.get(their_key)
                ours = local[our_key].time
                if not theirs_raw or not ours:
                    continue
                from datetime import datetime

                theirs = datetime.fromisoformat(theirs_raw)
                delta = abs((ours - theirs).total_seconds()) / 60.0
                checks += 1
                if delta > worst.get(our_key, 0):
                    worst[our_key] = delta
                if delta > TOLERANCE_MINUTES:
                    failures.append(
                        f"{city.name} {day} {our_key}: שלנו {ours:%H:%M:%S} / "
                        f"Hebcal {theirs:%H:%M:%S} (פער {delta:.2f} דק')"
                    )

    print(f"\nבוצעו {checks} השוואות בסבילות של {TOLERANCE_MINUTES} דקות.\n")
    print("הפער המרבי לכל זמן:")
    for key in KEY_MAP:
        if key in worst:
            flag = "  " if worst[key] <= TOLERANCE_MINUTES else "!!"
            print(f" {flag} {key:16} {worst[key]:6.2f} דק'")

    if failures:
        print(f"\n{len(failures)} חריגות:")
        for line in failures[:25]:
            print("  -", line)
        return 1

    print("\nהכול בתוך הסבילות.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
