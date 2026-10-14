---
title: TASK-1014 — Zarządzane checkpointy na D
status: todo
last_updated: 2026-10-14
---

# TASK-1014 — Zarządzane checkpointy na D

## Status

`todo`

## Goal

Uniezależnić użycie baz od jedynej kopii checkpointu na C.

## Context

Task jest częścią zaakceptowanej rewizji 6. Trwałość i integralność artefaktów. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1015; odczyt manifestów i dostępność miejsca.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. kontrolowana kopia z hashami.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: TASK-0957, VISION_LAB, zasady przechowywania modeli.

## Scope

- Rozszerzyć instalator o potrzebne artefakty treningowe i receipt pochodzenia.
- Staging, weryfikacja, atomowa publikacja; wznowienie nie nadpisuje odmiennego pakietu.

## Out of scope

- Bez usuwania C, kopiowania całego korpusu i wykonywania treningu.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Zgodny hash i rozmiar; przerwana kopia wznawia się; obcy katalog nie jest nadpisywany; nowy proces odczytuje bazę z D.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Rozszerzyć instalator o potrzebne artefakty treningowe i receipt pochodzenia. Staging, weryfikacja, atomowa publikacja; wznowienie nie nadpisuje odmiennego pakietu.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [grid_engine_model_store.py](../../services/api/src/game_predictor_api/storage/grid_engine_model_store.py) — `ManagedGridEngineModelStore`; [instalator](../../scripts/install_grid_engine_models.py) — `install_version`.
- Istniejące: [checkpoint.py](../../services/worker/src/game_predictor_worker/training_core/checkpoint.py) — zapis, odczyt i odtworzenie checkpointu.
- Pozostały zakres wskazany w zaakceptowanym planie: nowy proponowany manifest receipt kopii i test instalatora. tylko do sprawdzenia odczytu checkpointu.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_managed_grid_checkpoints_on_d.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Zgodny hash i rozmiar; przerwana kopia wznawia się; obcy katalog nie jest nadpisywany; nowy proces odczytuje bazę z D.

## Verification

Zakres: API/WORKER dla kontraktu artefaktów, test instalatora, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_grid_proposal.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_training_core.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez usuwania C, kopiowania całego korpusu i wykonywania treningu.

## Outcome

### Execution phase

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `claude-fable-5-1`, reasoning `medium`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: źródło, docelowe ścieżki, hashe i receipt; brak zgody na cleanup odnotowany.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-0994
