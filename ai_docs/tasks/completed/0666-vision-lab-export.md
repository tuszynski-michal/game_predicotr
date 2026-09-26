---
title: TASK-0666 — T01 — eksporter tylko do odczytu
status: done
last_updated: 2026-09-25
---

# TASK-0666 — T01 — eksporter tylko do odczytu

## Status

`done`

## Goal

Opublikować ograniczony manifestem, kompletny snapshot źródeł i rewizji bez zapisu do bazy.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

P00 done; manifest dostarczonych zdjęć i dostęp do lokalnej bazy w trybie read-only. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `high`. Integralność odczytu bazy i atomowej publikacji wymaga analizy transakcji oraz plików. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T01 — eksporter tylko do odczytu)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Eksport wskazanych źródeł i dostępnych rewizji, słowników, zatwierdzonych etykiet i porównania 777. Manifest wejściowy v1 zawiera `schemaVersion`, `datasetName` i pozycje `{gameId, sourceImageId, expectedSourceSha256, sourceFamilyId, role}`. Krótkie transakcje `REPEATABLE READ READ ONLY` z timeoutami i partiami; atomowa publikacja po checksum.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [x] Brak zapisu DB i częściowego snapshotu; idempotentny import; V1.1 oznacza selective_board_review_v1_1, a późniejsza rewizja jest osobna.
- [x] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Pierwsza transakcja przypina dokładne ID, rewizje i fingerprinty powiązanych wierszy. Każda kolejna partia w osobnej transakcji czyta wyłącznie przypięte ID i wykrywa brak/drift. Potem kopiuj zarządzane obrazy po kontroli SHA, zapisz manifest tymczasowy, wykonaj fsync plików i atomowy rename na jednym wolumenie. Snapshot ID = SHA-256 kanonicznego wejścia, wersji eksportera i przypiętych ID/rewizji. Identyczny retry weryfikuje gotowe pliki; konflikt odrzuca publikację. Błędy integralności i infrastruktury zatrzymują cały snapshot.

## Expected files

- Istniejące `services/api/src/game_predictor_api/storage/models.py::SourceImageModel`, `ImageSourceGeometryRevisionModel`, `RecognizedBoardModel`, `ImageBoardGeometryRevisionModel`, `ImageSymbolReviewCellModel`, `SymbolModel`; `services/api/src/game_predictor_api/storage/image_grid_review_repository.py::SqlAlchemyImageGridReviewRepository` (tylko odczyt kontraktu).
- Nowe (proponowane) `scripts/vision_lab_export.py::export_snapshot`, `::freeze_export_identity`, `::publish_snapshot`; `services/worker/tests/test_vision_lab_export.py::test_read_only_snapshot`.

## Test cases

- Źródło z pierwotną i późniejszą rewizją → obie pozycje; brak pierwotnej → brak porównania. Drift wiersza między partiami lub zmieniony plik źródła → brak publikacji. Przerwany eksport → brak częściowego snapshotu; identyczny retry → ta sama tożsamość i kontrola checksum; konflikt payloadu → błąd.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_export.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Po teście wykonaj lint/typecheck zmienionych modułów i wymagane kontrole kontraktu, każdą jako skończony proces z limitem maksymalnie 120 s. Testy tu są planowane, niezaliczone; zaliczenie wymaga kryteriów powyżej i braku regresji.

## Risks / open questions

- Zmiana schematu danych, zakresu zdjęć lub kosztu poza planem wymaga jawnej aktualizacji przed zależnym działaniem.

## Outcome

Wypełnia agent po pracy.

### Changed

- `scripts/vision_lab_export.py`: walidacja manifestu, zamrożenie tożsamości
  w transakcji tylko do odczytu, odczyt partiami z kontrolą driftu, kopie
  artefaktów po SHA-256, bezpieczna publikacja i weryfikacja ponowienia.
- Projekcje etykiet z bieżącą bramką kwalifikacji oraz porównanie historycznego
  V1.1 z ręcznymi rewizjami bez użycia bieżącego wskaźnika źródła planszy.
- `services/worker/tests/test_vision_lab_export.py`: 11 testów jednostkowych i
  procesowych, w tym routing, przerwanie, konflikt, reparse i korekta ręczna.

### Verification results

- `pytest -p no:tmpdir services/worker/tests/test_vision_lab_export.py -q`: 11/11.
- `ruff check` i `ruff format --check` dla obu plików Python: PASS.
- `mypy --explicit-package-bases --follow-imports=silent` dla obu plików
  Python, z `MYPYPATH` obu pakietów: PASS.
- `git diff --check`: PASS. Niezależny audyt `gpt-6-astra/high`: PASS,
  bez otwartych P0–P2 po dwóch cyklach poprawek.

### Not completed

- Nie uruchomiono eksportu na żywej bazie ani migracji; nie otrzymano
  produkcyjnego manifestu. Routing PostgreSQL zweryfikowano mockami, bez
  integracyjnej bazy danych.
- Nie wykonano T02 ani dalszych zadań etapu A w tym commicie.

### Documentation updates

- Dodano `ai_docs/guides/VISION_LAB_EXPORT.md`, odnośniki w indeksie i
  architekturze oraz aktualizację `CURRENT_STATE.md`.

### Recommended next task

- TASK-0667 (T02) zgodnie z etapem A zatwierdzonego planu.
