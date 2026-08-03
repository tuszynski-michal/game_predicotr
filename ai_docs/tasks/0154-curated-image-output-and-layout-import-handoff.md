---
title: TASK-0154 curated image output and layout import handoff
status: todo
release: "0.4"
last_updated: 2026-08-02
---

# TASK-0154 — Curated image output and layout import handoff

## Status

`todo`

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
- `ai_docs/tasks/0153-fast-sequential-image-grouping-and-quality-selection.md`

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

- [ ] Każdy wybrany zakres występuje dokładnie raz w manifeście i katalogu.
- [ ] Nazwa używa rzeczywistego dodatniego zakresu i checksumy.
- [ ] Źródłowy folder jest bajtowo i strukturalnie niezmieniony.
- [ ] Awaria przed atomowym commitem nie publikuje częściowego manifestu.
- [ ] Handoff ponownie sprawdza manifest i checksumy wszystkich zdjęć.
- [ ] Ten sam handoff jest idempotentny i nie duplikuje logicznego źródła.
- [ ] `Rozpocznij import` pozostaje jawną osobną akcją użytkownika.
- [ ] Właściwy image import zachowuje provenance runu selekcji.

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

Do uzupełnienia po realizacji.
