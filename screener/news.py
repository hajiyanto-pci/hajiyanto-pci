"""Lightweight news headlines for IHSG / macro context (Google News RSS)."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable


POSITIVE = (
    "naik",
    "menguat",
    "rekor",
    "optimis",
    "stimulus",
    "pemulihan",
    "surplus",
    "rally",
    "bullish",
    "cut rate",
    "pemangkasan suku bunga",
    "inflow",
    "foreign buy",
)

NEGATIVE = (
    "turun",
    "melemah",
    "anjlok",
    "koreksi",
    "tekanan",
    "inflasi",
    "perang",
    "sanksi",
    "default",
    "krisis",
    "outflow",
    "foreign sell",
    "hawkish",
    "naik suku bunga",
    "rate hike",
    "resesi",
)


@dataclass
class Headline:
    title: str
    source: str
    link: str
    tone: int  # -1 / 0 / +1


def _tone(title: str) -> int:
    t = title.lower()
    pos = sum(1 for w in POSITIVE if w in t)
    neg = sum(1 for w in NEGATIVE if w in t)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def _fetch_rss(query: str, limit: int = 8) -> list[Headline]:
    q = urllib.parse.quote(query)
    url = (
        "https://news.google.com/rss/search?"
        f"q={q}&hl=id&gl=ID&ceid=ID:id"
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; StockScreenerBot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()
    except Exception:
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    out: list[Headline] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else "Google News"
        if not title:
            continue
        # Strip trailing " - Source" sometimes duplicated
        title = re.sub(r"\s+-\s+[^-]+$", "", title).strip() or title
        out.append(Headline(title=title, source=source, link=link, tone=_tone(title)))
        if len(out) >= limit:
            break
    return out


def fetch_ihsg_headlines(limit: int = 6) -> list[Headline]:
    """Fetch Indonesian market / macro headlines relevant to IHSG."""
    queries = (
        "IHSG",
        "Bank Indonesia suku bunga",
        "rupiah USD",
    )
    seen: set[str] = set()
    merged: list[Headline] = []
    for q in queries:
        for h in _fetch_rss(q, limit=4):
            key = h.title.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(h)
            if len(merged) >= limit:
                return merged
    return merged


def news_bias_score(headlines: Iterable[Headline]) -> int:
    return sum(h.tone for h in headlines)


def format_news_block(headlines: list[Headline]) -> str:
    if not headlines:
        return "Berita: tidak ada headline terambil."
    lines = ["Headline terkait (Google News):"]
    for h in headlines[:6]:
        mark = "▲" if h.tone > 0 else ("▼" if h.tone < 0 else "•")
        lines.append(f"{mark} {h.title} ({h.source})")
    score = news_bias_score(headlines)
    if score >= 2:
        lines.append("Nada berita cenderung positif untuk risk appetite.")
    elif score <= -2:
        lines.append("Nada berita cenderung menekan pasar.")
    else:
        lines.append("Nada berita campuran.")
    return "\n".join(lines)
