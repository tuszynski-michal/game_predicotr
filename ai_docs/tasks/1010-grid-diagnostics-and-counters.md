---
title: TASK-1010 — Jednoznaczne liczniki i diagnoza obu gier
status: todo
last_updated: 2026-10-14
---

# TASK-1010 — Jednoznaczne liczniki i diagnoza obu gier

## Status

`todo`

## Goal

Wyjaśnić różnice liczników przez wspólne jednostki i konkretne przyczyny.

## Context

Task jest częścią zaakceptowanej rewizji 6. Kilka źródeł liczników i różne jednostki. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1015; odczyt bazy we właściwym zakresie gry.
- Brak dostępu blokuje pomiar rzeczywistych liczb, nie testy logiki.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. kilka źródeł prawdy i nakładające się stany.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [IMAGE_INGESTION](../requirements/IMAGE_INGESTION.md).
- [ADMIN_APP](../requirements/ADMIN_APP.md).
- [DATA_MODEL](../architecture/DATA_MODEL.md).
- Zakres odczytu uzupełniający z planu: IMAGE_INGESTION, ADMIN_APP, DATA_MODEL, D-484/D-541/D-543.

- [D-484](../process/decisions/DECISION_LOG_2026.md#d-484--kompletność-geometrii-zdjęcia-jest-bramką-przed-cięciem-na-symbole) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-541](../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-543](../process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Rozszerzyć istniejący raport pokrycia i diagnostykę, zachowując unikalność sekwencji.
- Dodać rozkład przyczyn i przecięcia kategorii.
- Raport Mumii/777a2 zawiera czas pomiaru i zakres danych.

## Out of scope

- Nie wnioskować o jakości z liczby niepotwierdzonych zdjęć; nie poprawiać danych podczas diagnozy.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Duplikaty, dane kanoniczne, pending, rejected, deferred i nieznane symbole mają jednoznaczne liczniki.
- [ ] Brak symbolu nie udaje braku planszy.
- [ ] Wszystkie różnice rzeczywistego raportu mają powód albo kategorię nierozstrzygniętą.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Rozszerzyć istniejący raport pokrycia i diagnostykę, zachowując unikalność sekwencji. Dodać rozkład przyczyn i przecięcia kategorii. Raport Mumii/777a2 zawiera czas pomiaru i zakres danych.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [board_import_coverage_repository.py](../../services/api/src/game_predictor_api/storage/board_import_coverage_repository.py) — `SqlAlchemyBoardImportCoverageRepository`.
- Istniejące: [image_geometry_completeness_repository.py](../../services/api/src/game_predictor_api/storage/image_geometry_completeness_repository.py) — raport i klasyfikacja kompletności.
- Istniejące: [image_review_repository.py](../../services/api/src/game_predictor_api/storage/image_review_repository.py) — ochrona decyzji człowieka, licznik korekt.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejące schematy `image_reviews.py`; nowy proponowany `services/api/src/game_predictor_api/application/grid_diagnostics.py` i panel diagnostyki w Adminie.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_diagnostics_and_counters.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Duplikaty, dane kanoniczne, pending, rejected, deferred i nieznane symbole mają jednoznaczne liczniki.
- Brak symbolu nie udaje braku planszy.
- Wszystkie różnice rzeczywistego raportu mają powód albo kategorię nierozstrzygniętą.

## Verification

Zakres: API, ADMIN, DOC; odczyty rzeczywistych danych bez zmian.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_import_coverage.py services/api/tests/test_board_import_coverage_api.py services/api/tests/test_image_geometry_completeness_domain.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Nie wnioskować o jakości z liczby niepotwierdzonych zdjęć; nie poprawiać danych podczas diagnozy.

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

- Nie rozpoczęto. Docelowy zapis wyniku: wyniki uzgodnienia, ograniczenia odczytu i dalsze przypadki wymagające korekty.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1017
