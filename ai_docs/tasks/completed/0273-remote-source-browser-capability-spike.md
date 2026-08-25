---
title: Remote source browser capability and filesystem feasibility spike
status: done
last_updated: 2026-08-23
---

# TASK-0273 — Browser capability i filesystem feasibility spike

## Status

`done`

## Goal

Jednoznacznie potwierdzić albo odrzucić browser-only MVP zdalnego wyboru jednej
partii bez tworzenia produkcyjnego route, uploadu lub stanu serwerowego.

## Context

To TASK 1 planu `REMOTE_MANUAL_IMAGE_SELECTION.md`. Wynik jest checkpointem
przed wydzieleniem wspólnego silnika w TASK 2.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`

## Scope

- Izolowany lokalny fixture browserowy dla capability, IndexedDB handle,
  permission, relink i fallbacku `webkitdirectory`.
- Deterministyczny manifest metadanych bez odczytu bajtów i bez pełnych ścieżek.
- Testy 1/500/1000 sztucznych JPEG-ów oraz content-addressed raport v1.
- Udokumentowana macierz Chrome/Edge/fallback i decyzja GO/NO-GO.

## Out of scope

- Shared core, zmiany lokalnego workspace, API, baza, upload, publiczny link,
  tunel, prawdziwe dane użytkownika i produkcyjny format JSON.

## Acceptance criteria

- [x] Fixture nie jest częścią produkcyjnego routingu ani buildu aplikacji.
- [x] Manifest jest deterministyczny, nie zawiera bajtów ani ścieżek absolutnych.
- [x] IndexedDB roundtrip/relink i permission mają jawne, testowalne stany.
- [x] Fallback `webkitdirectory` jest oznaczony jako sesyjny i wymaga relink.
- [x] Benchmark 1/500/1000 nie dekoduje wszystkich plików.
- [x] Raport v1 ma zweryfikowaną checksumę i decyzję GO/NO-GO z ograniczeniami.
- [x] Nie powstał endpoint, tunel, upload, migracja ani runtime state aplikacji.

## Technical notes

- Automatyczny browser smoke może użyć uchwytu OPFS do sprawdzenia structured
  clone w IndexedDB. Nie jest to dowód trwałego uprawnienia do wybranego
  katalogu OS; ten przypadek pozostaje oddzielnym manualnym scenariuszem.
- MVP nie może zależeć od Background Sync ani od trwałego permission grant.

## Expected files

- `apps/reviewer/test/fixtures/remote-source-capability-spike.mjs`
- `apps/reviewer/test/fixtures/remote-source-capability-spike.html`
- `apps/reviewer/test/remote-source-capability-spike.test.mjs`
- `apps/reviewer/test/run-remote-source-capability-spike.mjs`
- `ai_docs/quality/REMOTE_SOURCE_BROWSER_CAPABILITY_SPIKE.md`
- `ai_docs/quality/remote-source-capability-report-v1.json`
- `ai_docs/quality/remote-source-capability-report-v1.schema.json`

## Verification

```powershell
npm test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
node apps/reviewer/test/run-remote-source-capability-spike.mjs --check
```

## Risks / open questions

- Automatyzacja nie może zaakceptować natywnego pickera w imieniu użytkownika;
  raport musi odróżnić smoke OPFS od ręcznego testu wybranego folderu OS.
- Rzeczywiste zachowanie permission po zamknięciu całej przeglądarki zależy od
  wersji i polityki profilu, dlatego relink pozostaje obowiązkowym fallbackiem.

## Outcome

TASK 1 zakończony decyzją `GO_WITH_CONSTRAINTS`.

### Changed

- Dodano izolowany browser fixture, deterministyczny manifest metadanych,
  permission/relink helpers, testy i generator content-addressed raportu.
- Dodano raport jakości, schemat JSON oraz macierz Chrome/Edge/fallback.

### Verification results

- Reviewer tests: `49/49` passed.
- Reviewer typecheck: passed.
- Reviewer lint: passed.
- Celowane testy spike: `9/9` passed.
- Node syntax checks i report `--check`: passed.
- Celowany Prettier: passed.
- Rzeczywisty Chromium smoke: capability detection, OPFS→IndexedDB, reload i
  zamknięcie/ponowne otwarcie karty — passed.

### Not completed

- Nie wykonano natywnego wyboru katalogu OS, odmowy/regrantu ani osobnego testu
  w zewnętrznym Edge. Pozostają ręczną bramką przed publicznym rolloutem.
- Nie rozpoczęto TASK 2.

### Documentation updates

- `ai_docs/quality/REMOTE_SOURCE_BROWSER_CAPABILITY_SPIKE.md`
- `ai_docs/quality/remote-source-capability-report-v1.json`
- `ai_docs/quality/remote-source-capability-report-v1.schema.json`
- Status TASK 1 i `CURRENT_STATE.md`.

### Recommended next task

- Po zatwierdzeniu checkpointu: TASK 2 — wspólny silnik selekcji i adapter
  lokalny, bez remote API/outboxu.
