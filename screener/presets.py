"""Katalog preset screening teknikal + deteksi dari chat sembarangan."""

from __future__ import annotations

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

    best_key = "breakout"
    best_score = 0.0
    for key, preset in PRESETS.items():
        score = 0.0
        for kw in preset.keywords:
            if kw in text:
                # keyword lebih panjang = lebih spesifik
                score = max(score, (len(kw) / 28.0) * preset.weight + 0.35)
        if score > best_score:
            best_score = score
            best_key = key

    # Heuristik tambahan messy prompts
    if "bandar" in text and best_key == "breakout":
        best_key, best_score = "bandar", max(best_score, 0.75)
    if ("cross" in text or "silang" in text) and "stochastic" in text:
        best_key, best_score = "stoch_cross", max(best_score, 0.85)
    if "oversold" in text and "rsi" in text:
        best_key, best_score = "rsi_oversold", max(best_score, 0.85)
    elif "oversold" in text and "stochastic" in text:
        best_key, best_score = "stoch_oversold", max(best_score, 0.88)
    elif "oversold" in text:
        best_key, best_score = "stoch_oversold", max(best_score, 0.7)

    if best_score <= 0:
        # default potensi/breakout jika ada kata saham/screening
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
