---
title: TASK-0287 — Finalizacja zdalnej ręcznej selekcji
status: done
last_updated: 2026-08-24
---

# TASK-0287 — Finalizacja zdalnej ręcznej selekcji

## Status

`done`

## Goal

Zamykać zdalną partię dopiero po trwałym uzgodnieniu operacji, transferów,
akcji hosta i plików oraz publikować zgodne manifesty lokalnego modułu v1.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- deterministyczny preview blokad i raport rozbieżności,
- transakcyjna bariera finalizacji po `expectedServerRevision`,
- bezpieczna publikacja output-v1, trace-v1 i manifestu operacyjnego,
- read-only ukończonej partii,
- kontrolowane host-only reopen dokładnej partii,
- typowane API, Reviewer i panel hosta,
- testy zgodności, konfliktów i crash-window retry.

## Out of scope

- zmiana schematów publicznych manifestów v1,
- automatyczny trening rankera,
- przechowywanie obrazów w bazie,
- recovery/GC należące do TASK 16.

## Acceptance criteria

- [x] Finalizacja nie przechodzi przy aktywnej operacji, transferze lub akcji hosta.
- [x] Każda aktualnie wybrana pozycja jest `synced` i zgodna checksumowo z plikiem.
- [x] Output zawiera wyłącznie aktualne, materializowane generacje bez duplikatu zakresu.
- [x] Trace zachowuje chronologię zastosowanych decyzji i jawne undo.
- [x] Trzy manifesty są publikowane atomowo per plik i można bezpiecznie wznowić retry.
- [x] Ukończona partia jest read-only, a reopen wymaga lokalnego exact targetu.
- [x] Zdalny proxy nie udostępnia reopen ani podmiany manifestów.
- [x] Istniejący lokalny kontrakt output/trace v1 pozostaje zgodny.

## Outcome

Wdrożono czysty preview, transakcyjną finalizację, journal odporny na crash,
trzy manifesty, read-only Reviewer i checksum-bound host-only reopen. Kontrakty
OpenAPI oraz oba interfejsy zostały zaktualizowane bez migracji i bez zmiany
publicznych schematów manifestów v1. Bramka obejmuje testy projekcji,
repozytorium, filesystemu, proxy, transportu i UI.
