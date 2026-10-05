# Renteprognose-tjekket

Hvor præcise er bankernes renteprognoser? Dette projekt tracker **hver prognose
siden 2011** (Nykredit siden 2019, seks banker i alt) og sammenligner den med det
renteniveau, der faktisk indtraf – visualiseret som et dashboard med
prognose-vs-facit-grafer, fejl-over-tid, horisont-analyse og et scoreboard
pr. lånetype.

Siden er statisk (HTML/CSS/JS + Chart.js) og hostes gratis på
**GitHub Pages**. Data opdateres automatisk hver mandag via
**GitHub Actions**.

## Resultat (oktober 2026)

- Gennemsnitlig fejl: **+0,25 procentpoint** (positiv = renten blev højere end spået)
- **70 %** af alle prognoser var for optimistiske
- Historie: 41 snapshots, 898 prognoser med facit (Nykredit fra 2019-07-23)
- Største fejlskud: Fast 30 år, jan. 2022 → okt. 2022 (spået 1,74 %, facit 5,52 %)

Samlet for alle seks banker: 3 578 prognoser, 2 661 med facit, spredt fra 2011
til i dag.

## Projektstruktur

| Sti | Indhold |
|---|---|
| `index.html`, `css/`, `js/` | Den statiske hjemmeside (dansk UI) |
| `scraper/scrape.py` | Orkestrering: live-scrape + Wayback-backfill pr. bank |
| `scraper/banks/*.py` | Parser-plugins pr. bank (nykredit, nordea, sydbank, jyske, rd) + ekstraserier: `sydbank_pdf` (månedlige renteforventnings-PDF'er), `nordea_auktion` (auktionsprognoser), `sydbank_refin` (refinansieringsartikler) |
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
Historikken (2011–2026) er genskabt fra Wayback Machine; fremadrettet scrapes
live-siden ugentligt. Se "Metode & data" på selve siden for forbehold.

To særlige regler:

- **Dubletter**: flere arkiverede optagelser af *samme* prognose (samme
  publiceringsdato og samme tal) tælles én gang – ellers ville en side, der
  blev arkiveret 96 gange i 2019, veje 96 gange tungere. Ved dublet beholdes
  den seneste optagelse, fordi den har det friskeste `Aktuelt`-niveau.
- **RD's facit**: publiceres kun 1. januar og 1. april, så der interpoleres
  lineært mellem observationerne (`RD_MAX_GAP_DAYS = 140`). Afstanden fra
  måldatoen til nærmeste observation gemmes i hvert punkt som `gap_days`.

## Dækning pr. bank

Backfill via Wayback (`--since`, default 2015). Bankernes `ALT_URLS` dækker
ældre og spejlede udgaver af den samme prognosetabel:

| Bank | Første prognose | Snapshots (unikke) | Kilder |
|---|---|---|---|
| Realkredit Danmark | 2012-01-21 | 68 | gammel SharePoint-side (2012–2021) + nuværende side + erhvervsspejl |
| Sydbank | 2011-07-10 | 35 | gammel renteforventningsside (2011–2019) + nuværende renteside + månedlige renteforventnings-PDF'er (2022–) + refinansieringsartikler |
| Nordea | 2019-05-16 | 45 | hovedtabel + auktionsprognoser (nordea.com, 3 stk/år) |
| Nykredit | 2019-07-23 | 41 | 3 ældre captures (2018–2019) har intet parsebart bord |
| Sparekassen Kronjylland | 2022-11-11 | 22 | + spejlesiderne `/da/`, lommepenge, kron (alle captures, `--full`) |
| Jyske Bank | 2024-06-18 | 8 | første capture (2024-02) uden prognosetabel |

Jyske Bank er det eneste hul: Wayback har kun 5 optagelser af
boligsiden (første med tabel juni 2024), og der findes ingen ældre
Jyske-boligprognosetabel – heller ikke under tidligere URL-strukturer.
Jyske Markets' månedlige renteprognose-PDF'er (findes fra ca. 2015) dækker
kun makro-/swaprenter, ikke F1/F3/F5-boligrenter, og er derfor ikke taget
med. Sparkron før november 2022 findes kun som prosatekst
("månedsprognoser" 2012ff. uden rentetabel).

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
python scraper/scrape.py backfill            # genhent historik fra Wayback (springer eksisterende over)
python scraper/scrape.py backfill nordea --since 2012   # dybere historik for én bank
python scraper/scrape.py backfill sparkron --full       # ALLE captures (uden digest-collapse)
python scraper/backfill_sydbank_pdf.py   # Sydbanks månedlige renteforventnings-PDF'er
python scraper/backfill_nordea_auktion.py  # Nordeas auktionsprognoser (via sitemap)
python scraper/backfill_sydbank_refin.py   # Sydbanks refinansieringsartikler (live + Wayback)
python scraper/validate.py          # udskriv metrics + spot-tjek
python scraper/validate_banks.py    # pub/capture-anomalier + metrics pr. bank
```

## Udgiv på GitHub Pages

1. Omdøb branchen til `main` og opret + push repoet (kræver `gh`, GitHub CLI,
   og at du er logget ind med `gh auth login`):
   ```powershell
   git branch -M main
   gh repo create renteprognose-tjekket --public --source=. --push
   ```
   Alternativt uden `gh`: opret et tomt repo på github.com, og kør
   `git remote add origin https://github.com/DIT-BRUGERNAVN/REPO.git`
   efterfulgt af `git push -u origin main`.
3. På GitHub: **Settings → Pages → Deploy from a branch → `main` / `/ (root)`**.
4. Siden er live på `https://DIT-BRUGERNAVN.github.io/REPO/` efter få minutter.
5. Auto-opdateringen kører af sig selv hver mandag (kan også startes manuelt under
   **Actions → Opdater renteprognose-data → Run workflow**).

## Disclaimer

Uafhængigt hobbyprojekt uden tilknytning til Nykredit. Datakilde: nykredit.dk
(egen scraping til researchbrug) + Internet Archive. Intet på siden er
investerings- eller lånerådgivning.
