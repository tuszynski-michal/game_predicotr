---
title: TASK-0830 — profil silnika siatek gry w polu „Format strony” (777 v2, Mumie)
status: todo
last_updated: 2026-10-04
---

# TASK-0830 — profil silnika siatek gry w polu „Format strony”

## Status

`todo`

## Goal

Przy tworzeniu i edycji gry operator wybiera w polu „Format strony” profil
silnika siatek „777 v2” albo „Mumie”; wybór jest trwale zapisany w grze i
wskazuje zamrożony, sprawdzony sumą kontrolną model `neural_grid` w
zarządzanym katalogu modeli, gotowy do użycia przez tryb shadow (TASK-0805).

## Context

Polecenie operatora 2026-10-04: po doszkoleniu na Mumiach chce przy
zakładaniu nowej gry wskazać, dla której gry silnik jest dostosowany — gry
„Mumie” i „777 v2” (dla 777 v2 nie ma jeszcze materiału, pojawi się
później; kolejne wersje, np. „777 v3”, mają móc użyć zapisanego profilu
777 v2). Dziś pole „Format strony” (`games.shape_geometry_configuration`)
ma wartości `framed_full_page_v2` („Pełna strona z ramką”) i
`requires_clarification`, związane z przygotowaniem preflightu (gotowość
`ShapeGeometryReadinessStatus`). Jedyna gra w katalogu to 777
(`requires_clarification`).

Modele (raport `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`):

| Profil | Model | Uzasadnienie |
|---|---|---|
| 777 v2 | run 1, preset A, eksport `neural-grid-runs\43933ac8d7d443c8b9079630a83de2e6\exports\2cd19738367121e6-round3` | wybrany na development przed odczytem holdoutów; pod niego skalibrowano bramkę `hybrid_v3` |
| Mumie | doszkolenie run 3, iteracja 3, eksport `neural-grid-runs\5bc981568c3f42bd96f6f9238e57aedc\exports\iteration03-f896da7196431be2` | 79% propozycji przyjętych bez zmian w ostatniej porcji; holdout Mumii 36/36 |

## Dependencies / entry conditions

- Head Alembic `0139` na gałęzi integracyjnej; nowa migracja `0140`
  (sprawdź przed commitem, czy inny tor nie zajął numeru).
- Inne okno pracuje równolegle na gałęzi integracyjnej (numery zadań 0825
  i 0826–0829 zajęte) — przed zmianami w Adminie sprawdź aktualny stan
  plików katalogu gier.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Zmiana katalogu gier (migracja,
kontrakt API, Admin) i wprowadzenie zarządzanego rejestru modeli
produkcyjnych. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` (katalog gier), `ai_docs/architecture/API_CONTRACT.md`,
  `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md` (D-447, D-461, D-490 i wpisy o
  `shape_geometry_configuration` — znajdź przez grep)
- `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`

## Scope

1. **Wartości pola** `shape_geometry_configuration` (enum domeny, schemat,
   migracja CHECK, OpenAPI, klient, Admin): dodać `grid_profile_777_v2`
   („777 v2”) i `grid_profile_mumie_v1` („Mumie”); istniejące wartości
   zostają bez zmian. Gotowość (`ShapeGeometryReadinessStatus`) dla nowych
   wartości: ustal z kodu znaczenie stanów i przypisz zachowanie
   równoważne `framed_full_page_v2` dla preflightu (nowe gry startują z
   ręczną weryfikacją pierwszego importu); jeżeli nowe wartości wymagałyby
   zmiany działania preflightu albo pipeline'u, zatrzymaj się i opisz.
2. **Rejestr modeli** (proponowane `services/api/.../grid_engine_profiles.py`
   i katalog `<ARTIFACT_ROOT>/models/grid-engine/<profil>/<wersja>/`):
   skrypt jednorazowo kopiuje wskazane eksporty ONNX (`screen.onnx`,
   `board.onnx`, `bundle.json`, preset) do zarządzanego katalogu z
   kontrolą SHA-256 i manifestem (profil, wersja, run, preset, fingerprint,
   wyniki z raportu V3-C, data); rejestr w kodzie mapuje profil → wersja →
   SHA. Brak pliku albo niezgodny SHA = jawny błąd, bez cichego fallbacku.
   Bez nowej tabeli bazy (wybór profilu jest w `games`, model w plikach).
3. **Admin:** etykiety w polu „Format strony” i krótki opis pod polem
   (który model, że profil 777 v2 służy też przyszłym wersjom 777);
   widoczność profilu w liście gier.
4. **Endpoint tylko do odczytu** z listą profili i stanem ich modeli
   (dostępny / brak / niezgodny SHA) dla Admina.
5. Dokumentacja: `ADMIN_APP.md`, `API_CONTRACT.md`, `DATA_MODEL.md`,
   wpis w przewodniku operatora o profilach.

## Out of scope

- Uruchamianie sieci w pipeline importu i tryb shadow (TASK-0805).
- Zmiana „Formatu strony” gry 777 (operator decyduje sam w Adminie).
- Tworzenie gier „Mumie” i „777 v2” — robi to operator.
- Trening, przekalibrowanie bramki.

## Acceptance criteria

- [ ] Operator może utworzyć grę z formatem „777 v2” albo „Mumie”;
      wartość zapisuje się i wraca w API i Adminie; stare wartości działają
      jak dotąd (test regresji).
- [ ] Migracja `0140` z `downgrade` (odmowa, gdy istnieje gra z nową
      wartością) przechodzi test cyklu na bazie `*_test`.
- [ ] Modele obu profili są w zarządzanym katalogu z manifestem; test
      wykrywa brak i zmianę pliku.
- [ ] Endpoint profili zwraca stan modeli; Admin pokazuje stan przy polu.
- [ ] Kontrakt pionem (OpenAPI, klient, wrapper, test żądania).
- [ ] Brak zapisu do bazy deweloperskiej przez wykonawcę; migrację na bazie
      deweloperskiej wykonuje orkiestrator.
- [ ] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

- Nazwy wartości są stabilne i niezależne od etykiet; etykiety po polsku w
  Adminie. Kolejna wersja modelu tej samej gry = nowa wersja w rejestrze
  profilu, nie nowa wartość pola.
- Katalog modeli w `ARTIFACT_ROOT` (konfiguracja API), nie w danych labu i
  nie w repo (pliki ONNX ~25 MB); rejestr w repo zawiera tylko SHA i
  metadane.

## Expected files

- Istniejące: `domain/catalog.py`, `schemas/catalog.py`,
  `application/catalog.py`, `storage/models.py`, Admin
  `features/games/game-catalog*.tsx|ts`, `packages/admin-api-client`.
- Nowe (proponowane): migracja `0140_grid_engine_profiles.py`,
  `grid_engine_profiles.py`, skrypt `scripts/install_grid_engine_models.py`,
  testy.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -q -p no:cacheprovider -k "catalog or grid_engine_profile"
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/<nowy test migracji> -q -p no:cacheprovider
npm run openapi:generate; npm run openapi:check
npm run typecheck --workspace @game-predictor/admin; npm run test --workspace @game-predictor/admin
```

## Outcome

Wypełnia agent po pracy.

### Changed

- Do uzupełnienia po wykonaniu.

### Verification results

- Do uzupełnienia po wykonaniu.

### Not completed

- Do uzupełnienia po wykonaniu.

### Documentation updates

- Do uzupełnienia po wykonaniu.

### Recommended next task

- Do uzupełnienia po wykonaniu.
