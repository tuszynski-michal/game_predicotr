# TASK-0479 — Czteropunktowa rejestracja pasa plansz

## Status

done

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`
- `ai_docs/tasks/0472-crop-v11-acceptance.md`

## Cel i założenia

Ograniczyć liczbę błędnie przyciętych zdjęć w lokalnym workflowie
`Przytnij wybrane zdjęcia` przez przenoszenie obszaru całego układu 3×3 z
wiarygodnej kotwicy. Kotwica zawiera cztery narożniki zewnętrznego obszaru
plansz, a nie 36 narożników dziewięciu osobnych plansz.

Nowy wariant musi zachować replay v10/v11. Nie modyfikuje istniejących
katalogów `cut`, importów ani ręcznych decyzji. Rejestracja jest pomocniczym
dowodem: słabe albo sprzeczne dopasowanie zawsze daje obowiązkową korektę.

## Zakres

- Dodać wersjonowany wariant czteropunktowej rejestracji sąsiednich zdjęć.
- Wyznaczać czteropunktową kotwicę wyłącznie z pełnego, strukturalnie
  potwierdzonego układu 3×3.
- Dopasowywać obrazy deterministycznie na ograniczonej skali i przenosić
  obrys przez odporną transformację afiniczną.
- Wymagać minimalnej liczby niezależnych dopasowań, pokrycia obszaru,
  dodatniej skali, ograniczonego zniekształcenia i małego błędu resztowego.
- Wyznaczać poziomy crop z ekstremów przeniesionych narożników oraz
  bezpiecznego marginesu. Rejestracja nie może zaciskać wyniku poniżej
  chronionego układu wykrytego strukturalnie.
- Dodać bounded kontekst kotwicy do Web Workera i narzędzia katalogowego.
- Zapisać fingerprint, źródło kotwicy, cztery punkty i metryki dowodu w
  manifeście wyniku.
- Naprawić trwałość zaznaczeń `Do poprawy`: stanem źródłowym pozostaje
  `.manual-image-crop-state/review-v2.json`; wznowienie nie może zastępować go
  pustą listą z legacy manifestu.

## Testy i DoD

- Testy transformacji, odrzucenia słabego/odbitego dopasowania oraz ochrony
  górnej i dolnej krawędzi.
- Ten sam input i kotwica dają deterministyczny wynik i fingerprint.
- V10/v11 pozostają bez zmian.
- Browser i runner zapisują ten sam kontrakt dowodu.
- Ograniczony odczytowy odbiór na rzeczywistych, source-disjoint zdjęciach:
  zero automatycznych cropów odcinających plansze lub numery oraz co najmniej
  95% poprawnych automatów. Cel 99% raportować wyłącznie, jeśli potwierdzą go
  dane; nie osłabiać bramek bezpieczeństwa.
- Jeżeli bramka jakości nie przejdzie, wariant pozostaje nieaktywny, a task
  pozostaje otwarty z konkretną diagnozą.

## Outcome

Dodano wersjonowany wariant v12 oparty na czteropunktowym obrysie całego układu
3×3, deterministycznych cechach i bounded affine RANSAC. Browser i runner
zapisują fingerprint oraz metryki dowodu, a browser potrafi ponowić wyłącznie
nierozwiązane zdjęcia po znalezieniu bliższej kotwicy. Słabe lub sprzeczne
dopasowanie trafia do obowiązkowej korekty. V10/v11 oraz istniejące katalogi
pozostały niezmienione.

Odczytowy odbiór 30 ujawnionych referencji dał 29 automatów, 1 manual i 0/29
odcięć plansz lub numerów, czyli 96,7% bezpiecznej automatyzacji. Tylko 16/29
wyników spełniło ścisły przedział obu linii, dlatego v12 jest dostępny wyłącznie
po jawnej akcji testowej i nie został aktywowany domyślnie. Szczegóły:
`ai_docs/quality/SELECTED_CROP_V12_REGISTRATION.md`.

## Commit

`v0.10.193 - register selected crop bands from four point anchors`
