---
title: TASK-1189 — Bieżący stan kandydata w widoku uczenia
status: done
---

# TASK-1189 — Bieżący stan kandydata w widoku uczenia

## Status

`done`

## Goal

Widok uczenia korekt pokazuje obok niezmiennego werdyktu uczenia najnowszą ocenę
kandydata oraz to, czy kandydat jest domyślny i przypisany do gry.

## Context

Po TASK-1188 kandydat Mumie a2 `bf327cfa` dostał osobną ocenę gate v4 PASS
(`6f7bcc1d`) i został zastosowany poleceniami rejestru. Panel uczenia `63767b36`
dalej pokazuje tylko przypięty werdykt REVISE (`8723857d`), co operator uznał za
mylące (2026-11-12).

## Dependencies / entry conditions

- `main` 2d396e4d. Bez migracji; tylko odczyt.

## Recommended execution

Claude Opus 5.5, reasoning medium; jednorazowy task na polecenie operatora, bez
audytu krzyżowego.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [D-604](../../process/decisions/DECISION_LOG_2026.md#d-604--bramka-oceny-siatek-odporna-na-szum)

## Scope

- Czysta funkcja `candidate_status` (domena) i pole `candidate` widoku uczenia
  (GET pojedynczy i lista), pomijane, gdy uczenie nie ma kandydata.
- Panel admina: przy przebiegu i w szczegółach — nowsza ocena, „domyślny”,
  „przypisany do gry”; pierwotny werdykt bez zmian.
- OpenAPI, klient, testy.

## Out of scope

- Zmiana zapisanego werdyktu uczenia, ścieżki „zastosuj” ani przypięcia oceny.

## Acceptance criteria

- [x] Uczenie z kandydatem zwraca najnowszą ukończoną ocenę jakości (bez porównań
      z przypisanym modelem) z werdyktem i wersją bramki.
- [x] Panel dla `63767b36` pokazuje REVISE oraz „nowsza ocena PASS (bramka v4)”,
      „domyślny” i „przypisany do gry”.
- [x] Widok bez kandydata ma ten sam JSON co dotąd.

## Outcome

Commit: v1.7.615 / `ca101e1ad909ec15df402d0c3862caab685ba499`.

### Changed

- `domain/grid_learning_candidate_status.py` (`candidate_status`), pole
  `candidate` w `GridCorrectionLearningView` (pomijane przy braku), wzbogacenie
  `get`/`list` w `application/grid_correction_learning.py` (najnowsza ukończona
  ocena jakości bez porównań z przypisanym, unieważnione pominięte).
- Panel: `learning-candidate-status.ts` i sekcja „Bieżący stan kandydata” oraz
  sufiks na liście przebiegów; eksport typu w wrapperze klienta; OpenAPI/klient.

### Verification results

- Odczyt na danych operatora kodem z worktree: `63767b36` = REVISE oraz
  `candidate` PASS gate v4 (`6f7bcc1d`), domyślny i przypisany; starsze
  przebiegi bez zmian przypisania.
- pytest: nowe 3 + API uczenia + apply: 77 PASS; mypy/ruff zmienionych modułów
  bez błędów; `openapi:check` 0; typecheck admina 0; admin lint 0; testy admina
  859/859; klient 167/167.

### Not completed

- Brak audytu krzyżowego (task jednorazowy).

### Documentation updates

- `requirements/VISION_LAB.md`, `CURRENT_STATE.md`.

### Recommended next task

- Brak.
