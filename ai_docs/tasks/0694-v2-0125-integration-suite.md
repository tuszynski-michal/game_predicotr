---
title: TASK-0694 — wiarygodny zestaw integracyjny po 0125
status: blocked
last_updated: 2026-09-26
---

# TASK-0694 — wiarygodny zestaw integracyjny po 0125

## Status

`blocked` — częściowe naprawy gotowe; zależny runtime wymaga TASK-0698.

## Goal

Przywrócić testy integracyjne zależne od 65 relacji game-owned tak, aby
sprawdzały `game_data_v2` na świeżym head 0125 i stanowiły wiarygodną bramkę
przed ponownym T08.

## Context

Poprzedni przebieg 28 plików po 0125 dał 64 passed i 49 failed. Aktualny
katalog ma 29 plików `test_*.py`, więc następny przebieg musi jawnie zapisać
zbiór wszystkich plików i komendę (np. `pytest -q
services/api/tests/integration`) oraz rzeczywisty wynik. W
`test_image_batch_store.py` 12/15 scenariuszy miało błąd brakującej relacji.
Część fixture używa gołej `Session(engine)` lub asercji na usuniętym
`public.<game-table>`. Sama liczba wystąpień tekstu nie dowodzi błędu; każdy
przypadek wymaga sprawdzenia właściciela tabeli według manifestu.

## Dependencies / entry conditions

T02–T07 done; T08 jest `no-go`. Testować wyłącznie na izolowanych bazach,
z weryfikacją dokładnych nazw przed uruchomieniem fixture z `DROP DATABASE`.

## Recommended execution

`gpt-6-sol`, reasoning `high`; niezależny review `gpt-6-astra`, reasoning
`medium`. Zmiana kontraktu produkcyjnego wymaga osobnego rozstrzygnięcia.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/delivery/LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md`
- `ai_docs/quality/LEGACY_PUBLIC_STORE_RELEASE_READINESS.md`

## Scope

- Naprawić fixture game-owned i asercje legacy w 28-pliku zestawie, zaczynając
  od `test_image_batch_store.py`, `test_worker_job_store.py` i pozostałych
  plików z faktycznymi awariami po 0125.
- Zachować osobny routing `public` dla catalog/control/shared według manifestu.
- Dodać regresję, która wykrywa brak V2 scope zamiast cicho akceptować pusty
  wynik; uruchomić pełny zestaw na świeżej bazie 0125.

## Out of scope

Apply 0125 na bazie użytkownika, zmiana API, martwy kod T11, dryf kontraktów
z TASK-0695.

## Acceptance criteria

- [ ] Każda naprawiana fixture ma jawny V2 scope i nie zależy od 65 kopii `public`.
- [ ] Pełny zestaw integracyjny po 0125 jest zielony albo pozostałe awarie są
      indywidualnie sklasyfikowane i przypisane do innych tasków.
- [ ] Nie osłabiono asercji ochronnych dotyczących catalog/control/shared.

## Outcome

Fixture imagebatch:15/16 przechodzi (13 head0125,2 historyczne migracje),
catalog2/2, image selection4/4, retention1/1. Release seed naprawiony,
ale runtime bez owner routing pozostaje czerwony. Duplicate pending,
import report/M2 i wcześniejsze błędy mypy zgrupowane w TASK-0695.

Niezależny audit gpt-6-astra/medium: brak nowych P0–P2 w fixture/smoke;
nie osłabiono ochrony shared/obcej gry. Ruff/format zmienionych fixture
passed; ograniczenia mypy opisane w raporcie readiness. Pełnej suite nie
wykonano, więc drugie kryterium i DoD nie są spełnione. Nie przenosić do
completed. Kontynuować po rozstrzygnięciu krytycznego TASK-0698.
