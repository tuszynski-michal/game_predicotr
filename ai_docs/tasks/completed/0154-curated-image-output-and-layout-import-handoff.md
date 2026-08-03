---
title: TASK-0154 curated image output and layout import handoff
status: done
release: "0.4"
last_updated: 2026-08-03
---

# TASK-0154 — Curated image output and layout import handoff

## Status

`done`

## Goal

Zapisać jeden niezmienny JPEG na rozpoznany zakres wraz z manifestem oraz
bezpiecznie przekazać kompletny run do istniejącego `Importu layoutów`.

## Context

Automatyczny wybór nie ma wartości operacyjnej bez odtwarzalnego wyniku.
Kopiowanie zamiast przenoszenia chroni źródła, a bezpośredni handoff eliminuje
ponowny upload wybranych zdjęć.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0153-fast-sequential-image-grouping-and-quality-selection.md`

## Scope

- tworzyć content-addressed output w `data/exports/image-selections`,
- nadawać nazwy `seq_<start:06>-<end:06>__<sha-prefix>.jpg`,
- zapisać kanoniczny checksumowany manifest bez ścieżek absolutnych,
- atomowo publikować run dopiero po weryfikacji wszystkich kopii,
- nie usuwać ani nie przenosić plików źródłowych,
- utworzyć idempotentny handoff token/source dla właściwego importu,
- zablokować handoff przy nierozwiązanej grupie lub rozjechanej checksumie,
- pokazać akcję i nawigację do `Importu layoutów`.

## Out of scope

- wykonanie pełnego pipeline'u w selektorze,
- manualny modal,
- automatyczne kasowanie historycznych outputów,
- eksport do chmury.

## Acceptance criteria

- [x] Każdy wybrany zakres występuje dokładnie raz w manifeście i katalogu.
- [x] Nazwa używa rzeczywistego dodatniego zakresu i checksumy.
- [x] Źródłowy folder jest bajtowo i strukturalnie niezmieniony.
- [x] Awaria przed atomowym commitem nie publikuje częściowego manifestu.
- [x] Handoff ponownie sprawdza manifest i checksumy wszystkich zdjęć.
- [x] Ten sam handoff jest idempotentny i nie duplikuje logicznego źródła.
- [x] `Rozpocznij import` pozostaje jawną osobną akcją użytkownika.
- [x] Właściwy image import zachowuje provenance runu selekcji.

## Technical notes

Manifest jest źródłem prawdy outputu; nazwa pliku jest pomocą operatorską, nie
identyfikatorem domenowym. Fizyczna deduplikacja może użyć hardlinku tylko w
zarządzanym storage i po sprawdzeniu zachowania na Windows.

## Expected files

- `services/api/src/game_predictor_api/application/`
- `services/api/src/game_predictor_api/api/`
- `services/worker/src/game_predictor_worker/images/selection/`
- `apps/admin/src/`
- `services/api/tests/`
- `services/worker/tests/`
- `apps/admin/test/`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests services/worker/tests -q
npm.cmd test --workspace @game-predictor/admin
npm.cmd run openapi:check
```

## Risks / open questions

- Przed cleanupem tymczasowego uploadu należy fsync/odczytem potwierdzić output
  i manifest; samo istnienie ścieżki nie wystarcza.

## Outcome

Ukończono 2026-08-03.

- Worker publikuje wybrane JPEG-i i kanoniczny manifest pod content address,
  weryfikuje kopie odczytem i udostępnia wynik dopiero po atomowym rename.
- Manifest nie zawiera czasu, hosta ani ścieżek absolutnych; nazwy JPEG używają
  dodatniego zakresu i prefiksu checksumy, a retry identycznego wyniku jest
  idempotentny.
- API trwale zapisuje ścieżkę oraz SHA-256 outputu, a handoff ponownie sprawdza
  manifest, wszystkie pliki, proweniencję i kompletność decyzji grup.
- Handoff używa stabilnego logicznego `selectionId = runId`; import zapisuje
  `imageSelectionRunId`, lecz pełny pipeline startuje dopiero po osobnym
  kliknięciu użytkownika.
- Admin pokazuje akcję dopiero dla opublikowanego outputu, przenosi poświadczony
  token do sekcji `Import layoutów` i nie uruchamia importu automatycznie.
- Weryfikacja: 22 testy selektora/outputu, 27 testów API związanych z runem,
  stagingiem i jobami, 149 testów Admina, 27 testów klienta API, Ruff, typecheck
  Admina, mypy nowego publishera oraz `openapi:check`.
- Pełny repozytoryjny `format:check` pozostaje historycznie czerwony dla
  niezwiązanych plików; wszystkie zmienione w tym zadaniu pliki frontendowe
  zostały sformatowane osobno.
