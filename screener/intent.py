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
}


def extract_stock_code(text: str) -> str | None:
    """Ambil kode saham dari chat, contoh: 'please cek saham emtk' -> EMTK.

    Return None jika bukan query saham tunggal.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower().strip()

    # Shortcut command
    m = re.match(r"^/(?:saham|stock|ticker)\s+([a-z]{3,5})\b", lower)
    if m:
        return m.group(1).upper()

    # Pola eksplisit "saham XXX"
    m = re.search(r"\bsaham\s+([a-z]{3,5})\b", lower)
    if m:
        return m.group(1).upper()

    # "cek emtk" / "analisa emtk" / "info emtk"
    m = re.match(
        r"^(?:cek|check|analisa|analisis|info|lihat)\s+([a-z]{3,5})\b$",
        lower,
    )
    if m:
        code = m.group(1)
        if code not in {"hari", "tgl", "tgl.", "kemarin", "today"}:
            return code.upper()

    # Kalimat panjang: ambil kandidat ticker 3-5 huruf, buang stopwords/tanggal
    # Jangan trigger jika ada kata tanggal
    date_hints = (
        "tanggal",
        "tgl",
        "kemarin",
        "yesterday",
        "hariini",
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
    candidates = [t for t in tokens if t not in _STOP]
    # Hindari kata umum
    ban = {
        "please",
        "bantu",
        "bantuan",
        "help",
        "start",
        "hari",
        "ini",
        "open",
        "break",
        "volume",
        "score",
        "skor",
    }
    candidates = [c for c in candidates if c not in ban]
    if len(candidates) == 1:
        return candidates[0].upper()
    # "please cek saham emtk ..." -> last ticker-like often the code
    if candidates:
        # prefer token after 'saham' already handled; else last candidate
        return candidates[-1].upper()
    return None
