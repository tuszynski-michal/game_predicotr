---
title: Pozycja kopii bez plansz i dłuższy odczyt podziału korekt
status: done
last_updated: 2026-11-11
---

# TASK-1186 — Pozycja kopii bez plansz i dłuższy odczyt podziału korekt

## Status

`done`

## Goal

Przycisk „Ulepsz siatki z korekt” dla Mumie a2 przestaje być blokowany przez
`GRID_CORRECTION_PROTECTION_CONFLICT` z ponownego importu, a odczyt podziału nie
kończy się `GRID_COHORT_TIMEOUT` przy obecnym rozmiarze danych.

## Context

Po imporcie z 2026-11-10 (`ce7b2f19`, 1121 zdjęć) każde nowe uczenie Mumie a2 było
zablokowane. 49 zdjęć tego importu to kopie bez plansz i bez własnego atestu, w tym
kopie zdjęć przypiętych do TRAIN i A z importu `fbca1ab5`. Reguła
`indivisible-import-v1` łączyła cały import w jedną grupę ze sprzecznymi
przypięciami. Odczyt podziału trwał 55–64 s przy budżecie 60 s. Kod sprzed
v1.7.603 dawał tę samą blokadę (to nie regresja D-602).

## Dependencies / entry conditions

- `main` v1.7.607 (`570fbe25`), baza `0184`.
- Operator zatwierdził w czacie obie zmiany 2026-11-11.

## Recommended execution

claude-opus-5-5 / high — mała zmiana domenowa chronionego podziału; zgoda
operatora w czacie zamiast planu. Audyt krzyżowy opcjonalny (decyzja operatora).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [D-577](../../process/decisions/DECISION_LOG_2026.md#d-577--podział-korekt-geometrii-z-atestów-i-trwała-ochrona-zdjęć)
- [D-602](../../process/decisions/DECISION_LOG_2026.md#d-602--skuteczne-uczenie-korekt-i-niezależny-pomiar-pełnych-wycinków)
- `ai_docs/requirements/VISION_LAB.md`

## Scope

- Kopia bez plansz przejmuje jednoznaczny atest dokładnej kopii (D-603).
- Budżet 120 s dla odczytu i startu podziału korekt; reszta komend 60 s.

## Out of scope

- Uruchomienie treningu, aktywacja modelu, zmiana defaultu.
- Zmiany historycznych przypięć, buforów i ledgera.
- Przyspieszenie samego odczytu podziału.

## Acceptance criteria

- [x] Ponowny import z przypiętymi kopiami bez plansz dostaje
  `copy-inherited-attestation-order-v1`, a kopie zachowują role oryginałów.
- [x] Kopia z planszami lub ze sprzecznymi zakresami nie przejmuje pozycji.
- [x] Test odtwarza błąd „Aliases or sessions have conflicting pins” na starym kodzie.
- [x] `CohortDeadline` przyjmuje budżet; podział korekt używa 120 s, domyślnie 60 s.
- [x] Podgląd na danych operatora (tylko odczyt) daje `canStart=true`.

## Technical notes

`_prepare_groups` zbiera atesty wszystkich źródeł według grupy kopii. Źródło bez
atestu, z `eligible_boards == 0` i bez `board_bindings` dostaje zakres, gdy zbiór
atestów jego kopii ma dokładnie jeden element. Kontrola nakładania zakresów i
spójności kopii w imporcie pozostaje bez zmian. Kopia jest w tej samej grupie co
oryginał (unia kopii), więc dziedziczy jego przypiętą rolę.

## Expected files

- `services/api/src/game_predictor_api/domain/grid_correction_split.py` — `_prepare_groups`
- `services/api/src/game_predictor_api/domain/grid_training_cohorts.py` — `LEARNING_SPLIT_SECONDS`
- `services/api/src/game_predictor_api/storage/grid_training_cohort_repository.py` — `CohortDeadline`
- `services/api/src/game_predictor_api/application/grid_correction_learning.py` — `_split`
- testy `test_grid_correction_split.py`, `test_grid_training_cohort_core.py`

## Test cases

- Import `n` z kopią TRAIN `a-0000` i kopią A `b-0019` bez plansz → podział
  wykonalny, metoda `copy-inherited-attestation-order-v1`, role zachowane.
- Ta sama kopia z planszą → `GRID_CORRECTION_PROTECTION_CONFLICT`.
- Kopia zdjęcia atestowanego w dwóch zakresach → import `indivisible-import-v1`.
- Zegar 61 s → domyślny budżet wygasa, 120 s nie; 121 s → `GRID_COHORT_TIMEOUT`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q services/api/tests/test_grid_correction_split.py services/api/tests/test_grid_correction_learning_api.py services/api/tests/test_grid_learning_material.py services/api/tests/test_grid_training_cohort_core.py
```

## Outcome

Commit: v1.7.608 / `6d37d0dcdec0b8c39e9d199d79ec7b565799e59b`.

- Kopia bez plansz przejmuje jednoznaczny atest kopii (`copy-inherited-attestation-order-v1`);
  podział korekt ma budżet 120 s, pozostałe komendy kohort 60 s. Decyzja D-603.
- Testy: `test_grid_correction_split.py` 20 PASS (3 nowe; test reimportu na starym
  kodzie odtwarza „Aliases or sessions have conflicting pins”),
  `test_grid_correction_learning_api.py` i `test_grid_learning_material.py` PASS,
  `test_grid_training_cohort_core.py` 52 PASS / 6 FAIL — te same 6 FAIL na czystym
  `main` 570fbe25 (atrapy `artifact_root`, `scalar_one`, `policyVersion`), nowy
  test budżetu PASS. Ruff check/format PASS; mypy --strict bez błędów w zmienionych
  modułach (zastane błędy w `schemas/source_lattice_geometry.py`).
- Odczyt operatora Mumie a2 (tylko odczyt, kod gałęzi, 56,3 s): `ce7b2f19` →
  `copy-inherited-attestation-order-v1`, `canStart=true`; TRAIN 178/293 (nowe 18/19),
  A 13/51, REG 13/21; szacowany przebieg 2580 s w budżecie.
- Audyt krzyżowy niewykonany: zmiana poza planem, zgoda operatora w czacie.
- Bez treningu, restartu, aktywacji i zmian historii ról.
