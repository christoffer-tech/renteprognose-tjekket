# Renteprognose-tjekket

Hvor præcise er Nykredits renteprognoser? Dette projekt tracker **hver prognose
siden 2020** og sammenligner den med det renteniveau, der faktisk indtraf –
visualiseret som et dashboard med prognose-vs-facit-grafer, fejl-over-tid,
horisont-analyse og et scoreboard pr. lånetype.

Siden er statisk (HTML/CSS/JS + Chart.js) og hostes gratis på
**GitHub Pages**. Data opdateres automatisk hver mandag via
**GitHub Actions**.

## Resultat (oktober 2026)

- Gennemsnitlig fejl: **+0,26 procentpoint** (positiv = renten blev højere end spået)
- **70 %** af alle prognoser var for optimistiske
- Største fejlskud: Fast 30 år, jan. 2022 → okt. 2022 (spået 1,74 %, facit 5,52 %)

## Projektstruktur

| Sti | Indhold |
|---|---|
| `index.html`, `css/`, `js/` | Den statiske hjemmeside (dansk UI) |
| `scraper/scrape.py` | Orkestrering: live-scrape + Wayback-backfill pr. bank |
| `scraper/banks/*.py` | Parser-plugins pr. bank (nykredit, nordea, sydbank, jyske, rd) |
| `scraper/common.py` | Fælles HTTP/parse/snapshot-hjælpere |
| `scraper/build.py` | Prognoser vs. facit pr. bank → `data/dataset.json` + `data/banks/*/dataset.json` |
| `scraper/compare.py` | Fællesmængde-rangering → `data/comparison.json` (mesterskab m.m.) |
| `scraper/validate.py`, `validate_banks.py` | Metrics + spot-tjek (køres manuelt) |
| `data/snapshots/` | Nykredit-snapshots (legacy-sti) |
| `data/banks/<bank>/snapshots/` | Snapshots pr. bank + `facit.json` (RD) |
| `.github/workflows/update.yml` | Ugentlig auto-opdatering (alle banker) |

Banker: Nykredit, Nordea, Sydbank, Jyske Bank, Realkredit Danmark,
Sparekassen Kronjylland.
Totalkredit er bevidst udeladt (ingen prognosetabel, kun prosatekst).

## Metode (kort)

Som *facit* bruges tabellens egen *Aktuelt*-kolonne fra det snapshot, hvis
observation ligger tættest på måldatoen (typisk få ugers afstand, maks. 60 dage).
Det sikrer identiske rentedefinitioner for prognose og facit. Fejl = facit −
prognose; positiv fejl = for optimistisk (set fra låntagers synspunkt).
Historikken (2020–2026) er genskabt fra Wayback Machine; fremadrettet scrapes
live-siden ugentligt. Se "Metode & data" på selve siden for forbehold.

## Kør lokalt

```powershell
# 1) (valgfrit) hent seneste prognoser + genbyg datasæt
pip install -r scraper/requirements.txt
python scraper/scrape.py update
python scraper/scrape.py facit-rd
python scraper/build.py all
python scraper/compare.py

# 2) servér siden (fetch af JSON virker ikke via file://)
python -m http.server --directory C:\sti\til\Renteprognose 8000
# åbn http://localhost:8000/
```

Nyttige kommandoer:

```powershell
python scraper/scrape.py backfill   # genhent historik fra Wayback (springer eksisterende over)
python scraper/validate.py          # udskriv metrics + spot-tjek
```

## Udgiv på GitHub Pages

1. Opret et nyt tomt repo på GitHub (fx `renteprognose-tjekket`).
2. Push projektet:
   ```powershell
   git remote add origin https://github.com/DIT-BRUGERNAVN/renteprognose-tjekket.git
   git push -u origin main
   ```
3. På GitHub: **Settings → Pages → Deploy from a branch → `main` / `/ (root)`**.
4. Siden er live på `https://DIT-BRUGERNAVN.github.io/renteprognose-tjekket/` efter få minutter.
5. Auto-opdateringen kører af sig selv hver mandag (kan også startes manuelt under
   **Actions → Opdater renteprognose-data → Run workflow**).

## Disclaimer

Uafhængigt hobbyprojekt uden tilknytning til Nykredit. Datakilde: nykredit.dk
(egen scraping til researchbrug) + Internet Archive. Intet på siden er
investerings- eller lånerådgivning.
