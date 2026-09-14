# TASK-0540 — zgodna tożsamość preflightu niepełnych boków v2

## Status

`done`

## Goal

Usunąć fałszywy `IMAGE_PAGE_GEOMETRY_PREFLIGHT_IDENTITY_MISMATCH` przy
odświeżaniu raportu stagingu, którego poprawny preflight używa aktualnego
snapshotu bocznych niepełnych plansz v2.

## Context

Staging `117829 - 128268 cut` ma job
`b028ce0e-0b37-4a3a-9579-a9181b24bb19` z wariantem
`structured_lattice_v4_partial_sides` oraz polityką
`structured-lattice-v4-lateral-partial-v2`. API zwraca ten job jako należący
do raportu. Admin nadal uznaje wyłącznie historyczną politykę v1, dlatego po
odczycie poprawnej odpowiedzi zgłasza konflikt tożsamości.

## Dependencies / entry conditions

- API i wygenerowany klient obsługują polityki v1 oraz v2.
- Wariant per-run pozostaje `structured_lattice_v4_partial_sides`.
- Nie zmienia się tożsamość gry, stagingu ani manifestu źródeł.

## Recommended execution

`gpt-5.6-sol`, reasoning `high`. Zmiana dotyczy jednego współdzielonego
predykatu tożsamości i jego trzech konsumentów; mocniejszy model jest potrzebny
tylko po wykryciu rozbieżności w backendowym snapshotowaniu albo trwałości
manifestu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0533-partial-grid-learning-profile.md`
- `ai_docs/tasks/completed/0514-v0-10-4-admin-launcher-and-report.md`

## Scope

- Zastąpić rozproszone porównania polityki v1 wspólną walidacją obsługiwanych
  snapshotów v1/v2.
- Zachować ścisłe sprawdzanie wariantu, gry, stagingu, checksum manifestu i
  managed-source identity.
- Objąć tą samą regułą raport browserowy, dopasowanie joba importu i
  managed-original reprocessing.
- Dodać regresję v2 oraz odrzucenia nieznanej wersji.
- Potwierdzić stan wskazanego joba bez retry, anulowania ani zmian danych.

## Out of scope

- Zmiana algorytmu, polityki lub zawartości snapshotu v2.
- Automatyczne uruchamianie, retry albo anulowanie joba.
- Zmiana API, OpenAPI, bazy lub wygenerowanego klienta.

## Acceptance criteria

- [x] Poprawny browserowy preflight v2 pasuje do raportu.
- [x] Historyczny preflight v1 nadal pasuje do raportu.
- [x] Nieznana polityka lub obcy wariant nadal są odrzucane.
- [x] Import i managed reprocessing używają tej samej reguły wersji.
- [x] Testy Admina, typecheck, lint i build przechodzą.

## Technical notes

Źródłem błędu są trzy porównania tekstowe do
`structured-lattice-v4-lateral-partial-v1` w
`image-folder-import-actions.ts`. Proponowany czysty predykat przyjmuje
wyłącznie wariant `structured_lattice_v4_partial_sides` oraz znaną politykę v1
albo v2. Nie rozluźnia pozostałych pól tożsamości. Historyczny snapshot bez
wariantu pozostaje niezgodny z raportem, który jawnie wybrał wariant.

## Expected files

- Istniejący `apps/admin/src/features/imports/image-folder-import-actions.ts`
  — wspólny predykat snapshotu i trzej konsumenci.
- Istniejący `apps/admin/test/image-folder-import-actions.test.mjs` — regresje
  v1/v2 i wersji nieznanej.
- Dokumentacja wskazana w `Relevant docs`.

## Test cases

- Raport lateral + browserowy preflight policy v2 → `true`.
- Raport lateral + historyczny preflight policy v1 → `true`.
- Raport lateral + policy v3 albo inny wariant → `false`.
- Import i managed preflight policy v2 → zgodne dopasowanie.
- Raport standardowy + snapshot lateral → `false`.

## Verification

```powershell
node --experimental-strip-types --test --test-concurrency=1 test/image-folder-import-actions.test.mjs test/image-folder-import-panel-contract.test.mjs
npm test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

Kryterium zaliczenia: komendy kończą się kodem 0, raport v2 nie zgłasza
fałszywego konfliktu, a wskazany job ma świeży heartbeat albo status terminalny.

## Risks / open questions

- Wersje v1 i v2 są jedynymi wersjami dopuszczonymi przez bieżący kontrakt;
  przyszła wersja nadal wymaga jawnej aktualizacji predykatu i testu.
- Brak pytań blokujących.

## Outcome

### Changed

- Dodano jeden wspólny predykat snapshotu lateral partial, który dopuszcza
  wyłącznie znane polityki v1 i v2 przy dokładnym wariancie
  `structured_lattice_v4_partial_sides`.
- Raport browserowy, dopasowanie istniejącego importu i managed reprocessing
  używają teraz tej samej reguły. Pozostałe elementy tożsamości nie zostały
  rozluźnione.
- Dodano regresje dla v1, v2, nieznanej v3, raportu standardowego i identity
  importu.

### Verification results

- 42 skupione testy `image-folder-import-actions` i kontraktu panelu: passed.
- Pełny zestaw testów Admina: passed, kod zakończenia 0.
- Admin typecheck, lint i produkcyjny build: passed.
- Job `b028ce0e-0b37-4a3a-9579-a9181b24bb19` nadal ma status `created` i
  prawidłowy snapshot v2; nie wykonano retry ani anulowania.

### Not completed

- Nie zmieniano kolejności jobów, workera, API, snapshotu ani danych.

### Documentation updates

- Zaktualizowano wymagania wersjonowania snapshotu, kontrakt dopasowania
  tożsamości i `CURRENT_STATE.md`.

### Recommended next task

- Brak. Po przejęciu joba przez worker odświeżenie raportu powinno pokazać jego
  rzeczywisty stan bez konfliktu tożsamości.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0540 — zgodna tożsamość preflightu niepełnych boków v2 | gpt-5.6-sol | high | Błąd jest ograniczony do wersjonowanego kontraktu tożsamości, ale ta sama reguła chroni trzy ścieżki uruchomienia. | Nie; testy v1/v2 i odrzucenia nieznanej wersji chronią granicę. |
