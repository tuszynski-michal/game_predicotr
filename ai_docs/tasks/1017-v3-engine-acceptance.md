---
title: TASK-1017 — Akceptacja nowych wyników przez silnik V3
status: todo
last_updated: 2026-10-14
---

# TASK-1017 — Akceptacja nowych wyników przez silnik V3

## Status

`todo`

## Goal

Nowa poprawna rewizja otrzymuje właściwy stan akceptacji silnika.

## Context

Task jest częścią zaakceptowanej rewizji 6. Akceptacja silnika i pochodzenie danych. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1010 i akceptacja decyzji doprecyzowującej D-484/D-541.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. zmiana kwalifikacji danych produkcyjnych.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [IMAGE_INGESTION](../requirements/IMAGE_INGESTION.md).
- [VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP](../architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md).
- Zakres odczytu uzupełniający z planu: IMAGE_INGESTION, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP, D-484/D-523/D-541.

- [D-484](../process/decisions/DECISION_LOG_2026.md#d-484--kompletność-geometrii-zdjęcia-jest-bramką-przed-cięciem-na-symbole) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-523](../process/decisions/DECISION_LOG_2026.md#d-523--operational-neural-crops-and-recoverable-symbol-verification) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-541](../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Zastąpić bezwarunkowe `needs_review` oceną kompletu pozycji i pochodzenia.
- Zachować odrębność engine/human approval.
- Aktualizacja statusu i projekcji należy do transakcji istniejącego zapisu.

## Out of scope

- Bez historycznego backfillu i bez poluzowania bramki jakości.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Komplet zgodnych pozycji może zostać przyjęty; deferred, partial, konflikt lub błąd blokuje akceptację.
- [ ] Żaden przypadek nie ustawia ręcznego zatwierdzenia.
- [ ] Stare snapshoty pozostają czytelne.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Zastąpić bezwarunkowe `needs_review` oceną kompletu pozycji i pochodzenia. Zachować odrębność engine/human approval. Aktualizacja statusu i projekcji należy do transakcji istniejącego zapisu.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [neural_pending_geometry.py](../../services/worker/src/game_predictor_worker/images/neural_pending_geometry.py) — `neural_pending_payload`; konsument: `services/worker/src/game_predictor_worker/images/production_workflow.py`.
- Istniejące: [image_geometry_completeness_state_repository.py](../../services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py) — `recompute_source_image_geometry_completeness`.
- Pozostały zakres wskazany w zaakceptowanym planie: i jego produkcyjny konsument, ; walidatory payloadu geometrii. Nowa proponowana czysta funkcja kwalifikacji akceptacji V3.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_v3_engine_acceptance.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Komplet zgodnych pozycji może zostać przyjęty; deferred, partial, konflikt lub błąd blokuje akceptację.
- Żaden przypadek nie ustawia ręcznego zatwierdzenia.
- Stare snapshoty pozostają czytelne.

## Verification

Zakres: WORKER, API; regresje `test_neural_folder_correction_pipeline.py` i produkcyjnego importu.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_geometry_completeness_domain.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_neural_folder_correction_pipeline.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez historycznego backfillu i bez poluzowania bramki jakości.

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

- Nie rozpoczęto. Docelowy zapis wyniku: wersja polityki, pokryte przyczyny i dowody ochrony zatwierdzeń.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1008
