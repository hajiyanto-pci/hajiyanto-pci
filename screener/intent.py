"""Intent parser bahasa natural untuk bot Telegram."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from screener.dates import extract_date_query, parse_natural_date, previous_trading_day
from screener.presets import detect_screen_type, is_tech_menu_request, normalize_preset_key

IntentKind = Literal[
    "help",
    "watchlist",
    "watch",
    "unwatch",
    "breakout",
    "ihsg",
    "screen",
    "stock",
    "fundamental",
    "tech_menu",
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
    "halo",
    "hai",
    "hello",
    "hi",
    "pagi",
    "siang",
    "sore",
    "malam",
    "kabar",
    "cuaca",
    "terima",
    "kasih",
    "thanks",
    "makasih",
    "bisa",
    "mau",
    "ingin",
    "maaf",
    "kedepan",
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
    "stoch",
    "stochastic",
    "oversold",
    "minggu",
    "pekan",
    "week",
    "bandar",
    "bandarmology",
    "akumulasi",
    "volume",
    "macd",
    "rsi",
    "cross",
    "silang",
    "filter",
    "menu",
    "fundamental",
    "fundamentals",
    "roe",
    "pbv",
    "per",
    "hutang",
    "valuasi",
}



# Kata yang menandakan screening banyak saham (bukan 1 ticker)
_SCREEN_HINTS = (
    "kemarin",
    "yesterday",
    "hari ini",
    "hariini",
    "today",
    "minggu ini",
    "pekan ini",
    "this week",
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
    "oversold",
    "stochastic",
    "stoch",
    "bandar",
    "bandarmology",
    "akumulasi",
    "accumulation",
    "volume",
    "macd",
    "rsi",
    "cross",
    "silang",
    "teknikal",
    "teknis",
)


@dataclass
class BotIntent:
    kind: IntentKind
    stock_code: str | None = None
    screen_label: str | None = None
    as_of: date | None = None
    screen_type: str = "breakout"  # breakout | stoch_oversold
    stoch_lookback: int | None = None
    raw: str = ""


def _normalize_chat(text: str) -> str:
    t = (text or "").strip().lower()
    # typo / bahasa santai umum
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
        r"\bdapatkah\b": "tolong",
        r"\bdapatkh\b": "tolong",
        r"\bdapetah\b": "tolong",
        r"\bbisakah\b": "tolong",
        r"\bbisa\s+tolong\b": "tolong",
        r"\bminta\s+tolong\b": "tolong",
        r"\bke\s+depan\b": "kedepan",
        r"\bkedeapan\b": "kedepan",
        r"\bkedepannya\b": "kedepan",
        r"\bgimana\b": "bagaimana",
        r"\bgmn\b": "bagaimana",
        r"\bbgm\b": "bagaimana",
        # typo stochastic
        r"\bschocastic\b": "stochastic",
        r"\bscoshatic\b": "stochastic",
        r"\bscocastic\b": "stochastic",
        r"\bstochastik\b": "stochastic",
        r"\bstochatic\b": "stochastic",
        r"\bstochasticc\b": "stochastic",
        r"\bstochastc\b": "stochastic",
        r"\bstochasstic\b": "stochastic",
        r"\bstochastoc\b": "stochastic",
        r"\bstoch\b": "stochastic",
        r"\bover\s*sold\b": "oversold",
        r"\bjenuh\s*jual\b": "oversold",
        r"\bmingguan\b": "minggu ini",
        r"\bpekan\s*ini\b": "minggu ini",
        r"\bthis\s*week\b": "minggu ini",
        r"\bweek\s*ini\b": "minggu ini",
        r"\bhari\s*ni\b": "hari ini",
        # bandarmology typos
        r"\bbandarmologi\b": "bandarmology",
        r"\bbandar\s*mology\b": "bandarmology",
        r"\bbandarmologyy\b": "bandarmology",
        r"\bbndar\b": "bandar",
        r"\baliran\s*dana\b": "aliran dana",
        r"\bmoney\s*flow\b": "money flow",
        # cross / silang
        r"\bcros\b": "cross",
        r"\bcrosss\b": "cross",
        r"\bsilang\s*keatas\b": "silang ke atas",
        r"\bcross\s*keatas\b": "cross ke atas",
        r"\bgolden\s*cros\b": "golden cross",
        r"\bvoli\b": "volume",
        r"\bvolum\b": "volume",
        r"\bakumulsi\b": "akumulasi",
        r"\bakumulasii\b": "akumulasi",
        r"\btolgn\b": "tolong",
        r"\btolng\b": "tolong",
        r"\bteknika\b": "teknikal",
        r"\bteknikal\b": "teknikal",
        r"\blgi\b": "lagi",
        r"\bbgus\b": "bagus",
        r"\bbguas\b": "bagus",
        r"\bnais\b": "bisa",
        r"\bbagimana\b": "bagaimana",
        r"\bkemauan\b": "kemauan",
        r"\bsemabrangan\b": "sembarangan",
        r"\bsembrangan\b": "sembarangan",
        r"\bimprve\b": "improve",
        r"\bpelase\b": "please",
        r"\bplese\b": "please",
        r"\bfundemental\b": "fundamental",
        r"\bfundametal\b": "fundamental",
        r"\bfundamentl\b": "fundamental",
        r"\bfundamentals\b": "fundamental",
        r"\bvaluasi\b": "valuasi",
        r"\bhutang\b": "hutang",
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
    # Hanya terima bare ticker jika pesan hampir murni 1 kode (hindari salah baca chat bebas)
    if len(candidates) == 1 and len(tokens) <= 3:
        # butuh sinyal analisa/cek, atau pesan hanya kode saja
        if len(tokens) == 1 or any(
            w in lower for w in ("cek", "check", "analisa", "analisis", "info", "lihat", "tolong")
        ):
            return candidates[0].upper()
    return None


def _is_fundamental_phrase(lower: str) -> bool:
    if "fundamental" in lower or "valuasi" in lower:
        return True
    # "cek roe/pbv/per saham bbca"
    if any(k in lower for k in ("roe", "pbv", "per ", " per", "hutang", "neraca")):
        if "saham" in lower or re.search(r"\b[a-z]{3,5}\b", lower):
            return True
    if lower.startswith("/fundamental") or lower.startswith("/fund"):
        return True
    return False


def _extract_fundamental_code(lower: str, raw: str) -> str | None:
    """Ambil kode saham dari frasa fundamental."""
    m = re.search(
        r"(?:/(?:fundamental|fund)|fundamental|valuasi|roe|pbv|per)\s+"
        r"(?:saham\s+)?([a-z]{3,5})\b",
        lower,
    )
    if m and m.group(1) not in _NOT_TICKERS and m.group(1) not in _STOP:
        return m.group(1).upper()

    m = re.search(r"\bsaham\s+([a-z]{3,5})\b", lower)
    if m and m.group(1) not in _NOT_TICKERS and m.group(1) not in _STOP:
        return m.group(1).upper()

    # fallback: extract_stock_code
    return extract_stock_code(raw)


def _is_stoch_oversold_phrase(lower: str) -> bool:
    has_stoch = "stochastic" in lower or "stoch" in lower
    has_oversold = "oversold" in lower or "jenuh jual" in lower
    if has_stoch and has_oversold:
        return True
    if has_stoch and ("rendah" in lower or "lemah" in lower or "<20" in lower or "di bawah 20" in lower):
        return True
    if has_oversold and ("saham" in lower or "screening" in lower or "scan" in lower or "cek" in lower):
        # jangan override jika jelas rsi oversold
        if "rsi" in lower:
            return False
        return True
    return False


def _is_technical_screen_phrase(lower: str) -> bool:
    """Ada sinyal user minta screening teknikal (bukan 1 ticker)."""
    if _is_stoch_oversold_phrase(lower):
        return True
    if is_tech_menu_request(lower):
        return True
    keys = (
        "bandar",
        "bandarmology",
        "money flow",
        "aliran dana",
        "akumulasi",
        "accumulation",
        "stochastic",
        "stoch",
        "oversold",
        "cross ke atas",
        "silang ke atas",
        "cross up",
        "volume tinggi",
        "volume spike",
        "volume naik",
        "rsi oversold",
        "rsi rendah",
        "macd",
        "filter teknikal",
        "screening",
        "screener",
        "scan saham",
        "teknikal stochastic",
        "teknis stochastic",
        "lagi bagus",
    )
    return any(k in lower for k in keys)


def _extract_screen_as_of(lower: str) -> tuple[str, date | None, int | None]:
    """Ambil tanggal/window screening dari frasa natural.

    Return (label, as_of_date|None, stoch_lookback|None).
    lookback dipakai khusus filter stoch oversold (1=hari ini, 5=minggu ini).
    """
    # kemarin / yesterday
    if "kemarin" in lower or "yesterday" in lower or "kemaren" in lower:
        return ("kemarin", previous_trading_day(), 1)

    if "minggu ini" in lower or "pekan ini" in lower:
        return ("minggu ini", None, 5)

    if re.search(r"\bhari\s+ini\b", lower) or "hariini" in lower or "today" in lower:
        return ("hari ini", None, 1)

    if "sekarang" in lower or "terbaru" in lower or "latest" in lower:
        return ("hari ini", None, 1)

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
        "stochastic",
        "oversold",
        "minggu",
        "pekan",
        "bandar",
        "bandarmology",
        "akumulasi",
        "accumulation",
        "volume",
        "macd",
        "rsi",
        "cross",
        "silang",
        "atas",
        "ke",
        "putar",
        "naik",
        "tinggi",
        "spike",
        "rendah",
        "golden",
        "money",
        "flow",
        "aliran",
        "dana",
        "obv",
        "lihat",
        "liat",
        "mau",
        "dong",
    ]
    for w in junk:
        cleaned = re.sub(rf"\b{re.escape(w)}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        # default: hari ini jika user bilang "cek saham potensi" tanpa tanggal
        return ("hari ini", None, 1)

    try:
        d = parse_natural_date(cleaned)
        return (d.isoformat(), d, 1)
    except Exception:
        try:
            label, as_of = extract_date_query(lower)
            return (label, as_of, 1)
        except Exception:
            # Chat teknikal tanpa tanggal eksplisit → default hari ini
            return ("hari ini", None, 1)


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

    # Fundamental: "please analisa fundamental saham bbca"
    if _is_fundamental_phrase(lower):
        code = _extract_fundamental_code(lower, raw)
        return BotIntent(kind="fundamental", stock_code=code, raw=raw)

    if lower in {"/teknikal", "/filter", "menu teknikal", "filter teknikal"}:
        return BotIntent(kind="tech_menu", raw=raw)

    # User minta daftar opsi teknikal
    if is_tech_menu_request(lower):
        return BotIntent(kind="tech_menu", raw=raw)

    # Screening teknikal spesifik (bandar / stoch / volume / dll) dari chat acak
    if _is_technical_screen_phrase(lower) or _is_stoch_oversold_phrase(lower):
        screen_type, _conf = detect_screen_type(lower)
        screen_type = normalize_preset_key(screen_type)
        label, as_of, lookback = _extract_screen_as_of(lower)
        return BotIntent(
            kind="screen",
            screen_label=label,
            as_of=as_of,
            screen_type=screen_type,
            stoch_lookback=lookback or 1,
            raw=raw,
        )

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
            only_stock = (
                m.group(1) not in _NOT_TICKERS
                and "potensi" not in lower
                and "kemarin" not in lower
                and "yesterday" not in lower
                and not re.search(r"\bhari\s+ini\b", lower)
                and "tanggal" not in lower
                and "minggu ini" not in lower
                and "oversold" not in lower
                and "stochastic" not in lower
                and "bandar" not in lower
                and "akumulasi" not in lower
                and "macd" not in lower
                and "volume" not in lower
            )
            if only_stock:
                code = m.group(1).upper()
        if code:
            return BotIntent(kind="stock", stock_code=code, raw=raw)

        label, as_of, lookback = _extract_screen_as_of(lower)
        screen_type, _conf = detect_screen_type(lower)
        return BotIntent(
            kind="screen",
            screen_label=label,
            as_of=as_of,
            screen_type=normalize_preset_key(screen_type),
            stoch_lookback=lookback,
            raw=raw,
        )

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
