"""Sparekassen Kronjyllands renteprognoser i Investeringsmagasinet (PDF).

Magasinet indeholder hvert kvartal en blok market RENTEPROGNOSE med:

    Aktuel 21. marts        +3 m        +12 m
    Cibor 3M                 -0,32 %     -0,30 %     -0,10 %
    Statsobligation, 2 års løbetid   -0,60 %  -0,45 %  -0,30 %
    Statsobligation, 10 års løbetid   0,13 %   0,33 %   0,57 %
    Boliglån
    F-kort                   -0,22 %     -0,20 %     -0,10 %
    F5                        0,03 %      0,35 %      0,45 %
    Fastrente 30-årig         1,83 %      2,05 %      2,25 %
    Kurs på 30-årig fastrente 2 % m. afdrag  102,25  99,55  97,00

Det er samme type data som den nuværende HTML-side, men rækkerne er et
undertal: der er ingen F1/F3/Cita3, og horisonterne er +3 m og +12 m (siden
skiftede til +6 m i 2022). PDF'erne er to-spaltede, saa tabellen isoleres
geometrisk paa x-koordinaten frem for at læse hele sideteksten.

Serien daekker juli 2017 - marts 2019 (6 udgaver, alle live). Derefter
stoppede magasinet; hullet 2020-02 .. 2022-11 er ikke daekket af nogen
kendt kilde.
"""
from __future__ import annotations

import io
import re

from common import add_months, obs_date_for

BANK_ID = "sparkron"

# Verificerede udgaver (HTTP 200, application/pdf). Stien er stabil, saa nye
# udgaver kan tilfoejes her; magasinet udkom ca. 2-3 gange om aaret.
MAGAZINE_URL = ("https://www.sparkron.dk/-/media/sparekassenkronjylland/"
                "pdf-filer/investeringsmagasiner/a4_investmag_{month}.pdf")

MAGAZINE_MONTHS = [
    ("juli2017", "2017-07-14"),
    ("oktober2017", "2017-10-26"),
    ("januar2018", "2018-01-30"),
    ("maj2018", "2018-05-04"),
    ("december2018", "2018-12-20"),
    ("marts2019", "2019-03-21"),
]

# (moenster i raekkelabel, kanonisk produktnoegle). Raekkefoelgen er vigtig:
# 'Fastrente' maa ikke fanges af F-reglerne, og kurslinjen skal ignoreres.
ROW_PRODUCTS = [
    (r"^cibor\s*3\s*m", "cibor3"),
    (r"^f\s*[-]?\s*kort", "fkort"),
    (r"^f\s*5\b", "f5"),
    (r"^fastrente\s*30", "fast30"),
]
IGNORE_ROWS = (r"^statsobligation", r"^kurs", r"^der\s+er\s+tale")

# Horisonter som kolonneoverskrifterne angiver.
HORIZONS = [3, 12]

# Tabellen ligger i hoejre spalte; alt til venstre er prosa.
TABLE_MIN_X = 225.0

# Afslutter tabelblokken.
STOP_MARKERS = ("der er tale om", "taget højde for", "kursskæring")


def _words_via_pdfplumber(pdf_bytes: bytes) -> list[list[dict]] | None:
    try:
        import pdfplumber
    except ImportError:
        return None
    pages: list[list[dict]] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_words())
    return pages


def _rate(text: str) -> float | None:
    t = (text or "").replace("\u00ad", "-").replace("\u00a0", " ")
    # Soft hyphen bruges som minus for negative tal i disse PDF'er
    t = t.replace("−", "-")
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", t)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", ".")), 3)
    except ValueError:
        return None


def _header_date(text: str, fallback_year: int) -> tuple[str | None, int, int]:
    """'Aktuel 21. marts' / 'Aktuel 14. juli 2017' -> (ISO-dato, dag, maaned).

    Aeldre udgaver skriver ikke aarstal i tabellen, saa aaret udledes af
    udgavens forventede dato (naermeste aar).
    """
    m = re.search(r"Aktuel\s+(\d{1,2})\.?\s*([a-zæøå]{3,})(?:\.)?\s*,?\s*(\d{4})?",
                  text, re.IGNORECASE)
    if not m:
        return None, 0, 0
    months = {
        "januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6,
        "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11,
        "december": 12,
        # Forkortelser, som de staar i tabellens header ('26. okt. 2017')
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
        "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
    }
    day = int(m.group(1))
    mo = months.get(m.group(2).lower())
    if mo is None:
        return None, 0, 0
    if m.group(3):
        year = int(m.group(3))
    else:
        year = fallback_year
        if mo - 11 > 0:      # udgaven hoerer til aaret foer
            year -= 1
    try:
        return f"{year}-{mo:02d}-{day:02d}", day, mo
    except ValueError:
        return None, 0, 0


