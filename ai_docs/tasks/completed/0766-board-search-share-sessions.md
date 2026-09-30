---
title: TASK-0766 — Sesje udostępniania wyszukiwania: model, serwis i API administracyjne
status: done
last_updated: 2026-09-30
---

# TASK-0766 — Sesje udostępniania wyszukiwania: model, serwis i API administracyjne

## Status

`done`

## Goal

Admin API tworzy, listuje i unieważnia sesje `board-search-share` (migracja Alembic, PBKDF2, audyt, limit 5 aktywnych).

## Context

Punkt 5 zgłoszenia operatora z 2026-09-30, decyzja D-471. Pełna specyfikacja: plan §3 R4, §4.3–4.5 i §5 T7.

## Dependencies / entry conditions

- TASK-0760 done.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Migracja, poświadczenia, blokady i audyt. Audyt: niezależny agent `claude-fable-5-1` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T7. Przed startem ponownie sprawdzić kod po etapie A i doprecyzować ten plik.

## Out of scope

Według planu §8.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T7 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §5 T7.

## Expected files

Patrz plan §5 T7.

## Test cases

Patrz plan §5 T7.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

Według planu §7.

## Outcome

### Changed

- Domena `domain/board_search_shares.py` (stałe, statusy, błędy, walidacja
  czasu życia i etykiety), serwis `application/board_search_share_access.py`
  (create z `assert_can_create` przed tunelem, list, revoke, unlock z
  rotacją tokenu i blokadą po 5 błędach, authenticate dla TASK-0767,
  sprawdzenie gotowości gry), repozytorium SQLAlchemy i w pamięci z blokadą
  doradczą dla limitu 5 aktywnych sesji i walidacją audytu bez sekretów.
- Migracja `0129_board_search_share_sessions` (sesje, audyt, dziennik
  zapytań D-472 — tabela dziennika tworzona od razu, aby TASK-0767 mógł do
  niej pisać; odczyt i odtworzenie w TASK-0771), modele ORM.
- Admin API `/admin/board-search-shares/sessions` (create, list, revoke),
  operacje wysokiego wpływu w `local_admin.py`, obsługa błędów w `main.py`,
  flaga `GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED` (niepoprawna wartość
  wyłącza).
- OpenAPI, wygenerowany klient i wrapper (`createBoardSearchShareSession`,
  `listBoardSearchShareSessions`, `revokeBoardSearchShareSession`).
- `API_CONTRACT.md`: sekcja sesji udostępniania.

### Verification results

- `test_board_search_share_access.py` i `_api.py`: 27/27 (czas życia, limit
  aktywnych, blokada po 5 błędach, reset licznika, wygaśnięcie, rotacja
  tokenu, unieważnienie, wyłączona flaga, gotowość, brak sekretów, tunel nie
  startuje przy błędnym żądaniu).
- Integracja PostgreSQL (tymczasowa baza `*_test`, migracja do head): 5/5.
- `test_local_admin_security.py`, `test_config.py`, testy szczegółów planszy
  i zdalnej selekcji: zielone. `test_openapi_contract.py` (2) i
  `test_migration_baseline.py::test_parallel_feature_migrations_converge_on_one_head`
  (head przypięty do 0125) zawodzą tak samo przed zadaniem.
- ruff czysto, mypy --strict nowych modułów czysto, OpenAPI i klient
  aktualne, `admin-api-client` 69/69.
- Migracja nie była uruchamiana na bazie deweloperskiej (wymaga zgody).
- Audyt niezależnego agenta `claude-fable-5-1`: PASS w pierwszym cyklu, bez
  P0–P2. P3 poprawione: adnotacje typów w teście API, opis parsowania flagi
  w komentarzu i kontrakcie. Pozostawione świadomie: `assert_can_create`
  czyta w sesji sterującej przed startem tunelu (bez blokad), limit
  surowego pola etykiety 200 znaków przed normalizacją do 100.

### Not completed

- Publiczne trasy (unlock, dane) — TASK-0767; panel Admina — TASK-0769.
