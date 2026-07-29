"""Agent planner: pahami chat user dulu, baru arahkan ke tool analisa saham.

Alur mirip agent:
1. understand() — baca bahasa natural → rencana (intent + parameter + ringkasan pemahaman)
2. clarify bila ragu
3. execute via tool (IHSG / screener / 1 saham / breakout / watchlist)

Opsional: set OPENAI_API_KEY (+ OPENAI_BASE_URL / OPENAI_MODEL) untuk NLU lebih bebas.
Tanpa API key, fallback ke rule-based intent yang sudah ada.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import requests

from screener.intent import BotIntent, parse_user_intent
from screener.presets import normalize_preset_key, preset_title

logger = logging.getLogger(__name__)

AgentKind = Literal[
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
    "clarify",
    "unknown",
]

TOOLS_CATALOG = """
Tools yang tersedia:
- help: tampilkan bantuan
- tech_menu: daftar filter teknikal (bandar, stoch, volume, dll)
- ihsg: outlook IHSG + makro + berita
- screen: screening saham
  screen_type:
    breakout | high_score | stoch_oversold | stoch_cross | stoch_bullish | bandar |
    accumulation | volume | rsi_oversold | macd_turn
  screen_label: kemarin | hari ini | minggu ini | YYYY-MM-DD
  stoch_lookback: 1 (hari) atau 5 (minggu)
- stock: analisa 1 kode saham BEI (teknikal)
- fundamental: analisa fundamental (PER, PBV, ROE, hutang, dll) + saran
  stock_code wajib, contoh BBCA
- breakout: cek break resistance baru
- watch / unwatch / watchlist
- clarify / unknown
"""

SYSTEM_PROMPT = f"""Kamu adalah planner untuk bot analisa saham Indonesia (IDX).
Tugasmu HANYA memahami permintaan user (boleh typo/acak) dan memilih 1 tool + parameter.
Jangan analisa harga sendiri. Jangan buat saran investasi.
Balas HANYA JSON valid tanpa markdown:

{{
  "kind": "<tool>",
  "stock_code": null atau "KODE",
  "screen_label": null atau "kemarin"|"hari ini"|"minggu ini"|"YYYY-MM-DD",
  "as_of": null atau "YYYY-MM-DD",
  "screen_type": "breakout|stoch_oversold|stoch_cross|stoch_bullish|bandar|accumulation|volume|rsi_oversold|macd_turn",
  "stoch_lookback": null atau angka,
  "confidence": 0.0-1.0,
  "understanding": "satu kalimat bahasa Indonesia",
  "clarify_question": null atau pertanyaan
}}

{TOOLS_CATALOG}