def _words_to_lines(words: list[dict]) -> list[tuple[float, list[dict]]]:
    """Gruppér ord i visuelle linjer sorteret efter top-position."""
    by_top: dict[float, list[dict]] = {}
    for w in words:
        by_top.setdefault(round(w["top"] / 3.0), []).append(w)
    lines = []
    for bucket in sorted(by_top):
        line = sorted(by_top[bucket], key=lambda w: w["x0"])
        lines.append((min(w["top"] for w in line), line))
    return lines


def _rate_token(text: str) -> float | None:
    """Tal fra en PDF-token. Bloedt bindetegn (u00ad) betyder minus her."""
    t = (text or "").replace("\u00ad", "-").replace("\u2212", "-")
    t = t.replace("\u00a0", " ")
    if not re.search(r"\d", t):
        return None
    m = re.search(r"(-?\d+(?:[.,]\d+)?)", t)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", ".")), 3)
    except ValueError:
        return None


def _value_groups(line: list[dict]) -> list[tuple[float, float]]:
    """Find (x, vaerdi) for hvert rentetal i en tabelraekke.

    Tallene skrives enten som '0,35' efterfulgt af '%' i sin egen token
    (2017-udgaverne) eller som '0,35%' i én token (2019-udgaven). Vi bruger
    hoejre kant som position, saa begge former giver samme kolonneanker.

    Kravet om decimal eller '%' i token er vigtigt: ellers bliver
    produktbetegnelser som 'Cibor 3M' og 'F5' laest som tal.
    """
    out: list[tuple[float, float]] = []
    for w in line:
        tok = w["text"].strip()
        if tok == "%" or not ("," in tok or "." in tok or "%" in tok):
            continue
        v = _rate_token(tok)
        if v is None:
            continue
        out.append((w["x1"], v))
    return out


