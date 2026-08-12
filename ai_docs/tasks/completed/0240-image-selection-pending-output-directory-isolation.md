---
title: TASK-0240 image selection pending output directory isolation
status: done
release: "0.5"
last_updated: 2026-08-12
---

# TASK-0240 — Image selection pending output directory isolation

## Goal

Zapobiec eksportowaniu decyzji historycznego runu do katalogu wybranego jako
wynik nowej, jeszcze nieutworzonej partii selekcji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Scope

- [x] Oddzielić oczekujący uchwyt folderu nowego uploadu od aktywnego katalogu
      historycznego runu.
- [x] Powiązać oczekujący folder z `runId` dopiero po poprawnym create-run.
- [x] Wymagać zgodnego `runId` przy progresywnym i ręcznym zapisie JPEG-a.
- [x] Dodać test regresyjny dla wybrania folderu przy widocznym starym runie.
- [x] Zaktualizować wymagania, architekturę i bieżący stan.

## Verification

```powershell
node --experimental-strip-types --test test/image-selection-workspace-contract.test.mjs
npm.cmd run typecheck
npm.cmd test
npm.cmd run lint
```

## Outcome

`chooseOutputFolder` zapisuje wyłącznie stan `pending` i nie dotyka IndexedDB
ani aktywnego powiązania historycznego runu. Po pomyślnym uploadzie uchwyt jest
atomowo przypisywany do zwróconego `runId`. Każdy zapis używa aktywnego
powiązania `runId + directory` i odmawia pracy, gdy identyfikator jest inny.

Skupiony test przeszedł 15/15. Pełny Admin przeszedł 195/195, TypeScript oraz
ESLint bez błędów.
