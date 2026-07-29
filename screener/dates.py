"""Parser tanggal natural (ID/EN) untuk perintah bot & CLI."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

JAKARTA = ZoneInfo("Asia/Jakarta")

MONTHS: dict[str, int] = {
    # English
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
    # Indonesian
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "agust": 8,
    "oktober": 10,
    "nopember": 11,
    "des": 12,
    "desember": 12,
}


def now_jakarta(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JAKARTA)
    if now.tzinfo is None:
        return now.replace(tzinfo=JAKARTA)
    return now.astimezone(JAKARTA)


def previous_trading_day(ref: date | None = None) -> date:
    d = ref or now_jakarta().date()
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _clean(text: str) -> str:
    t = text.strip().lower()
    t = t.replace(",", " ")
    # buang kata pengisi umum
    junk = [
        "tanggal",
        "tgl",
        "tgl.",
        "pada",
        "untuk",
        "analisa",
        "analisis",
        "cek",
        "check",
        "saham",
        "potensi",
        "naik",
        "ini",
        "ya",
        "dong",
        "tolong",
        "mohon",
        "please",
        "as-of",
        "asof",
        "/cek",
        "/asof",
    ]
    for w in junk:
        t = re.sub(rf"\b{re.escape(w)}\b", " ", t)
    t = re.sub(r"[^0-9a-z/\-\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_natural_date(value: str | None, *, now: datetime | None = None) -> date | None:
    """Terima banyak format tanggal natural.

    Contoh yang valid:
      - kemarin / yesterday / hari ini / today
      - 2026-07-20
      - 20/07/2026 , 20-07-2026 , 20/7
      - 20 july , 20 juli , 20 july 2026
      - juli 20 , july 20 2026
      - tanggal 20 july ini
    """
    if value is None or str(value).strip() == "":
        return None

    n = now_jakarta(now)
    today = n.date()
    raw = str(value).strip().lower()

    if raw in {"yesterday", "kemarin", "h-1", "prev", "last", "last-session"}:
        return previous_trading_day(today)
    if raw in {"today", "hariini", "hari ini", "sekarang", "latest", "terbaru"}:
        return today

    cleaned = _clean(raw)
    if not cleaned:
        return None
    if cleaned in {"yesterday", "kemarin", "h-1", "prev", "last"}:
        return previous_trading_day(today)
    if cleaned in {"today", "hariini", "hari ini", "sekarang"}:
        return today

    # YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", cleaned)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # DD/MM/YYYY or DD-MM-YYYY or DD/MM
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", cleaned)
    if m:
        dd, mm = int(m.group(1)), int(m.group(2))
        yy = m.group(3)
        year = today.year if yy is None else int(yy)
        if year < 100:
            year += 2000
        return _safe_date(year, mm, dd)

    tokens = cleaned.split()

    # "20 july" / "20 juli 2026"
    if len(tokens) >= 2 and tokens[0].isdigit() and tokens[1] in MONTHS:
        dd = int(tokens[0])
        mm = MONTHS[tokens[1]]
        year = today.year
        if len(tokens) >= 3 and tokens[2].isdigit():
            year = int(tokens[2])
            if year < 100:
                year += 2000
        return _safe_date(year, mm, dd)

    # "july 20" / "juli 20 2026"
    if len(tokens) >= 2 and tokens[0] in MONTHS and tokens[1].isdigit():
        mm = MONTHS[tokens[0]]
        dd = int(tokens[1])
        year = today.year
        if len(tokens) >= 3 and tokens[2].isdigit():
            year = int(tokens[2])
            if year < 100:
                year += 2000
        return _safe_date(year, mm, dd)

    # Cari pola day+month di mana saja dalam teks
    m = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(MONTHS.keys()) + r")(?:\s+(\d{2,4}))?\b",
        cleaned,
    )
    if m:
        dd = int(m.group(1))
        mm = MONTHS[m.group(2)]
        year = today.year
        if m.group(3):
            year = int(m.group(3))
            if year < 100:
                year += 2000
        return _safe_date(year, mm, dd)

    m = re.search(
        r"\b(" + "|".join(MONTHS.keys()) + r")\s+(\d{1,2})(?:\s+(\d{2,4}))?\b",
        cleaned,
    )
    if m:
        mm = MONTHS[m.group(1)]
        dd = int(m.group(2))
        year = today.year
        if m.group(3):
            year = int(m.group(3))
            if year < 100:
                year += 2000
        return _safe_date(year, mm, dd)

    raise ValueError(
        "Format tanggal tidak dikenali. Contoh: kemarin, 20 july, 20 juli 2026, "
        "20/07/2026, 2026-07-20"
    )


def _safe_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"Tanggal tidak valid: {day}/{month}/{year}") from exc


def extract_date_query(text: str) -> tuple[str, date | None]:
    """Dari chat bebas, tentukan mode label + tanggal.

    Return (label, as_of_date|None). None date = data terbaru.
    """
    lower = (text or "").strip().lower()
    if not lower:
        raise ValueError("Pesan kosong")

    # Command shortcuts
    if lower in {"/kemarin", "kemarin", "/yesterday", "yesterday"}:
        d = previous_trading_day()
        return ("kemarin", d)
    if lower in {"/hariini", "/today", "hariini", "hari ini", "today"}:
        return ("hari ini", None)
    if lower in {"/start", "/help", "help", "bantuan"}:
        raise ValueError("__HELP__")

    # /cek ... atau cek ...
    body = lower
    for prefix in ("/cek", "/asof", "cek", "check", "analisa", "analisis"):
        if body == prefix:
            raise ValueError(
                "Sebutkan tanggalnya. Contoh: cek tanggal 20 july / cek kemarin"
            )
        if body.startswith(prefix + " "):
            body = body[len(prefix) :].strip()
            break

    # Jika masih ada slash command lain
    if body.startswith("/") and " " in body:
        body = body.split(maxsplit=1)[1]

    if body in {"kemarin", "yesterday"}:
        d = previous_trading_day()
        return ("kemarin", d)
    if body in {"hari ini", "hariini", "today", "sekarang", "terbaru"}:
        return ("hari ini", None)

    d = parse_natural_date(body)
    return (d.isoformat(), d)
