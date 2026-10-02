"""Fælles hjælpefunktioner til bank-scrapere: HTTP, parsing af danske
renter/datoer, snapshot-IO og Wayback-backfill."""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) renteprognose-tracker (research project)"}

DK_MONTHS = {
    "januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}


BROWSER_HEADERS = {
    **UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}


def fetch(url: str, timeout: int = 60, headers: dict | None = None) -> str:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers or UA, timeout=timeout)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except requests.RequestException as e:
            print(f"    forsøg {attempt + 1} fejlede ({e}), venter...", flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Kunne ikke hente {url}")


def parse_rate(text: str) -> float | None:
    """'2,50 %' -> 2.5. Håndterer dansk komma-decimal og minustegn."""
    if not text:
        return None
    m = re.search(r"(-?[\d\s\u00a0\u202f.,]+)\s*%", text.replace("\u200b", ""))
    if not m:
        return None
    num = m.group(1).replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
    if "," in num:
        num = num.replace(".", "").replace(",", ".")
    try:
        return round(float(num), 3)
    except ValueError:
        return None


def parse_interval(text: str) -> tuple[float, float] | None:
    """'2,9 % - 3,2 %' -> (2.9, 3.2). Returner None hvis intet interval."""
    if not text:
        return None
    clean = text.replace("\u200b", "")
    parts = re.split(r"\s*[-–—]\s*", clean)
    if len(parts) != 2:
        return None
    lo, hi = parse_rate(parts[0] + " %"), parse_rate(parts[1])
    if lo is None or hi is None:
        # prøv: begge parter har allerede %-tegn
        lo, hi = parse_rate(parts[0]), parse_rate(parts[1])
    if lo is None or hi is None:
        return None
    return (lo, hi)


def parse_dk_date(text: str) -> str | None:
    """'30-12-26', '30.12.2026', '30. december 2026' -> '2026-12-30'."""
    if not text:
        return None
    t = text.replace("\u200b", " ").strip()
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 70 else 1900
        try:
            return dt.date(y, mo, d).isoformat()
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\.\s*([a-zæøå]+)\s*(\d{4})", t, re.IGNORECASE)
    if m:
        month = DK_MONTHS.get(m.group(2).lower())
        if month is None:
            return None
        try:
            return dt.date(int(m.group(3)), month, int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def add_months(date_iso: str, n: int) -> str:
    """Læg n måneder til en ISO-dato (klem dag til månedens længde)."""
    d = dt.date.fromisoformat(date_iso)
    total = (d.year * 12 + d.month - 1) + n
    y, m = divmod(total, 12)
    m += 1
    import calendar
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, min(d.day, last)).isoformat()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u200b", " ")).strip()


def table_rows(table) -> list[list[str]]:
    rows = [[clean(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
            for tr in table.find_all("tr")]
    return [r for r in rows if any(r)]


def obs_date_for(source: str, capture_ts: str | None, today: str) -> str:
    """Dato for hvornår 'Aktuelt' er observeret: capture-dato (wayback) eller i dag (live)."""
    if capture_ts:
        return f"{capture_ts[0:4]}-{capture_ts[4:6]}-{capture_ts[6:8]}"
    return today


def snapshot_fingerprint(snap: dict) -> str:
    core = {k: v for k, v in snap.items() if k not in ("source", "capture")}
    return json.dumps(core, sort_keys=True)


def list_captures(page_url: str, since: str = "2020") -> list[dict]:
    """List unikke Wayback-captures (collapse på digest) for en side-URL."""
    host_path = re.sub(r"^https?://(www\.)?", "", page_url).rstrip("/") + "/"
    params = {
        "url": host_path,
        "from": since,
        "output": "json",
        "filter": ["statuscode:200", "mimetype:text/html"],
        "collapse": "digest",
    }
    print(f"Henter capture-liste for {page_url} ...", flush=True)
    r = requests.get("https://web.archive.org/cdx/search/cdx",
                     params=params, headers=UA, timeout=120)
    r.raise_for_status()
    data = r.json()
    header, rows = data[0], data[1:]
    captures = [dict(zip(header, row)) for row in rows]
    print(f"  {len(captures)} unikke captures fundet", flush=True)
    return captures


def wayback_url(capture: dict) -> str:
    return f"https://web.archive.org/web/{capture['timestamp']}id_/{capture['original']}"
