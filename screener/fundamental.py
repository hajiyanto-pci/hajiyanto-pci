"""Analisa fundamental saham IDX via Yahoo Finance + saran sederhana."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yfinance as yf

from screener.universe import to_yahoo_symbol


@dataclass
class FundamentalReport:
    symbol: str
    name: str
    sector: str
    industry: str
    price: float | None
    per: float | None  # trailing P/E
    forward_per: float | None
    pbv: float | None
    roe: float | None  # percent
    debt_to_equity: float | None
    current_ratio: float | None
    profit_margin: float | None  # percent
    revenue_growth: float | None  # percent
    earnings_growth: float | None  # percent
    dividend_yield: float | None  # percent
    market_cap: float | None
    book_value: float | None
    checklist: dict[str, bool] = field(default_factory=dict)
    score: float = 0.0
    decision: str = ""
    outlook: str = ""
    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        x = float(v)
        if x != x:  # NaN
            return None
        return x
    except (TypeError, ValueError):
        return None


def _pct_from_ratio(v: float | None) -> float | None:
    """Yahoo often returns 0.22 for 22% ROE/margins."""
    if v is None:
        return None
    # Jika sudah seperti persen (>1.5 untuk ROE jarang >150%), anggap sudah persen
    if abs(v) <= 1.5:
        return v * 100.0
    return v


def _fmt(v: float | None, *, digits: int = 2, suffix: str = "") -> str:
    if v is None:
        return "n/a"
    return f"{v:.{digits}f}{suffix}"


def _fmt_rp(v: float | None) -> str:
    if v is None:
        return "n/a"
    if v >= 1e12:
        return f"Rp {v/1e12:.1f} T"
    if v >= 1e9:
        return f"Rp {v/1e9:.1f} M"
    return f"Rp {v:,.0f}"


def _score_fundamentals(
    *,
    per: float | None,
    pbv: float | None,
    roe: float | None,
    debt_to_equity: float | None,
    current_ratio: float | None,
    profit_margin: float | None,
    revenue_growth: float | None,
    earnings_growth: float | None,
    dividend_yield: float | None,
    sector: str,
) -> tuple[float, dict[str, bool], list[str], str, str]:
    """Heuristik sederhana untuk IDX (bukan saran investasi resmi)."""
    notes: list[str] = []
    checklist: dict[str, bool] = {}
    score = 0.0
    is_bank = "bank" in (sector or "").lower() or "financial" in (sector or "").lower()

    # PER
    if per is None or per <= 0:
        checklist["per"] = False
        notes.append("PER tidak tersedia / negatif (rugi?)")
    elif 8 <= per <= 20:
        checklist["per"] = True
        score += 18
        notes.append(f"PER {per:.1f}x di zona wajar")
    elif 5 <= per < 8:
        checklist["per"] = True
        score += 14
        notes.append(f"PER {per:.1f}x relatif murah")
    elif 20 < per <= 30:
        checklist["per"] = False
        score += 8
        notes.append(f"PER {per:.1f}x agak mahal")
    else:
        checklist["per"] = False
        score += 2
        notes.append(f"PER {per:.1f}x terlalu ekstrem / mahal")

    # PBV
    pbv_ok_max = 3.5 if is_bank else 4.0
    if pbv is None or pbv <= 0:
        checklist["pbv"] = False
        notes.append("PBV tidak tersedia")
    elif pbv < 1:
        checklist["pbv"] = True
        score += 16
        notes.append(f"PBV {pbv:.2f}x di bawah nilai buku (potensi undervalued)")
    elif pbv <= pbv_ok_max:
        checklist["pbv"] = True
        score += 14
        notes.append(f"PBV {pbv:.2f}x masih wajar")
    elif pbv <= pbv_ok_max + 2:
        checklist["pbv"] = False
        score += 6
        notes.append(f"PBV {pbv:.2f}x premium")
    else:
        checklist["pbv"] = False
        score += 1
        notes.append(f"PBV {pbv:.2f}x mahal")

    # ROE
    if roe is None:
        checklist["roe"] = False
        notes.append("ROE tidak tersedia")
    elif roe >= 15:
        checklist["roe"] = True
        score += 20
        notes.append(f"ROE {roe:.1f}% kuat (efisiensi modal bagus)")
    elif roe >= 10:
        checklist["roe"] = True
        score += 14
        notes.append(f"ROE {roe:.1f}% cukup baik")
    elif roe >= 5:
        checklist["roe"] = False
        score += 6
        notes.append(f"ROE {roe:.1f}% tipis")
    else:
        checklist["roe"] = False
        score += 0
        notes.append(f"ROE {roe:.1f}% lemah")

    # Hutang (D/E)
    if debt_to_equity is None:
        checklist["debt"] = True if is_bank else False
        if is_bank:
            notes.append("D/E bank sering tidak relevan di Yahoo — cek CAR/NPL terpisah")
            score += 6
        else:
            notes.append("Rasio hutang (D/E) tidak tersedia")
    else:
        # Yahoo debtToEquity sering sudah *100 (mis. 45.2 = 45%)
        de = debt_to_equity / 100.0 if debt_to_equity > 5 else debt_to_equity
        if de <= 0.8:
            checklist["debt"] = True
            score += 14
            notes.append(f"D/E {de:.2f}x rendah — struktur hutang sehat")
        elif de <= 1.5:
            checklist["debt"] = True
            score += 10
            notes.append(f"D/E {de:.2f}x masih terkendali")
        elif de <= 2.5:
            checklist["debt"] = False
            score += 4
            notes.append(f"D/E {de:.2f}x agak tinggi — pantau beban bunga")
        else:
            checklist["debt"] = False
            score += 0
            notes.append(f"D/E {de:.2f}x tinggi — risiko leverage")

    # Current ratio (likuiditas)
    if current_ratio is None:
        checklist["liquidity"] = is_bank
        if not is_bank:
            notes.append("Current ratio tidak tersedia")
        else:
            score += 4
    elif current_ratio >= 1.2:
        checklist["liquidity"] = True
        score += 8
        notes.append(f"Current ratio {current_ratio:.2f} cukup likuid")
    elif current_ratio >= 1.0:
        checklist["liquidity"] = True
        score += 5
        notes.append(f"Current ratio {current_ratio:.2f} pas-pasan")
    else:
        checklist["liquidity"] = False
        score += 0
        notes.append(f"Current ratio {current_ratio:.2f} rendah")

    # Margin
    if profit_margin is None:
        checklist["margin"] = False
    elif profit_margin >= 15:
        checklist["margin"] = True
        score += 10
        notes.append(f"Profit margin {profit_margin:.1f}% kuat")
    elif profit_margin >= 5:
        checklist["margin"] = True
        score += 6
        notes.append(f"Profit margin {profit_margin:.1f}% ok")
    else:
        checklist["margin"] = False
        score += 1
        notes.append(f"Profit margin {profit_margin:.1f}% tipis")

    # Growth
    growth_pts = 0.0
    if revenue_growth is not None:
        if revenue_growth >= 10:
            growth_pts += 5
            notes.append(f"Revenue growth {revenue_growth:.1f}% positif")
        elif revenue_growth >= 0:
            growth_pts += 2
            notes.append(f"Revenue growth {revenue_growth:.1f}% datar")
        else:
            notes.append(f"Revenue growth {revenue_growth:.1f}% negatif")
    if earnings_growth is not None:
        if earnings_growth >= 10:
            growth_pts += 5
            notes.append(f"Earnings growth {earnings_growth:.1f}% kuat")
        elif earnings_growth >= 0:
            growth_pts += 2
            notes.append(f"Earnings growth {earnings_growth:.1f}% tipis")
        else:
            notes.append(f"Earnings growth {earnings_growth:.1f}% negatif")
    checklist["growth"] = growth_pts >= 5
    score += growth_pts

    # Dividend (bonus kecil)
    if dividend_yield is not None and dividend_yield >= 2:
        score += 4
        notes.append(f"Dividend yield ~{dividend_yield:.1f}%")

    score = max(0.0, min(100.0, score))

    if score >= 70:
        decision = "FUNDAMENTAL KUAT"
        outlook = (
            "Secara fundamental terlihat menarik untuk jangka menengah/panjang, "
            "asalkan harga tidak terlalu mahal dan tren industri mendukung. "
            "Tetap konfirmasi dengan teknikal & sentimen makro."
        )
    elif score >= 55:
        decision = "FUNDAMENTAL CUKUP"
        outlook = (
            "Fundamental cukup layak dipantau. Cocok untuk akumulasi bertahap "
            "bila ada koreksi harga, bukan FOMO di puncak valuasi."
        )
    elif score >= 40:
        decision = "FUNDAMENTAL CAMPURAN"
        outlook = (
            "Ada sisi positif dan negatif. Tunggu perbaikan margin/growth "
            "atau valuasi lebih murah sebelum menambah posisi."
        )
    else:
        decision = "FUNDAMENTAL LEMAH"
        outlook = (
            "Fundamental saat ini kurang mendukung. Hindari averaging-down "
            "tanpa katalis jelas; prioritaskan saham dengan ROE & neraca lebih sehat."
        )

    return score, checklist, notes, decision, outlook


def analyze_fundamental(code: str) -> FundamentalReport:
    symbol = code.strip().upper().replace(".JK", "")
    if not symbol:
        raise ValueError("Kode saham kosong")

    yahoo = to_yahoo_symbol(symbol, "IDX")
    ticker = yf.Ticker(yahoo)
    info = {}
    try:
        info = ticker.info or {}
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Gagal ambil data fundamental {symbol}: {exc}") from exc

    if not info or (not info.get("symbol") and not info.get("shortName") and not info.get("longName")):
        # fallback: coba fast_info / history untuk pastikan ticker ada
        try:
            hist = ticker.history(period="5d")
            if hist is None or hist.empty:
                raise ValueError(f"Data fundamental {symbol} tidak ditemukan")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Data fundamental {symbol} tidak ditemukan: {exc}") from exc

    per = _num(info.get("trailingPE"))
    forward_per = _num(info.get("forwardPE"))
    pbv = _num(info.get("priceToBook"))
    roe = _pct_from_ratio(_num(info.get("returnOnEquity")))
    debt = _num(info.get("debtToEquity"))
    current_ratio = _num(info.get("currentRatio"))
    profit_margin = _pct_from_ratio(_num(info.get("profitMargins")))
    revenue_growth = _pct_from_ratio(_num(info.get("revenueGrowth")))
    earnings_growth = _pct_from_ratio(_num(info.get("earningsGrowth")))
    # dividendYield di Yahoo kadang sudah persen (5.65), kadang rasio (0.056)
    dy_raw = _num(info.get("dividendYield"))
    if dy_raw is not None and dy_raw <= 0.3:
        dividend_yield = dy_raw * 100.0
    else:
        dividend_yield = dy_raw

    price = _num(info.get("currentPrice")) or _num(info.get("previousClose"))
    market_cap = _num(info.get("marketCap"))
    book_value = _num(info.get("bookValue"))
    sector = str(info.get("sector") or "")
    industry = str(info.get("industry") or "")
    name = str(info.get("longName") or info.get("shortName") or symbol)

    score, checklist, notes, decision, outlook = _score_fundamentals(
        per=per,
        pbv=pbv,
        roe=roe,
        debt_to_equity=debt,
        current_ratio=current_ratio,
        profit_margin=profit_margin,
        revenue_growth=revenue_growth,
        earnings_growth=earnings_growth,
        dividend_yield=dividend_yield,
        sector=sector,
    )

    return FundamentalReport(
        symbol=symbol,
        name=name,
        sector=sector,
        industry=industry,
        price=price,
        per=per,
        forward_per=forward_per,
        pbv=pbv,
        roe=roe,
        debt_to_equity=debt,
        current_ratio=current_ratio,
        profit_margin=profit_margin,
        revenue_growth=revenue_growth,
        earnings_growth=earnings_growth,
        dividend_yield=dividend_yield,
        market_cap=market_cap,
        book_value=book_value,
        checklist=checklist,
        score=round(score, 1),
        decision=decision,
        outlook=outlook,
        notes=notes,
        raw={k: info.get(k) for k in (
            "trailingPE", "priceToBook", "returnOnEquity", "debtToEquity",
            "currentRatio", "profitMargins", "revenueGrowth", "earningsGrowth",
            "dividendYield", "marketCap",
        )},
    )


def format_fundamental_report(r: FundamentalReport) -> str:
    def mark(ok: bool | None) -> str:
        if ok is True:
            return "✅"
        if ok is False:
            return "❌"
        return "•"

    c = r.checklist
    lines = [
        f"📊 Fundamental {r.symbol}",
        f"{r.name}",
    ]
    if r.sector or r.industry:
        lines.append(f"Sektor: {r.sector or '-'} | {r.industry or '-'}")
    if r.price is not None:
        lines.append(f"Harga: {_fmt_rp(r.price)}")
    if r.market_cap is not None:
        lines.append(f"Market cap: {_fmt_rp(r.market_cap)}")
    lines.append("")
    lines.append("Ringkasan rasio:")
    lines.append(f"{mark(c.get('per'))} PER: {_fmt(r.per, digits=1, suffix='x')}"
                 + (f" (fwd {_fmt(r.forward_per, digits=1, suffix='x')})" if r.forward_per else ""))
    lines.append(f"{mark(c.get('pbv'))} PBV: {_fmt(r.pbv, digits=2, suffix='x')}")
    lines.append(f"{mark(c.get('roe'))} ROE: {_fmt(r.roe, digits=1, suffix='%')}")
    # tampilkan D/E ramah
    de_txt = "n/a"
    if r.debt_to_equity is not None:
        de = r.debt_to_equity / 100.0 if r.debt_to_equity > 5 else r.debt_to_equity
        de_txt = f"{de:.2f}x"
    lines.append(f"{mark(c.get('debt'))} Hutang (D/E): {de_txt}")
    lines.append(f"{mark(c.get('liquidity'))} Current ratio: {_fmt(r.current_ratio)}")
    lines.append(f"{mark(c.get('margin'))} Profit margin: {_fmt(r.profit_margin, digits=1, suffix='%')}")
    lines.append(
        f"{mark(c.get('growth'))} Growth rev/earn: "
        f"{_fmt(r.revenue_growth, digits=1, suffix='%')} / "
        f"{_fmt(r.earnings_growth, digits=1, suffix='%')}"
    )
    if r.dividend_yield is not None:
        lines.append(f"• Dividend yield: {_fmt(r.dividend_yield, digits=1, suffix='%')}")
    if r.book_value is not None:
        lines.append(f"• Book value/saham: {_fmt(r.book_value, digits=1)}")

    lines.append("")
    lines.append(f"Skor fundamental: {r.score}/100")
    lines.append(f"Keputusan: {r.decision}")
    lines.append("")
    lines.append("Catatan:")
    for n in r.notes[:8]:
        lines.append(f"• {n}")
    lines.append("")
    lines.append(f"Saran ke depan: {r.outlook}")
    lines.append("")
    lines.append(
        "Catatan: data dari Yahoo Finance (bisa delay/tidak lengkap untuk IDX). "
        "Ini ringkasan heuristik, bukan saran investasi."
    )
    return "\n".join(lines)
