"""חישוב זמני היום ההלכתיים — מקומי לחלוטין, בלי קריאות רשת.

המנוע הוא אלגוריתם המיקום הסולרי של NOAA. הזמנים מחושבים ל**גובה פני הים**
(מישור), כמו ברוב הלוחות המקובלים בארץ, ולא לפי גובה היישוב בפועל.

סקריפט ``scripts/verify_zmanim.py`` משווה את הפלט כאן מול Hebcal לאורך שנה
שלמה בכמה ערים. הוא כלי פיתוח בלבד — האתר עצמו לעולם לא פונה החוצה.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import acos, asin, cos, degrees, radians, sin, tan
from zoneinfo import ZoneInfo

from . import hebcal

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")

# הזווית המקובלת לזריחה ולשקיעה: חצי קוטר השמש + שבירה אטמוספרית.
ZENITH_SUNRISE_SUNSET = 90.833

#: זוויות שקיעת השמש מתחת לאופק, לפי הדעות המקובלות.
DEPRESSION_ALOT = 16.1        # עלות השחר
DEPRESSION_MISHEYAKIR = 11.5  # זמן טלית ותפילין
DEPRESSION_TZEIT = 8.5        # צאת הכוכבים, שלושה כוכבים בינוניים

_JD_OFFSET = 1721424.5  # toordinal() -> Julian Day בחצות UT


@dataclass(frozen=True)
class City:
    slug: str
    name: str
    lat: float
    lon: float
    elevation: int
    #: דקות לפני השקיעה להדלקת נרות, לפי מנהג המקום.
    candle_offset: int
    #: מקור המנהג, מוצג למשתמש כדי שלא ייראה כמספר שרירותי.
    candle_note: str = ""


#: ערים בישראל. זמני הדלקת הנרות הם מנהג המקום ולא חישוב — ראה candle_note.
CITIES: tuple[City, ...] = (
    City("jerusalem", "ירושלים", 31.7683, 35.2137, 754, 40, "מנהג ירושלים"),
    City("tel-aviv", "תל אביב–יפו", 32.0853, 34.7818, 34, 18),
    City("haifa", "חיפה", 32.7940, 34.9896, 300, 30, "מנהג חיפה"),
    City("beer-sheva", "באר שבע", 31.2530, 34.7915, 260, 18),
    City("petah-tikva", "פתח תקווה", 32.0878, 34.8878, 51, 22, "מנהג פתח תקווה"),
    City("rishon", "ראשון לציון", 31.9730, 34.7925, 60, 18),
    City("ashdod", "אשדוד", 31.8040, 34.6550, 50, 18),
    City("netanya", "נתניה", 32.3215, 34.8532, 25, 18),
    City("bnei-brak", "בני ברק", 32.0840, 34.8330, 35, 18),
    City("holon", "חולון", 32.0158, 34.7874, 30, 18),
    City("ramat-gan", "רמת גן", 32.0684, 34.8248, 50, 18),
    City("rehovot", "רחובות", 31.8928, 34.8113, 76, 18),
    City("herzliya", "הרצליה", 32.1624, 34.8447, 40, 18),
    City("kfar-saba", "כפר סבא", 32.1750, 34.9070, 60, 18),
    City("ashkelon", "אשקלון", 31.6688, 34.5715, 55, 18),
    City("bet-shemesh", "בית שמש", 31.7500, 34.9886, 300, 18),
    City("modiin", "מודיעין", 31.8928, 35.0104, 300, 18),
    City("modiin-illit", "מודיעין עילית", 31.9320, 35.0430, 320, 18),
    City("beitar", "ביתר עילית", 31.6969, 35.1178, 700, 18),
    City("elad", "אלעד", 32.0522, 34.9511, 130, 18),
    City("tzfat", "צפת", 32.9646, 35.4960, 900, 30, "מנהג צפת"),
    City("tiberias", "טבריה", 32.7959, 35.5300, -200, 18),
    City("nahariya", "נהריה", 33.0059, 35.0947, 20, 18),
    City("akko", "עכו", 32.9281, 35.0818, 20, 18),
    City("afula", "עפולה", 32.6078, 35.2897, 60, 18),
    City("kiryat-shmona", "קריית שמונה", 33.2075, 35.5695, 145, 18),
    City("lod", "לוד", 31.9514, 34.8953, 60, 18),
    City("ramla", "רמלה", 31.9288, 34.8667, 80, 18),
    City("ariel", "אריאל", 32.1056, 35.1872, 550, 18),
    City("hebron", "קריית ארבע", 31.5300, 35.1000, 950, 18),
    City("dimona", "דימונה", 31.0700, 35.0333, 570, 18),
    City("eilat", "אילת", 29.5577, 34.9519, 12, 18),
)

CITIES_BY_SLUG = {c.slug: c for c in CITIES}
DEFAULT_CITY = CITIES_BY_SLUG["jerusalem"]


def get_city(slug: str | None) -> City:
    return CITIES_BY_SLUG.get(slug or "", DEFAULT_CITY)


# ---------------------------------------------------------------------------
# מנוע סולרי
# ---------------------------------------------------------------------------


def _solar_params(julian_day: float) -> tuple[float, float]:
    """(נטיית השמש במעלות, משוואת הזמן בדקות) לרגע נתון."""
    t = (julian_day - 2451545.0) / 36525.0

    mean_long = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    mean_anom = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)

    m_rad = radians(mean_anom)
    center = (
        sin(m_rad) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + sin(2 * m_rad) * (0.019993 - 0.000101 * t)
        + sin(3 * m_rad) * 0.000289
    )

    omega = 125.04 - 1934.136 * t
    apparent_long = mean_long + center - 0.00569 - 0.00478 * sin(radians(omega))

    mean_obliquity = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    obliquity = mean_obliquity + 0.00256 * cos(radians(omega))

    declination = degrees(asin(sin(radians(obliquity)) * sin(radians(apparent_long))))

    var_y = tan(radians(obliquity / 2.0)) ** 2
    l_rad = radians(mean_long)
    eq_of_time = 4.0 * degrees(
        var_y * sin(2 * l_rad)
        - 2 * eccentricity * sin(m_rad)
        + 4 * eccentricity * var_y * sin(m_rad) * cos(2 * l_rad)
        - 0.5 * var_y * var_y * sin(4 * l_rad)
        - 1.25 * eccentricity * eccentricity * sin(2 * m_rad)
    )
    return declination, eq_of_time


def _event_minutes_utc(day: date, lat: float, lon: float, zenith: float, rising: bool) -> float | None:
    """דקות מחצות UTC שבהן השמש חוצה את הזווית. None אם היא לא חוצה אותה כלל.

    מריצים שלוש איטרציות: ההערכה הראשונה נלקחת בחצות היום, ואז מחשבים מחדש
    את נטיית השמש ומשוואת הזמן ברגע המשוער עצמו. בלי זה יש סטייה של עד דקה.
    """
    jd_midnight = day.toordinal() + _JD_OFFSET
    minutes = 720.0

    for _ in range(3):
        declination, eq_of_time = _solar_params(jd_midnight + minutes / 1440.0)
        d_rad, lat_rad = radians(declination), radians(lat)
        argument = cos(radians(zenith)) / (cos(lat_rad) * cos(d_rad)) - tan(lat_rad) * tan(d_rad)
        if not -1.0 <= argument <= 1.0:
            return None
        # זווית השעה חיובית לפני חצות היום, ולכן שלילית אחריו.
        hour_angle = degrees(acos(argument))
        if not rising:
            hour_angle = -hour_angle
        minutes = 720.0 - 4.0 * (lon + hour_angle) - eq_of_time

    return minutes


def _solar_noon_minutes_utc(day: date, lon: float) -> float:
    """מעבר השמש במרידיאן — חצות היום האסטרונומי."""
    jd_midnight = day.toordinal() + _JD_OFFSET
    minutes = 720.0
    for _ in range(3):
        _, eq_of_time = _solar_params(jd_midnight + minutes / 1440.0)
        minutes = 720.0 - 4.0 * lon - eq_of_time
    return minutes


def _to_local(day: date, minutes_utc: float | None) -> datetime | None:
    if minutes_utc is None:
        return None
    midnight_utc = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo("UTC"))
    return (midnight_utc + timedelta(minutes=minutes_utc)).astimezone(ISRAEL_TZ)


def sun_event(day: date, city: City, zenith: float, *, rising: bool) -> datetime | None:
    return _to_local(day, _event_minutes_utc(day, city.lat, city.lon, zenith, rising))


def sunrise(day: date, city: City) -> datetime | None:
    return sun_event(day, city, ZENITH_SUNRISE_SUNSET, rising=True)


def sunset(day: date, city: City) -> datetime | None:
    return sun_event(day, city, ZENITH_SUNRISE_SUNSET, rising=False)


def solar_noon(day: date, city: City) -> datetime | None:
    return _to_local(day, _solar_noon_minutes_utc(day, city.lon))


# ---------------------------------------------------------------------------
# זמני היום ההלכתיים
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Zman:
    key: str
    label: str
    time: datetime | None
    note: str = ""
    #: זמנים ראשיים מוצגים בולט בראש העמוד.
    primary: bool = False

    @property
    def formatted(self) -> str:
        return self.time.strftime("%H:%M") if self.time else "—"

    @property
    def iso(self) -> str:
        return self.time.isoformat() if self.time else ""


def _shift(base: datetime | None, minutes: float) -> datetime | None:
    return base + timedelta(minutes=minutes) if base else None


def _proportional(start: datetime | None, end: datetime | None, hours: float) -> datetime | None:
    """נקודה אחרי ``hours`` שעות זמניות מ-``start``, כשהיום נמתח עד ``end``."""
    if not start or not end:
        return None
    return start + (end - start) * (hours / 12.0)


def compute(day: date, city: City) -> dict:
    """כל זמני היום עבור תאריך ועיר."""
    rise = sunrise(day, city)
    set_ = sunset(day, city)

    alot = sun_event(day, city, 90.0 + DEPRESSION_ALOT, rising=True)
    misheyakir = sun_event(day, city, 90.0 + DEPRESSION_MISHEYAKIR, rising=True)
    tzeit = sun_event(day, city, 90.0 + DEPRESSION_TZEIT, rising=False)

    # שיטת המגן אברהם מותחת את היום מעלות השחר עד צאת הכוכבים של ר"ת,
    # ובמימוש המקובל שניהם ע"ב דקות מהזריחה ומהשקיעה.
    alot_72 = _shift(rise, -72)
    tzeit_72 = _shift(set_, 72)

    # חצות נלקח מהמעבר במרידיאן ולא מאמצע היום. ההפרש קטן מדקה, אבל המעבר
    # הוא ההגדרה המדויקת וגם מה שהלוחות המקובלים מציגים.
    chatzot = solar_noon(day, city)
    shaa_gra = (set_ - rise) / 12 if rise and set_ else None
    shaa_mga = (tzeit_72 - alot_72) / 12 if alot_72 and tzeit_72 else None

    candle = _shift(set_, -city.candle_offset)

    zmanim = [
        Zman("alot", "עלות השחר", alot, f"{DEPRESSION_ALOT}° מתחת לאופק"),
        Zman("alot72", "עלות השחר (ע\"ב דקות)", alot_72, "72 דקות לפני הזריחה"),
        Zman("misheyakir", "משיכיר — טלית ותפילין", misheyakir, f"{DEPRESSION_MISHEYAKIR}° מתחת לאופק"),
        Zman("sunrise", "הנץ החמה", rise, "זריחה במישור", primary=True),
        Zman("shema_mga", "סוף זמן ק\"ש — מג\"א", _proportional(alot_72, tzeit_72, 3), "3 שעות זמניות מעלות השחר"),
        Zman("shema_gra", "סוף זמן ק\"ש — הגר\"א", _proportional(rise, set_, 3), "3 שעות זמניות מהנץ", primary=True),
        Zman("tefila_mga", "סוף זמן תפילה — מג\"א", _proportional(alot_72, tzeit_72, 4), "4 שעות זמניות מעלות השחר"),
        Zman("tefila_gra", "סוף זמן תפילה — הגר\"א", _proportional(rise, set_, 4), "4 שעות זמניות מהנץ"),
        Zman("chatzot", "חצות היום", chatzot, "אמצע היום המדויק", primary=True),
        Zman("mincha_gedola", "מנחה גדולה", _proportional(rise, set_, 6.5), "חצי שעה זמנית אחרי חצות"),
        Zman("mincha_ketana", "מנחה קטנה", _proportional(rise, set_, 9.5), "9.5 שעות זמניות מהנץ"),
        Zman("plag", "פלג המנחה", _proportional(rise, set_, 10.75), "10.75 שעות זמניות מהנץ"),
        Zman("sunset", "שקיעת החמה", set_, "שקיעה במישור", primary=True),
        Zman("tzeit", "צאת הכוכבים", tzeit, f"{DEPRESSION_TZEIT}° מתחת לאופק", primary=True),
        Zman("tzeit72", "צאת הכוכבים — ר\"ת", tzeit_72, "72 דקות אחרי השקיעה"),
        Zman("chatzot_layla", "חצות הלילה", _shift(chatzot, 12 * 60), "12 שעות אחרי חצות היום"),
    ]

    return {
        "date": day,
        "city": city,
        "zmanim": zmanim,
        "by_key": {z.key: z for z in zmanim},
        "candle_lighting": candle,
        "shaa_zmanit_gra": shaa_gra,
        "shaa_zmanit_mga": shaa_mga,
        "hebrew_date": hebcal.format_hebrew_date(day),
        "holidays": hebcal.holidays_for(day),
        "omer": hebcal.omer_day(day),
    }


# ---------------------------------------------------------------------------
# שבת
# ---------------------------------------------------------------------------


def shabbat_times(day: date, city: City) -> dict:
    """זמני השבת הרלוונטית לתאריך נתון."""
    if day.weekday() == 5:
        # בשבת עצמה השבת הרלוונטית היא זו שנכנסה אתמול, לא זו שבעוד שבוע.
        friday = day - timedelta(days=1)
    else:
        friday = day + timedelta(days=(4 - day.weekday()) % 7)
    saturday = friday + timedelta(days=1)

    entry = _shift(sunset(friday, city), -city.candle_offset)
    exit_ = sun_event(saturday, city, 90.0 + DEPRESSION_TZEIT, rising=False)
    exit_rt = _shift(sunset(saturday, city), 72)

    return {
        "friday": friday,
        "saturday": saturday,
        "entry": entry,
        "exit": exit_,
        "exit_rabbeinu_tam": exit_rt,
        "city": city,
        "hebrew_date": hebcal.format_hebrew_date(saturday),
        "holidays": hebcal.holidays_for(saturday),
    }


def upcoming_shabbat(city: City, now: datetime | None = None) -> dict:
    """השבת שעוד לפנינו. אחרי צאת השבת עוברים כבר לשבוע הבא.

    בלי הבדיקה הזו, במוצאי שבת דף הבית היה מציג זמנים שכבר עברו.
    """
    now = now or datetime.now(ISRAEL_TZ)
    times = shabbat_times(now.date(), city)
    if times["exit"] and now > times["exit"]:
        times = shabbat_times(now.date() + timedelta(days=1), city)
    return times
