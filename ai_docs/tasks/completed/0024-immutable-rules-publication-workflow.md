---
title: TASK-0024 Immutable rules publication workflow
status: done
last_updated: 2026-07-27
---

# TASK-0024 — Immutable rules publication workflow

## Status

`done`

## Goal

Udostępnić deterministyczny raport gotowości oraz atomową publikację kompletnej
wersji reguł, po której wymiary, paylines, konfiguracje symboli i payout rules
są niezmienne.

## Context

TASK-0021–0023 utworzyły edytowalny draft wersji reguł. TASK-0024 domyka M2.3
przez walidację pełnego kontraktu payout-v2 i kontrolowane przejścia statusu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- D-028 w `ai_docs/process/DECISION_LOG.md`

## Scope

- czysta, deterministyczna walidacja gotowości wersji reguł,
- co najmniej jedna aktywna payline i jeden aktywny zwykły symbol,
- walidacja aktywnych konfiguracji symboli i pełnej macierzy payoutów,
- zakaz payoutów jokera, nieaktywnego symbolu i długości poza zakresem,
- wymaganie ściśle rosnących payoutów dla każdego zwykłego symbolu,
- endpoint raportu gotowości,
- atomowy endpoint publikacji z blokadą rekordu i serwerowym timestampem,
- idempotentna archiwizacja opublikowanej wersji,
- stabilne błędy oraz szczegółowa lista problemów gotowości,
- generowany klient TypeScript,
- modal potwierdzenia publikacji i prezentacja raportu w panelu,
- archiwizacja opublikowanej wersji po jawnym potwierdzeniu,
- testy domeny, API, PostgreSQL, klienta i logiki panelu.

## Out of scope

- dataset_versions, layouty i publikacja datasetu,
- precomputing payoutów,
- generowanie SQLite lub APK,
- automatyczne archiwizowanie poprzedniej opublikowanej wersji.

## Acceptance criteria

- [x] raport gotowości jest deterministyczny i wskazuje wszystkie problemy,
- [x] publikacja wymaga aktywnej payline i aktywnego zwykłego symbolu,
- [x] każdy aktywny zwykły symbol ma komplet payoutów od minimum do `columns`,
- [x] payouty jednego symbolu rosną ściśle wraz z długością,
- [x] joker, nieaktywny symbol i długość poza zakresem nie mają aktywnych payoutów,
- [x] niegotowy draft nie zmienia statusu ani `published_at`,
- [x] gotowy draft jest atomowo zmieniany na `published`,
- [x] drugi publish i każda późniejsza mutacja danych są blokowane,
- [x] archiwizacja zmienia `published` na `archived` i zachowuje `published_at`,
- [x] panel pokazuje raport, wymaga potwierdzenia i blokuje podwójny submit,
- [x] OpenAPI, generowany klient, testy i produkcyjny build panelu przechodzą.

## Technical notes

Aktywne rekordy `rules_version_symbols` definiują skład wersji. Nieaktywne
konfiguracje mogą pozostać w historii, ale nie mogą mieć aktywnych payout rules.
Publikacja nie archiwizuje automatycznie wcześniejszych wersji tej samej gry.

GET raportu jest read-only. POST publikacji ponownie wykonuje identyczną
walidację po `SELECT ... FOR UPDATE`, więc wynik nie może zostać unieważniony
przez równoległą mutację w tej samej lokalnej bazie.

## Expected files

- `services/api/src/game_predictor_api/{domain,application,storage,schemas,api}/`
- `services/api/tests/`
- `packages/admin-api-client/`
- `apps/admin/src/features/rules/`
- `apps/admin/src/app/globals.css`
- `ai_docs/requirements/{ADMIN_APP,ALGORITHMS}.md`
- `ai_docs/architecture/{API_CONTRACT,DATA_MODEL}.md`
- `ai_docs/process/{CURRENT_STATE,DECISION_LOG}.md`

## Verification

```powershell
npm run openapi:generate
npm run quality
npm run admin:build
npm run db:baseline:verify
```

## Risks / open questions

- Blokada rekordu chroni publikację i inne ścieżki publikacji; aplikacja jest
  lokalna i nie wymaga rozproszonego lock managera.
- Brak pytań produktowych blokujących zadanie.

## Outcome

Zadanie ukończone 2026-07-27. Bramka G2.3 została zaliczona.

### Changed

- Dodano czysty walidator raportujący wszystkie blokady gotowości w stabilnej
  kolejności.
- Dodano read-only preflight, atomową publikację pod `SELECT ... FOR UPDATE`
  oraz idempotentną archiwizację zachowującą `published_at`.
- Wszystkie mutacje danych wersji reguł blokują ten sam rekord, więc nie mogą
  wyprzedzić publikacji.
- Rozszerzono OpenAPI i wygenerowany klient TypeScript.
- Panel otrzymał modal raportu i potwierdzenia publikacji oraz potwierdzaną
  archiwizację.
- Uzupełniono testy domeny, API, klienta, panelu i fizycznego PostgreSQL.

### Verification results

- `format:check`, `openapi:check`, lint i typecheck: passed.
- Testy: 113 Python (2 integracyjne pomijane w standardowym przebiegu), 63
  mobile, 36 admin, 23 shared TypeScript, 6 klienta API.
- `db:baseline:verify`: 2/2 testy na fizycznym PostgreSQL passed.
- `admin:build`: produkcyjny build Next.js passed.
- Walidacja snapshotu `m1-fixture.2` i fixture: passed.

### Not completed

- Nie rozpoczęto datasetów, precomputingu, snapshotu ani APK; należą do
  kolejnych etapów.
- Nie dodano migracji, ponieważ istniejący schemat zawierał status i
  `published_at`.

### Documentation updates

- Zaktualizowano wymagania panelu, model danych, kontrakt API, architekturę
  systemu, strategię testów, plan M2, dziennik decyzji i bieżący stan.

### Recommended next task

- `TASK-0025 — Mock dataset generation and staging`
