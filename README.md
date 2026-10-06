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
- **67 %** af alle prognoser var for optimistiske
- Historie: 41 snapshots, 848 prognoser, 653 med facit (Nykredit fra 2019-07-23)
- Største fejlskud: Fast 30 år, jan. 2022 → okt. 2022 (spået 1,74 %, facit 5,52 %)

Samlet for alle seks banker: 3 383 prognoser, 2 469 med facit, spredt fra 2011
til i dag.

Tallene tæller **én prognose én gang**. Bankerne genudgiver jævnligt samme
prognosedato med et nyt `Aktuelt`-niveau, og uden dedup på (produkt,
publiceringsdato, måldato) ville fx Nykredits 848 prognoser blive til 1 100
punkter — og de prognoser, Wayback tilfældigt arkiverede flest gange, ville
veje tungest. Se "Dubletter" under Metode.

## Projektstruktur

| Sti | Indhold |
|---|---|
| `index.html`, `css/`, `js/` | Den statiske hjemmeside (dansk UI) |
| `scraper/scrape.py` | Orkestrering: live-scrape + Wayback-backfill pr. bank |
| `scraper/banks/*.py` | Parser-plugins pr. bank (nykredit, nordea, sydbank, jyske, rd) + ekstraserier: `sydbank_pdf` (månedlige renteforventnings-PDF'er), `nordea_auktion` (auktionsprognoser), `sydbank_refin` (refinansieringsartikler), `sparkron_pdf` (Investeringsmagasinets renteprognosetabel 2017-2019), `sydbank_oversigt` (Økonomisk Oversigt 2020-2022) |
| `scraper/common.py` | Fælles HTTP/parse/snapshot-hjælpere |
| `scraper/build.py` | Prognoser vs. facit pr. bank → `data/dataset.json` + `data/banks/*/dataset.json` |
| `scraper/compare.py` | Fællesmængde-rangering → `data/comparison.json` (mesterskab m.m.) |
| `scraper/validate.py` | Integritetschecks + metrics + spot-tjek. **Exit-kode 1** ved fejl; bruges som gate i CI |
| `scraper/validate_banks.py` | Pub/capture-anomalier pr. snapshot + metrics pr. bank. Exit-kode 1 ved fejl |
| `data/snapshots/` | Nykredit-snapshots (legacy-sti) |
| `data/banks/<bank>/snapshots/` | Snapshots pr. bank + `facit.json` (RD) |
| `.github/workflows/update.yml` | Ugentlig auto-opdatering (alle banker), med validering som gate før commit |

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

- **Dubletter**: samme prognose tælles én gang. Det gøres i to trin, fordi
  bankerne genudgiver samme publiceringsdato med ændret indhold:
  1. *Snapshot-niveau* ([build.py](scraper/build.py)): to optagelser med samme
     publiceringsdato og samme prognosticerede tal er samme prognose, også selv
     om `Aktuelt`-kolonnen er læst på forskellige dage. Den seneste optagelse
     beholdes, fordi den har det friskeste `Aktuelt`-niveau.
  2. *Punkt-niveau*: samme (produkt, publiceringsdato, måldato) kan stadig
     optræde i snapshots der adskiller sig på andre rækker. Punktet tælles én
     gang, og facit tages fra den nyeste optagelse.

  Uden trin 1+2 ville en side, der blev arkiveret 96 gange i 2019, veje 96
  gange tungere — og Nykredits tal ville være 23 % for høje.
- **RD's facit**: publiceres kun 1. januar og 1. april, så der interpoleres
  lineært mellem observationerne (`RD_MAX_GAP_DAYS = 140`). Afstanden fra
  måldatoen til nærmeste observation gemmes i hvert punkt som `gap_days`.

## Dækning pr. bank

Backfill via Wayback (`--since`, default 2015). Bankernes `ALT_URLS` dækker
ældre og spejlede udgaver af den samme prognosetabel:

| Bank | Første prognose | Snapshots | Unikke prognoser | Kilder |
|---|---|---|---|---|
| Realkredit Danmark | 2012-01-21 | 68 | 684 | gammel SharePoint-side (2012–2021) + nuværende side + erhvervsspejl |
| Sydbank | 2011-07-10 | 40 | 375 | gammel renteforventningsside (2011–2019) + nuværende renteside + "Økonomisk Oversigt"-PDF'er (2020–2022, `backfill_sydbank_oversigt.py`) + månedlige renteforventnings-PDF'er (2022–) + refinansieringsartikler |
| Nordea | 2019-05-16 | 45 | 1 044 | hovedtabel + auktionsprognoser (nordea.com, 3 stk/år) |
| Nykredit | 2019-07-23 | 41 | 848 | 3 ældre captures (2018–2019) har intet parsebart bord |
| Sparekassen Kronjylland | 2017-07-14 | 28 | 300 | Investeringsmagasinets `RENTEPROGNOSE`-tabel (2017–2019, `backfill_sparkron_pdf.py`) + nuværende renteside + spejlesiderne `/da/`, lommepenge, kron (alle captures, `--full`) |
| Jyske Bank | 2024-06-18 | 8 | 132 | første capture (2024-02) uden prognosetabel |

"Snapshots" er antallet af optagelser der overlever dublet-fjernelsen, og
"unikke prognoser" er antallet af (produkt, publiceringsdato, måldato)-punkter
i `dataset.json`. De rå filer i `data/**/snapshots/` er flere: fx ligger der
183 RD-filer, hvoraf langt de fleste er genarkiveringer af en uændret side.
`python scraper/validate_banks.py` viser fordelingen.

Jyske Bank er det største hul: Wayback har kun 8 optagelser af boligsiden
(første med tabel juni 2024). Jyske Realkredit udgiver ellers et kvartalsnotat,
"Boliglånsanbefaling", med en tabel "Forventninger til realkreditrenten"
(F1/F3/F5/fast 30 år på faste måldatoer) — formatet er verificeret og
parsebart, men **kilden er ikke tilgængelig**: de gamle
`/wps/wcm/connect/jfo/<uuid>/...pdf`-URL'er afvises af Jyskes WAF, Wayback har
mistet WARC-indholdet (CDX rapporterer stadig HTTP 200), og den stabile
`/pdf/qqcnz2ut/boliglaansanbefaling.pdf` giver i dag en *generel* anbefaling
uden tabel. Der er altså ingen aktiv Jyske-PDF-parser i repoet; den blev
skrevet, verificeret mod Q1 2024-udgaven (5 måldatoer × F1/F3/F5 = 15 nye
punkter) og fjernet igen, fordi kilden ikke kunne hentes. Skal den genoptages,
er tabellen i PDF'en på formen "Forventninger til realkreditrenten" med
kolonnerne F1/F3/F5/fast 30 år og rækker på formen `03-01-2024`, og
kolonnemappingen bør ske på x-koordinater (overskrifterne er skrevet over to
linjer). Jyske Markets' månedlige renteprognose-PDF'er dækker kun
makro-/swaprenter, ikke F1/F3/F5-boligrenter, og er derfor ikke taget med.

For Sparekassen Kronjylland gik historikken fra 2022-11-11 tilbage til
**2017-07-14** via Investeringsmagasinets renteprognosetabel (se
`scraper/banks/sparkron_pdf.py`). Den har kun F-kort, F5 og fast 30-årig, og
horisonterne er +3 og +12 måneder. Perioden **februar 2020 – november 2022** er
stadig et hul: magasinet stoppede efter januar 2020, og der findes ingen
arkiveret rentetabel i vinduet (hverken i magasinet, i cheføkonom-materialet
eller under ældre URL-stier).

Sydbanks hul **2020–2022** er derimod delvist lukket. Bankens månedlige
makroanalyse "Økonomisk Oversigt" indeholder en tabel *"Renteniveau i procent,
ultimo perioden"* med realiseret ultimoværdi plus prognoser for de to kommende
år (10-årig stat, 3 måneders Cibor, 30-årig realkreditrente). Fire udgaver er
arkiveret og hentet (maj 2020, marts 2021, juni 2021, marts 2022), hvilket giver
24 nye punkter — 17 med facit — i et vindue hvor Sydbank ellers var tom.
Udgaverne ligger på `markets.sydbank.dk/PublicationsWebHandler/Default.aspx?ID=…`
og er arkiveret som rigtige PDF'er. Bemærk at serien fra juni 2023 skiftede til
"3/6/12 mdr."-kolonner, hvor første kolonne er en horisont og ikke en realiseret
værdi; de udgaver udelades bevidst af parseren, da `Aktuelt` ellers ville blive
fejltolket.

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
python scraper/backfill_sparkron_pdf.py  # Sparkrons renteprognoser fra Investeringsmagasinet (2017-2019)
python scraper/backfill_sydbank_oversigt.py  # Sydbanks Økonomisk Oversigt (2020-2022)
python scraper/backfill_sydbank_pdf.py   # Sydbanks månedlige renteforventnings-PDF'er
python scraper/backfill_nordea_auktion.py  # Nordeas auktionsprognoser (via sitemap)
python scraper/backfill_sydbank_refin.py   # Sydbanks refinansieringsartikler (live + Wayback)
python scraper/validate.py          # integritetschecks + metrics (exit 1 ved fejl)
python scraper/validate_banks.py    # pub/capture-anomalier + metrics pr. bank
```

Valideringen er en **gate**: `validate_banks.py` kører før genbygningen og
`validate.py` efter, begge før commit i CI. Fejler de, committes der intet —
så et parserbrud eller et tavst scrape-nedbrud bliver ikke publiceret som data.
`validate.py` tjekker bl.a. at ingen prognose tælles to gange, at `meta`-tallene
stemmer med indholdet, at ingen fejl er absurd stor, og at den nyeste prognose
ikke er over 120 dage gammel.

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