Aturan:
- Prompt acak tetap diarahkan ke tool terdekat
- bandar/bandarmology/money flow → screen_type=bandar
- stochastic oversold / jenuh jual → stoch_oversold
- stochastic cross / silang ke atas → stoch_cross
- stochastic bagus / teknikal stochastic / stochastic potensi naik → stoch_bullish
- score tinggi / skor tinggi teknikal → screen_type=high_score
- akumulasi/obv → accumulation
- volume tinggi/spike → volume
- rsi oversold → rsi_oversold
- macd putar/cross → macd_turn
- minta daftar filter/teknikal → tech_menu
- ihsg/makro → ihsg
- analisa fundamental / roe / pbv / per / valuasi + kode saham → fundamental
- cek EMTK / analisa BBCA (tanpa kata fundamental) → stock
"""


@dataclass
class AgentPlan:
    kind: AgentKind
    stock_code: str | None = None
    screen_label: str | None = None
    as_of: date | None = None
    screen_type: str = "breakout"
    stoch_lookback: int | None = None
    confidence: float = 0.0
    understanding: str = ""
    clarify_question: str | None = None
    source: str = "rules"  # rules | llm
    raw: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_clarify(self) -> bool:
        return self.kind in {"clarify", "unknown"} or (
            self.confidence < 0.45 and self.kind not in {"help"}
        )


def _intent_understanding(intent: BotIntent) -> str:
    if intent.kind == "help":
        return "Kamu minta bantuan / daftar perintah bot."
    if intent.kind == "tech_menu":
        return "Kamu ingin melihat daftar filter teknikal yang bisa dipakai."
    if intent.kind == "ihsg":
        return "Kamu ingin outlook IHSG beserta konteks makro dan berita."
    if intent.kind == "screen":
        label = intent.screen_label or "hari ini"
        st = normalize_preset_key(getattr(intent, "screen_type", "breakout"))
        return f"Kamu ingin screening {preset_title(st)} untuk {label}."
    if intent.kind == "stock" and intent.stock_code:
        return f"Kamu ingin analisa teknikal saham {intent.stock_code}."
    if intent.kind == "fundamental":
        if intent.stock_code:
            return (
                f"Kamu ingin analisa fundamental {intent.stock_code} "
                "(PER, PBV, ROE, hutang, dll) plus saran ke depan."
            )
        return "Kamu ingin analisa fundamental, tapi kode sahamnya belum jelas."
    if intent.kind == "breakout":
        return "Kamu ingin cek saham yang baru break resistance."
    if intent.kind == "watch" and intent.stock_code:
        return f"Kamu ingin menambah {intent.stock_code} ke watchlist."
    if intent.kind == "unwatch" and intent.stock_code:
        return f"Kamu ingin menghapus {intent.stock_code} dari watchlist."
    if intent.kind == "watchlist":
        return "Kamu ingin melihat daftar watchlist."
    return "Saya belum yakin maksud permintaanmu."


def _confidence_for_intent(intent: BotIntent) -> float:
    if intent.kind == "unknown":
        return 0.15
    if intent.kind in {"help", "watchlist", "breakout", "ihsg", "tech_menu"}:
        return 0.92
    if intent.kind in {"watch", "unwatch"} and intent.stock_code:
        return 0.9
    if intent.kind == "fundamental" and intent.stock_code:
        return 0.9
    if intent.kind == "fundamental":
        return 0.4
    if intent.kind == "stock" and intent.stock_code:
        return 0.88
    if intent.kind == "screen":
        return 0.85
    return 0.5


def plan_from_rules(text: str) -> AgentPlan:
    intent = parse_user_intent(text)
    understanding = _intent_understanding(intent)
    conf = _confidence_for_intent(intent)
    if intent.kind == "unknown":
        return AgentPlan(
            kind="clarify",
            confidence=conf,
            understanding=understanding,
            clarify_question=(
                "Maksudnya apa ya? Chat boleh acak, contoh:\n"
                "• ihsg hari ini\n"
                "• analisa fundamental saham BBCA\n"
                "• cek saham bandarmology\n"
                "• stochastic yang lagi bagus\n"
                "• saham potensi hari ini\n"
                "• cek saham EMTK\n"
                "• /teknikal  (lihat semua filter)"
            ),
            source="rules",
            raw=text,
        )
    if intent.kind == "fundamental" and not intent.stock_code:
        return AgentPlan(
            kind="clarify",
            confidence=0.4,
            understanding=understanding,
            clarify_question=(
                "Saham mana yang mau dianalisa fundamental?\n"
                "Contoh: analisa fundamental saham BBCA"
            ),
            source="rules",
            raw=text,
        )
    return AgentPlan(
        kind=intent.kind,  # type: ignore[arg-type]
        stock_code=intent.stock_code,
        screen_label=intent.screen_label,
        as_of=intent.as_of,
        screen_type=normalize_preset_key(getattr(intent, "screen_type", "breakout")),
        stoch_lookback=getattr(intent, "stoch_lookback", None),
        confidence=conf,
        understanding=understanding,
        source="rules",
        raw=text,
    )


def _llm_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    raw = (content or "").strip()
    if not raw:
        return None
    # strip ```json fences if any
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def plan_from_llm(text: str) -> AgentPlan | None:
    """Optional OpenAI-compatible chat completion for freer NLU."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM planner gagal: %s", exc)
        return None

    data = _parse_llm_json(content)
    if not data:
        return None

    kind = str(data.get("kind") or "unknown").lower().strip()
    allowed = {
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
        "clarify",
        "unknown",
    }
    if kind not in allowed:
        kind = "clarify"

    stock_code = data.get("stock_code")
    if isinstance(stock_code, str) and stock_code.strip():
        stock_code = re.sub(r"[^A-Za-z]", "", stock_code).upper()[:5] or None
    else:
        stock_code = None

    as_of: date | None = None
    as_of_raw = data.get("as_of")
    if isinstance(as_of_raw, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", as_of_raw):
        try:
            as_of = date.fromisoformat(as_of_raw)
        except ValueError:
            as_of = None

    screen_label = data.get("screen_label")
    if not isinstance(screen_label, str) or not screen_label.strip():
        screen_label = as_of.isoformat() if as_of else None
    else:
        screen_label = screen_label.strip()

    screen_type = normalize_preset_key(str(data.get("screen_type") or "breakout"))

    stoch_lookback = data.get("stoch_lookback")
    try:
        stoch_lookback = int(stoch_lookback) if stoch_lookback is not None else None
    except (TypeError, ValueError):
        stoch_lookback = None
    if kind == "screen" and screen_type != "breakout" and stoch_lookback is None:
        if screen_label and "minggu" in str(screen_label):
            stoch_lookback = 5
        else:
            stoch_lookback = 1

    try:
        confidence = float(data.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    confidence = max(0.0, min(1.0, confidence))

    understanding = str(data.get("understanding") or "").strip()
    clarify_q = data.get("clarify_question")
    if clarify_q is not None:
        clarify_q = str(clarify_q).strip() or None

    if kind == "stock" and not stock_code:
        kind = "clarify"
        clarify_q = clarify_q or "Kode saham mana yang mau dianalisa? Contoh: EMTK / BBCA"
    if kind == "fundamental" and not stock_code:
        kind = "clarify"
        clarify_q = clarify_q or (
            "Saham mana yang mau dianalisa fundamental?\n"
            "Contoh: analisa fundamental saham BBCA"
        )
    if kind in {"watch", "unwatch"} and not stock_code:
        kind = "clarify"
        clarify_q = clarify_q or "Sebutkan kode sahamnya. Contoh: /watch EMTK"

    if not understanding:
        understanding = _intent_understanding(
            BotIntent(
                kind=kind if kind != "clarify" else "unknown",  # type: ignore[arg-type]
                stock_code=stock_code,
                screen_label=screen_label,
                as_of=as_of,
                screen_type=screen_type,
                stoch_lookback=stoch_lookback,
                raw=text,
            )
        )

    return AgentPlan(
        kind=kind,  # type: ignore[arg-type]
        stock_code=stock_code,
        screen_label=screen_label,
        as_of=as_of,
        screen_type=screen_type,
        stoch_lookback=stoch_lookback,
        confidence=confidence,
        understanding=understanding,
        clarify_question=clarify_q,
        source="llm",
        raw=text,
    )


def understand(text: str, *, prefer_llm: bool | None = None) -> AgentPlan:
    """Pahami request user → AgentPlan.

    Default: coba LLM jika ada API key, lalu merge/fallback ke rules.
    Rules selalu jadi safety net (terutama untuk perintah /slash yang jelas).
    """
    rules = plan_from_rules(text)
    use_llm = _llm_enabled() if prefer_llm is None else prefer_llm

    # Perintah slash jelas: jangan ganggu dengan LLM
    lower = (text or "").strip().lower()
    if lower.startswith("/") and rules.kind not in {"clarify", "unknown"} and rules.confidence >= 0.8:
        return rules

    if not use_llm:
        return rules

    llm = plan_from_llm(text)
    if llm is None:
        return rules

    # Jika LLM ragu tapi rules yakin → pakai rules
    if llm.needs_clarify and rules.confidence >= 0.75 and rules.kind not in {"clarify", "unknown"}:
        rules.source = "rules+llm_fallback"
        return rules

    # Jika rules yakin tinggi dan LLM beda jauh → prefer rules untuk screen/stock known patterns
    if rules.confidence >= 0.85 and llm.kind != rules.kind and llm.confidence < 0.8:
        return rules

    return llm


def format_understanding(plan: AgentPlan) -> str:
    """Pesan singkat sebelum tool dijalankan."""
    conf_pct = int(round(plan.confidence * 100))
    lines = [
        f"📌 Saya paham ({conf_pct}%): {plan.understanding}",
    ]
    if plan.kind == "ihsg":
        lines.append("→ Menjalankan agent: IHSG + makro + berita")
    elif plan.kind == "tech_menu":
        lines.append("→ Menampilkan menu filter teknikal")
    elif plan.kind == "screen":
        label = plan.screen_label or "hari ini"
        lines.append(
            f"→ Menjalankan agent: {preset_title(plan.screen_type)} ({label})"
        )
    elif plan.kind == "stock" and plan.stock_code:
        lines.append(f"→ Menjalankan agent: analisa teknikal {plan.stock_code}")
    elif plan.kind == "fundamental" and plan.stock_code:
        lines.append(f"→ Menjalankan agent: fundamental {plan.stock_code}")
    elif plan.kind == "breakout":
        lines.append("→ Menjalankan agent: cek breakout baru")
    elif plan.kind in {"watch", "unwatch", "watchlist"}:
        lines.append("→ Menjalankan agent: watchlist")
    return "\n".join(lines)
