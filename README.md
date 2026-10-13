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

Samlet for alle seks banker: 3 740 prognoser, 2 766 med facit, spredt fra 2011
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
| `scraper/banks/*.py` | Parser-plugins pr. bank (nykredit, nordea, sydbank, jyske, rd) + ekstraserier: `sydbank_pdf` (månedlige renteforventnings-PDF'er), `nordea_auktion` (auktionsprognoser), `sydbank_refin` (refinansieringsartikler), `sparkron_pdf` (Investeringsmagasinets renteprognosetabel 2017-2019), `sydbank_oversigt` (Økonomisk Oversigt 2020-2022), `jyske_pdf` (Boliglånsanbefalingens prognosetabel) |
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
| Sydbank | 2011-07-10 | 40 | 384 | gammel renteforventningsside (2011–2019) + nuværende renteside + "Økonomisk Oversigt"-PDF'er (2020–2022, `backfill_sydbank_oversigt.py`) + månedlige renteforventnings-PDF'er (2022–) + refinansieringsartikler |
| Nordea | 2019-05-16 | 45 | 1 044 | hovedtabel + auktionsprognoser (nordea.com, 3 stk/år) |
| Nykredit | 2019-07-23 | 41 | 720 | 3 ældre captures (2018–2019) har intet parsebart bord |
| Sparekassen Kronjylland | 2017-07-14 | 28 | 300 | Investeringsmagasinets `RENTEPROGNOSE`-tabel (2017–2019, `backfill_sparkron_pdf.py`) + nuværende renteside + spejlesiderne `/da/`, lommepenge, kron (alle captures, `--full`) |
| Jyske Bank | 2017-07-03 | 57 | 717 | kvartalsnotaterne "Boliglånsanbefaling" (2024-, tabel) og "Forventning til rentetilpasning" (2020-2023, grafer) + **markedsrente-prognoserne i "Renteprognose"** (2017-2026, `backfill_jyske_renteprognose.py`) med facit fra Danmarks Statistik (`fetch_facit.py`) og bankens egne Spot-kolonner + den nuværende HTML-side |

"Snapshots" er antallet af optagelser der overlever dublet-fjernelsen, og
"unikke prognoser" er antallet af (produkt, publiceringsdato, måldato)-punkter
i `dataset.json`. De rå filer i `data/**/snapshots/` er flere: fx ligger der
183 RD-filer, hvoraf langt de fleste er genarkiveringer af en uændret side.
`python scraper/validate_banks.py` viser fordelingen.

Jyske Banks hul er nu **lukket for markedsrenternes vedkommende** — og delvist
for boligrenternes. Bankens boligrenter (F1/F3/F5) findes i to slags notater,
som hver kraever sin parser:

- **Tabelformat (2024-)**: "Boliglånsanbefaling" med tabellen "Forventninger
  til realkreditrenten". Laeses af `banks/jyske_pdf.py` (pdfplumber).
- **Graf-format (2020-2023)**: "Forventning til rentetilpasning pr. 1.
  <måned>" med én figur pr. produkt, hvor prognosen staar som label over
  sojlen for den kommende refinansiering (`F1: 2023*`) ved siden af den
  *realiserede* rente fra den seneste (`F1: 2022`). Laeses af
  `banks/jyske_anbefaling.py`, som finder kolonnerne paa x-position praecis
  som tabel-parseren. Notaterne ligger ikke laengere paa jyskebank.dk (404) og
  hentes derfor fra Wayback via `backfill_jyske_forventning.py`.

Figurens realiserede rente er samme stoerrelse som tabelformatets foerste
raekke ("Lånerente pr. <dato>"), og backfill'en samler dem i
`data/banks/jyske/facit.json` **dateret paa refinansieringsdatoen** — ikke paa
notatets publiceringsdato. Den suppleres af Jyskes egne
**"Resultat af rentetilpasning pr. 1. <måned>"**-notater, som udsendes efter
hver auktion og oplyser den kontantlånsrente kunderne faktisk fik pr. produkt
(laest af `banks/jyske_resultat.py`). De to kilder krydstjekker hinanden: for
1. januar 2022 oplyser begge F1 = −0,22 %. Auktionsopgoerelserne bruges kun for
perioden **foer 2024-01-01**; derefter har banken egne observationer fra
HTML-siden og "Lånerente pr."-raekken, og de staar uaendret.

Det giver:

| Serie | Punkter | Med facit | MAE | Dækning (med facit) |
|---|---|---|---|---|
| `f1` | 41 | 23 | 0,40 | 2020-12 → 2026-04 |
| `f3` | 40 | 21 | 0,40 | 2021-12 → 2026-04 |
| `f5` | 41 | 22 | 0,35 | 2021-09 → 2026-04 |

`f1` er dermed løftet fra 2,3 til 5,3 aars historik, og `f3`/`f5` fra 2024 til
2021-2022. De nye punkter er de foerste der viser banken under rentechokket i
2022: for 1. april 2022 spåede Jyske F3 = −0,16 % og F5 = 0,10 %, mens
auktionsresultatet blev 0,51 % og 0,81 % (fejl +0,67 og +0,71 pp).

Enkelte maal mangler fortsat facit: 1. april 2021 og 1. januar/april 2023, hvor
arkivet hverken har et prognosenotat med realiserede labels eller en
auktionsopgoerelse. `f3` og `f5` har derfor 40-41 prognosepunkter, men kun
21-22 med facit.

Bankens **markedsrenteprognoser** ligger i et helt andet notat: det månedlige
"Renteprognose" fra Jyske Markets med tabellerne `STATSRENTER` og
`SWAPRENTER` (fra 2024 samlet i `STATS- OG SWAPRENTER`). Notatet er hentet
tilbage til **juli 2017**, og hver udgave oplyser både statsrenterne og **hele
swapkurven**: `swap2`, `swap5`, `swap10`, `swap30` for Danmark samt de afledte
hældninger (`SWAP 5y - 2y` osv., som ikke gemmes). Eurozonen og USA ligger
under samme nøgler med `_eu`/`_us`-suffix. Samme notat indeholder desuden
"Tabel 1: Jyske Bank Boligrenteprognose" (`rtl1`-`rtl10`, se nedenfor).

| Produkt | Med facit | MAE |
|---|---|---|
| `stat10` (10-årig statsobligation) | 200/210 | 0,69 |
| `cibor3` | 164/205 | 0,42 |
| `cibor6` | 128/180 | 0,59 |
| `swap2` / `swap5` / `swap10` / `swap30` (kun i snapshots) | 44/80, 44/80, 44/80, 37/70 | 0,27 / 0,31 / 0,36 / 0,35 |

`stat2`, `stat5`, `stat30`, `leading_dk` og hele swapkurven er parset og ligger
i de rå snapshots, men udgår af datasættet — se afsnittet om sammenlignelighed
nedenfor.

Facit kommer fra to kilder der supplerer hinanden:

1. **Danmarks Statistiks tabel MPK3** ("Rentesatser, ultimo"), hentet af
   `scraper/fetch_facit.py`. Månedlig tilbage til 1985 med *10 årig
   statsobligation*, *CIBOR 3 måneder* og *Nationalbankens udlånsrente*.
2. **Bankens egne Spot-kolonner.** Hver udgave oplyser det aktuelle niveau, og
   de værdier er observationer på publiceringsdagen. Med 47 udgaver giver det
   dækning for de løbetider MPK3 ikke har (`stat2`, `stat5`, `stat30`,
   `cibor6`) — og for `cibor3` efter MPK3's serie slutter.

Kilderne **flettes** i `build.py` frem for at erstatte hinanden. En ren
erstatning ville slette `cibor3`-dækningen, fordi MPK3's CIBOR-serie slutter i
august 2019 — før bankens første prognose.

Det gjorde også `stat10`, `cibor3` og `cibor6` **sammenlignelige på tværs af
banker**. Jyske møder Sydbank på statsrenten, og Nordea på begge CIBOR-løbetider.
Banken går fra 12 til 20 discipliner i mesterskabet.

### To fælder undervejs

**CIBOR-serien i DST's `DNRENTM` ser ud til at dække til 2024, men er død.**
Tabellen `MCI03M` har 420 observationer frem til 2024M07 — men de sidste 113 er
alle præcis `0.0`. Reelle data stopper i december 2013; derefter er der
pladsholdere. Havde de været brugt som facit, ville Jyskes CIBOR-prognoser se
katastrofalt dårlige ud (spået −0,4 mod "facit" 0,0) — en fuldstændig falsk
konklusion. Fælden blev fanget ved at sammenligne med bankens egne Spot-værdier.

**pdfplumber kan ikke læse de nyere udgaver.** Fra slutningen af 2024 er
prognosetabellerne roteret, og pdfplumbers tekstudtræk blander tegnrækkefølgen
(`'b e l 1 : J y s k e'`). `pdftotext` (poppler) håndterer layoutet korrekt, så
parseren prøver det først og falder tilbage til pdfplumber. CI installerer
`poppler-utils`.

Boligrenterne kan derimod godt kobles til markedsrenterne. Den tidligere
konklusion her i README ("banken spår kun om én løbetid pr. marked") var et
artefakt af parseren: `SWAPRENTER`-tabellen har hele kurven — 2y, 5y, 10y og
30y samt hældningerne imellem — men parseren matchede kun `STAT`-rækker og
stoppede desuden ved den næste tables kolonneoverskrift, så netop swaprækkerne
faldt ud.

Målt på de fælles observationer følger F5-kontantrenten `swap5` med et spænd på
**−0,22 til +0,15 pp** (middel −0,03, spredning 0,10 over ni parringer
2019–2025; Nykredits F5-facit mod Jyskes Spot-kolonne for swap 5y). Til
sammenligning ligger de målte prognosefejl på 0,26–0,79 pp, altså en
størrelsesorden over spændets variation. **SWAP 5y er dermed en brugbar proxy
for F5-niveauet**, mens SWAP 10y ikke er: forskellen mellem de to løbetider er
kurvens hældning, ikke et fast spread.

To forbehold: proxyen gælder den *markedsrente* F5-lånet refinansieres til —
ikke en kundes samlede rente, som også indeholder bidragssats og kursfradrag —
og spændet er kun målt i perioder med normal markedsfunktion. Under stress
(bankuroen i marts 2020, april 2025) udvides realkredit-/swapspændet, og netop
de episoder skriver banken selv om i notaterne.

### Bankens egne boligrenter i samme notat

"Renteprognose" indeholder også **"Tabel 1: Jyske Bank Boligrenteprognose"** med
bankens renter for rentetilpasningslån — etiketten skifter gennem årene
(`F1-rente`/`F5-rente` i 2017, `RTL1`-`RTL10` fra 2019). Kolonnerne er `I dag`
plus en-to refinansieringsdatoer (`Pr. 1. okt` / `Pr. 1.okt` / `Pr 1. ju li`),
og `_parse_boligrente` gemmer dem under **egne nøgler** `rtl1`, `rtl3`, `rtl5`,
`rtl10` — ikke under `f1`/`f3`/`f5`:

| Serie | Punkter | Med facit | MAE | Dækning |
|---|---|---|---|---|
| `rtl1` | 16 | 10 | 0,19 | 2019-01 → 2022-05 |
| `rtl3` | 15 | 11 | 0,27 | 2019-06 → 2024-06 |
| `rtl5` | 19 | 12 | 0,31 | 2019-01 → 2024-06 |
| `rtl10` | 15 | 11 | 0,29 | 2019-06 → 2024-06 |

De to tabeller måler ikke samme rentebegreb. Ved fælles datoer ligger `rtl5` tæt
på Nykredits F5-facit (middel +0,04, spredning 0,10, fire parringer), mens
bankens `f5` fra Boliglånsanbefalingen ligger 0,15 pp højere i middel med en
spredning på 0,20 og en enkelt afvigelse på 0,53 pp. `rtl5` er altså tættere på
den fælles F5-definition, men serien **stopper i 2024**, hvor notatet droppede
tabellen, og den må derfor ikke flettes ind i `f5`: de to serier ville give et
niveaubrud midt i 2024 og en facit-serie i to forskellige definitioner.
Februar- og apriludgaven 2025 har slet ingen boligrentetabel.

Bemærk at juninotatet 2019 (11.06.2019) *kun* har boligrentetabellen — det har
ingen `STATSRENTER`/`SWAPRENTER`, og snapshottet får derfor `kind` =
`boligrenter`. Det var tidligere det ene notat backfill'en meldte "ingen tabel"
på.

## Kun sammenlignelige produkter

Datasættet indeholder **kun produkter som mindst to banker kan måles på**. Ellers
peger den enkelte banks produktliste i sin egen retning, og tallene kan ikke
stilles op mod hinanden.

Kriteriet er ikke bare at flere banker *nævner* produktet, men at mindst to
banker har mindst tre evaluerede prognoser, så der faktisk kan dannes en celle.
`scraper/validate.py` håndhæver det: hvis et produkt ender med under to
dækkede banker, fejler gaten med en besked om hvilke banker der mangler.

Følgende er derfor holdt ude af datasættet (`EXCLUDED_PRODUCTS` i `build.py`),
men ligger stadig i de rå snapshots og kan flyttes tilbage uden at hente noget
forfra:

| Produkt | Grund |
|---|---|
| `fast30kupon`, `frihed`, `leading_dk`, `stat2`, `stat5`, `stat30`, `swap2`, `swap5`, `swap10`, `swap30` | oplyses kun af Jyske Bank |
| `fast20` | oplyses af Nykredit og Sydbank, men Sydbank har 1 prognose med facit mod Nykredits 100 |

Til gengæld blev `cita6` koblet på sammenligningen. Produktet var oplyst af
både Nykredit og Nordea, men havde aldrig været mappet, så det lå ubrugt hen.

Resultatet er ti kanoniske produkter — F1, F3, F5, F-kort, CITA3, CITA6, CIBOR3,
CIBOR6, Fast 30 år og 10-årig statsrente — hvor hver enkelt bank kun viser
produkter, som mindst én anden bank også oplyser.

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
python scraper/backfill_jyske_pdf.py     # Jyskes Boliglånsanbefaling (arkiv + nyeste udgave)
python scraper/backfill_jyske_renteprognose.py  # Jyske Markets' Renteprognose (2019-2024)
python scraper/fetch_facit.py            # facit for markedsrenter (Danmarks Statistik MPK3)
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
