"""Tests intent deteksi kode saham dari chat natural."""

from __future__ import annotations

from screener.intent import extract_stock_code


def test_stock_phrases():
    assert extract_stock_code("please cek saham emtk") == "EMTK"
    assert extract_stock_code("cek saham BBCA") == "BBCA"
    assert extract_stock_code("cek emtk") == "EMTK"
    assert extract_stock_code("/saham EMTK") == "EMTK"
    assert extract_stock_code("analisa goto") == "GOTO"


def test_date_not_stock():
    assert extract_stock_code("cek tanggal 20 july") is None
    assert extract_stock_code("/kemarin") is None
    assert extract_stock_code("cek 20/07/2026") is None


if __name__ == "__main__":
    test_stock_phrases()
    test_date_not_stock()
    print("OK: intent tests passed")
