"""Telegram bot interaktif — agent-style: pahami request dulu, lalu analisa.

Contoh natural:
  dapatkah cek potensi ihsg
  cek saham potensi kemarin
  please cek saham emtk
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from screener.agent import AgentPlan, format_understanding, understand
from screener.alerts import add_watch, load_watchlist, remove_watch, run_breakout_alert_job
from screener.analyze import analyze_stock, format_stock_report
from screener.fundamental import analyze_fundamental, format_fundamental_report
from screener.ihsg import analyze_ihsg, format_ihsg_report
from screener.notifier import build_message
from screener.presets import format_preset_menu, normalize_preset_key, preset_title
from screener.runner import run_screen

logger = logging.getLogger(__name__)

HELP_TEXT = """📈 Saham Gacor Bot (agent mode)

Chat bebas / boleh typo — bot pahami dulu, baru analisa.

Contoh:
• cek saham score tinggi teknikal
• analisa fundamental saham BBCA
• please cek roe pbv per BBRI
• dapatkah cek potensi ihsg
• cek saham bandarmology hari ini
• tolong cek saham teknikal stochastic yang lagi bagus
• please cek saham emtk
• /teknikal  ← daftar filter teknikal
• /watch EMTK

Opsional NLU AI: set OPENAI_API_KEY di .env
"""


def _api(token: str, method: str, **params: Any) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    timeout = 90 if method == "getUpdates" else 60
    resp = requests.post(url, json=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(str(data))
    return data["result"]


def send_text(token: str, chat_id: str | int, text: str, *, markdown: bool = False) -> None:
    chunks = []
    while text:
        chunks.append(text[:3500])
        text = text[3500:]
    for chunk in chunks:
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if markdown:
            payload["parse_mode"] = "Markdown"
        try:
            _api(token, "sendMessage", **payload)
        except Exception:
            payload.pop("parse_mode", None)
            _api(token, "sendMessage", **payload)


def _run_screen_and_reply(
    token: str,
    chat_id: str | int,
    *,
    label: str,
    as_of_arg: str | None,
    screen_type: str = "breakout",
    stoch_lookback: int | None = None,
) -> None:
    st = normalize_preset_key(screen_type)
    title = preset_title(st)
    send_text(
        token,
        chat_id,
        f"⏳ Screening {title} ({label})...\nTunggu 10–40 detik.",
    )
    signals = run_screen(
        as_of=as_of_arg,
        mode="eod",
        screen_type=st,
        stoch_oversold_lookback=stoch_lookback,
        notify=False,
        telegram=False,
        whatsapp=False,
    )
    msg = build_message(
        signals,
        mode="eod",
        markdown=False,
        as_of=as_of_arg,
        screen_type=st,
        screen_label=label,
    )
    if not signals:
        tips = (
            f"\n\nTidak ada yang lolos filter {title}.\n"
            "Coba:\n"
            "• minggu ini (lebih longgar)\n"
            "• stochastic yang lagi bagus\n"
            "• stoch cross ke atas\n"
            "• /teknikal"
        )
        msg += tips
    send_text(token, chat_id, msg)


def _execute_plan(token: str, chat_id: str | int, plan: AgentPlan) -> None:
    """Jalankan tool analisa sesuai plan agent."""
    if plan.kind == "help":
        send_text(token, chat_id, HELP_TEXT)
        return

    if plan.kind == "tech_menu":
        send_text(token, chat_id, format_preset_menu())
        return

    if plan.kind in {"clarify", "unknown"}:
        q = plan.clarify_question or (
            "Maaf, saya belum yakin maksudnya.\n"
            "Coba: ihsg hari ini | saham potensi hari ini | cek saham EMTK | /help"
        )
        send_text(token, chat_id, f"❓ {plan.understanding}\n\n{q}")
        return

    if plan.kind == "watchlist":
        syms = load_watchlist()
        if not syms:
            send_text(token, chat_id, "Watchlist kosong. Contoh: /watch EMTK")
        else:
            send_text(token, chat_id, "Watchlist:\n" + ", ".join(syms))
        return

    if plan.kind == "watch" and plan.stock_code:
        syms = add_watch(plan.stock_code)
        send_text(
            token,
            chat_id,
            f"✅ {plan.stock_code} ditambahkan ke watchlist.\n"
            f"Daftar: {', '.join(syms)}\n"
            "Kamu akan dapat notif jika baru break resistance.",
        )
        return

    if plan.kind == "unwatch" and plan.stock_code:
        syms = remove_watch(plan.stock_code)
        send_text(
            token,
            chat_id,
            f"🗑️ {plan.stock_code} dihapus dari watchlist.\n"
            f"Sisa: {', '.join(syms) if syms else '(kosong)'}",
        )
        return

    if plan.kind == "breakout":
        send_text(token, chat_id, "⏳ Cek breakout resistance baru...")
        try:
            pending = run_breakout_alert_job(
                mode="manual",
                telegram=True,
                only_watchlist=False,
            )
            if not pending:
                send_text(token, chat_id, "Tidak ada breakout BARU saat ini.")
        except Exception as exc:  # noqa: BLE001
            send_text(token, chat_id, f"❌ Gagal cek breakout: {exc}")
        return

    if plan.kind == "ihsg":
        send_text(
            token,
            chat_id,
            "⏳ Analisa IHSG + makro + headline berita...\nTunggu 10–30 detik.",
        )
        try:
            outlook = analyze_ihsg()
            if outlook is None:
                send_text(token, chat_id, "❌ Data IHSG tidak tersedia saat ini.")
            else:
                send_text(token, chat_id, format_ihsg_report(outlook))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gagal analisa IHSG")
            send_text(token, chat_id, f"❌ Gagal analisa IHSG: {exc}")
        return

    if plan.kind == "stock" and plan.stock_code:
        code = plan.stock_code
        send_text(token, chat_id, f"⏳ Analisa teknikal {code}...\nTunggu sebentar.")
        try:
            report = analyze_stock(code)
            send_text(token, chat_id, format_stock_report(report))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gagal analisa saham")
            send_text(
                token,
                chat_id,
                f"❌ Gagal analisa {code}: {exc}\n"
                "Pastikan kode saham BEI benar (contoh EMTK, BBCA).",
            )
        return

    if plan.kind == "fundamental" and plan.stock_code:
        code = plan.stock_code
        send_text(
            token,
            chat_id,
            f"⏳ Analisa fundamental {code} + bandingkan peers large-cap sektor...\n"
            "Tunggu 15–40 detik.",
        )
        try:
            report = analyze_fundamental(code)
            send_text(token, chat_id, format_fundamental_report(report))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gagal analisa fundamental")
            send_text(
                token,
                chat_id,
                f"❌ Gagal fundamental {code}: {exc}\n"
                "Pastikan kode saham BEI benar (contoh BBCA, TLKM).",
            )
        return

    if plan.kind == "screen":
        label = plan.screen_label or "terbaru"
        as_of_arg = plan.as_of.isoformat() if plan.as_of is not None else None
        try:
            _run_screen_and_reply(
                token,
                chat_id,
                label=label,
                as_of_arg=as_of_arg,
                screen_type=plan.screen_type or "breakout",
                stoch_lookback=plan.stoch_lookback,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gagal screening")
            send_text(token, chat_id, f"❌ Gagal analisa: {exc}")
        return

    send_text(
        token,
        chat_id,
        "Maaf, saya belum yakin maksudnya.\n\n"
        "Coba contoh ini:\n"
        "• dapatkah cek potensi ihsg\n"
        "• saham hari ini\n"
        "• please cek saham emtk\n"
        "• /help",
    )


def handle_command(token: str, chat_id: str | int, text: str) -> None:
    """Agent flow: understand → confirm → execute tool."""
    plan = understand(text)
    logger.info(
        "Agent plan: kind=%s conf=%.2f src=%s raw=%r | %s",
        plan.kind,
        plan.confidence,
        plan.source,
        plan.raw,
        plan.understanding,
    )

    # Selalu tampilkan pemahaman dulu (kecuali help singkat)
    if plan.kind != "help":
        send_text(token, chat_id, format_understanding(plan))

    _execute_plan(token, chat_id, plan)


def poll_forever(token: str, allowed_chat_id: str | None = None) -> None:
    try:
        _api(token, "deleteWebhook", drop_pending_updates=False)
    except Exception:  # noqa: BLE001
        pass

    offset = None
    llm_on = bool(os.getenv("OPENAI_API_KEY", "").strip())
    print("Bot online (agent mode). Contoh:")
    print("  dapatkah cek potensi ihsg")
    print("  cek saham potensi kemarin")
    print("  please cek saham emtk")
    print(f"  NLU LLM: {'ON' if llm_on else 'OFF (rules only; set OPENAI_API_KEY untuk AI)'}")
    print("Menunggu pesan... (Ctrl+C untuk stop)")

    while True:
        try:
            params: dict[str, Any] = {"timeout": 25}
            if offset is not None:
                params["offset"] = offset
            updates = _api(token, "getUpdates", **params)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = msg.get("text") or ""
                if chat_id is None or not text:
                    continue
                if allowed_chat_id and str(chat_id) != str(allowed_chat_id):
                    send_text(
                        token,
                        chat_id,
                        "Bot ini pribadi. Chat_id kamu belum diizinkan.",
                    )
                    continue
                print(f"Pesan dari {chat_id}: {text}")
                handle_command(token, chat_id, text)
        except KeyboardInterrupt:
            print("Bot dihentikan.")
            return
        except Exception as exc:  # noqa: BLE001
            logger.error("Poll error: %s", exc)
            time.sleep(3)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN belum diisi di .env")
        return 1
    allowed = os.getenv("TELEGRAM_CHAT_ID", "").strip() or None
    poll_forever(token, allowed_chat_id=allowed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
