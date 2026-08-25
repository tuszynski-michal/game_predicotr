---
title: Grid cropping versus symbol model diagnosis
status: accepted
last_updated: 2026-08-23
---

# Diagnoza geometrii cropów i modelu symboli

## Cel

Ten dokument rozdziela błąd geometrii komórek od błędu modelu symboli.
Nie zmienia jobów, wyników review, aktywnego modelu ani artefaktów źródłowych.

## Potwierdzony pipeline

- Pełny import używa `board-cell-crops-v18-source-direct-validated-v1`.
- Ręczna geometria i pending-only recrop używają
  `board-cell-geometry-v19-multi-point-source-direct-v1` oraz
  `board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1`.
- Oba aktywne croppery pobierają finalny crop bezpośrednio z obrazu źródłowego
  w jednym resamplingu; różnica dotyczy granic pól, nie jakości źródła.
- Dla `seq_*` numeracja pochodzi z poświadczonej nazwy pliku — OCR numerów nie
  bierze udziału w tym eksperymencie.

## Read-only A/B — 2026-08-23

Raport `grid-cropping-vs-symbol-model-diagnosis-v1`:

- checksum: `e7f09e594d4013aee49362d7c22b0a0916acf47361f6ca742f15895a163e14eb`,
- artefakt: `artifacts/quality/grid-symbol-diagnosis/e7f09e594d4013aee49362d7c22b0a0916acf47361f6ca742f15895a163e14eb.json`,
- 81 ręcznie rozwiązanych plansz v19, 1215 symboli, sześć stagingów,
- trzy nieaktualne rewizje geometrii zostały jawnie wykluczone,
- baseline i porównanie używają dokładnie tego samego fingerprintu aktywnego
  modelu ONNX,
- `recognized_boards.board_geometry` jest po ręcznej korekcie zastępowane v19;
  baseline raportuje więc jawnie metodę historyczną
  `fixed-5x3-from-board-quad-v18`, a nie błędnie obecną rewizję v19.

| Metryka | Cropy bazowe v18 | Ręczna geometria v19 | Różnica |
|---|---:|---:|---:|
| Accuracy symboli | 71,03% | 95,80% | +24,77 pp |
| Plansze bez błędu | 22,22% | 72,84% | +50,62 pp |
| Ręczne korekty/planszę | 4,35 | 0,63 | −3,72 |

Wniosek: `CONFIRMED` — jakość granic pól jest główną przyczyną obecnych
błędów. Pozostałe błędy na poprawnych cropach są kandydatami M1/M2 i wymagają
osobnej kohorty po ustabilizowaniu v19.

## Kontrakt diagnostyki

Skrypt `scripts/build_grid_symbol_diagnostic.py`:

- odczytuje wyłącznie `accepted/corrected` z ręczną rewizją v19,
- weryfikuje checksumy cropów i modelu,
- odrzuca przypadek, gdy baseline job i aktywny model mają różne fingerprinty,
- uruchamia aktywny ONNX na zapisanych cropach v19 w jednym batchu,
- zapisuje content-addressed raport i nie wykonuje żadnego zapisu do bazy,
- raportuje wykluczenia zamiast ukrywać nieporównywalne plansze.

Odtworzenie:

```powershell
.\.venv\Scripts\python.exe scripts\build_grid_symbol_diagnostic.py `
  --game-id 80f3c7ec-6110-4e20-a263-2675ee5b15d6

.\.venv\Scripts\python.exe scripts\build_grid_symbol_diagnostic.py `
  --game-id 80f3c7ec-6110-4e20-a263-2675ee5b15d6 `
  --check
```

`--check` porównuje ponownie zbudowany raport z istniejącym artefaktem o tej
samej checksumie. Zmiana danych wejściowych, geometrii lub modelu tworzy nową
checksumę i celowo nie przechodzi starej kontroli.

## Invarianty

- Benchmark jest read-only względem danych produkcyjnych.
- Porównanie A/B wymaga identycznego fingerprintu modelu.
- Każda plansza ma dokładnie 15 pól row-major.
- Manualne etykiety są źródłem prawdy dla eksperymentu.
- Crop v19 musi przejść checksumę przed inferencją.
- Raport nie zawiera bezwzględnych ścieżek użytkownika.
- Wysokie confidence nie jest dowodem poprawnej geometrii.

## Następne kroki

TASK 2 rozszerzył benchmark do 300 stron i zweryfikował automatyczne v19 na
sześciu stagingach. Jakość trafień przeszła bramki, ale automatyczne pokrycie
`93,78%` nie osiągnęło wymaganego `98%`, dlatego checkpoint zablokował
domyślną aktywację. Właściciel później jawnie dopuścił wyłącznie bezpieczny,
staging-local opt-in v20 z trwałym deferred; v18 pozostał domyślny.

TASK 8 potwierdził na poprawnych cropach v19 jeden istotny residual M2, a TASK
9 wytrenował kandydata od początku. Kandydat poprawił metryki, lecz został
kontrolowanie odrzucony po jednym błędzie o confidence co najmniej `0,99`.
Końcowy stan, rollback i odwołania do wszystkich niezmiennych raportów opisuje
`ai_docs/quality/BOARD_CELL_GEOMETRY_V19_ROLLOUT.md`.

## Changelog

- 2026-08-23 — utworzono wersję v1 z immutable A/B i kontrolą tego samego
  snapshotu modelu.
- 2026-08-23 — TASK 2 zakończył cross-staging shadow benchmark wynikiem
  `REJECTED_FOR_ROLLOUT` z powodu niewystarczającego pokrycia.
- 2026-08-23 — uzupełniono końcowy stan kontrolowanego opt-in v20 oraz
  odrzuconego kandydata modelu symboli.
