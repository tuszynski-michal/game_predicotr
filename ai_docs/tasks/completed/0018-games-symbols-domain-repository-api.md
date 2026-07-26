---
title: TASK-0018 Games and symbols domain, repository and API
status: done
last_updated: 2026-07-26
---

# TASK-0018 — Games and symbols domain, repository and API

## Goal

Dostarczyć przetestowany pion backendowy CRUD gier i symboli, oparty na
PostgreSQL, migracji Alembic i stabilnym kontrakcie OpenAPI.

## Context

M2.1 dostarczyło lokalną platformę administracyjną, bazę i generowany klient.
Pierwszy pion M2.2 ustanawia tożsamość gry oraz katalog jej symboli, zanim
powstaną formularze panelu i wersjonowane reguły.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- encje domenowe i walidacja gier oraz symboli,
- tabele PostgreSQL `games` i `symbols` przez odwracalną migrację Alembic,
- repozytorium SQLAlchemy z jawną granicą transakcji,
- listowanie, tworzenie, odczyt, aktualizacja i archiwizacja gier,
- listowanie, tworzenie, odczyt, aktualizacja i archiwizacja symboli gry,
- stabilne kody błędów dla braku zasobu, walidacji i konfliktu unikalności,
- regeneracja OpenAPI i typowanego klienta panelu,
- testy domenowe, API oraz repozytorium na izolowanym PostgreSQL.

## Out of scope

- ekrany panelu administracyjnego,
- kopiowanie i obsługa plików obrazów referencyjnych,
- reguły blokujące fizyczne usunięcie symbolu użytego w opublikowanej wersji,
- wersje reguł, wymiary planszy, koszt spinu, paylines i payout rules,
- jakiekolwiek połączenie HTTP w aplikacji mobilnej.

## Acceptance criteria

- [x] gra ma UUID, stabilny unikalny kod, nazwę, status i timestamps,
- [x] symbol ma UUID, grę, stabilne `mobile_code` oraz kod, nazwę, opcjonalną
      ścieżkę referencji, joker, kolejność i status,
- [x] baza blokuje duplikat kodu gry oraz duplikaty kodu i `mobile_code`
      symbolu w obrębie gry,
- [x] `mobile_code` akceptuje wyłącznie zakres `1..32767`,
- [x] API udostępnia CRUD z archiwizacją zamiast fizycznego DELETE,
- [x] błędy API mają stabilny `code`, `message` i `details`,
- [x] kontrakt OpenAPI i wygenerowany klient są aktualne,
- [x] test repozytorium przechodzi na izolowanym PostgreSQL,
- [x] aplikacja mobilna pozostaje bez zależności od Admin API.

## Technical notes

- stabilne kody oraz `mobile_code` nie są edytowalne po utworzeniu,
- `DELETE` ma semantykę idempotentnej archiwizacji; fizyczne kasowanie nie jest
  częścią publicznego API,
- ścieżka obrazu jest wyłącznie względną metadaną; zapis pliku należy do
  TASK-0020,
- wymiary i koszt spinu pozostają własnością `rules_versions` w TASK-0021.

## Expected files

- `services/api/alembic/versions/0002_games_and_symbols.py`
- `services/api/src/game_predictor_api/domain/catalog.py`
- `services/api/src/game_predictor_api/application/catalog.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/storage/catalog_repository.py`
- `services/api/src/game_predictor_api/schemas/catalog.py`
- `services/api/src/game_predictor_api/api/catalog.py`
- `services/api/tests/**`
- `packages/admin-api-client/**`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run openapi:generate
npm run openapi:check
npm run quality
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_postgres_baseline.ps1
```

## Risks / open questions

- Brak pytania blokującego. Reguła „użyty symbol nie jest fizycznie usuwany”
  stanie się egzekwowalna po dodaniu wersjonowanych zależności w M2.3; do tego
  czasu publiczne API i tak oferuje wyłącznie archiwizację.

## Outcome

### Changed

- Dodano niezależną od HTTP/ORM domenę katalogu oraz serwis aplikacyjny dla
  gier i symboli.
- Migracja `0002_games_symbols` tworzy enumy, tabele, klucz obcy, constraints
  zakresu i unikalności oraz ma pełną ścieżkę downgrade.
- Repozytorium SQLAlchemy mapuje konflikty PostgreSQL na stabilne błędy domenowe.
- Dodano dziesięć operacji CRUD pod `/api/v1/admin/games`; `DELETE` archiwizuje.
- Zregenerowano OpenAPI i klient TypeScript, który udostępnia typowane operacje
  gier oraz symboli.
- Ustabilizowano generowanie klienta na Windows przez zapis do katalogu
  tymczasowego przed formatowaniem i podmianą artefaktu.
- Powtarzalny timeout jednego testu integracyjnego mobile pod obciążeniem pełnej
  bramki otrzymał lokalny limit 15 sekund; jego zachowanie nie zostało zmienione.

### Verification results

- `npm run quality` — sukces: format, drift OpenAPI, lint, PowerShell, typecheck,
  63 testy mobile, 4 panelu, 2 klienta, 23 shared i 85 testów Python przeszło;
  2 testy PostgreSQL są celowo pomijane w zwykłym przebiegu.
- `scripts/verify_postgres_baseline.ps1` — sukces: 2/2 fizyczne testy na
  PostgreSQL 18.4, w tym migracje `upgrade → downgrade → upgrade`, CRUD
  repozytorium i constraints unikalności.
- `npm run openapi:generate` i `npm run openapi:check` — sukces.
- Snapshot M1 i fixture M1 pozostały poprawne.

### Not completed

- Nie dodano ekranów panelu; lista i formularz gry należą do TASK-0019.
- Nie dodano obsługi plików referencyjnych ani UI symboli; to TASK-0020.
- Nie dodano wersji reguł, wymiarów ani kosztu spinu; to M2.3.

### Documentation updates

- Zaktualizowano `API_CONTRACT.md`, `DATA_MODEL.md`, `TECH_STACK.md`, README,
  plan M2, Current State i rejestr decyzji.
- D-024 utrwala stabilne kody oraz archiwizującą semantykę `DELETE`.

### Recommended next task

- Po poleceniu właściciela rozpocząć TASK-0019 — Admin shell and games identity
  UI.
