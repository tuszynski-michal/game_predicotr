---
title: TASK-0021 Rules versions domain, API and dimensions UI
status: done
last_updated: 2026-07-27
---

# TASK-0021 — Rules versions domain, API and dimensions UI

## Status

`done`

## Goal

Umożliwić administratorowi utworzenie dla wybranej gry wersjonowanego draftu
reguł, ustawienie liczby rzędów, kolumn i kosztu spinu oraz późniejszą edycję
tych pól przez typowane Admin API i panel.

## Context

Gra oraz jej symbole istnieją po M2.2, ale wymiary i koszt spinu są częścią
historycznie odtwarzalnej wersji reguł. Ten pion otwiera M2.3 i przygotowuje
rekord nadrzędny dla paylines i payout rules z kolejnych zadań.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-025 w `ai_docs/process/DECISION_LOG.md`

## Scope

- domenowy model `rules_version` ze statusami `draft`, `published`, `archived`,
- migracja Alembic z constraints wymiarów, kosztu, wersji i unikalności,
- deterministyczne listowanie oraz tworzenie i edycja draftu przez Admin API,
- przydzielanie kolejnego numeru wersji po stronie serwera,
- regeneracja klienta TypeScript z OpenAPI,
- sekcja panelu do wyboru gry, listowania wersji oraz tworzenia i edycji
  wymiarów i kosztu spinu,
- testy domeny, API, migracji, repozytorium i logiki panelu.

## Out of scope

- przypisywanie symboli do wersji reguł i `minimum_match_length`,
- edytor paylines,
- payout rules,
- publikacja i archiwizacja wersji reguł,
- generowanie datasetu albo APK.

## Acceptance criteria

- [x] migracja tworzy i odwracalnie usuwa `rules_versions` oraz enum statusu,
- [x] `rows` i `columns` są dodatnimi `smallint`, `spin_cost >= 0`, a
  `(game_id, version)` jest unikalne,
- [x] nowy rekord otrzymuje kolejny numer wersji oraz status `draft` bez
  przyjmowania tych wartości z UI,
- [x] API listuje wersje gry i pozwala pobrać oraz edytować wyłącznie draft,
- [x] wersja `published` albo `archived` jest chroniona przed edycją,
- [x] panel pozwala utworzyć draft 3 × 5 z kosztem spinu oraz poprawić jego pola,
- [x] typy i wywołania panelu pochodzą z wygenerowanego klienta,
- [x] testy i bramki jakości zmienionych części przechodzą.

## Technical notes

API przydziela `max(version) + 1` po zablokowaniu rekordu gry w tej samej
transakcji. Lista jest zwracana od najnowszego numeru wersji. TASK-0021
modeluje wszystkie trzy statusy, ale nie udostępnia przejść statusów; ich
walidacja i niezmienna publikacja należą do TASK-0024.

## Expected files

- `services/api/alembic/versions/0003_rules_versions.py`
- `services/api/src/game_predictor_api/{domain,application,storage,schemas,api}/`
- `services/api/tests/`
- `packages/admin-api-client/`
- `apps/admin/src/features/rules/`
- `apps/admin/src/features/catalog/catalog-workspace.tsx`
- `apps/admin/src/components/admin-shell.tsx`
- `apps/admin/src/app/globals.css`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/{CURRENT_STATE,DECISION_LOG}.md`

## Verification

```powershell
npm run openapi:generate
npm run quality
npm run admin:build
npm run api:test:integration
```

## Risks / open questions

- Równoległe utworzenie dwóch wersji musi być serializowane blokadą gry; sam
  constraint unikalności jest wyłącznie ostatnią linią obrony.
- Brak pytań produktowych blokujących ten zakres.

## Outcome

Zadanie ukończone 2026-07-27. Pierwszy pion M2.3 tworzy wersjonowany rekord
nadrzędny dla przyszłych paylines i payout rules oraz udostępnia go w panelu.

### Changed

- dodano odwracalną migrację `0003_rules_versions`, enum statusu, constraints,
  klucz obcy oraz indeks gry,
- dodano czystą domenę, serwis aplikacyjny i repozytorium SQLAlchemy z blokadą
  rekordu gry oraz numeracją `max(version) + 1`,
- dodano listowanie, tworzenie, pobieranie i aktualizację draftu przez Admin API
  ze stabilnymi błędami oraz wygenerowany klient TypeScript,
- dodano responsywną sekcję panelu z wyborem gry, domyślnym draftem 3 × 5 / 10,
  historią wersji i edycją wyłącznie statusu `draft`,
- dodano testy domeny, API, OpenAPI, migracji, fizycznego repozytorium,
  klienta i logiki panelu.

### Verification results

- `npm run quality`: zaliczone; 23 testy panelu, 63 mobile, 3 klienta,
  23 shared oraz 94 testy Python przy 2 jawnych skipach PostgreSQL,
- `npm run db:baseline:verify`: 2/2 fizyczne testy PostgreSQL, w tym
  `upgrade → downgrade → upgrade` i repozytorium rules versions,
- `npm run admin:build`: produkcyjny build Next.js zaliczony,
- OpenAPI i wygenerowany klient nie wykazują driftu.

### Not completed

- paylines, minima symboli, payout rules oraz przejścia publikacji i archiwizacji
  pozostają zgodnie z planem w TASK-0022–TASK-0024.

### Documentation updates

- zaakceptowano D-025 i dopisano szczegółowy kontrakt Rules Versions,
- zaktualizowano plan M2, stos migracji i bieżący stan projektu.

### Recommended next task

- `TASK-0022 — Payline grid editor and duplicate validation`
