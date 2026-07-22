"""CLI entrypoint untuk menjalankan stock screener."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from screener.data import fetch_history
from screener.notifier import notify_all
from screener.signals import screen_all
from screener.universe import DEFAULT_IDX_SYMBOLS


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Screening saham IDX: volume spike + break resistance + potensi naik. "
            "Hasil dikirim ke console / JSON / Telegram."
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
    load_dotenv()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"Config tidak ditemukan: {cfg_path}", file=sys.stderr)
        return 1

    cfg = load_config(cfg_path)
    if args.min_score is not None:
        cfg["min_score"] = args.min_score
    if args.volume_spike is not None:
        cfg["volume_spike_min"] = args.volume_spike
    if args.no_telegram:
        cfg.setdefault("notify", {})["telegram"] = False

    symbols = args.symbols or cfg.get("symbols") or DEFAULT_IDX_SYMBOLS
    symbols = [str(s).strip().upper() for s in symbols if str(s).strip()]
    market = str(cfg.get("market", "IDX"))

    print(f"Memindai {len(symbols)} saham ({market})...")
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
