---
title: TASK-0644 — Gra 777: kalibracja weryfikatora siatek na złotym zbiorze
status: done
---

# TASK-0644 — Kalibracja weryfikatora siatek 777 (read-only)

## Status

`done`

## Goal

Zmierzyć na złotym zbiorze z bazy, przy jakich progach niezależny weryfikator siatki daje zero fałszywych akceptacji, i zapisać regułę jako D-445.

## Context

Plan: `ai_docs/delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`. Automatyczne zatwierdzanie ~474 tys. plansz „Do walidacji” i rozwiązywanie 19 608 slotów „Do poprawy” jest bezpieczne tylko przy progach potwierdzonych danymi.

## Dependencies / entry conditions

- PostgreSQL działa, gra 777 na `game_data_v2`, pliki źródeł dostępne w `artifact_root`.
- Złoty zbiór czytany w chwili uruchomienia (obejmuje nowe ręczne przykłady cięcia).

## Recommended execution

`claude-opus-5-5`, reasoning `high` — zgodnie z tabelą planu. Eskalacja: jeśli żaden próg nie daje 0 fałszywych akceptacji przy pokryciu G+ ≥ 50%, zatrzymać plan i zaproponować drugi weryfikator.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`

## Scope

- Proponowany `scripts/reverify_777_grids.py` z podkomendą `calibrate` (+ wspólne ładowanie źródła i uruchamianie weryfikatora, używane później przez `plan`/`execute`).
- Złoty zbiór G+, G−, GP zgodnie z planem; pomiar odchyleń narożników, `status`, p95, inliers, czas/planszę; opcjonalnie V1.2, jeśli profil 777 jest dostępny.
- Raport JSON w `artifacts/grid-reverify-777/calibration-*.json` + podsumowanie na stdout.
- Wpis D-445 z wybranymi progami (τ, r, n, ε_h) po akceptacji użytkownika.

## Out of scope

- Jakikolwiek zapis do bazy; zmiany API/UI; pełny przebieg po populacji.

## Acceptance criteria

- [ ] `calibrate` działa w transakcji `READ ONLY` i w `game_storage_scope`.
- [ ] Raport zawiera liczności G+/G−/GP, rozkłady odchyleń, tabelę progów → (fałszywe akceptacje, pokrycie), czas/planszę.
- [ ] Wybrane progi mają 0 fałszywych akceptacji na G− i GP.
- [ ] Testy jednostkowe metryk (maks. odchylenie narożnika, klasyfikacja progów) przechodzą.

## Technical notes

- Źródło obrazu i normalizacja EXIF: jak `VirtualGridGeometryService._prepare` (`game_predictor_worker.images.normalization`); rozwiązywanie ścieżki jak `application/image_review_assets.py`.
- Podpowiedź dla weryfikatora: `boardFrameQuad` (fallback `analysisQuad`, `initialQuad`) z automatycznej rewizji źródła (`engine_kind = structured_opencv_v1`) — nigdy z siatki człowieka.
- Porównanie: maks. odległość odpowiadających narożników (TL, TR, BR, BL).
- G−: siatka silnika = `symbolGridQuad` rewizji 0; siatka człowieka = bieżąca rewizja `local-admin`.

## Expected files

- Nowe (proponowane): `scripts/reverify_777_grids.py`, test w lokalizacji testów skryptów wg konwencji repo.
- Istniejące: `ai_docs/process/DECISION_LOG.md` (D-445).

## Test cases

- Identyczne quady → odchylenie 0; narożnik przesunięty o 5 px → 5.
- Plansza G− z odchyleniem > ε_h odrzucona przez próg → poprawna odmowa, nie fałszywa akceptacja.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest <test file> -q   # timeout 120 s
.\.venv\Scripts\python.exe scripts/reverify_777_grids.py calibrate --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --import-job-id <id>
npm run python:lint; npm run python:typecheck
```

## Risks / open questions

- Weryfikator może dzielić błędy z silnikiem — wtedy eskalacja zamiast osłabiania progów.

## Outcome

### Changed

- `scripts/reverify_777_grids.py` (nowy): `calibrate` — read-only (połączenie
  `read_only`, `game_storage_scope`), złoty zbiór z bazy, estymator przy trzech
  skalach podpowiedzi, przemiatanie progów, raport JSON; `review-sheet` —
  ślepy arkusz wizualny 70 plansz (klucz w osobnym JSON).
- `services/api/tests/test_reverify_777_grids_script.py` (nowy): 6 testów metryk
  i bramek.
- Plan `GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md` — aktualizacja po
  kalibracji; `DECISION_LOG.md` D-445.

### Verification results

- `pytest services/api/tests/test_reverify_777_grids_script.py` — 6/6.
- `ruff check`/`ruff format --check` czyste dla nowych plików; `mypy` bez błędów
  w nowych plikach (29 wcześniejszych błędów w 7 innych plikach bez zmian).
- Kalibracja na żywej bazie (read-only, 318 s): złoty zbiór 63 zatwierdzone
  bez zmian + 127 ręcznie zapisanych + 8 rozwiązanych slotów; ręczne siatki
  różnią się od silnika o medianę 0,5 px (max 2,04 px); estymator przy tej
  samej podpowiedzi = siatka silnika (0,0 px); sloty odroczone: błąd
  estymatora 1–6 px, pokrycie próbki 8–26%; ~35 ms/planszę.

### Not completed

- Progi D-445 w pierwotnym sensie nie zostały ustalone — kryterium „0
  fałszywych akceptacji” nie jest mierzalne na zbiorze bez błędów silnika;
  zgodnie z warunkiem eskalacji plan został wstrzymany. Arkusz ślepej oceny
  nie został oceniony — użytkownik wskazał kierunek silnika v3.

### Documentation updates

- Plan reweryfikacji 777 (sekcja „Aktualizacja”), D-445, CURRENT_STATE.

### Recommended next task

- TASK-0648 — prototyp silnika siatek v3.
