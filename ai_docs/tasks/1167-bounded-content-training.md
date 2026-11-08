---
title: Kontrolowane warianty treningu zawartości i ratunku
status: todo
last_updated: 2026-11-08
---

# TASK-1167 — Kontrolowane warianty treningu zawartości i ratunku

## Status

`todo`

## Goal

Istniejący trwały proces wykonuje ograniczony eksperyment R0–R3 z nowymi
celami, rzeczywistą oceną i wytrenowanymi wariantami ratunkowymi.

## Dependencies / entry conditions

T1–T3. Implementacja bez rzeczywistego treningu operatora; gotowość
danych/budżetu sprawdzana i raportowana, nie symulowana jako PASS.

## Recommended execution

gpt-6-astra/high; Claude Code claude-opus-5-5/high.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T4)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-581/586/587)
- ai_docs/architecture/CODE_MAP.md

## Scope

Dokładnie cztery maksymalne ramiona i budżety T4, bez drugiego trenera.
Bank błędów tylkoTRAIN/rodowód/SHA. Cele/maski i trzy próby jitter→skip.
Nowe batchnorm_stats bez zmiany starego tokenu. R2 screen768/1280,
board320×192/.15 i480×288/.30, równy udział. R3 pomocnicza głowica15
obwiedni i lokalnej widoczności wyłącznie po niezaliczeniu A przezR2.
R0/R1 bez niewytrenowanego rescue. 1redetekcja/zdjęcie+1crop/boardsuspect,
jednoznaczność, osobne progi i końcowa ocena zamrożonego routingu.

## Acceptance criteria

- [ ] Przypięte base/dane/seed,1200kroków/ramię,1500/1500/2100/2100s, suma7200s.
- [ ] Preflight i pełna rezerwa przed startem; niepełne ramię nie jest wybierane.
- [ ] Ranking A/co200kroków i koniec, równa waga gier, REG nie stroi.
- [ ] Checkpoint/resume zachowuje stan earlystop/rank/zużycie; replay nie duplikuje.
- [ ] Bank nie korzysta z A/REG ani użytych przez przodka źródeł.
- [ ] R3 wymaga właściwych zatwierdzonych etykiet, nie klasyfikuje symboli.
- [ ] Rescue dostępny tylko po treningu/ocenie, jeden dozwolony routing.
- [ ] B/REG30dobrych+30błędnych rzeczywistych źródeł per gra/ścieżka dla automatu,
  próbka zamknięta przed zwycięzcą, brak→unqualified, nie dobieranie po wynikach.
- [ ] Prawdziwy test ONNX i zgodności wejść, trwałość/PG/scopedchecks i audyt.

## Expected files

worker training_core/grid_training.py, grid_training_admission.py,
neural_grid_network.py, neural_grid_augmentation.py, images/grid_training_data.py,
geometry_core/rescue.py, handler uczenia; API presets/jobs/pins/readiness.
Rozwinąć przed implementacją po scoped inspekcji.

## Test cases

Gradient affine i zamrożone statystyki, legacybatchnorm; rotacja wejść i export;
nierozdzielny budżet, restart/utrataodpowiedzi, routingcacheperfoto, cutoffR3,
braketykiet i ukrytegoGTfallback; ścieżka bez kalibracji nie otrzymuje automatu.

## Verification

Scoped testy+ONNX+PostgreSQL, typy/lint/docs/map; bez operatorGPU.
Dokładne komendy i dowody w quality/TASK-1167_VERIFICATION.md.

## Outcome

Nie rozpoczęto.
