---
title: Active symbol model cohort filter
status: done
last_updated: 2026-09-06
---

# TASK-0476 — Filtr kohorty aktywnego modelu w Weryfikacji symboli

## Status

`done`

## Goal

Operator może wyświetlić w `Weryfikacji symboli` dokładnie te bieżące,
checksum-bound cropy, które należą do niezmiennej kohorty aktualnie aktywnego
modelu symboli wybranej gry.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`

## Scope

- Dodać filtr `Kohorta aktywnego modelu` obok stanów review.
- Rozwiązywać kohortę z najnowszego zdarzenia aktywacji modelu dla gry.
- Pokazywać wyłącznie komórki obecne w niezmiennej kohorcie i nadal zgodne z
  jej checksumą cropa oraz trybem assetu.
- Przypiąć identyfikator kohorty do cursora, aby aktywacja innego modelu
  unieważniła wcześniejszą paginację.
- Zachować filtry symbolu, confidence, keyset pagination i oddzielne liczniki.
- Nie dodawać migracji ani nowej tabeli.

## Out of scope

- Przegląd historycznej kohorty wybranej ręcznie.
- Odtwarzanie nieaktualnego cropa z historycznego manifestu.
- Automatyczne trenowanie lub zmiana aktywnego modelu.

## Acceptance criteria

- [x] Radio ma nazwę `Kohorta aktywnego modelu`.
- [x] Filtr używa kohorty przypiętej do najnowszej aktywacji, nie najnowszej
  zamrożonej kohorty.
- [x] Obca gra, inna kohorta i crop o zmienionej checksumie są wykluczone.
- [x] Brak aktywnego modelu daje pusty wynik, nie fallback do wszystkich
  zatwierdzonych cropów.
- [x] Cursor jest związany z identyfikatorem aktywnej kohorty.
- [x] Zwykłe filtry `Wszystkie`, `Oczekujące`, `Zatwierdzone` zachowują
  dotychczasowe zachowanie.
- [x] Operacja obejmująca cały filtr kohorty jest fail-closed; jawnie zaznaczone
  cropy nadal używają istniejącej checksum-bound mutacji.

## Expected files

- `services/api/src/game_predictor_api/domain/image_symbol_reviews.py`
- `services/api/src/game_predictor_api/application/image_symbol_reviews.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/src/game_predictor_api/application/image_symbol_review_bulk_operations.py`
- `services/api/tests/`
- `packages/admin-api-client/`
- `apps/admin/src/features/symbol-reviews/`
- właściwa dokumentacja wymagania, API i bieżącego stanu

## Verification

Najpierw testy domeny, API, klienta i workspace, następnie Ruff/mypy dla
zmienionych modułów, lint/typecheck Admina, kontrola OpenAPI i build Admina.

## Outcome

- Dodano filtr `active_model_cohort` w domenie, API, wygenerowanym kliencie i
  lokalnym workspace Admina pod etykietą `Kohorta aktywnego modelu`.
- Repozytorium rozwiązuje kohortę z najnowszego eventu aktywacji i wymaga
  dokładnej zgodności bieżącej tożsamości cropa z zamrożonym samplem.
- Cursor v5 wiąże paginację z kohortą; brak aktywacji zwraca pusty wynik.
- Filter-wide bulk jest odrzucany stabilnym błędem; explicit bulk pozostaje bez
  zmian.
- Weryfikacja: 46 testów domeny/API/SQL, 9 testów kontraktu workspace, Ruff i
  TypeScript typecheck przeszły. Scoped mypy zmienionych modułów nie wykazał
  nowego błędu po odjęciu istniejących problemów importowanych modułów; pełny
  graf nadal raportuje wcześniejsze błędy opisane w raporcie końcowym.
