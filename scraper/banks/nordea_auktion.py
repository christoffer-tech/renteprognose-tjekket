"""Nordea auktions-prognoser (nordea.com/da/nyhed/forventninger-til-f1-...).

Hver artikel giver een prognose pr. produkt (F1/F3/F5) for den kommende
refinansiering (1. januar / 1. april / 1. oktober) inkl. 'rente i dag'
(facit-definition, samme kontantlaansrente efter kursfradrag som
hovedtabellen i banks/nordea.py).

Serien gaar mindst tilbage til 2025 (verificeret) og opdages via
nordea.com-sitemap'et, saa nye artikler kommer med automatisk.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from common import clean, obs_date_for, parse_dk_date, parse_rate

BANK_ID = "nordea"

# Verificerede artikler (sitemap'et finder evt. flere automatisk).
ARTICLE_URLS = [
    "https://www.nordea.com/da/nyhed/forventninger-til-f1-f3-og-f5-renten-til-november-2025-auktionen",
    "https://www.nordea.com/da/nyhed/forventninger-til-f1-f3-og-f5-renten-1.-april-2026",
    "https://www.nordea.com/da/nyhed/forventninger-til-f1-f3-og-f5-renten-1.-oktober-2026",
    "https://www.nordea.com/da/nyhed/forventninger-til-f1-f3-og-f5-renten-1.-januar-2027",
]

SITEMAP_URL = "https://www.nordea.com/da/sitemap.xml"


def discover_urls(sitemap_xml: str) -> list[str]:
    """Find alle forventnings-artikler i sitemap'et (serien skifter slug-format)."""
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap_xml)
    out = [u for u in urls
           if re.search(r"forventninger-til-f1", u, re.IGNORECASE)]
    # 'ny-rente'-artikler er facit (auktionsresultat), ikke prognoser
    return sorted(set(out))


def _rate(text: str) -> float | None:
    # artiklerne skriver 'pct.' i stedet for '%'
    return parse_rate(text.replace("pct.", "%").replace("pct", "%"))


def parse_article(html: str, url: str, source: str,
                  capture_ts: str | None, fallback_date: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")

    pub_date = None
    m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', html)
    if m:
        pub_date = m.group(1)
    if pub_date is None:
        t = soup.find("time")
        if t and t.get("datetime"):
            pub_date = parse_dk_date(t["datetime"])
    if pub_date is None:
        pub_date = fallback_date

    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    # maaldato: '1. januar 2026' i titel/tekst (refinansieringsdatoen)
    target = None
    for mm in re.finditer(
            r"1\.\s*(januar|april|juli|oktober)\s*20\d{2}", txt, re.I):
        target = parse_dk_date(mm.group(0))
        break
    if target is None:
        return None

    rows: dict[str, dict] = {}
    raw_rows: dict[str, list] = {}
    names = {"f1": "Rentetilpasningslån F1", "f3": "Rentetilpasningslån F3",
             "f5": "Rentetilpasningslån F5"}
    for key in ("f1", "f3", "f5"):
        # 'F1-rente: 2,2 pct. (rente i dag: 2,54 pct.)'
        rx = re.compile(re.escape(key.upper()) + r"-rente:\s*"
                        r"(-?[\d,.\s]+)\s*pct\.\s*\(rente i dag:\s*"
                        r"(-?[\d,.\s]+)\s*pct\.", re.IGNORECASE)
        mm = rx.search(txt)
        if not mm:
            continue
        fc, act = _rate(mm.group(1) + " %"), _rate(mm.group(2) + " %")
        if fc is None:
            continue
        rows[key] = {"name": names[key], "aktuelt": act, "forecasts": [fc],
                     "targets": [target]}
        raw_rows[names[key]] = [act, fc]

    if not rows:
        return None
    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": [target],
        "rows": rows,
        "raw_rows": raw_rows,
        "article_url": url,
    }
