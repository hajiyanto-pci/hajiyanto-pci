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
    "clarify",
    "unknown",
]

TOOLS_CATALOG = """
Tools yang tersedia:
- help: tampilkan bantuan
- ihsg: outlook IHSG + makro + berita
- screen: screening saham potensi naik (bisa as_of: kemarin / hari ini / tanggal)
- stock: analisa 1 kode saham BEI (stock_code wajib, contoh EMTK)
- breakout: cek saham yang baru break resistance
- watch: tambah ke watchlist (stock_code)
- unwatch: hapus dari watchlist (stock_code)
- watchlist: lihat watchlist
- clarify: minta klarifikasi jika ambigu
- unknown: tidak bisa diproses
"""

SYSTEM_PROMPT = f"""Kamu adalah planner untuk bot analisa saham Indonesia (IDX).
Tugasmu HANYA memahami permintaan user dan memilih 1 tool + parameter.
Jangan analisa harga sendiri. Jangan buat saran investasi.
Balas HANYA JSON valid tanpa markdown:

{{
  "kind": "<tool>",
  "stock_code": null atau "KODE",
  "screen_label": null atau "kemarin"|"hari ini"|"YYYY-MM-DD",
  "as_of": null atau "YYYY-MM-DD",
  "confidence": 0.0-1.0,
  "understanding": "satu kalimat bahasa Indonesia: apa yang user minta",
  "clarify_question": null atau pertanyaan klarifikasi
}}

{TOOLS_CATALOG}

Aturan:
- "potensi ihsg", "makro", "outlook indeks" → ihsg
- "saham potensi", "kandidat naik", "screening" tanpa kode → screen
- "cek EMTK", "analisa BBCA" → stock
- Jika ambigu antara screen vs stock vs ihsg → clarify
- Kode saham BEI biasanya 4 huruf (kadang 3–5)
"""


@dataclass
class AgentPlan:
    kind: AgentKind
    stock_code: str | None = None
    screen_label: str | None = None
    as_of: date | None = None
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
    if intent.kind == "ihsg":
        return "Kamu ingin outlook IHSG beserta konteks makro dan berita."
    if intent.kind == "screen":
        label = intent.screen_label or "hari ini"
        return f"Kamu ingin screening saham potensi naik untuk {label}."
    if intent.kind == "stock" and intent.stock_code:
        return f"Kamu ingin analisa teknikal saham {intent.stock_code}."
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
    if intent.kind in {"help", "watchlist", "breakout", "ihsg"}:
        return 0.92
    if intent.kind in {"watch", "unwatch"} and intent.stock_code:
        return 0.9
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
                "Maksudnya apa ya?\n"
                "• Outlook IHSG/makro → ketik: ihsg hari ini\n"
                "• Screening potensi naik → ketik: saham potensi hari ini\n"
                "• Analisa 1 saham → ketik: cek saham EMTK\n"
                "• Breakout baru → ketik: /breakout"
            ),
            source="rules",
            raw=text,
        )
    return AgentPlan(
        kind=intent.kind,  # type: ignore[arg-type]
        stock_code=intent.stock_code,
        screen_label=intent.screen_label,
        as_of=intent.as_of,
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
                raw=text,
            )
        )

    return AgentPlan(
        kind=kind,  # type: ignore[arg-type]
        stock_code=stock_code,
        screen_label=screen_label,
        as_of=as_of,
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
    elif plan.kind == "screen":
        label = plan.screen_label or "hari ini"
        lines.append(f"→ Menjalankan agent: screening potensi ({label})")
    elif plan.kind == "stock" and plan.stock_code:
        lines.append(f"→ Menjalankan agent: analisa {plan.stock_code}")
    elif plan.kind == "breakout":
        lines.append("→ Menjalankan agent: cek breakout baru")
    elif plan.kind in {"watch", "unwatch", "watchlist"}:
        lines.append("→ Menjalankan agent: watchlist")
    return "\n".join(lines)
