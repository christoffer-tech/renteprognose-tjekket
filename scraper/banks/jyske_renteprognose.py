"""Jyske Markets' månedlige "Renteprognose" (PDF).

Hvert notat indeholder tabelblokke med renteforventninger for Danmark,
Eurozonen og USA. Fra 2024 er stats- og swaprenterne slået sammen i én tabel;
før det stod de i to:

    Jyske Bank renteprognose
        STATSRENTER
        Danmark      Spot     Q3-24   Q4-24   Q1-25   Q2-25   Q4-25
        Leading       3,35     3,10    2,85    2,60    2,35    1,85
        Cibor 3m      3,63     3,35    3,10    2,85    2,65    2,30
        STAT 2y       2,94     2,75    2,45    2,20    2,05    2,00
        STAT 30y      2,58     2,50    2,35    2,25    2,20    2,45

        SWAPRENTER
        Danmark      Spot     Q3-24   Q4-24   Q1-25   Q2-25   Q4-25
        SWAP 2y       2,50     2,45    2,35    2,25    2,20    2,30
        SWAP 5y       2,44     2,35    2,40    2,50    2,60    2,65
        SWAP 10y      2,74     2,70    2,80    2,95    3,00    3,05

Bemaerk: dette er MARKEDSRENTER. STAT 30y svarer til den 30-aarige statsrente,
ikke til bankens 30-aarige realkreditlaan (fast30), som har et andet spread;
SWAP 5y er heller ikke det samme som bankens F5-laan (se README). Serierne
holdes derfor adskilt fra de oevrige produktnoegler.

Parseren er **positionsbaseret**: kolonnerne findes ud fra x-koordinaterne i
`pdftotext -layout`, og hver vaerdi placeres i den kolonne den staar under.
Det er noedvendigt, fordi flere udgaver (fx januar 2020) har skiftevis en
prognose- og en "chg."-kolonne, hvor blanke celler forskyder raekkefoelgen, og
fordi nogle udgaver (november/december 2020) er to-spaltede sider, hvor
venstre spaltes boligrentetabel deler linjer med hoejre spaltes prognosetabel.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re

from common import UA

BANK_ID = "jyske"

# Raekkelabels. Moenstrene matches som *suffiks* af etiketten, saa de ogsaa
# virker naar der staar andet tekst til venstre for tabellen (to-spaltede sider).
ROWS = [
    # 2019-2024-udgaverne
    (r"leading", "leading_dk"),
    # 2024-2026-udgaverne kalder den Politikrente
    (r"politikrente", "leading_dk"),
    (r"cibor\s*3\s*m", "cibor3"),
    (r"cibor\s*6\s*m", "cibor6"),
    # Loebetider skrives skiftevis 'STAT 2y' og 'STAT 2-årig'
    (r"stat\s*2\s*-?\s*(?:y|årig|årige)", "stat2"),
    (r"stat\s*5\s*-?\s*(?:y|årig|årige)", "stat5"),
    (r"stat\s*10\s*-?\s*(?:y|årig|årige)", "stat10"),
    (r"stat\s*30\s*-?\s*(?:y|årig|årige)", "stat30"),
    (r"swap\s*2\s*-?\s*(?:y|årig|årige)", "swap2"),
    (r"swap\s*5\s*-?\s*(?:y|årig|årige)", "swap5"),
    (r"swap\s*10\s*-?\s*(?:y|årig|årige)", "swap10"),
    (r"swap\s*30\s*-?\s*(?:y|årig|årige)", "swap30"),
]
# Afledte rentespænd ('SWAP 5y - 2y', 'STAT 10y - 5y') er ikke selvstændige
# serier; de kan genskabes ud fra løbetiderne og ville ellers blive laest som
# endnu en løbetid. Bindestregen skal staa frit, ellers rammer mønstret også
# 'STAT 2-årig'.
IGNORE = (r"^(?:stat|swap)\s*\d+\s*(?:y|årig|årige)?\s+-\s*\d",
          r"^amn", r"^kilde")

# --- "Tabel 1: Jyske Bank Boligrenteprognose" -------------------------------
# Samme notat indeholder bankens *egne* renter for rentetilpasningslaan, med
# etiketten skiftende gennem aarene:
#
#   2017:      F1-rente, F5-rente
#   2019:      RTL1(-rente), RTL5(-rente)
#   2019-2024: RTL1, RTL3, RTL5, RTL10
#
# Kolonnerne er 'I dag' plus en-to refinansieringsdatoer skrevet som
# 'Pr. 1. okt' / 'Pr . 1. o kt.' / 'Pr. 1.okt' / 'Pr 1. ju li'. RTL1/RTL3/
# RTL5/RTL10 er bankens 1/3/5/10-aarige rentetilpasningslaan. De gemmes under
# *egne* noegler (rtl*), ikke under f1/f3/f5: ved faelles datoer ligger RTL5 og
# bankens 'Jyske Rentetilpasning F5' fra Boliglånsanbefalingen ca. 0,5 pp fra
# hinanden, saa de to tabeller maaler ikke samme rentebegreb (se README).
BOLIG_START = "boligrenteprognose"
IDAG_RE = re.compile(r"i\s?d\s?a\s?g", re.IGNORECASE)
PRA_RE = re.compile(r"p\s?r\s?\.?\s*1\s?\.?\s*([a-zæøå](?:\s?[a-zæøå])*)",
                    re.IGNORECASE)
MONTHS = {"jan": 1, "januar": 1, "feb": 2, "februar": 2, "mar": 3, "marts": 3,
          "apr": 4, "april": 4, "maj": 5, "jun": 6, "juni": 6, "jul": 7,
          "juli": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
          "okt": 10, "oktober": 10, "nov": 11, "november": 11, "dec": 12,
          "december": 12}
BOLIG_ROWS = [
    (r"rtl\s*10(?:\s*-?\s*rente)?", "rtl10"),
    (r"f\s*10\s*-?\s*rente", "rtl10"),
    (r"rtl\s*5(?:\s*-?\s*rente)?", "rtl5"),
    (r"f\s*5\s*-?\s*rente", "rtl5"),
    (r"rtl\s*3(?:\s*-?\s*rente)?", "rtl3"),
    (r"f\s*3\s*-?\s*rente", "rtl3"),
    (r"rtl\s*1(?:\s*-?\s*rente)?", "rtl1"),
    (r"f\s*1\s*-?\s*rente", "rtl1"),
]
BOLIG_IGNORE = (r"^kurs", r"^tilbudskurs", r"^rente", r"^note", r"^kilde",
                r"^se\s")

# Omraader: 'Danmark', 'Eurozonen'/'EUROLAND'/'Europa', 'USA'
AREAS = [(r"danmark", "dk"), (r"euro", "eu"), (r"usa", "us")]

# 2019-2024: "Tabel N: Jyske Bank Renteprognose"
# 2024-2026: samme titel, men sektionen hedder "STATS- OG SWAPRENTER"
TABEL_START = "jyske bank renteprognose"
TABEL_ALT = ("stats- og swaprenter", "statsrenter", "swaprenter")
TITLE_ONLY = re.compile(r"^(?:stats-?\s*og\s*)?(?:swaprenter|statsrenter)$",
                        re.IGNORECASE)
STOP_RE = re.compile(r"vigtig\s+(?:investor)?information", re.IGNORECASE)

# Kvartalsetiketter: Q1-24 .. Q4-26. Brevspærrede overskrifter fra
# pdftotext -layout skriver 'Q 3-17', saa der tillades mellemrum.
QRE = re.compile(r"Q\s?([1-4])\s?-\s?(\d{2})", re.IGNORECASE)
SPOT_RE = re.compile(r"S\s?p\s?o\s?t", re.IGNORECASE)
CHG_RE = re.compile(r"c\s?h\s?g", re.IGNORECASE)
# Dansk tal: -0,13 -> -0.13. Lookbehind saa '1.234,5' ikke laeses som '234,5'.
NUM_RE = re.compile(r"(?<![\d.,])-?\d+,\d+")
# To-spaltet side: en tabeltitel langt ude paa linjen betyder at siden har en
# hoejre spalte, som skal laeses for sig. Kun 'Tabel N:' tæller - prosa naevner
# 'statsrenter'/'swaprenter' i flæng ('... mens swaprenter'), og et falsk klip
# midt i en tabel skærer vaerdierne fra deres etiketter.
TWOUP_RE = re.compile(r"[Tt]abel\s*\d\s*:")
TWOUP_X = 40


def _num(s: str) -> float | None:
    try:
        return round(float(s.replace(".", "").replace(",", ".")), 3)
    except ValueError:
        return None


def _area_of(text: str) -> str | None:
    """Find omraadet ud fra en (evt. brevspaerret) overskriftstekst."""
    sq = re.sub(r"\s+", "", text).lower()
    for pat, key in AREAS:
        if re.search(pat, sq):
            return key
    return None


def _qdate(m: re.Match) -> str:
    """'Q 3-17' -> '2017-09-30' (sidste dag i kvartalets sidste maaned)."""
    q, y = int(m.group(1)), 2000 + int(m.group(2))
    month = q * 3
    return f"{y}-{month:02d}-{calendar.monthrange(y, month)[1]:02d}"


def _anchor_row(line: str) -> list[tuple[int, int, str, str | None]]:
    """Kolonnedefinition fra en tabeloverskrift: (x0, x1, art, maaldato)."""
    items: list[tuple[int, int, str, str | None]] = []
    for m in SPOT_RE.finditer(line):
        items.append((m.start(), m.end(), "spot", None))
    for m in QRE.finditer(line):
        items.append((m.start(), m.end(), "q", _qdate(m)))
    for m in CHG_RE.finditer(line):
        items.append((m.start(), m.end(), "chg", None))
    items.sort()
    return items


def _match_row(label: str) -> str | None:
    for pat, key in ROWS:
        if re.search(rf"(?:^|\s)(?:{pat})\s*$", label):
            return key
    return None


def _effective_lines(text: str) -> list[str]:
    """Klip to-spaltede sider op, saa hver spalte laeses for sig.

    November og december 2020 er landskabssider, hvor boligrentetabellen
    ("Tabel 1: Jyske Bank Boligrenteprognose") staar i venstre spalte og
    markedsrentetabellerne i hoejre. pdftotext lægger begge spalter paa samme
    linje, saa en raekke som 'RTL5 ... -0,27 -0,25  Leading -0,60 ...' ellers
    ville blive laest som én raekke med forkert etiket.

    Begge halvdele beholdes: markedstabel-parseren genkender ikke RTL-etiketter
    og springer dem over, og boligrentetabellen ligger i november 2020 i den
    *venstre* halvdel, som derfor ikke maa kastes vaek.
    """
    out: list[str] = []
    for page in text.split("\f"):
        lines = page.splitlines()
        split: int | None = None
        for ln in lines:
            for m in TWOUP_RE.finditer(ln):
                # Kun naar der staar noget til venstre for titlen: en centreret
                # enkelttitel er ikke en to-spaltet side.
                if m.start() >= TWOUP_X and ln[:m.start()].strip():
                    split = m.start() if split is None else min(split, m.start())
        for ln in lines:
            if not split:
                out.append(ln)
                continue
            out.append(ln[:split])
            out.append(ln[split:])
    return out


def _cells(line: str, table: dict,
           warn: list[str]) -> tuple[float | None, list[float | None]]:
    """Laes Spot- og kvartalsvaerdier ud fra deres x-position.

    To strategier, fordi udgaverne er indbyrdes forskellige:

    1. **Rækkefølge.** Tabeller uden 'chg.'-kolonner har praecis én vaerdi pr.
       kolonne, og naar antallet passer, laeses de i raekkefoelge. Det er
       noedvendigt, fordi overskriftsraekken i flere udgaver er komprimeret i
       forhold til talsøjlerne (fx 2024-2026), saa en positionslaesning ville
       forskyde hver enkelt vaerdi et felt mod højre.
    2. **Position.** Tabeller med 'chg.'-kolonner (fx januar 2020) har blanke
       celler, saa raekkefølgen alene kan ikke afgøre hvilken kolonne et tal
       hoerer til; her bruges x-positionen. Er der set en komplet raekke i
       tabellen, bruges dens kolonnepositioner som facit for de ukomplette
       rækker - ellers overskriftens.
    """
    anchors = table["anchors"]
    value_idx = [i for i, a in enumerate(anchors) if a[2] != "chg"]
    has_chg = len(value_idx) != len(anchors)
    nums = [(m.start(), m.end(), _num(m.group(0)))
            for m in NUM_RE.finditer(line)]

    values: dict[int, float | None]
    if not has_chg and len(nums) == len(value_idx):
        values = {i: v for i, (_s, _e, v) in zip(value_idx, nums)}
        # Komplet raekke: husk kolonnernes faktiske x-positioner.
        table["x"] = [(s + e) // 2 for s, e, _v in nums]
    else:
        xs = table.get("x") or [(a[0] + a[1]) // 2 for a in anchors]
        values = {}
        for s, e, v in nums:
            centre = (s + e) // 2
            i = min(range(len(xs)), key=lambda j: abs(xs[j] - centre))
            if i in values:
                warn.append(f"flere tal i samme kolonne: {line.strip()[:70]!r}")
            else:
                values[i] = v

    spot: float | None = None
    quarters: list[float | None] = []
    for i, (_x0, _x1, kind, _tgt) in enumerate(anchors):
        if kind == "spot":
            spot = values.get(i)
        elif kind == "q":
            quarters.append(values.get(i))
    return spot, quarters


def _reset_date(pub: str, month: int) -> str:
    """Refinansieringsdatoen 'Pr. 1. <maaned>' som ISO-dato.

    Datoen ligger i publiceringsaaret, medmindre maaneden allerede er passeret
    (notatet udkommer efter selve tilpasningen), og hoerer saa til naeste aar.
    """
    year = int(pub[:4])
    if month <= int(pub[5:7]):
        year += 1
    return f"{year}-{month:02d}-01"


def _bolig_anchors(line: str,
                   pub: str) -> list[tuple[int, int, str, str | None]]:
    """Kolonnedefinition for boligrentetabellen: 'I dag' plus reset-datoer."""
    items: list[tuple[int, int, str, str | None]] = []
    for m in IDAG_RE.finditer(line):
        items.append((m.start(), m.end(), "spot", None))
    for m in PRA_RE.finditer(line):
        month = MONTHS.get(re.sub(r"\s+", "", m.group(1)).lower())
        if month is None:
            return []          # ukendt maaned: kolonnerne kan ikke stedfaestes
        items.append((m.start(), m.end(), "q", _reset_date(pub, month)))
    items.sort()
    if not any(a[2] == "q" for a in items):
        return []
    return items


def _match_bolig_row(label: str) -> str | None:
    for pat, key in BOLIG_ROWS:
        if re.search(rf"(?:^|\s)(?:{pat})\s*$", label):
            return key
    return None


def _parse_boligrente(lines: list[str], pub: str,
                      warn: list[str]) -> tuple[dict, list[str]]:
    """Parse 'Tabel 1: Jyske Bank Boligrenteprognose'.

    Returnerer (raekker, maaldatoer). Tabellen findes ikke i alle udgaver - den
    blev droppet i loebet af 2024 - og den ligger i nogle udgaver i venstre
    spalte af en to-spaltet side (se _effective_lines).
    """
    rows: dict[str, dict] = {}
    targets: list[str] = []
    for i, ln in enumerate(lines):
        if BOLIG_START not in ln.lower():
            continue
        table = None
        for j in range(i, min(len(lines), i + 6)):
            anchors = _bolig_anchors(lines[j], pub)
            if anchors:
                table = {"anchors": anchors, "x": None,
                         "targets": [a[3] for a in anchors if a[2] == "q"]}
                start = j
                break
        if table is None:
            warn.append(f"boligrentetabel uden laesbar overskrift ({pub})")
            continue
        for ln2 in lines[start + 1:start + 14]:
            s = re.sub(r"[ \t]+", " ", ln2).strip()
            if not s:
                continue
            m = NUM_RE.search(ln2)
            if not m:
                continue
            label = re.sub(r"[^a-zæøå0-9.\-\s]", " ", ln2[:m.start()].lower())
            label = re.sub(r"\s+", " ", label).strip()
            if not label or any(re.match(p, label) for p in BOLIG_IGNORE):
                continue
            key = _match_bolig_row(label)
            if key is None:
                continue
            spot, quarters = _cells(ln2, table, warn)
            if not any(q is not None for q in quarters):
                continue
            rows[key] = {"name": key, "aktuelt": spot,
                         "forecasts": quarters,
                         "targets": table["targets"][:len(quarters)]}
        targets = table["targets"]
        break               # hoejst én boligrentetabel pr. notat
    return rows, targets


def parse_text(text: str, source: str, capture_ts: str | None,
               pub_date: str, fallback_date: str) -> dict | None:
    """Parse alle prognosetabeller i notatet."""
    lines = _effective_lines(text)
    # Tabeltitlen er det sikre anker. Prosaen naevner 'statsrenter' flere sider
    # foer tabellen, saa sektionsoverskrifter bruges kun som reserve.
    start = None
    for i, ln in enumerate(lines):
        if TABEL_START in ln.lower():
            start = i
            break
    if start is None:
        for i, ln in enumerate(lines):
            low = ln.lower()
            if any(a in low for a in TABEL_ALT):
                start = i
                break
    if start is None:
        return None

    warn: list[str] = []
    rows: dict[str, dict] = {}
    tables: list[dict] = []
    cur: dict | None = None
    pending_area: str | None = None
    blanks = 0
    for ln in lines[start + 1:start + 700]:
        s = re.sub(r"[ \t]+", " ", ln).strip()
        if not s:
            blanks += 1
            if blanks >= 8 and tables:
                break
            continue
        blanks = 0
        if STOP_RE.search(s):
            break
        # Ny tabelblok ('STATSRENTER' / 'SWAPRENTER' / 'STATS- OG SWAPRENTER')
        if TITLE_ONLY.match(s):
            continue
        # Kolonneoverskrift: mindst tre kvartaler paa samme linje
        qm = list(QRE.finditer(ln))
        if len(qm) >= 3:
            area = _area_of(ln[:qm[0].start()]) or pending_area
            cur = {"area": area, "anchors": _anchor_row(ln), "x": None,
                   "targets": [_qdate(m) for m in qm], "rows": {}}
            tables.append(cur)
            continue
        # Omraade som selvstaendig overskrift
        area = _area_of(s)
        if area and len(re.sub(r"\s+", "", s)) <= len("eurolandspot"):
            pending_area = area
            if cur is not None and cur["area"] is None:
                cur["area"] = area
            continue
        if cur is None:
            continue
        # Datarække: etiketten er teksten foer det foerste decimaltal
        m = NUM_RE.search(ln)
        if not m:
            continue
        label = re.sub(r"[^a-zæøå0-9.\-\s]", " ", ln[:m.start()].lower())
        label = re.sub(r"\s+", " ", label).strip()
        if not label or any(re.match(p, label) for p in IGNORE):
            continue
        prod = _match_row(label)
        if prod is None:
            continue
        spot, quarters = _cells(ln, cur, warn)
        if not any(q is not None for q in quarters):
            continue
        # Kun Nationalbankens rente er landespecifik; de oevrige serier har
        # kanoniske noegler for Danmark, mens Eurozonen og USA faar suffix, saa
        # de ikke overskriver de danske vaerdier.
        if prod == "leading_dk":
            area_key = cur["area"] or "dk"
            key = f"leading_{area_key}"
        elif cur["area"] in (None, "dk"):
            key = prod
        else:
            key = f"{prod}_{cur['area']}"
        row = {"name": key, "aktuelt": spot, "forecasts": quarters,
               "targets": cur["targets"][:len(quarters)]}
        cur["rows"][key] = row
        rows[key] = row

    # Bankens egne boligrenter ("Tabel 1: Jyske Bank Boligrenteprognose") staar
    # i samme notat. De gemmes under rtl*-noegler, fordi de ikke er samme
    # rentebegreb som bankens 'Jyske Rentetilpasning F1/F3/F5' fra
    # Boliglånsanbefalingen (ca. 0,5 pp forskel ved faelles datoer).
    bolig, bolig_targets = _parse_boligrente(lines, pub_date, warn)
    rows.update(bolig)

    if not rows:
        return None

    # Snapshot-niveauets måldatoer: den tabel der dækker flest kolonner.
    # Rækkerne har deres egne måldatoer, så tabeller med forskellige kolonner
    # ikke forskyder hinanden.
    widest = max((t for t in tables if t["rows"]),
                 key=lambda t: len(t["targets"]), default=None)
    if widest is None and not bolig:
        return None
    snap_targets = widest["targets"] if widest is not None else list(bolig_targets)
    if bolig and len(bolig_targets) > len(snap_targets):
        snap_targets = list(bolig_targets)

    if warn:
        for w in warn[:3]:
            print(f"[jyske] ADVARSEL: {w}")

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        # 'Spot'-kolonnen er observeret paa publiceringsdagen, saa
        # observationsdatoen ER publiceringsdatoen. Uden dette arver alle
        # snapshots den fallback-dato backfill'en sender, og facit-serien
        # kollapser til én dato.
        "obs_date": pub_date,
        "pub_date": pub_date,
        "recalc_date": None,
        "targets": snap_targets,
        "rows": rows,
        "raw_rows": {k: [v["aktuelt"]] + v["forecasts"]
                     for k, v in rows.items()},
        "kind": "markedsrenter" if widest is not None else "boligrenter",
    }


def _text_via_pdftotext(pdf_bytes: bytes) -> str | None:
    """pdftotext haandterer de roterede tabeller, hvor pdfplumber blander
    tegnrækkefølgen. Returnerer None hvis værktøjet ikke findes."""
    import shutil
    import subprocess
    import tempfile

    exe = shutil.which("pdftotext")
    if not exe:
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(pdf_bytes)
        path = fh.name
    try:
        r = subprocess.run([exe, "-layout", path, "-"],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8", "replace")
    except Exception:
        return None
    finally:
        try:
            import os
            os.unlink(path)
        except OSError:
            pass


def _text_via_pdfplumber(pdf_bytes: bytes) -> str | None:
    try:
        import io

        import pdfplumber
    except ImportError:
        # pdfplumber er kun en reserve, naar pdftotext mangler eller fejler.
        return None
    parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text(layout=True) or "")
    return "\n".join(parts)


def _pub_date(text: str, fallback: str) -> str:
    # Dagen kan mangle foranstillet nul ('4.12.2025')
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return fallback


def parse_pdf_bytes(pdf_bytes: bytes, source: str, capture_ts: str | None,
                    fallback_date: str) -> dict | None:
    """Proev begge tekstudtraek og brug det der giver en tabel.

    Rækkefølgen betyder noget: pdftotext læser de roterede tabeller i
    2024-2026-udgaverne korrekt, mens pdfplumber er bedst til de ældre.
    """
    for getter in (_text_via_pdftotext, _text_via_pdfplumber):
        text = getter(pdf_bytes)
        if not text:
            continue
        snap = parse_text(text, source, capture_ts, _pub_date(text, fallback_date),
                          fallback_date)
        if snap is not None:
            return snap
    return None


def fetch_and_parse(url: str, source: str = "renteprognose",
                    capture_ts: str | None = None,
                    fallback_date: str | None = None) -> dict | None:
    import requests
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        return None
    return parse_pdf_bytes(r.content, source, capture_ts,
                           fallback_date or dt.date.today().isoformat())
