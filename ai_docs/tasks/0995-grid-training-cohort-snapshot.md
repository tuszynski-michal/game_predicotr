---
title: TASK-0995 — Kwalifikacja korekt i niezmienny snapshot
status: todo
last_updated: 2026-10-14
---

# TASK-0995 — Kwalifikacja korekt i niezmienny snapshot

## Status

`todo`

## Goal

Dostarczyć trenerowi odtwarzalny zbiór z czytelną listą braków.

## Context

Task jest częścią zaakceptowanej rewizji 6. Kwalifikacja i niezmienne dane dowodowe. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1002, TASK-1009; przyjęta decyzja rozszerzająca D-480.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. aktualność etykiet i dane dowodowe.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB_EXPORT](../guides/VISION_LAB_EXPORT.md).
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- [DATA_MODEL](../architecture/DATA_MODEL.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB_EXPORT, VISION_LAB, DATA_MODEL.

## Scope

- Preview required/eligible/missing per gra i rola.
- Osobne targety board/screen.
- Freeze źródeł, rewizji, preprocessing, base, ról i hashy.
- Cofnięte dowody unieważniają kwalifikację kandydata.

## Out of scope

- Stary eksporter zachowuje dotychczasową domyślną semantykę; bez treningu.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Pełna plansza z niekompletnego zdjęcia działa w grid-only.
- [ ] Niepełne zdjęcie nie jest screen targetem.
- [ ] Auto-accept nie tworzy etykiety.
- [ ] Drift między preview/freeze blokuje zapis.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Preview required/eligible/missing per gra i rola. Osobne targety board/screen. Freeze źródeł, rewizji, preprocessing, base, ról i hashy. Cofnięte dowody unieważniają kwalifikację kandydata.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Pozostały zakres wskazany w zaakceptowanym planie: istniejący eksporter geometrii jako wzorzec; nowe proponowane `services/api/src/game_predictor_api/domain/grid_training_cohorts.py`, application/storage, migracja, `services/worker/src/game_predictor_worker/training_core/grid_dataset.py`, `grid-cohort-preview.tsx`.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_training_cohort_snapshot.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Pełna plansza z niekompletnego zdjęcia działa w grid-only.
- Niepełne zdjęcie nie jest screen targetem.
- Auto-accept nie tworzy etykiety.
- Drift między preview/freeze blokuje zapis.

## Verification

Zakres: API, WORKER, MIG, ADMIN, OpenAPI, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_cohorts.py services/api/tests/test_verified_training_datasets.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_training_manifest.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Stary eksporter zachowuje dotychczasową domyślną semantykę; bez treningu.

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

- Nie rozpoczęto. Docelowy zapis wyniku: manifest, liczby braków i dowody kwalifikacji.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1005
