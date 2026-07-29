"""Katalog preset screening teknikal + deteksi dari chat sembarangan."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenPreset:
    key: str
    title: str
    short: str
    example: str
    keywords: tuple[str, ...]
    # bobot ekstra jika keyword spesifik ketemu
    weight: float = 1.0


# Urutan penting: keyword lebih spesifik harus menang (score + length)
PRESETS: dict[str, ScreenPreset] = {
    "breakout": ScreenPreset(
        key="breakout",
        title="Breakout / potensi naik",
        short="volume + break resistance + akumulasi",
        example="cek saham potensi naik hari ini",
        keywords=(
            "potensi naik",
            "kandidat naik",
            "breakout",
            "break resistance",
            "tembus resisten",
            "tembus resistance",
            "screening potensi",
            "saham gacor",
        ),
        weight=1.0,
    ),
    "stoch_oversold": ScreenPreset(
        key="stoch_oversold",
        title="Stochastic oversold",
        short="%K ≤ 20 (jenuh jual)",
        example="cek saham stochastic oversold hari ini",
        keywords=(
            "stochastic oversold",
            "stoch oversold",
            "oversold stochastic",
            "jenuh jual",
            "stochastic rendah",
            "stoch rendah",
            "oversold",
        ),
        weight=1.3,
    ),
    "stoch_cross": ScreenPreset(
        key="stoch_cross",
        title="Stochastic cross ke atas",
        short="%K silang naik di atas %D",
        example="cek saham stochastic cross ke atas",
        keywords=(
            "stochastic cross",
            "stoch cross",
            "cross ke atas",
            "silang ke atas",
            "golden cross stoch",
            "stochastic golden",
            "stoch putar naik",
            "stochastic putar",
            "cross atas",
            "silang naik",
            "cross up",
        ),
        weight=1.4,
    ),
    "stoch_bullish": ScreenPreset(
        key="stoch_bullish",
        title="Stochastic bagus / potensi naik",
        short="%K > %D di zona sehat, atau cross naik",
        example="cek saham teknikal stochastic yang lagi bagus",
        keywords=(
            "stochastic bagus",
            "stoch bagus",
            "stochastic baik",
            "stochastic sehat",
            "stochastic bullish",
            "stochastic potensi",
            "stoch potensi",
            "teknikal stochastic",
            "teknis stochastic",
            "stochastic naik",
            "stoch naik",
            "stochastic yang bagus",
            "lagi bagus",
        ),
        weight=1.45,
    ),
    "bandar": ScreenPreset(
        key="bandar",
        title="Bandarmology / money-flow",
        short="CMF/MFI proksi aliran dana bandar",
        example="cek saham bandarmology hari ini",
        keywords=(
            "bandarmology",
            "bandarmologi",
            "bandar mology",
            "bandar",
            "money flow",
            "moneyflow",
            "aliran dana",
            "cmf",
            "mfi kuat",
            "asing beli",
            "foreign buy",
        ),
        weight=1.35,
    ),
    "accumulation": ScreenPreset(
        key="accumulation",
        title="Akumulasi OBV",
        short="OBV naik + volume beli dominan",
        example="cek saham akumulasi hari ini",
        keywords=(
            "akumulasi",
            "accumulation",
            "obv naik",
            "sedang diakumulasi",
            "akumulasi bandar",
        ),
        weight=1.2,
    ),
    "volume": ScreenPreset(
        key="volume",
        title="Volume spike",
        short="volume jauh di atas rata-rata",
        example="cek saham volume tinggi hari ini",
        keywords=(
            "volume tinggi",
            "volume spike",
            "volume naik",
            "voli tinggi",
            "voli naik",
            "unusual volume",
            "volume besar",
        ),
        weight=1.15,
    ),
    "rsi_oversold": ScreenPreset(
        key="rsi_oversold",
        title="RSI oversold",
        short="RSI ≤ 30",
        example="cek saham rsi oversold",
        keywords=(
            "rsi oversold",
            "rsi rendah",
            "rsi jenuh jual",
            "rsi di bawah 30",
            "rsi <30",
            "rsi < 30",
        ),
        weight=1.25,
    ),
    "macd_turn": ScreenPreset(
        key="macd_turn",
        title="MACD putar naik",
        short="histogram MACD membaik / silang naik",
        example="cek saham macd cross",
        keywords=(
            "macd cross",
            "macd putar",
            "macd naik",
            "macd bullish",
            "macd histogram",
            "macd turn",
        ),
        weight=1.2,
    ),
}


PRESET_ALIASES: dict[str, str] = {
    "stochastic_oversold": "stoch_oversold",
    "oversold": "stoch_oversold",
    "stoch_oversold": "stoch_oversold",
    "stoch_cross_up": "stoch_cross",
    "stochastic_cross": "stoch_cross",
    "stoch_bullish": "stoch_bullish",
    "stochastic_bullish": "stoch_bullish",
    "stochastic": "stoch_bullish",
    "stoch": "stoch_bullish",
    "bandarmology": "bandar",
    "bandarmologi": "bandar",
    "money_flow": "bandar",
    "akumulasi": "accumulation",
    "volume_spike": "volume",
    "rsi": "rsi_oversold",
    "macd": "macd_turn",
    "potensi": "breakout",
    "break": "breakout",
}


def normalize_preset_key(key: str | None) -> str:
    k = (key or "breakout").strip().lower()
    return PRESET_ALIASES.get(k, k if k in PRESETS else "breakout")


def preset_title(key: str | None) -> str:
    p = PRESETS.get(normalize_preset_key(key))
    return p.title if p else "Screening"


def format_preset_menu() -> str:
    lines = ["Filter teknikal yang tersedia:"]
    for p in PRESETS.values():
        lines.append(f"• {p.title} — {p.short}")
        lines.append(f"  contoh: {p.example}")
    lines.append("")
    lines.append("Bisa juga gabung waktu: hari ini / kemarin / minggu ini")
    return "\n".join(lines)


def detect_screen_type(lower: str) -> tuple[str, float]:
    """Deteksi preset dari teks (boleh acak/typo sudah dinormalisasi).

    Return (preset_key, confidence 0..1).
    """
    text = (lower or "").strip().lower()
    if not text:
        return "breakout", 0.3

    has_stoch = "stochastic" in text or re.search(r"\bstoch\b", text) is not None

    # Stochastic selalu menang atas "potensi naik" generik
    if has_stoch:
        if "oversold" in text or "jenuh jual" in text or "rendah" in text:
            return "stoch_oversold", 0.92
        if any(w in text for w in ("cross", "silang", "golden", "putar")):
            return "stoch_cross", 0.9
        # "stochastic bagus / potensi naik / teknikal stochastic" → bullish
        return "stoch_bullish", 0.88

    best_key = "breakout"
    best_score = 0.0
    for key, preset in PRESETS.items():
        score = 0.0
        for kw in preset.keywords:
            if kw in text:
                score = max(score, (len(kw) / 28.0) * preset.weight + 0.35)
        if score > best_score:
            best_score = score
            best_key = key

    # Heuristik tambahan messy prompts
    if "bandar" in text and best_key == "breakout":
        best_key, best_score = "bandar", max(best_score, 0.75)
    if "oversold" in text and "rsi" in text:
        best_key, best_score = "rsi_oversold", max(best_score, 0.85)
    elif "oversold" in text:
        best_key, best_score = "stoch_oversold", max(best_score, 0.7)
    if any(w in text for w in ("lagi bagus", "yang bagus", "yang baik")) and best_key == "breakout":
        # tanpa indikator eksplisit — minta menu lebih aman, tapi bila ada saham → breakout
        pass

    if best_score <= 0:
        if any(w in text for w in ("saham", "screening", "scan", "potensi", "kandidat")):
            return "breakout", 0.55
        return "breakout", 0.35

    conf = min(0.95, 0.45 + best_score)
    return best_key, conf


def is_tech_menu_request(lower: str) -> bool:
    """User minta daftar/filter teknikal tanpa spesifikasi jelas."""
    t = lower or ""
    triggers = (
        "teknikal lain",
        "teknis lain",
        "filter teknikal",
        "filter teknis",
        "mau lihat teknikal",
        "lihat teknikal",
        "ada filter apa",
        "bisa filter apa",
        "menu teknikal",
        "menu screening",
        "screen apa saja",
        "screening apa saja",
        "jenis screening",
        "jenis analisa",
        "opsi screening",
        "opsi teknikal",
    )
    if any(x in t for x in triggers):
        return True
    # sangat generik: "cek teknikal" tanpa indikator
    if ("teknikal" in t or "teknis" in t) and not any(
        k in t
        for k in (
            "stochastic",
            "oversold",
            "bandar",
            "rsi",
            "macd",
            "volume",
            "akumulasi",
            "breakout",
            "cross",
            "ihsg",
        )
    ):
        return True
    return False
