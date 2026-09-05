---
title: Structured Geometry feasibility spike v1
status: measured_insufficient_corpus
last_updated: 2026-08-30
---

# Wynik read-only spike'a Structured Geometry

## Decyzja

**Techniczny conditional go wyłącznie do rozszerzenia read-only spike'a.**

Nie ma zgody na produkcyjny rollout, zmianę progów 95/98, migrację ani
przełączenie trybu gry. Korpus jest za wąski: 43 zdjęcia jednej gry, zero
częściowych stron, jeden formalnie oznaczony historyczny false-success i brak
osobnego bucketu blur.

Pełny lokalny raport:

- `artifacts/structured-geometry-feasibility-v1/report.json`;
- checksum SHA-256 raportu:
  `ce94bcf8d643c0b7f7fea64e1e57861cc7902a07231ce26a29dc1bbb3f46fdb6`;
- 43 per-image JSON, 43 source overlays i 43 contact sheets;
- łącznie 130 plików diagnostycznych, około 17,8 MB.

Artefakty są regenerowalne i pozostają poza Git. Runner weryfikuje checksumy
wszystkich wejściowych JPEG-ów i zapisuje wyłącznie do wskazanego katalogu.

## Korpus

| Wymaganie | Wynik |
|---|---:|
| rzeczywiste zdjęcia | 43 — spełnione |
| aktywne plansze | 387 |
| gry | 1 — brak wymaganej różnorodności |
| pełne strony | 43 |
| częściowe strony | 0 — brak |
| historyczne false-success | 1 — wymagane co najmniej 3 |
| angle / brightness / glare / occlusion | obecne |
| blur | brak osobnego bucketu |

## Porównanie kandydatów

Próg `0,025` przekątnej obrazu służy wyłącznie do porównania w spike'u. Nie
jest progiem produkcyjnym ani bramką cutoveru.

| Kandydat | dostępne | poprawne eksperymentalnie | błędne | niedostępne |
|---|---:|---:|---:|---:|
| generic global projection bez profilu | 0 | 0 | 0 | 387 |
| known-layout projection z anchora | 324 | 323 | 1 | 63 |
| Structured hybrid po lokalnym refine | 312 | 309 | 3 | 75 |
| lokalny refine z oracle ROI | 382 | 380 | 2 | 5 |
| historyczny detected quad, gdzie dostępny | 27 | 27 | 0 | 360 |

Historyczny detected quad jest porównaniem z wersjonowanego korpusu M5, a nie
replayem produkcyjnego joba v20. Oracle ROI używa ludzkiej adnotacji i mierzy
wyłącznie wykonalność lokalnego etapu; nie jest kandydatem do wdrożenia.

## Odpowiedzi techniczne

- Inicjalizacja bez profilu nie jest wystarczająca: nie zwróciła żadnego quada.
- Profilowa known-layout projection jest obiecująca na tej jednej rodzinie
  strony: 323/324 dostępnych quadów mieści się w eksperymentalnej tolerancji.
- Lokalny refiner ma wystarczającą zdolność korekty przy prawidłowym ROI:
  380/382 dostępnych wyników mieści się w tolerancji.
- Same linie wewnętrzne nie są stabilnym warunkiem akceptacji. Wszystkie 387
  plansz zakończyły się `needs_manual_correction`; 324 miały niewystarczające
  linie poziome i 324 niewystarczające przecięcia.
- Średni dowód ramki wyniósł `0,7526`, Hough `0,7134`, regularność `0,9375`, a
  pomocniczy sygnał centrów `0,9407`. Profile gradientów były słabsze:
  pionowy `0,2863`, poziomy `0,1561`.
- Dane wspierają dalsze badanie kombinacji mocnej ramki, known-layout
  projection i regularności 5×3 przy słabych liniach. Nie wspierają uznania
  obecnych hard gates LSD za finalne.
- Trzy źródła, czyli 27 plansz, wywołały
  `ImageGeometryContractError` po profilowej projekcji niepoprawnego quada.
  Przyszła konfiguracja musi walidować każdy projektowany quad przed budową
  kontraktu i kierować go do kontrolowanego review zamiast wyjątku.

## Klasy błędów

Najczęstsze reason codes:

- `horizontal_line_coverage_insufficient`: 324;
- `intersection_coverage_insufficient`: 324;
- `vertical_line_coverage_insufficient`: 112;
- `global_initialization_unavailable`: 36;
- `outer_boundary_evidence_incomplete`: 15;
- `initialization_alignment_failed`: 12;
- `local_homography_unavailable`: 12;
- `local_reprojection_error_exceeded`: 12;
- `source_support_incomplete`: 12;
- profilowy niepoprawny quad / `ImageGeometryContractError`: 27.

## Warunek kolejnego etapu geometrii produkcyjnej

Schema ownership review może zostać wykonany niezależnie, ponieważ nie zmienia
algorytmu ani rolloutu. Przed konfiguracją kolejnego silnika geometrii lub
zmianą progów produkcyjnych należy rozszerzyć wejście tego samego runnera o:

1. co najmniej drugą grę i inną rodzinę wizualną;
2. rzeczywiste częściowe strony;
3. co najmniej dwa dodatkowe historyczne false-success;
4. osobny bucket blur;
5. rozdzielone źródła do strojenia i oceny.

Dopiero wtedy można ponownie wydać GO / conditional go / no-go. Bramki 95/98
pozostają odrębnym, późniejszym odbiorem minimum 100 źródeł i 500 plansz.
