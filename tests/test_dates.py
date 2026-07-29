"""Tests parser tanggal natural untuk bot chat."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from screener.dates import extract_date_query, parse_natural_date

JAKARTA = ZoneInfo("Asia/Jakarta")
NOW = datetime(2026, 7, 23, 10, 0, tzinfo=JAKARTA)


def test_iso_and_slash():
    assert parse_natural_date("2026-07-20", now=NOW) == date(2026, 7, 20)
    assert parse_natural_date("20/07/2026", now=NOW) == date(2026, 7, 20)
    assert parse_natural_date("20/7", now=NOW) == date(2026, 7, 20)


def test_month_names():
    assert parse_natural_date("20 july", now=NOW) == date(2026, 7, 20)
    assert parse_natural_date("20 juli", now=NOW) == date(2026, 7, 20)
    assert parse_natural_date("20 july 2026", now=NOW) == date(2026, 7, 20)
    assert parse_natural_date("juli 20", now=NOW) == date(2026, 7, 20)


def test_natural_phrases():
    assert parse_natural_date("tanggal 20 july ini", now=NOW) == date(2026, 7, 20)
    assert parse_natural_date("kemarin", now=NOW) == date(2026, 7, 22)
    label, d = extract_date_query("cek tanggal 20 july")
    assert d == date(2026, 7, 20)
    label2, d2 = extract_date_query("/cek 20/07/2026")
    assert d2 == date(2026, 7, 20)


if __name__ == "__main__":
    test_iso_and_slash()
    test_month_names()
    test_natural_phrases()
    print("OK: date tests passed")
