---
title: TASK-1012 — Dynamiczne snapshoty i spójny routing V3
status: todo
last_updated: 2026-10-14
---

# TASK-1012 — Dynamiczne snapshoty i spójny routing V3

## Status

`todo`

## Goal

Nowe wersje z katalogu działają bez dopisywania do statycznego rejestru.

## Context

Task jest częścią zaakceptowanej rewizji 6. Snapshoty i zgodność całego importu. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0994.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. zgodność rozpoczętych zadań i wielu konsumentów.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [IMAGE_INGESTION](../requirements/IMAGE_INGESTION.md).
- [API_CONTRACT](../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: IMAGE_INGESTION, API_CONTRACT, D-544, kontrakt snapshotu tego planu.

- [D-544](../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Nowa wersja snapshotu oraz czytnik starej.
- Jeden resolver możliwości dla preflightu, importu, ponownego użycia, workera i własności sekwencji.

## Out of scope

- Bez przepisywania historycznych payloadów i ukrytych aliasów starego profilu.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Trzecia rodzina działa; stary job wznawia się po zmianie aktywacji; stary preflight nie uruchamia innej wersji; brak lub zmiana hashy nie powoduje fallbacku.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Nowa wersja snapshotu oraz czytnik starej. Jeden resolver możliwości dla preflightu, importu, ponownego użycia, workera i własności sekwencji.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [neural_grid_proposal.py](../../services/api/src/game_predictor_api/domain/neural_grid_proposal.py) — `NeuralGridSnapshot`.
- Istniejące: [grid_profile_snapshot_resolver.py](../../services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py) — `resolve_neural_grid_proposal`, routing profilu.
- Istniejące: [grid_engine_model_store.py](../../services/api/src/game_predictor_api/storage/grid_engine_model_store.py) — `ManagedGridEngineModelStore`; [instalator](../../scripts/install_grid_engine_models.py) — `install_version`.
- Istniejące: [jobs.py](../../services/api/src/game_predictor_api/application/jobs.py) — preflight, snapshoty, admission i start zadań.
- Pozostały zakres wskazany w zaakceptowanym planie: `services/api/src/game_predictor_api/storage/image_sequence_canonical_repository.py::uses_neural_grid_pilot`; konsumenci snapshotów w workerze.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_dynamic_grid_snapshots.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Trzecia rodzina działa; stary job wznawia się po zmianie aktywacji; stary preflight nie uruchamia innej wersji; brak lub zmiana hashy nie powoduje fallbacku.

## Verification

Zakres: API, WORKER, testy snapshotów/resolvera/importu, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_grid_proposal.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_neural_folder_correction_pipeline.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez przepisywania historycznych payloadów i ukrytych aliasów starego profilu.

## Outcome

### Execution phase

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `claude-fable-5-1`, reasoning `high`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: obsługiwane wersje kontraktu i lista zweryfikowanych konsumentów.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-0998
