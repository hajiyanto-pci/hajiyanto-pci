"""Deteksi apakah chat meminta analisa 1 saham vs screening tanggal."""

from __future__ import annotations

import re

# Kata yang sering muncul di chat natural
_STOP = {
    "cek",
    "check",
    "please",
    "tolong",
    "mohon",
    "dong",
    "ya",
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
    "the",
    "a",
    "of",
    "on",
    "/saham",
    "/stock",
    "/ticker",
    "hari",
    "ini",
    "today",
    "kemarin",
    "yesterday",
    "potensi",
    "naik",
    "break",
    "open",
}

# Bukan kode saham meski 3-5 huruf
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
}


def extract_stock_code(text: str) -> str | None:
    """Ambil kode saham dari chat, contoh: 'please cek saham emtk' -> EMTK.

    Return None jika bukan query saham tunggal.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower().strip()

    # Frasa screening tanggal / hari ini — bukan ticker
    if re.search(r"\bhari\s+ini\b", lower) or lower in {
        "saham hari ini",
        "cek saham hari ini",
        "hari ini",
        "/hariini",
    }:
        return None

    # Shortcut command
    m = re.match(r"^/(?:saham|stock|ticker)\s+([a-z]{3,5})\b", lower)
    if m:
        code = m.group(1)
        return None if code in _NOT_TICKERS else code.upper()

    # Pola eksplisit "saham XXX" (hindari "saham hari")
    m = re.search(r"\bsaham\s+([a-z]{3,5})\b", lower)
    if m:
        code = m.group(1)
        if code in _NOT_TICKERS:
            return None
        return code.upper()

    # "cek emtk" / "analisa emtk" / "info emtk"
    m = re.match(
        r"^(?:cek|check|analisa|analisis|info|lihat)\s+([a-z]{3,5})\b$",
        lower,
    )
    if m:
        code = m.group(1)
        if code in _NOT_TICKERS:
            return None
        return code.upper()

    # Kalimat panjang: ambil kandidat ticker 3-5 huruf, buang stopwords/tanggal
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
