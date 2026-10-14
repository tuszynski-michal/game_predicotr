---
title: TASK-1013 — Trwałe propozycje dla „Złej siatki”
status: todo
last_updated: 2026-10-14
---

# TASK-1013 — Trwałe propozycje dla „Złej siatki”

## Status

`todo`

## Goal

Model przygotowuje korektę, a operator decyduje o jej zastosowaniu.

## Context

Task jest częścią zaakceptowanej rewizji 6. Decyzje człowieka i rewizje propozycji. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0993, TASK-0999.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. ochrona zgłoszenia i atomowy zapis decyzji.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [API_CONTRACT](../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: D-462/D-543, API_CONTRACT, schemat propozycji z sekcji 4.

- [D-462](../process/decisions/DECISION_LOG_2026.md#d-462--weryfikacja-per-komórka-bez-zatwierdzania-planszy-i-siatki) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-543](../process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Wdrożyć tabele propozycji i zdarzeń.
- Reviewer pokazuje porównanie, przyjęcie, edycję i odrzucenie.
- Przyjęcie korzysta z `VirtualGridGeometryService.save_review_item`, a nie z usługi samych liczników.

## Out of scope

- Automatyczny wynik nie może zostać oznaczony jako ręczny przed decyzją operatora.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Utworzenie nie zmienia cropów ani zgłoszenia.
- [ ] Przyjęcie działa raz, zapisuje autora i zamyka właściwy problem.
- [ ] Zmieniona rewizja daje konflikt.
- [ ] Odrzucenie pozostawia zgłoszenie otwarte.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Wdrożyć tabele propozycji i zdarzeń. Reviewer pokazuje porównanie, przyjęcie, edycję i odrzucenie. Przyjęcie korzysta z `VirtualGridGeometryService.save_review_item`, a nie z usługi samych liczników.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [virtual_grid_geometry.py](../../services/api/src/game_predictor_api/application/virtual_grid_geometry.py) — `VirtualGridGeometryService.save_review_item`, `save_pending_slot`.
- Istniejące: [virtual_grid_geometry_repository.py](../../services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py) — `save_virtual_geometry_revision`.
- Istniejące: [image_review_repository.py](../../services/api/src/game_predictor_api/storage/image_review_repository.py) — ochrona decyzji człowieka, licznik korekt.
- Istniejące: [models.py](../../services/api/src/game_predictor_api/storage/models.py) — encje i relacje magazynu.
- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `services/api/src/game_predictor_api/application/grid_geometry_proposals.py`, `services/api/src/game_predictor_api/storage/grid_geometry_proposals.py`, schema/router, migracja oraz komponent propozycji w Reviewerze.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_geometry_proposals.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Utworzenie nie zmienia cropów ani zgłoszenia.
- Przyjęcie działa raz, zapisuje autora i zamyka właściwy problem.
- Zmieniona rewizja daje konflikt.
- Odrzucenie pozostawia zgłoszenie otwarte.

## Verification

Zakres: API, MIG, REVIEWER, OpenAPI; integracja rzeczywistej ścieżki zapisu geometrii.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test:geometry --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py services/api/tests/test_virtual_grid_geometry_repository.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Automatyczny wynik nie może zostać oznaczony jako ręczny przed decyzją operatora.

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

- Nie rozpoczęto. Docelowy zapis wyniku: tabela stanów, dowody idempotencji i stale-proposal conflict.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1003
