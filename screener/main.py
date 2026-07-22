"""CLI entrypoint untuk menjalankan stock screener."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from screener.data import fetch_history
from screener.notifier import (
    discover_telegram_chat_id,
    notify_all,
    print_setup_guide,
    send_test_notifications,
    write_telegram_env,
)
from screener.schedule import MODES, explain_schedule, recommend_primary_mode
from screener.signals import parse_as_of, screen_all
from screener.universe import DEFAULT_IDX_SYMBOLS


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Screening saham IDX: volume + di atas MA + akumulasi + break resistance. "
            "Hasil dikirim ke console / JSON / Telegram / WhatsApp."
        )
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Path file konfigurasi YAML (default: config.yaml)",
    )
    parser.add_argument(
        "-s",
        "--symbols",
        nargs="+",
        help="Override daftar saham, contoh: BBCA BBRI TLKM",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        help="Mode notifikasi: morning | midday | eod (default dari config / eod)",
    )
    parser.add_argument(
        "--as-of",
        help=(
            "Analisa per tanggal: yesterday/kemarin atau YYYY-MM-DD. "
            "Contoh: --as-of kemarin"
        ),
    )
    parser.add_argument(
        "--explain-schedule",
        action="store_true",
        help="Tampilkan rekomendasi jadwal pagi/siang/sore lalu keluar",
    )
    parser.add_argument(
        "--setup-notify",
        action="store_true",
        help="Tampilkan panduan setup Telegram & WhatsApp",
    )
    parser.add_argument(
        "--test-notify",
        action="store_true",
        help="Kirim pesan uji ke Telegram/WhatsApp yang sudah dikonfigurasi",
    )
    parser.add_argument(
        "--get-chat-id",
        action="store_true",
        help="Ambil TELEGRAM_CHAT_ID: buka bot, tekan Start, lalu jalankan perintah ini",
    )
    parser.add_argument(
        "--chat-id",
        help="Set TELEGRAM_CHAT_ID manual (dari @userinfobot) lalu simpan ke .env jika --save-env",
    )
    parser.add_argument(
        "--token",
        help="Token bot Telegram (opsional; default dari .env TELEGRAM_BOT_TOKEN)",
    )
    parser.add_argument(
        "--save-env",
        action="store_true",
        help="Simpan token/chat_id ke file .env",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        help="Override skor minimum",
    )
    parser.add_argument(
        "--volume-spike",
        type=float,
        help="Override kelipatan volume minimum, contoh: 1.5",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Nonaktifkan kirim Telegram untuk run ini",
    )
    parser.add_argument(
        "--no-whatsapp",
        action="store_true",
        help="Nonaktifkan kirim WhatsApp untuk run ini",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log lebih detail",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.explain_schedule:
        print(explain_schedule())
        print(f"\nRekomendasi utama: --mode {recommend_primary_mode()}")
        return 0

    if args.setup_notify:
        print_setup_guide()
        return 0

    load_dotenv()

    if args.chat_id:
        token = (args.token or "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = str(args.chat_id).strip()
        if not token:
            print("Token belum ada. Pakai --token atau isi TELEGRAM_BOT_TOKEN di .env")
            return 1
        print(f"Menggunakan chat_id: {chat_id}")
        if args.save_env or True:
            write_telegram_env(token, chat_id)
        # auto uji setelah set
        os.environ["TELEGRAM_BOT_TOKEN"] = token
        os.environ["TELEGRAM_CHAT_ID"] = chat_id
        return send_test_notifications()

    if args.get_chat_id:
        token = (args.token or "").strip() or None
        chat_id = discover_telegram_chat_id(token)
        if not chat_id:
            return 1
        if args.save_env:
            used_token = (args.token or "").strip() or os.getenv(
                "TELEGRAM_BOT_TOKEN", ""
            )
            write_telegram_env(used_token.strip(), chat_id)
            os.environ["TELEGRAM_BOT_TOKEN"] = used_token.strip()
            os.environ["TELEGRAM_CHAT_ID"] = chat_id
            return send_test_notifications()
        return 0

    if args.test_notify:
        return send_test_notifications()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"Config tidak ditemukan: {cfg_path}", file=sys.stderr)
        return 1

    cfg = load_config(cfg_path)
    mode = (args.mode or cfg.get("mode") or recommend_primary_mode()).lower()
    if mode not in MODES:
        print(f"Mode tidak valid: {mode}. Pilih: {', '.join(MODES)}", file=sys.stderr)
        return 1
    cfg["mode"] = mode

    if args.min_score is not None:
        cfg["min_score"] = args.min_score
    if args.volume_spike is not None:
        cfg["volume_spike_min"] = args.volume_spike
    if args.no_telegram:
        cfg.setdefault("notify", {})["telegram"] = False
    if args.no_whatsapp:
        cfg.setdefault("notify", {})["whatsapp"] = False

    as_of = parse_as_of(args.as_of)
    if as_of is not None:
        cfg["as_of"] = as_of
        # Analisa historis selalu pakai bar harian lengkap (bukan midday projection)
        cfg["mode"] = "eod"
        mode = "eod"

    symbols = args.symbols or cfg.get("symbols") or DEFAULT_IDX_SYMBOLS
    symbols = [str(s).strip().upper() for s in symbols if str(s).strip()]
    market = str(cfg.get("market", "IDX"))

    as_of_label = as_of.isoformat() if as_of else "terbaru"
    print(
        f"Mode: {mode} | As-of: {as_of_label} | "
        f"Memindai {len(symbols)} saham ({market})..."
    )
    histories = fetch_history(
        symbols,
        history_days=int(cfg.get("history_days", 90)),
        market=market,
    )
    print(f"Data berhasil diambil: {len(histories)} saham")

    signals = screen_all(histories, cfg)
    notify_all(signals, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
