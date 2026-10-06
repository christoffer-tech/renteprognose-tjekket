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

Samlet for alle seks banker: 4 362 prognoser, 2 755 med facit, spredt fra 2011
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
| Sydbank | 2011-07-10 | 40 | 375 | gammel renteforventningsside (2011–2019) + nuværende renteside + "Økonomisk Oversigt"-PDF'er (2020–2022, `backfill_sydbank_oversigt.py`) + månedlige renteforventnings-PDF'er (2022–) + refinansieringsartikler |
| Nordea | 2019-05-16 | 45 | 1 044 | hovedtabel + auktionsprognoser (nordea.com, 3 stk/år) |
| Nykredit | 2019-07-23 | 41 | 848 | 3 ældre captures (2018–2019) har intet parsebart bord |
| Sparekassen Kronjylland | 2017-07-14 | 28 | 300 | Investeringsmagasinets `RENTEPROGNOSE`-tabel (2017–2019, `backfill_sparkron_pdf.py`) + nuværende renteside + spejlesiderne `/da/`, lommepenge, kron (alle captures, `--full`) |
| Jyske Bank | 2019-09-02 | 41 | 1 093 | kvartalsnotatet "Boliglånsanbefaling" (arkivet + ugentligt snapshot) + **markedsrente-prognoserne i "Renteprognose"** (2019–2024, `backfill_jyske_renteprognose.py`) med facit fra Danmarks Statistik (`fetch_facit.py`) + den nuværende HTML-side |

"Snapshots" er antallet af optagelser der overlever dublet-fjernelsen, og
"unikke prognoser" er antallet af (produkt, publiceringsdato, måldato)-punkter
i `dataset.json`. De rå filer i `data/**/snapshots/` er flere: fx ligger der
183 RD-filer, hvoraf langt de fleste er genarkiveringer af en uændret side.
`python scraper/validate_banks.py` viser fordelingen.

Jyske Banks hul er nu **delvist lukket**, og det viste sig at ligge et andet
sted end antaget. Bankens boligrenter (F1/F3/F5) findes kun som maskinlæsbar
tabel i kvartalsnotatet "Boliglånsanbefaling" — Q1 2024-udgaven er hentet fra
Wayback og giver 16 punkter, hvoraf 12 med facit.

Men bankens **markedsrenteprognoser** ligger i et helt andet notat: det
månedlige "Renteprognose" fra Jyske Markets, som indeholder de maskinlæsbare
tabeller `STATSRENTER` og `SWAPRENTER` for Danmark, Eurozonen og USA. Serien
dækker **september 2019 – juni 2024**, og PDF'erne ligger stadig på
jyskebank.dk. Det tilføjer 945 punkter på `stat10`, `stat2`, `stat5`, `stat30`,
`cibor3`, `cibor6` og `leading_dk` — og løfter bankens første prognose fra
2024-06-18 til **2019-09-02**.

Markedsrenterne havde ingen facit, fordi bankens egne observationer først
begynder i 2024. Det er løst med en uafhængig, autoritativ kilde:

> Danmarks Statistiks tabel **MPK3** ("Rentesatser, ultimo") er månedlig tilbage
> til 1985 og indeholder både *10 årig statsobligation*, *CIBOR 3 måneder* og
> *Nationalbankens udlånsrente*. Den hentes af `scraper/fetch_facit.py` og
> bruges som facit for `stat10`, `cibor3` og `leading_dk`.

Det giver 274 markedsrente-punkter med facit. `stat10` (MAE 0,78) og
`leading_dk` (MAE 0,94) er de bærende. `cibor3` har ingen facit, fordi CIBOR 3M
blev nedlagt i august 2019. `stat2`, `stat5` og `stat30` har kun enkelte
facit-punkter, da MPK3 ikke har de løbetider.

Fasit-koblingen gjorde også `stat10` **sammenlignelig på tværs af banker**:
Sydbank har samme produkt, og begge er nu i den kanoniske mapping. Jyske
kommer dermed ind i mesterskabet med 12 discipliner mod 9 før.

Verificeret mod uafhængig kilde: Jyskes egen *Spot*-kolonne for 4. december 2019
er −0,34, og DST's måling for november 2019 er −0,34.

Det øvrige Jyske-materiale er afprøvet og kan ikke bruges:

- **CDX-indekset viser 22 relevante kvartals-PDF'er**, men kun **1 af 22** kan
  faktisk afspilles; resten svarer 404 selv om indekset melder HTTP 200. De
  gamle `/wps/wcm/connect/jfo/<uuid>/`-URL'er svarer 403/404.
- **Graferne i "Renteprognose"** er vektorgrafik og kan i princippet læses ud
  (akser og kurver er koordinater), men tabellerne i samme PDF'er gør det
  overflødigt. Kalibreringen ligger uverificeret i `scraper/experiments/`.
- **`forventning-til-rentetilpasning.pdf`** har den kvartalsvise boligrente-
  prognose i en figur, ikke en tabel. **`resultat-rentetilpasning-privat.pdf`**
  har en maskinlæsbar F1/F3/F5-tabel, men det er facit, ikke en prognose.

Det er stadig ikke lykkedes at aflede boligrenterne fra markedsrenterne. Jyske
spår kun om én løbetid pr. marked (10-årig swap/stat), og i Q1 2024-notatet
ligger F5-forventningen på 2,47–2,58 % — på niveau med eller under den 10-årige
swap. Forskellen er ikke et spread, men hele rentekurvens hældning, som banken
ikke spår om.

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
