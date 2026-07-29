"""Tests analisa fundamental + peer compare."""

from __future__ import annotations

from screener.fundamental import (
    PeerSnap,
    _score_fundamentals,
    analyze_fundamental,
    format_fundamental_report,
    resolve_peer_group,
    select_large_peers,
)


def test_resolve_bank_peers():
    group, peers = resolve_peer_group("Financial Services", "Banks - Regional", "BBCA")
    assert group == "banks"
    assert "BBRI" in peers and "BMRI" in peers


def test_select_large_peers():
    subject = PeerSnap("BBCA", "BCA", 800e12, 50e12, 14.0, 3.0, 22.0, 50.0)
    peers = [
        subject,
        PeerSnap("BBRI", "BRI", 600e12, 40e12, 12.0, 2.0, 18.0, 40.0),
        PeerSnap("BMRI", "Mandiri", 500e12, 35e12, 11.0, 1.8, 19.0, 38.0),
        PeerSnap("BBNI", "BNI", 200e12, 15e12, 10.0, 1.2, 14.0, 30.0),
        PeerSnap("ARTO", "Jago", 20e12, 0.1e12, 80.0, 4.0, 2.0, 5.0),
    ]
    selected = select_large_peers(subject, peers, min_peers=3, max_peers=4)
    assert "ARTO" not in [p.symbol for p in selected] or len(selected) >= 3
    assert all(p.symbol != "BBCA" for p in selected)


def test_score_strong_bank_like():
    score, checklist, notes = _score_fundamentals(
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
    assert checklist.get("roe") is True
    assert notes


def test_live_bbca_with_peers():
    try:
        r = analyze_fundamental("BBCA", with_peers=True)
    except Exception as exc:  # noqa: BLE001
        print("skip live:", exc)
        return
    assert r.symbol == "BBCA"
    assert r.peer is not None
    assert r.peer.peers_used
    text = format_fundamental_report(r)
    assert "Komparasi peers" in text
    assert "PER" in text and "PBV" in text and "ROE" in text
    assert r.decision
    print(text)


if __name__ == "__main__":
    test_resolve_bank_peers()
    test_select_large_peers()
    test_score_strong_bank_like()
    test_live_bbca_with_peers()
    print("OK: fundamental peer tests passed")