def _calibrate_columns(value_lines: list[list[tuple[float, float]]]) -> list[float]:
    """Find x-centrene for tabelkolonnerne ud fra datarraekkerne.

    Header-teksten ('+3 m' / '+12 m') staar ikke noedvendigvis over selve
    talvaerdierne, saa vi klynger vaerdipositionerne i stedet og forventer
    praecis tre klynger (Aktuel, +3 m, +12 m).
    """
    xs = sorted(x for vals in value_lines for x, _ in vals)
    if len(xs) < 3:
        return []
    groups: list[list[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - groups[-1][-1] <= 12:
            groups[-1].append(x)
        else:
            groups.append([x])
    # Slaa smaaklynger sammen med naermeste nabo indtil vi har tre
    while len(groups) > 3:
        gaps = [(groups[i + 1][0] - groups[i][-1], i) for i in range(len(groups) - 1)]
        _, i = min(gaps)
        groups[i] += groups.pop(i + 1)
    if len(groups) != 3:
        return []
    return [sum(g) / len(g) for g in groups]


def _rows_from_words(words: list[dict], fallback_date: str
                     ) -> tuple[str | None, dict[str, list[float]], int, int]:
    """Returner (pub_date, {produkt: [aktuelt, +3m, +12m]}, dag, maaned)."""
    right = [w for w in words if w["x0"] >= TABLE_MIN_X]
    if not right:
        return None, {}, 0, 0
    fallback_year = int(fallback_date[:4])

    lines = _words_to_lines(right)

    # Tabelhovedet er den linje hvor 'Aktuel <dag>. <maaned>' staar sammen med
    # '+3' / '+12' kolonneoverskrifter.
    head_i = None
    pub = None
    day = mo = 0
    for i, (_top, line) in enumerate(lines):
        text = " ".join(w["text"] for w in line).replace("\u00ad", "")
        if "aktuel" in text.lower() and re.search(r"\+\s*3", text):
            pub, day, mo = _header_date(text, fallback_year)
            if pub:
                head_i = i
                break
    if head_i is None or pub is None:
        return None, {}, 0, 0

    # Saml vaerdilinjer. Prosa kan ligge imellem tabelraekkerne (magasinet
    # saetter to spalter om kap), saa vi springer prosa over i stedet for at
    # afslutte - men giver op efter nok prosa i traek.
    value_lines: list[tuple[float, list[dict]]] = []
    gap = 0
    for top, line in lines[head_i + 1:]:
        text = " ".join(w["text"] for w in line).lower()
        if any(s in text for s in STOP_MARKERS):
            break
        if _value_groups(line):
            gap = 0
            value_lines.append((top, line))
            continue
        gap += 1
        if gap > 8:
            break

    # Kun raekker med tre vaerdier hoerer til tabelkernen
    core = [vals for _t, line in value_lines
            if len(vals := _value_groups(line)) == 3]
    if len(core) < 2:
        return None, {}, 0, 0
    col_x = _calibrate_columns(core)
    if len(col_x) != 3:
        return None, {}, 0, 0

    out: dict[str, list[float]] = {}
    for _top, line in value_lines:
        vals = _value_groups(line)
        if len(vals) != 3:
            continue
        # Prosa kan dele visuel linje med tabelraekken (fx '... december
        # Fastrente 30-aarig 2,13% ...'). Vi tager derfor kun teksten lige til
        # venstre for det foerste tal - dér staar produktnavnet.
        first_x = min(x for x, _ in vals)
        # Number-tokens har deres egen gruppe; de maa ikke regnes som label.
        value_ids = {id(w) for w in line if w["x1"] in {x for x, _ in vals}}
        left = [w for w in line
                if id(w) not in value_ids and w["x1"] <= first_x + 2]
        # Naar prosa deler linje med tabellen, ligger der et stort hul mellem
        # prosaen og selve produktnavnet. Vi gaar derfor fra hoejre mod
        # venstre og stopper ved det foerste store hul.
        # Naermeste ord til venstre for tallet er altid en del af labelen;
        # derefter udvides mod venstre saa laenge ordene haenger sammen.
        label_parts: list[str] = []
        prev_x = first_x
        for w in reversed(left):
            if label_parts and prev_x - w["x1"] > 20:
                break
            label_parts.append(w["text"])
            prev_x = w["x0"]
        label = " ".join(reversed(label_parts)).replace("\u00ad", " ").strip()
        low = label.lower()
        if any(re.match(p, low) for p in IGNORE_ROWS):
            continue
        key = None
        for pat, k in ROW_PRODUCTS:
            if re.match(pat, low):
                key = k
                break
        if key is None:
            continue
        order: dict[int, float] = {}
        for x, v in vals:
            i = min(range(3), key=lambda j: abs(col_x[j] - x))
            order[i] = v
        if len(order) != 3:
            continue
        aktuelt = order[0]
        out[key] = [aktuelt, order[1], order[2]]
    return pub, out, day, mo


def parse_pdf(pdf_bytes: bytes, source: str, capture_ts: str | None,
              fallback_date: str) -> dict | None:
    pages = _words_via_pdfplumber(pdf_bytes)
    if pages is None:
        return None

    pub, rows, day, mo = None, {}, 0, 0
    for words in pages:
        p, r, d, m = _rows_from_words(words, fallback_date)
        if r:
            pub, rows, day, mo = p, r, d, m
            break
    if not rows or pub is None:
        return None
    # Horisonterne regnes fra tabellens egen dato (fx '21. marts'), ikke fra
    # PDF'ens oprettelsesdato - de kan ligge nogle dage fra hinanden.
    base = f"{pub[:4]}-{mo:02d}-{day:02d}" if day and mo else pub

    points: dict[str, dict] = {}
    for key, vals in rows.items():
        aktuelt, forecasts = vals[0], vals[1:]
        if len(forecasts) != len(HORIZONS):
            continue
        points[key] = {"name": key, "aktuelt": aktuelt, "forecasts": forecasts}

    if not points:
        return None

    return {
        "bank": BANK_ID,
        "source": source,
        "capture": capture_ts,
        "obs_date": obs_date_for(source, capture_ts, fallback_date),
        "pub_date": pub,
        "recalc_date": None,
        "targets": [add_months(base, h) for h in HORIZONS],
        "rows": points,
        "raw_rows": {k: [v["aktuelt"]] + v["forecasts"] for k, v in points.items()},
    }


def fetch_and_parse(url: str, source: str = "magazine",
                    capture_ts: str | None = None,
                    fallback_date: str | None = None) -> dict | None:
    """Hent og parse en magasin-PDF.

    fallback_date bruges til at udlede aarstal naar tabellens header kun skriver
    dag og maaned (2019-udgaven goer det). Giv altid udgavens forventede dato
    med - dagens dato giver et forkert aar for aeldre udgaver.
    """
    import datetime as dt

    import requests

    from common import UA
    r = requests.get(url, headers=UA, timeout=180)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        return None
    return parse_pdf(r.content, source, capture_ts,
                     fallback_date or dt.date.today().isoformat())
