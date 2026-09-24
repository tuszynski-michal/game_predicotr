---
title: TASK-0648 — Prototyp silnika siatek v3 (model ekranu 3 × 3)
status: done
---

# TASK-0648 — Prototyp silnika siatek v3 (model ekranu 3 × 3)

## Status

`done`

## Goal

Deterministyczny, niezależny od gry prototyp, który na zdjęciach ekranu 3 × 3 wyznacza 9 siatek symboli 5 × 3 wraz z oceną pewności, sprawdzony wizualnie na kilku zdjęciach z każdego katalogu testowego i oddany użytkownikowi do oceny.

## Context

TASK-0644 wykazał, że obecny silnik 777 ma widoczne przesunięcia siatek, a lokalny estymator nie jest od niego niezależny. Decyzja użytkownika (2026-09-24): nie używać ręcznych siatek jako wzorca; silnik ma sam wynikać z analizy zdjęć. Zdjęcia różnych gier (777, GANG, Treasure, Blazing, Reels, Mumie) mają różną perspektywę, rozmazanie, zasłonięcia i zakrzywienie (obiektyw szerokokątny/ekran). Wspólny jest układ ekranu 3 × 3 z numerem pod każdą planszą.

## Dependencies / entry conditions

- Zdjęcia lokalne: `C:\Users\tuszy\Documents\test folder` i `C:\Users\tuszy\Documents\dane testowe do planu automatycznego wyboru zdjec` (po kilka na katalog). Zdjęcia nie trafiają do repozytorium.
- Bez nowych zależności (OpenCV + numpy).

## Recommended execution

`claude-opus-5-5`, reasoning `high` — projekt algorytmu wizyjnego z iteracyjną weryfikacją wizualną. Eskalacja: gdy wspólny model nie obejmuje którejś gry, raport zamiast osłabiania reguł pewności.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`

## Scope

- Proponowany moduł `services/worker/src/game_predictor_worker/images/screen_layout_v3/` (czysta funkcja: RGB → 9 wyników planszy) i skrypt podglądu `scripts/preview_screen_layout_v3.py` (HTML z nałożonymi siatkami, artefakty w `artifacts/screen-layout-v3/`).
- Reguły: plansza może być ucięta tylko bokiem (całe kolumny → komórki niedostępne); ucięcie góry/dołu → do poprawy; zasłonięte elementy nie blokują dopasowania ekranu.
- Testy jednostkowe na syntetycznym obrazie; dokument propozycji `ai_docs/architecture/GRID_ENGINE_V3_PROPOSAL.md`.

## Out of scope

- Zapis do bazy, integracja z importem/workerem, zmiany API/UI, reweryfikacja 777 (dalsze taski planu).

## Acceptance criteria

- [x] Skrypt podglądu działa na zdjęciach ze wszystkich katalogów testowych.
- [x] Każdy wynik obejrzany wizualnie przez agenta; znane porażki opisane.
- [x] Testy jednostkowe przechodzą; ruff/mypy czyste dla nowych plików.
- [x] Dokument propozycji v3 z opisem algorytmu, pewności i wyników.

## Outcome

### Changed

- Nowy pakiet `services/worker/src/game_predictor_worker/images/screen_layout_v3/`
  (`panels.py`, `layout.py`, `lattice.py`, `engine.py`): `detect_screen_layout_v3(rgb)`
  → 9 siatek 5 × 3 (punkty 4 × 6 w pikselach źródła) + status
  `complete|partial|needs_review` i kody powodów. Bez wzorca per gra,
  bez nowych zależności (OpenCV + numpy), bez zapisu danych.
- `scripts/preview_screen_layout_v3.py` — lokalny podgląd HTML + `report.json`
  (`artifacts/screen-layout-v3/<czas>/`).
- `services/worker/tests/test_screen_layout_v3.py` — 7 testów.
- `ai_docs/architecture/GRID_ENGINE_V3_PROPOSAL.md` + wpis w `ai_docs/README.md`.

### Verification results

- `pytest services/worker/tests/test_screen_layout_v3.py` — 7/7.
- `ruff check`, `ruff format --check` czyste; `mypy` bez błędów w nowych
  plikach (29 wcześniejszych błędów w 7 innych plikach bez zmian).
- Podgląd na 36 zdjęciach (po 3 z 11 katalogów danych testowych + 6 z
  `test folder`), 324 plansze: 278 `complete`, 1 `partial`, 45
  `needs_review`; 7–26 s/zdjęcie. Ocena wizualna agenta: siatki `complete`
  trafiają w komórki na 777, Blazing, GANG (wszystkie 3 katalogi), Reels,
  Treasure, Mumie, także przy pochyleniu, zakrzywieniu i ręce na ekranie.
  Całe zdjęcie do poprawy przy słabym modelu: Reels 145600_000382,
  218400_000648, Treasure 375300_000220/_292 (część z tych siatek wygląda
  poprawnie — nadmierna ostrożność). Przed zaostrzeniem progu jedno zdjęcie
  (Reels 145600_000382) miało fałszywie pewne, przesunięte siatki; po
  zaostrzeniu (25% komórki + bramka konsensusu) nie zaobserwowano
  fałszywej pewności w próbce.

### Not completed

- Brak oceny użytkownika; progi pewności ustalone na oko na 36 zdjęciach.
- Brak integracji z importem/workerem i reweryfikacji 777 (TASK-0645–0647
  wymagają przepisania na v3).

### Documentation updates

- `GRID_ENGINE_V3_PROPOSAL.md`, `ai_docs/README.md`, `CURRENT_STATE.md`.

### Recommended next task

- Ocena podglądu przez użytkownika i dociągnięcie progów; potem task
  „v3 jako źródło siatek dla reweryfikacji 777” (dry-run na próbce 777).
