# Eksperimenter (ikke i brug)

Kode her er **ikke** en del af pipelinen og ikke verificeret. Den ligger her for
at arbejdet ikke skal gå tabt.

## `chart_extract.py` — læsning af vektorgrafer i "Renteprognose"

Jyske Markets' prognosegrafer er vektorgrafik, så serierne ligger som
koordinater og kan i princippet læses præcist uden OCR. Det viste sig
**unødvendigt**, fordi de samme PDF'er har maskinlæsbare prognosetabeller
(`STATSRENTER`, `SWAPRENTER`), som `banks/jyske_renteprognose.py` bruger i
stedet.

### Hvad der virker

- Gitterkasserne findes per graf (to grafer pr. side), og y-aksen kalibreres
  ved at parre gitterlinjer med de nærmeste aksetal. Testet på 5 PDF'er.
- Bankens serie identificeres konsistent: det er den dominerende kurve
  (790–840 punkter mod 10–66 for reference- og forward-serierne).
- x-aksen kalibreres korrekt, når datoetiketternes **centrum** bruges —
  etiketterne er centrerede om deres position, ikke venstrejusterede. Med
  venstrekanten blev alle datoer forskudt med en halv labelbredde.
- Korttitlen kan knyttes til grafen via ordets position over gitterkassen.

### Hvad der er uverificeret

Tallene er **ikke** efterprøvet mod en uafhængig kilde. Før det sker, må
resultatet ikke bruges i datasættet. En naturlig kontrol ville være at
sammenligne en udtrukket `DKK SWAP 10y`-serie med faktiske swaprenter.

Bemærk at eksperimentet blandede to grafer sammen på samme side, indtil
gitterkasserne blev adskilt — vær opmærksom på det, hvis det genoptages.
