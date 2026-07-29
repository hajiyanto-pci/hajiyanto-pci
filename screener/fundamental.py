"""Analisa fundamental saham IDX + komparasi peers sektor (large-cap)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from statistics import median
from typing import Any

import yfinance as yf

from screener.universe import to_yahoo_symbol


# Peer groups IDX (large / likuid) per sektor
SECTOR_PEERS: dict[str, tuple[str, ...]] = {
    "banks": (
        "BBCA",
        "BBRI",
        "BMRI",
        "BBNI",
        "BRIS",
        "BBTN",
        "BNGA",
        "NISP",
        "PNBN",
        "MEGA",
        "BJBR",
        "BJTM",
        "BTPS",
        "ARTO",
    ),
    "telecom": ("TLKM", "EXCL", "ISAT", "TOWR", "TBIG"),
    "consumer": ("UNVR", "ICBP", "INDF", "MYOR", "GGRM", "HMSP", "KLBF", "SIDO"),
    "auto": ("ASII", "AUTO", "IMPC"),
    "mining_coal": ("ADRO", "PTBA", "ITMG", "HRUM", "BSSR", "BYAN", "INDY"),
    "mining_metal": ("ANTM", "INCO", "MDKA", "NCKL", "BRMS", "TPIA"),
    "oil_gas": ("PGAS", "MEDC", "AKRA", "ENRG", "ESSA"),
    "cement": ("SMGR", "INTP", "WIKA", "WSKT", "PTPP"),
    "property": ("BSDE", "CTRA", "PWON", "SMRA", "ASRI", "DMAS", "LPKR"),
    "retail": ("ACES", "MAPI", "ERAA", "RALS", "LPPF", "MAPA"),
    "media_tech": ("EMTK", "GOTO", "BUKA", "SCMA", "MNCN"),
    "plantation": ("AALI", "LSIP", "SGRO", "SSMS", "TAPG", "PALM"),
    "healthcare": ("KLBF", "MIKA", "HEAL", "SIDO", "KAEF"),
}


@dataclass
class PeerSnap:
    symbol: str
    name: str
    market_cap: float | None
    net_income: float | None
    per: float | None
    pbv: float | None
    roe: float | None
    profit_margin: float | None


@dataclass
class PeerCompare:
    peer_group: str
    peers_used: list[str]
    median_per: float | None = None
    median_pbv: float | None = None
    median_roe: float | None = None
    median_margin: float | None = None
    median_mcap: float | None = None
    median_net_income: float | None = None
    per_vs_peer: str = ""  # cheaper / fair / premium
    pbv_vs_peer: str = ""
    roe_vs_peer: str = ""
    mcap_rank: str = ""
    profit_rank: str = ""
    notes: list[str] = field(default_factory=list)
    score_adjust: float = 0.0
    peer_rows: list[PeerSnap] = field(default_factory=list)


@dataclass
class FundamentalReport:
    symbol: str
    name: str
    sector: str
    industry: str
    price: float | None
    per: float | None
    forward_per: float | None
    pbv: float | None
    roe: float | None
    debt_to_equity: float | None
    current_ratio: float | None
    profit_margin: float | None
    revenue_growth: float | None
    earnings_growth: float | None
    dividend_yield: float | None
    market_cap: float | None
    book_value: float | None
    net_income: float | None = None
    checklist: dict[str, bool] = field(default_factory=dict)
    score: float = 0.0
    decision: str = ""
    outlook: str = ""
    notes: list[str] = field(default_factory=list)
    peer: PeerCompare | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        x = float(v)
        if x != x:
            return None
        return x
    except (TypeError, ValueError):
        return None


def _pct_from_ratio(v: float | None) -> float | None:
    if v is None:
        return None
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
    if abs(v) >= 1e12:
        return f"Rp {v/1e12:.1f} T"
    if abs(v) >= 1e9:
        return f"Rp {v/1e9:.1f} M"
    return f"Rp {v:,.0f}"


def _median(vals: list[float | None]) -> float | None:
    clean = [v for v in vals if v is not None and v == v]
    if not clean:
        return None
    return float(median(clean))


def resolve_peer_group(sector: str, industry: str, symbol: str) -> tuple[str, list[str]]:
    """Pilih peer group dari sektor/industri Yahoo atau fallback kode."""
    blob = f"{sector} {industry} {symbol}".lower()
    rules = (
        ("banks", ("bank", "financial services")),
        ("telecom", ("telecom", "communication", "tower")),
        ("mining_coal", ("coal", "thermal coal")),
        ("mining_metal", ("metal", "copper", "nickel", "gold", "mining")),
        ("oil_gas", ("oil", "gas", "energy")),
        ("cement", ("building materials", "cement", "construction")),
        ("property", ("real estate", "property")),
        ("retail", ("retail", "department", "specialty retail")),
        ("auto", ("auto", "auto manufacturers", "auto parts")),
        ("plantation", ("farm", "plantation", "palm", "agricultural")),
        ("healthcare", ("health", "drug", "pharma", "medical")),
        ("consumer", ("consumer", "food", "beverage", "household", "packaged")),
        ("media_tech", ("software", "internet", "media", "entertainment", " techn")),
    )
    for key, kws in rules:
        if any(k in blob for k in kws):
            peers = list(SECTOR_PEERS.get(key, ()))
            return key, peers

    # Fallback: jika simbol ada di salah satu group
    for key, peers in SECTOR_PEERS.items():
        if symbol.upper() in peers:
            return key, list(peers)
    return "unknown", []


def _extract_snap(symbol: str, info: dict[str, Any]) -> PeerSnap:
    net_income = (
        _num(info.get("netIncomeToCommon"))
        or _num(info.get("netIncome"))
        or _num(info.get("netIncomeFromContinuingOps"))
    )
    return PeerSnap(
        symbol=symbol,
        name=str(info.get("shortName") or info.get("longName") or symbol),
        market_cap=_num(info.get("marketCap")),
        net_income=net_income,
        per=_num(info.get("trailingPE")),
        pbv=_num(info.get("priceToBook")),
        roe=_pct_from_ratio(_num(info.get("returnOnEquity"))),
        profit_margin=_pct_from_ratio(_num(info.get("profitMargins"))),
    )


def _fetch_info(symbol: str) -> dict[str, Any]:
    yahoo = to_yahoo_symbol(symbol, "IDX")
    try:
        return yf.Ticker(yahoo).info or {}
    except Exception:
        return {}


def fetch_peer_snaps(symbols: list[str], *, max_workers: int = 6) -> list[PeerSnap]:
    out: list[PeerSnap] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(_fetch_info, s): s for s in symbols}
        for fut in as_completed(futs):
            sym = futs[fut]
            try:
                info = fut.result()
            except Exception:
                continue
            if not info:
                continue
            snap = _extract_snap(sym, info)
            if snap.market_cap is None and snap.per is None and snap.pbv is None:
                continue
            out.append(snap)
    return out


def select_large_peers(
    subject: PeerSnap,
    peers: list[PeerSnap],
    *,
    min_peers: int = 3,
    max_peers: int = 6,
) -> list[PeerSnap]:
    """Ambil peers large-cap setara (market cap besar + profit besar bila ada)."""
    others = [p for p in peers if p.symbol != subject.symbol]
    if not others:
        return []

    # Sort by market cap desc
    ranked = sorted(
        others,
        key=lambda p: (p.market_cap or 0.0, p.net_income or 0.0),
        reverse=True,
    )

    subj_cap = subject.market_cap or 0.0
    # Threshold: minimal 15% market cap subjek, atau top big caps peergroup
    floor = max(subj_cap * 0.15, 5e12) if subj_cap > 0 else 5e12  # ~Rp 5 T
    large = [p for p in ranked if (p.market_cap or 0) >= floor]

    # Jika subjek sudah big-cap, prioritaskan peers dengan mcap >= 30% subjek
    if subj_cap >= 50e12:  # >= Rp 50 T
        floor2 = subj_cap * 0.25
        tighter = [p for p in ranked if (p.market_cap or 0) >= floor2]
        if len(tighter) >= min_peers:
            large = tighter

    if len(large) < min_peers:
        large = ranked[:max_peers]
    else:
        large = large[:max_peers]
    return large


def _vs_label(subject: float | None, peer_med: float | None, *, lower_better: bool) -> str:
    if subject is None or peer_med is None or peer_med == 0:
        return "n/a"
    diff_pct = (subject - peer_med) / abs(peer_med) * 100.0
    if lower_better:
        if diff_pct <= -15:
            return "lebih murah"
        if diff_pct >= 15:
            return "lebih mahal"
        return "setara"
    if diff_pct >= 15:
        return "lebih tinggi"
    if diff_pct <= -15:
        return "lebih rendah"
    return "setara"


def compare_with_peers(
    subject: PeerSnap,
    sector: str,
    industry: str,
) -> PeerCompare:
    group, peer_codes = resolve_peer_group(sector, industry, subject.symbol)
    if subject.symbol not in peer_codes and peer_codes:
        peer_codes = [subject.symbol, *peer_codes]
    if not peer_codes:
        return PeerCompare(
            peer_group=group,
            peers_used=[],
            notes=["Peer sektor tidak tersedia untuk komparasi otomatis."],
        )

    # Batasi fetch agar cepat: subjek + hingga 10 kandidat
    uniq = []
    for c in peer_codes:
        cu = c.upper()
        if cu not in uniq:
            uniq.append(cu)
    snaps = fetch_peer_snaps(uniq[:12])
    by_sym = {s.symbol: s for s in snaps}
    subj = by_sym.get(subject.symbol, subject)
    selected = select_large_peers(subj, snaps)
    if not selected:
        return PeerCompare(
            peer_group=group,
            peers_used=[],
            notes=["Gagal ambil data peer large-cap."],
        )

    med_per = _median([p.per for p in selected])
    med_pbv = _median([p.pbv for p in selected])
    med_roe = _median([p.roe for p in selected])
    med_margin = _median([p.profit_margin for p in selected])
    med_mcap = _median([p.market_cap for p in selected])
    med_ni = _median([p.net_income for p in selected])

    per_vs = _vs_label(subj.per, med_per, lower_better=True)
    pbv_vs = _vs_label(subj.pbv, med_pbv, lower_better=True)
    roe_vs = _vs_label(subj.roe, med_roe, lower_better=False)

    # Ranking market cap & net income di antara subjek+peers
    basket = [subj, *selected]
    by_mcap = sorted(basket, key=lambda p: p.market_cap or 0, reverse=True)
    by_ni = sorted(basket, key=lambda p: p.net_income or 0, reverse=True)
    mcap_rank_i = next((i + 1 for i, p in enumerate(by_mcap) if p.symbol == subj.symbol), None)
    ni_rank_i = next((i + 1 for i, p in enumerate(by_ni) if p.symbol == subj.symbol), None)
    mcap_rank = f"#{mcap_rank_i}/{len(basket)}" if mcap_rank_i else "n/a"
    profit_rank = f"#{ni_rank_i}/{len(basket)}" if ni_rank_i else "n/a"

    notes: list[str] = []
    score_adj = 0.0
    peer_names = ", ".join(p.symbol for p in selected)
    notes.append(f"Peers large-cap ({group}): {peer_names}")

    if per_vs == "lebih murah":
        score_adj += 8
        notes.append(
            f"PER {_fmt(subj.per, digits=1, suffix='x')} lebih murah vs median peer "
            f"{_fmt(med_per, digits=1, suffix='x')}"
        )
    elif per_vs == "lebih mahal":
        score_adj -= 8
        notes.append(
            f"PER {_fmt(subj.per, digits=1, suffix='x')} lebih mahal vs median peer "
            f"{_fmt(med_per, digits=1, suffix='x')}"
        )
    elif per_vs == "setara":
        score_adj += 2
        notes.append(f"PER setara peers (median {_fmt(med_per, digits=1, suffix='x')})")

    if pbv_vs == "lebih murah":
        score_adj += 6
        notes.append(
            f"PBV {_fmt(subj.pbv)}x lebih murah vs median peer {_fmt(med_pbv)}x"
        )
    elif pbv_vs == "lebih mahal":
        # Premium PBV boleh jika ROE lebih tinggi
        if roe_vs == "lebih tinggi":
            score_adj += 2
            notes.append(
                f"PBV premium ({_fmt(subj.pbv)}x vs {_fmt(med_pbv)}x) "
                f"masih wajar karena ROE lebih tinggi"
            )
        else:
            score_adj -= 6
            notes.append(
                f"PBV {_fmt(subj.pbv)}x lebih mahal vs median peer {_fmt(med_pbv)}x"
            )
    elif pbv_vs == "setara":
        score_adj += 1

    if roe_vs == "lebih tinggi":
        score_adj += 10
        notes.append(
            f"ROE {_fmt(subj.roe, digits=1, suffix='%')} unggul vs median peer "
            f"{_fmt(med_roe, digits=1, suffix='%')}"
        )
    elif roe_vs == "lebih rendah":
        score_adj -= 8
        notes.append(
            f"ROE {_fmt(subj.roe, digits=1, suffix='%')} di bawah median peer "
            f"{_fmt(med_roe, digits=1, suffix='%')}"
        )
    elif roe_vs == "setara":
        score_adj += 3
        notes.append(f"ROE setara peers (median {_fmt(med_roe, digits=1, suffix='%')})")

    if mcap_rank_i == 1:
        score_adj += 3
        notes.append("Market cap terbesar di kelompok peer large-cap")
    if ni_rank_i == 1:
        score_adj += 4
        notes.append("Nett profit terbesar di kelompok peer large-cap")
    elif ni_rank_i and ni_rank_i <= 3:
        score_adj += 2
        notes.append(f"Nett profit termasuk top {ni_rank_i} peer large-cap")

    return PeerCompare(
        peer_group=group,
        peers_used=[p.symbol for p in selected],
        median_per=med_per,
        median_pbv=med_pbv,
        median_roe=med_roe,
        median_margin=med_margin,
        median_mcap=med_mcap,
        median_net_income=med_ni,
        per_vs_peer=per_vs,
        pbv_vs_peer=pbv_vs,
        roe_vs_peer=roe_vs,
        mcap_rank=mcap_rank,
        profit_rank=profit_rank,
        notes=notes,
        score_adjust=score_adj,
        peer_rows=selected,
    )


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
) -> tuple[float, dict[str, bool], list[str]]:
    notes: list[str] = []
    checklist: dict[str, bool] = {}
    score = 0.0
    is_bank = "bank" in (sector or "").lower() or "financial" in (sector or "").lower()

    if per is None or per <= 0:
        checklist["per"] = False
        notes.append("PER tidak tersedia / negatif (rugi?)")
    elif 8 <= per <= 20:
        checklist["per"] = True
        score += 18
        notes.append(f"PER {per:.1f}x di zona wajar absolut")
    elif 5 <= per < 8:
        checklist["per"] = True
        score += 14
        notes.append(f"PER {per:.1f}x relatif murah (absolut)")
    elif 20 < per <= 30:
        checklist["per"] = False
        score += 8
        notes.append(f"PER {per:.1f}x agak mahal (absolut)")
    else:
        checklist["per"] = False
        score += 2
        notes.append(f"PER {per:.1f}x ekstrem / mahal (absolut)")

    pbv_ok_max = 3.5 if is_bank else 4.0
    if pbv is None or pbv <= 0:
        checklist["pbv"] = False
        notes.append("PBV tidak tersedia")
    elif pbv < 1:
        checklist["pbv"] = True
        score += 16
        notes.append(f"PBV {pbv:.2f}x di bawah nilai buku")
    elif pbv <= pbv_ok_max:
        checklist["pbv"] = True
        score += 14
        notes.append(f"PBV {pbv:.2f}x masih wajar absolut")
    elif pbv <= pbv_ok_max + 2:
        checklist["pbv"] = False
        score += 6
        notes.append(f"PBV {pbv:.2f}x premium absolut")
    else:
        checklist["pbv"] = False
        score += 1
        notes.append(f"PBV {pbv:.2f}x mahal absolut")

    if roe is None:
        checklist["roe"] = False
        notes.append("ROE tidak tersedia")
    elif roe >= 15:
        checklist["roe"] = True
        score += 20
        notes.append(f"ROE {roe:.1f}% kuat")
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
        notes.append(f"ROE {roe:.1f}% lemah")

    if debt_to_equity is None:
        checklist["debt"] = True if is_bank else False
        if is_bank:
            notes.append("D/E bank di Yahoo sering kosong — bandingkan kualitas aset/NPL terpisah")
            score += 6
        else:
            notes.append("Rasio hutang (D/E) tidak tersedia")
    else:
        de = debt_to_equity / 100.0 if debt_to_equity > 5 else debt_to_equity
        if de <= 0.8:
            checklist["debt"] = True
            score += 14
            notes.append(f"D/E {de:.2f}x rendah")
        elif de <= 1.5:
            checklist["debt"] = True
            score += 10
            notes.append(f"D/E {de:.2f}x terkendali")
        elif de <= 2.5:
            checklist["debt"] = False
            score += 4
            notes.append(f"D/E {de:.2f}x agak tinggi")
        else:
            checklist["debt"] = False
            notes.append(f"D/E {de:.2f}x tinggi")

    if current_ratio is None:
        checklist["liquidity"] = is_bank
        if is_bank:
            score += 4
        else:
            notes.append("Current ratio tidak tersedia")
    elif current_ratio >= 1.2:
        checklist["liquidity"] = True
        score += 8
        notes.append(f"Current ratio {current_ratio:.2f} likuid")
    elif current_ratio >= 1.0:
        checklist["liquidity"] = True
        score += 5
        notes.append(f"Current ratio {current_ratio:.2f} pas-pasan")
    else:
        checklist["liquidity"] = False
        notes.append(f"Current ratio {current_ratio:.2f} rendah")

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

    growth_pts = 0.0
    if revenue_growth is not None:
        if revenue_growth >= 10:
            growth_pts += 5
            notes.append(f"Revenue growth {revenue_growth:.1f}%")
        elif revenue_growth >= 0:
            growth_pts += 2
            notes.append(f"Revenue growth {revenue_growth:.1f}% datar")
        else:
            notes.append(f"Revenue growth {revenue_growth:.1f}% negatif")
    if earnings_growth is not None:
        if earnings_growth >= 10:
            growth_pts += 5
            notes.append(f"Earnings growth {earnings_growth:.1f}%")
        elif earnings_growth >= 0:
            growth_pts += 2
            notes.append(f"Earnings growth {earnings_growth:.1f}% tipis")
        else:
            notes.append(f"Earnings growth {earnings_growth:.1f}% negatif")
    checklist["growth"] = growth_pts >= 5
    score += growth_pts

    if dividend_yield is not None and dividend_yield >= 2:
        score += 4
        notes.append(f"Dividend yield ~{dividend_yield:.1f}%")

    return max(0.0, min(100.0, score)), checklist, notes


def _decision_from_score_and_peers(score: float, peer: PeerCompare | None) -> tuple[str, str]:
    cheapish = False
    quality = False
    expensive = False
    if peer:
        cheapish = peer.per_vs_peer == "lebih murah" or peer.pbv_vs_peer == "lebih murah"
        quality = peer.roe_vs_peer == "lebih tinggi"
        expensive = peer.per_vs_peer == "lebih mahal" and peer.pbv_vs_peer == "lebih mahal"

    if score >= 72 and (quality or cheapish):
        decision = "FUNDAMENTAL KUAT vs PEER"
        outlook = (
            "Relatif terhadap peers large-cap sektor yang sama, saham ini terlihat kompetitif. "
            "Layak dipertimbangkan jangka menengah/panjang, terutama jika teknikal mendukung. "
            "Pantau apakah premium valuasi (bila ada) tetap diimbangi ROE/profit."
        )
    elif score >= 70:
        decision = "FUNDAMENTAL KUAT"
        outlook = (
            "Fundamental absolut kuat. Bandingkan terus dengan peers: jika valuasi sudah premium "
            "tanpa ROE unggul, lebih baik akumulasi saat koreksi."
        )
    elif score >= 55:
        decision = "FUNDAMENTAL CUKUP vs PEER"
        outlook = (
            "Layak dipantau vs peers. Cocok akumulasi bertahap bila masih setara/lebih murah "
            "dari median sektor, bukan chase harga mahal."
        )
    elif score >= 40:
        decision = "FUNDAMENTAL CAMPURAN vs PEER"
        if expensive and not quality:
            outlook = (
                "Valuasi lebih mahal dari peers tanpa keunggulan ROE yang jelas. "
                "Tunggu diskon ke median sektor atau perbaikan profitabilitas."
            )
        else:
            outlook = (
                "Campuran vs peers. Tunggu perbaikan margin/growth atau valuasi lebih menarik "
                "sebelum menambah posisi."
            )
    else:
        decision = "FUNDAMENTAL LEMAH vs PEER"
        outlook = (
            "Di bawah standar peers large-cap sektornya. Prioritaskan kompetitor dengan "
            "ROE & nett profit lebih kuat, atau tunggu turnaround yang terbukti."
        )
    return decision, outlook


def analyze_fundamental(code: str, *, with_peers: bool = True) -> FundamentalReport:
    symbol = code.strip().upper().replace(".JK", "")
    if not symbol:
        raise ValueError("Kode saham kosong")

    yahoo = to_yahoo_symbol(symbol, "IDX")
    try:
        info = yf.Ticker(yahoo).info or {}
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Gagal ambil data fundamental {symbol}: {exc}") from exc

    if not info or (not info.get("symbol") and not info.get("shortName") and not info.get("longName")):
        try:
            hist = yf.Ticker(yahoo).history(period="5d")
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
    dy_raw = _num(info.get("dividendYield"))
    dividend_yield = dy_raw * 100.0 if dy_raw is not None and dy_raw <= 0.3 else dy_raw
    price = _num(info.get("currentPrice")) or _num(info.get("previousClose"))
    market_cap = _num(info.get("marketCap"))
    book_value = _num(info.get("bookValue"))
    net_income = (
        _num(info.get("netIncomeToCommon"))
        or _num(info.get("netIncome"))
        or _num(info.get("netIncomeFromContinuingOps"))
    )
    sector = str(info.get("sector") or "")
    industry = str(info.get("industry") or "")
    name = str(info.get("longName") or info.get("shortName") or symbol)

    score, checklist, notes = _score_fundamentals(
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

    peer: PeerCompare | None = None
    if with_peers:
        subj_snap = PeerSnap(
            symbol=symbol,
            name=name,
            market_cap=market_cap,
            net_income=net_income,
            per=per,
            pbv=pbv,
            roe=roe,
            profit_margin=profit_margin,
        )
        peer = compare_with_peers(subj_snap, sector, industry)
        score = max(0.0, min(100.0, score + peer.score_adjust))
        notes.extend(peer.notes)

    decision, outlook = _decision_from_score_and_peers(score, peer)

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
        net_income=net_income,
        checklist=checklist,
        score=round(score, 1),
        decision=decision,
        outlook=outlook,
        notes=notes,
        peer=peer,
        raw={k: info.get(k) for k in (
            "trailingPE", "priceToBook", "returnOnEquity", "debtToEquity",
            "currentRatio", "profitMargins", "revenueGrowth", "earningsGrowth",
            "dividendYield", "marketCap", "netIncomeToCommon",
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
    if r.net_income is not None:
        lines.append(f"Nett profit: {_fmt_rp(r.net_income)}")

    lines.append("")
    lines.append("Ringkasan rasio (absolut):")
    lines.append(
        f"{mark(c.get('per'))} PER: {_fmt(r.per, digits=1, suffix='x')}"
        + (f" (fwd {_fmt(r.forward_per, digits=1, suffix='x')})" if r.forward_per else "")
    )
    lines.append(f"{mark(c.get('pbv'))} PBV: {_fmt(r.pbv, digits=2, suffix='x')}")
    lines.append(f"{mark(c.get('roe'))} ROE: {_fmt(r.roe, digits=1, suffix='%')}")
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

    if r.peer and r.peer.peers_used:
        p = r.peer
        lines.append("")
        lines.append(f"Komparasi peers large-cap ({p.peer_group}):")
        lines.append(f"• Peers: {', '.join(p.peers_used)}")
        lines.append(
            f"• PER: {_fmt(r.per, digits=1, suffix='x')} vs median peer "
            f"{_fmt(p.median_per, digits=1, suffix='x')} → {p.per_vs_peer or 'n/a'}"
        )
        lines.append(
            f"• PBV: {_fmt(r.pbv)}x vs median peer {_fmt(p.median_pbv)}x "
            f"→ {p.pbv_vs_peer or 'n/a'}"
        )
        lines.append(
            f"• ROE: {_fmt(r.roe, digits=1, suffix='%')} vs median peer "
            f"{_fmt(p.median_roe, digits=1, suffix='%')} → {p.roe_vs_peer or 'n/a'}"
        )
        lines.append(f"• Ranking market cap di peer set: {p.mcap_rank}")
        lines.append(f"• Ranking nett profit di peer set: {p.profit_rank}")
        lines.append(
            f"• Median peer mcap / nett profit: "
            f"{_fmt_rp(p.median_mcap)} / {_fmt_rp(p.median_net_income)}"
        )
        # tabel singkat top peers
        lines.append("• Detail peer (mcap | PER | PBV | ROE | nett):")
        for row in p.peer_rows[:6]:
            lines.append(
                f"  - {row.symbol}: {_fmt_rp(row.market_cap)} | "
                f"{_fmt(row.per, digits=1, suffix='x')} | "
                f"{_fmt(row.pbv)}x | "
                f"{_fmt(row.roe, digits=1, suffix='%')} | "
                f"{_fmt_rp(row.net_income)}"
            )

    lines.append("")
    lines.append(f"Skor fundamental (setelah peer): {r.score}/100")
    lines.append(f"Keputusan: {r.decision}")
    lines.append("")
    lines.append("Catatan:")
    for n in r.notes[:10]:
        lines.append(f"• {n}")
    lines.append("")
    lines.append(f"Saran ke depan: {r.outlook}")
    lines.append("")
    lines.append(
        "Catatan: data Yahoo Finance; peer = large-cap sektor yang sama. "
        "Ringkasan heuristik, bukan saran investasi."
    )
    return "\n".join(lines)
