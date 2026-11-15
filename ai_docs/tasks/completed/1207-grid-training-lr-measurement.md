---
title: TASK-1207 — Pomiar tempa nauki uczenia korekt siatek
status: done
last_updated: 2026-11-13
---

# TASK-1207 — Pomiar tempa nauki uczenia korekt siatek

## Status

`done`

## Goal

Zmierzyć, czy tempo nauki 2e-5 zamiast 1e-4 zapobiega pogorszeniu modelu przy ponownym
uczeniu korekt, i wprowadzić je tylko przy korzystnym wyniku obu przypadków.

## Context

Etap B naprawy po uczeniu `12ffda06` (D-612). Operator: „Etap A, potem B”, z pomiarem
1–2 przebiegów na GPU.

## Dependencies / entry conditions

- TASK-1205 (próg kroku 0) na tej gałęzi; GPU wolne.

## Recommended execution

Claude Opus 5.5, reasoning medium; bez dodatkowego review (pomiar bez zmiany kodu).

## Relevant docs

- `AGENTS.md`
- [D-612](../../process/decisions/DECISION_LOG_2026.md#d-612--uczenie-korekt-siatek-musi-pobić-własny-model-bazowy)

## Scope

- Dwa przebiegi trenera z 2e-5: `abe39bce`+`7e239be4` (przypadek spadku) i kontrolnie
  `bf327cfa`+`0630f2cc` (przypadek poprawy przy 1e-4); raport i decyzja.

## Out of scope

- Zmiana presetu bez korzystnego pomiaru; rejestracja kandydatów z pomiaru.

## Acceptance criteria

- [x] Oba przebiegi zmierzone na tych samych danych i ziarnie co oryginały.
- [x] Decyzja oparta na pomiarze zapisana w D-614 i raporcie jakości.

## Verification

Przebiegi plikowe poza kolejką (bez bazy), wynik w `result-1.json` katalogów pomiaru.

## Outcome

Commit: v1.7.638 / `49009e4ed7ea9d7c911a4489a783a0099ed6180d`.

### Changed

- Raport `ai_docs/quality/GRID_TRAINING_LR_MEASUREMENT_20261113.md`, decyzja D-614.
  Bez zmiany kodu: preset zachowuje 1e-4.

### Verification results

- 2e-5 na `abe39bce`: 0,678 → 0,573/0,573/0,573, `GRID_TRAINING_NO_IMPROVEMENT`.
- 2e-5 na `bf327cfa`: 0,743 → 0,743/0,743/0,681, `GRID_TRAINING_NO_IMPROVEMENT`
  (1e-4 dało 0,806). Próg TASK-1205 zadziałał na prawdziwych danych w obu przebiegach.

### Not completed

- Usunięcie katalogów pomiaru (2 × ~228 MB) — decyzja operatora.

### Documentation updates

- D-614 (wpis, indeks; D-583 do archiwum indeksu), raport jakości.

### Recommended next task

- Więcej korekt siatek przed kolejnym uczeniem; ewentualnie większa VALIDATION.
