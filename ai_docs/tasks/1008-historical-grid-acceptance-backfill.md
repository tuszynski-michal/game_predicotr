---
title: TASK-1008 — Historyczna akceptacja bez ponownego cięcia
status: todo
last_updated: 2026-10-14
---

# TASK-1008 — Historyczna akceptacja bez ponownego cięcia

## Status

`todo`

## Goal

Uzgodnić historyczne statusy przy zachowaniu istniejącej geometrii.

## Context

Task jest częścią zaakceptowanej rewizji 6. Historyczne statusy i atomowe projekcje. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1017; wykonanie na danych operatora dopiero po podglądzie i potwierdzeniu.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. masowa operacja na stanach i projekcjach.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [DATA_MODEL](../architecture/DATA_MODEL.md).
- Zakres odczytu uzupełniający z planu: D-484/D-485/D-541, DATA_MODEL, zasady operacji danych.

- [D-484](../process/decisions/DECISION_LOG_2026.md#d-484--kompletność-geometrii-zdjęcia-jest-bramką-przed-cięciem-na-symbole) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-485](../process/decisions/DECISION_LOG_2026.md#d-485--bramka-kompletności-stan-trwały-zdjęcia-dokument-sekwencji-bez-dowodu-symboli-przepinanie-plansz-uzupełnia-d-484) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-541](../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Podgląd, zamrożony zakres, idempotentne uruchomienie, kursor i raport.
- Dla źródła jedna transakcja: kontrola rewizji, akceptacja, `materialize=False`, synchronizacja istniejących dokumentów wyszukiwania, receipt.

## Out of scope

- Bez modelu, recropu i tworzenia komórek; brak automatycznego wykonania na całej grze.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Awaria między statusem a projekcją cofa całość.
- [ ] Powtórzenie nie dubluje zdarzeń.
- [ ] Wycinki, approval, payloady i właściciele są identyczni przed/po.
- [ ] Mieszane rewizje nie są akceptowane na skróty.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Podgląd, zamrożony zakres, idempotentne uruchomienie, kursor i raport. Dla źródła jedna transakcja: kontrola rewizji, akceptacja, `materialize=False`, synchronizacja istniejących dokumentów wyszukiwania, receipt.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [image_geometry_completeness_repository.py](../../services/api/src/game_predictor_api/storage/image_geometry_completeness_repository.py) — raport i klasyfikacja kompletności.
- Istniejące: [image_geometry_completeness_state_repository.py](../../services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py) — `recompute_source_image_geometry_completeness`.
- Istniejące: [board_search_projection_repository.py](../../services/api/src/game_predictor_api/storage/board_search_projection_repository.py) — `sync_review_items`, `stale_review_item_ids`.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejący `scripts/backfill_image_geometry_completeness.py` jako wzorzec wznowienia; nowe proponowane `services/api/src/game_predictor_api/application/grid_engine_acceptance.py`, repozytorium operacji i UI podglądu.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_historical_grid_acceptance_backfill.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Awaria między statusem a projekcją cofa całość.
- Powtórzenie nie dubluje zdarzeń.
- Wycinki, approval, payloady i właściciele są identyczni przed/po.
- Mieszane rewizje nie są akceptowane na skróty.

## Verification

Zakres: API, MIG dla nowych zapisów operacji, ADMIN, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_geometry_completeness_domain.py services/api/tests/test_image_geometry_completeness_api.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez modelu, recropu i tworzenia komórek; brak automatycznego wykonania na całej grze.

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

- Nie rozpoczęto. Docelowy zapis wyniku: dowody niezmienności, podgląd skutków i ewentualne operacyjne wykonanie opisane oddzielnie.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-0993
