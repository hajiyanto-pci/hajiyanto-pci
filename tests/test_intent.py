"""Tests intent natural language untuk bot."""

from __future__ import annotations

from screener.intent import extract_stock_code, parse_user_intent


def test_screen_phrases():
    for phrase in [
        "cek saham potensi kemarin",
        "Ek saham potensi kemarin",
        "saham potensi naik kemarin",
        "saham hari ini",
        "cek saham hari ini",
        "cek tanggal 20 july",
    ]:
        intent = parse_user_intent(phrase)
        assert intent.kind == "screen", phrase
        assert extract_stock_code(phrase) is None or intent.kind == "screen"


def test_stock_phrases():
    assert parse_user_intent("please cek saham emtk").kind == "stock"
    assert parse_user_intent("please cek saham emtk").stock_code == "EMTK"
    assert parse_user_intent("cek saham BBCA").stock_code == "BBCA"
    assert parse_user_intent("/saham EMTK").stock_code == "EMTK"


def test_kemarin_label():
    intent = parse_user_intent("cek saham potensi kemarin")
    assert intent.kind == "screen"
    assert intent.screen_label == "kemarin"
    assert intent.as_of is not None


def test_ihsg_phrases():
    for phrase in [
        "ihsg hari ini",
        "potensi ihsg",
        "prediksi ihsg ke depan",
        "/ihsg",
        "analisa ihsg",
        "makro hari ini",
        "outlook ihsg",
    ]:
        intent = parse_user_intent(phrase)
        assert intent.kind == "ihsg", phrase


if __name__ == "__main__":
    test_screen_phrases()
    test_stock_phrases()
    test_kemarin_label()
    test_ihsg_phrases()
    print("OK: intent natural tests passed")
