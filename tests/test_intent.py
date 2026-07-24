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


def test_stoch_oversold_phrases():
    for phrase, label, lookback in [
        ("cek saham stochastic oversold hari ini", "hari ini", 1),
        ("cek saham scoshatic oversold hari ni", "hari ini", 1),
        ("cek saham schocastic oversold minggu ini", "minggu ini", 5),
        ("saham stoch oversold pekan ini", "minggu ini", 5),
        ("cek saham oversold hari ini", "hari ini", 1),
    ]:
        intent = parse_user_intent(phrase)
        assert intent.kind == "screen", phrase
        assert intent.screen_type == "stoch_oversold", phrase
        assert intent.screen_label == label, (phrase, intent.screen_label)
        assert intent.stoch_lookback == lookback, (phrase, intent.stoch_lookback)


def test_tech_presets_messy():
    cases = [
        ("cek dong saham bandarmologi hari ni", "bandar"),
        ("mau liat stoch cross ke atas", "stoch_cross"),
        ("saham akumulasi minggu ini", "accumulation"),
        ("volume tinggi hari ini", "volume"),
        ("rsi oversold dong", "rsi_oversold"),
        ("macd putar naik", "macd_turn"),
        ("cek saham potensi naik kemarin", "breakout"),
    ]
    for phrase, expected in cases:
        intent = parse_user_intent(phrase)
        assert intent.kind == "screen", phrase
        assert intent.screen_type == expected, (phrase, intent.screen_type)


def test_tech_menu():
    assert parse_user_intent("/teknikal").kind == "tech_menu"
    assert parse_user_intent("filter teknikal apa aja").kind == "tech_menu"


if __name__ == "__main__":
    test_screen_phrases()
    test_stock_phrases()
    test_kemarin_label()
    test_ihsg_phrases()
    test_stoch_oversold_phrases()
    test_tech_presets_messy()
    test_tech_menu()
    print("OK: intent natural tests passed")
