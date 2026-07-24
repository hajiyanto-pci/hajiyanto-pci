"""Intent parser bahasa natural untuk bot Telegram."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from screener.dates import extract_date_query, parse_natural_date, previous_trading_day

IntentKind = Literal[
    "help",
    "watchlist",
    "watch",
    "unwatch",
    "breakout",
    "ihsg",
    "screen",
    "stock",
    "unknown",
]

_STOP = {
    "cek",
    "check",
    "please",
    "pls",
    "tolong",
    "mohon",
    "dong",
    "ya",
    "yah",
    "kak",
    "bang",
    "saham",
    "ticker",
    "kode",
    "analisa",
    "analisis",
    "info",
    "tentang",
    "untuk",
    "bagaimana",
    "gimana",
    "apakah",
    "saran",
    "detail",
    "teknikal",
    "teknis",
    "the",
    "a",
    "of",
    "on",
    "lihat",
    "cari",
    "tampilkan",
    "kasih",
    "kasi",
    "ada",
    "yang",
    "mana",
    "rekomendasi",
    "rekom",
    "candidate",
    "kandidat",
    "list",
    "daftar",
}

_NOT_TICKERS = {
    "hari",
    "ini",
    "tgl",
    "today",
    "kemarin",
    "open",
    "break",
    "volume",
    "score",
    "skor",
    "help",
    "start",
    "please",
    "bantu",
    "list",
    "watch",
    "alert",
    "potensi",
    "naik",
    "turun",
    "bullish",
    "bearish",
    "strong",
    "bagus",
    "gacor",
    "cuán",
    "breakout",
    "resisten",
    "resistance",
    "akumulasi",
    "ihsg",
    "indeks",
    "makro",
    "outlook",
    "prediksi",
    "prospek",
}

# Kata yang menandakan screening banyak saham (bukan 1 ticker)
_SCREEN_HINTS = (
    "kemarin",
    "yesterday",
    "hari ini",
    "hariini",
    "today",
    "potensi",
    "kandidat",
    "rekomendasi",
    "rekom",
    "screening",
    "screener",
    "scan",
    "breakout",
    "banyak",
    "semua",
    "daftar",
    "list",
    "tanggal",
    "tgl",
    "naik",
)


@dataclass
class BotIntent:
    kind: IntentKind
    stock_code: str | None = None
    screen_label: str | None = None
    as_of: date | None = None
    raw: str = ""


def _normalize_chat(text: str) -> str:
    t = (text or "").strip().lower()
    # typo umum
    replacements = {
        r"\bek\b": "cek",
        r"\bcok\b": "cek",
        r"\bcekk\b": "cek",
        r"\bceki\b": "cek",
        r"\bhri\b": "hari",
        r"\bkmrin\b": "kemarin",
        r"\bkemaren\b": "kemarin",
        r"\bpotensi\s+naiknya\b": "potensi naik",
        r"\bsahm\b": "saham",
    }
    for pat, rep in replacements.items():
        t = re.sub(pat, rep, t)
    t = re.sub(r"[^0-9a-z/\-\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_screen_phrase(lower: str) -> bool:
    if any(h in lower for h in _SCREEN_HINTS):
        return True
    # "saham potensi ..." tanpa kode ticker jelas
    if "saham" in lower and ("potensi" in lower or "naik" in lower):
        return True
    return False


def extract_stock_code(text: str) -> str | None:
    """Ambil kode saham dari chat, contoh: 'please cek saham emtk' -> EMTK."""
    raw = (text or "").strip()
    if not raw:
        return None
    lower = _normalize_chat(raw)

    # Screening phrase: jangan anggap ticker
    if _is_screen_phrase(lower):
        # Kecuali eksplisit "cek saham EMTK" tanpa hint screening lain
        # "cek saham emtk" tidak punya screen hint kecuali kata saham saja
        pass

    if re.search(r"\bhari\s+ini\b", lower) or "kemarin" in lower or "yesterday" in lower:
        # Boleh "cek emtk kemarin"? rare — treat as screen if no clear ticker after saham
        if not re.search(r"\bsaham\s+[a-z]{3,5}\b", lower) and not re.search(
            r"/(?:saham|stock|ticker)\s+[a-z]{3,5}\b", lower
        ):
            return None

    # Jika ada hint screening + tidak ada pola "saham KODE" eksplisit → bukan stock
    explicit = re.search(r"(?:/(?:saham|stock|ticker)|\bsaham)\s+([a-z]{3,5})\b", lower)
    if _is_screen_phrase(lower):
        if not explicit:
            return None
        code = explicit.group(1)
        if code in _NOT_TICKERS:
            return None
        # "cek saham potensi kemarin" matches saham potensi → potensi is not ticker
        if code in _NOT_TICKERS or code in {"potensi", "naik", "hari"}:
            return None
        # Jika ada kemarin/hari ini bersamaan dengan ticker, tetap stock? prefer stock only if code valid
        # "cek saham emtk kemarin" -> EMTK analysis as-of kemarin (future). For now return EMTK.
        if code not in _NOT_TICKERS and code not in _STOP:
            # But "saham potensi" -> code=potensi already filtered
            return code.upper()
        return None

    m = re.match(r"^/(?:saham|stock|ticker)\s+([a-z]{3,5})\b", lower)
    if m:
        code = m.group(1)
        return None if code in _NOT_TICKERS else code.upper()

    m = re.search(r"\bsaham\s+([a-z]{3,5})\b", lower)
    if m:
        code = m.group(1)
        if code in _NOT_TICKERS:
            return None
        return code.upper()

    m = re.match(
        r"^(?:cek|check|analisa|analisis|info|lihat)\s+([a-z]{3,5})\b$",
        lower,
    )
    if m:
        code = m.group(1)
        if code in _NOT_TICKERS:
            return None
        return code.upper()

    date_hints = (
        "tanggal",
        "tgl",
        "kemarin",
        "yesterday",
        "hariini",
        "hari ini",
        "july",
        "juli",
        "januari",
        "februari",
        "maret",
        "april",
        "mei",
        "juni",
        "agustus",
        "september",
        "oktober",
        "november",
        "desember",
        "january",
        "february",
        "march",
        "august",
        "october",
        "december",
        "potensi",
    )
    if any(h in lower for h in date_hints):
        return None
    if re.search(r"\b\d{1,2}[/-]\d{1,2}", lower) or re.search(r"\b\d{4}-\d{2}-\d{2}\b", lower):
        return None

    tokens = re.findall(r"[a-z]{3,5}", lower)
    candidates = [t for t in tokens if t not in _STOP and t not in _NOT_TICKERS]
    if len(candidates) == 1:
        return candidates[0].upper()
    if candidates:
        return candidates[-1].upper()
    return None


def _extract_screen_as_of(lower: str) -> tuple[str, date | None]:
    """Ambil tanggal screening dari frasa natural."""
    # kemarin / yesterday
    if "kemarin" in lower or "yesterday" in lower or "kemaren" in lower:
        return ("kemarin", previous_trading_day())

    if re.search(r"\bhari\s+ini\b", lower) or "hariini" in lower or "today" in lower:
        return ("hari ini", None)

    if "sekarang" in lower or "terbaru" in lower or "latest" in lower:
        return ("hari ini", None)

    # tanggal natural tersisa
    cleaned = lower
    junk = [
        "cek",
        "check",
        "please",
        "tolong",
        "saham",
        "potensi",
        "naik",
        "kandidat",
        "rekomendasi",
        "rekom",
        "screening",
        "screener",
        "scan",
        "daftar",
        "list",
        "yang",
        "bagus",
        "gacor",
        "bullish",
        "analisa",
        "analisis",
        "dong",
        "ya",
        "untuk",
        "tanggal",
        "tgl",
    ]
    for w in junk:
        cleaned = re.sub(rf"\b{re.escape(w)}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        # default: hari ini jika user bilang "cek saham potensi" tanpa tanggal
        return ("hari ini", None)

    try:
        d = parse_natural_date(cleaned)
        return (d.isoformat(), d)
    except Exception:
        # fallback ke extract_date_query lama
        return extract_date_query(lower)


def _is_ihsg_phrase(lower: str) -> bool:
    """Deteksi tanya IHSG / makro / outlook indeks."""
    if lower in {"/ihsg", "ihsg", "/makro", "makro"}:
        return True
    if "ihsg" in lower or "jkse" in lower:
        return True
    if "indeks" in lower and ("hari" in lower or "potensi" in lower or "outlook" in lower):
        return True
    if any(
        p in lower
        for p in (
            "outlook ihsg",
            "potensi ihsg",
            "prediksi ihsg",
            "prospek ihsg",
            "analisa ihsg",
            "analisis ihsg",
            "makro hari ini",
            "kondisi makro",
            "sentimen makro",
        )
    ):
        return True
    return False


def parse_user_intent(text: str) -> BotIntent:
    """Pahami maksud user dari chat natural."""
    raw = (text or "").strip()
    lower = _normalize_chat(raw)
    if not lower:
        return BotIntent(kind="unknown", raw=raw)

    if lower in {"/start", "/help", "help", "bantuan", "menu"}:
        return BotIntent(kind="help", raw=raw)

    # IHSG / makro sebelum screening umum ("potensi" juga dipakai di screen)
    if _is_ihsg_phrase(lower):
        return BotIntent(kind="ihsg", raw=raw)

    if lower in {"/watchlist", "watchlist"}:
        return BotIntent(kind="watchlist", raw=raw)

    if lower.startswith("/watch ") or lower.startswith("watch "):
        code = lower.split(maxsplit=1)[1].strip().upper()
        return BotIntent(kind="watch", stock_code=code, raw=raw)

    if lower.startswith("/unwatch ") or lower.startswith("unwatch "):
        code = lower.split(maxsplit=1)[1].strip().upper()
        return BotIntent(kind="unwatch", stock_code=code, raw=raw)

    if lower in {"/breakout", "breakout", "/alert breakout", "cek breakout"}:
        return BotIntent(kind="breakout", raw=raw)

    # Screening natural: "cek saham potensi kemarin", "saham hari ini", dll
    if _is_screen_phrase(lower):
        # Kecuali jelas 1 ticker: "cek saham emtk" (tanpa potensi/kemarin/hari ini)
        code = None
        m = re.search(r"(?:/(?:saham|stock|ticker)|\bsaham)\s+([a-z]{3,5})\b", lower)
        if m and m.group(1) not in _NOT_TICKERS and m.group(1) not in {
            "potensi",
            "naik",
            "hari",
        }:
            # Jika juga ada kemarin/hari ini/potensi → tetap screen kecuali ticker eksplisit
            # dan TIDAK ada kata potensi/kemarin/hari sebagai konteks umum
            only_stock = (
                m.group(1) not in _NOT_TICKERS
                and "potensi" not in lower
                and "kemarin" not in lower
                and "yesterday" not in lower
                and not re.search(r"\bhari\s+ini\b", lower)
                and "tanggal" not in lower
            )
            if only_stock:
                code = m.group(1).upper()
        if code:
            return BotIntent(kind="stock", stock_code=code, raw=raw)

        label, as_of = _extract_screen_as_of(lower)
        return BotIntent(kind="screen", screen_label=label, as_of=as_of, raw=raw)

    # Single stock
    code = extract_stock_code(raw)
    if code:
        return BotIntent(kind="stock", stock_code=code, raw=raw)

    # Date-only / cek tanggal ...
    try:
        label, as_of = extract_date_query(lower)
        return BotIntent(kind="screen", screen_label=label, as_of=as_of, raw=raw)
    except ValueError as exc:
        if str(exc) == "__HELP__":
            return BotIntent(kind="help", raw=raw)

    return BotIntent(kind="unknown", raw=raw)
