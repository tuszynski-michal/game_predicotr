---
title: TASK-0294 — Masowa weryfikacja pojedynczych symboli
status: in_progress
last_updated: 2026-08-26
---

# TASK-0294 — Masowa weryfikacja pojedynczych symboli

## Goal

Udostępnić lokalny, skalowalny workflow masowej weryfikacji cropów symboli,
który synchronizuje stan pojedynczych komórek z kanoniczną decyzją całej planszy.

## Context

Istniejący Reviewer zapisuje wyłącznie kompletne decyzje 15 komórek. Właściciel
zaakceptował nowy model: stan review jest trwały per crop, błąd siatki jest
flagą komórki, a pełna plansza domyka się automatycznie tylko po zatwierdzeniu
wszystkich bieżących cropów. Szczegółowy, zaakceptowany plan wykonania znajduje
się w historii zadania Codex z 2026-08-26.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/TEST_STRATEGY.md`

## Scope

- domena, migracje i resumowalny backfill stanów komórek,
- transakcyjna synchronizacja pełnej planszy i 15 cropów,
- bounded API oraz lokalny workspace Admina,
- durable operacje masowe w istniejącym general worker lane,
- filtr `Do poprawy siatki` w Reviewerze,
- benchmark 2 mln komórek i odbiór dokumentacyjny.

## Out of scope

- automatyczne trenowanie klasyfikatora symboli lub croppera,
- nowy worker lane, Redis, Celery, usługa zewnętrzna albo przechowywanie binariów
  cropów w PostgreSQL,
- rozwiązanie przyczyny tworzenia duplikatów pending z TASK-0291.

## Acceptance criteria

- [ ] Stan pojedynczej komórki jest checksum-bound i audytowalny.
- [ ] Wszystkie zatwierdzone plansze otrzymują po 15 zatwierdzonych komórek.
- [ ] Zatwierdzenie 15 komórek bez `?` domyka planszę przez istniejący canonical flow.
- [ ] Zła siatka jest flagą komórki i zasila filtr Reviewera bez drugiego źródła prawdy.
- [ ] Listowanie działa keysetowo po 60 elementów i nie materializuje pełnego wyniku.
- [ ] Masowe operacje są idempotentne, resumowalne i raportują konflikty jawnie.

## Technical notes

- `?` jest technicznym brakiem przypisania i nie może zostać zatwierdzony.
- Aktywna plansza bez `sequence_number` blokuje gotowość feature'u stabilnym błędem.
- Operacja wielotysięczna jest atomowa per plansza, nie globalnie; targety mają
  jawne wyniki `applied/conflict/failed/pending`.
- Nowy read path pokazuje tylko właściciela z `image_board_search_fast_documents`.

## Expected files

- `services/api/src/game_predictor_api/domain/image_symbol_reviews.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/alembic/versions/0066_*` i kolejne
- `apps/admin/src/features/symbol-reviews/`
- `apps/reviewer/src/features/operational-reviews/`

## Verification

Każdy pion uruchamia własne testy API/UI/worker oraz kontrolę typów. Końcowy
odbiór uruchamia `npm run quality`, build Admina i Reviewera oraz benchmark
skalowy z izolowaną PostgreSQL.

## Risks / open questions

- TASK-0291 nadal odpowiada za zapobieganie źródłowym duplikatom pending.
- Po rozpoczęciu częściowego review rollback kodu nie może automatycznie usuwać
  nowych tabel, ponieważ utraciłby niedomknięte decyzje komórek.

## Outcome

### TASK 1 — ukończony w `v0.8.19`

- Dodano czystą domenę pojedynczego cropa: identity, przejścia `approve`,
  `reassign`, `mark_grid_issue`, unieważnianie po geometrii i agregację
  `accepted/corrected` pełnej planszy.
- Dodano testy przejść, zakazu zatwierdzania `?`, unieważnienia 15 cropów,
  kompletności i agregacji planszy.
- Weryfikacja: test domenowy, trzy istniejące testy decyzji pełnej planszy,
  Ruff i izolowany mypy nowego modułu przeszły. Pełny mypy katalogu API ma
  istniejące, niezwiązane błędy brakujących stubs `game_predictor_worker`; nowy
  moduł jest czysty przy `--follow-imports=skip`.
- Nie dodano migracji, modelu ORM, endpointów, jobów ani UI — to pozostaje
  zakresem TASK 2+.
