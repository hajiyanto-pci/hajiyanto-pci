"""Tests analisa fundamental."""

from __future__ import annotations

from screener.fundamental import (
    _score_fundamentals,
    analyze_fundamental,
    format_fundamental_report,
)


def test_score_strong_bank_like():
    score, checklist, notes, decision, outlook = _score_fundamentals(
        per=14.0,
        pbv=2.5,
        roe=22.0,
        debt_to_equity=None,
        current_ratio=None,
        profit_margin=40.0,
        revenue_growth=5.0,
        earnings_growth=8.0,
        dividend_yield=3.0,
        sector="Financial Services",
    )
    assert score >= 55
    assert "FUNDAMENTAL" in decision
    assert outlook


def test_score_weak():
    score, _c, _n, decision, _o = _score_fundamentals(
        per=55.0,
        pbv=8.0,
        roe=2.0,
        debt_to_equity=300.0,
        current_ratio=0.6,
        profit_margin=1.0,
        revenue_growth=-10.0,
        earnings_growth=-20.0,
        dividend_yield=0.0,
        sector="Consumer",
    )
    assert score < 45
    assert "LEMAH" in decision or "CAMPURAN" in decision


def test_live_bbca_optional():
    try:
        r = analyze_fundamental("BBCA")
    except Exception as exc:  # noqa: BLE001
        print("skip live:", exc)
        return
    assert r.symbol == "BBCA"
    text = format_fundamental_report(r)
    assert "PER" in text and "PBV" in text and "ROE" in text
    assert r.decision
    print(text[:500])


if __name__ == "__main__":
    test_score_strong_bank_like()
    test_score_weak()
    test_live_bbca_optional()
    print("OK: fundamental tests passed")
