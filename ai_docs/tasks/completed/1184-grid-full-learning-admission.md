---
title: Pełne uczenie i odbiór zawartości
status: done
last_updated: 2026-11-11
---

# TASK-1184 — Pełne uczenie i odbiór zawartości

## Status

`done`

## Goal

Zrealizować mierzalny wynik T3 zaakceptowanego planu skutecznego uczenia.

## Context

Operator zatwierdził całe T1–T4, koszt6–10h i audyty terminalowe; na końcu pytać o scalenie.

## Dependencies / entry conditions

Plan EFFECTIVE_GRID_LEARNING_PLAN_20261111.md, część T3. Potwierdzona diagnoza T1:
różnica precyzji TF32 w ocenie checkpointu; T2 integruje wykluczenia i zachowanie
partial TRAIN. Niezależna implementacja T3 dopuszczona przez prowadzącego;
audyt i commit T3 po zamknięciu TASK-1183.

## Recommended execution

claude-opus-5-5/high (dokończenie na polecenie operatora2026-11-11). Ryzyko i warunki według tabeli planu. Audyt zmian Claude: gpt-6.1-sol/high; wcześniejsze części Codex weryfikuje niezależnie Claude przed modyfikacją.

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/EFFECTIVE_GRID_LEARNING_PLAN_20261111.md`
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CROSS_AUDIT.md`
- `ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md`

## Scope

Wszystkie wymagania części T3 planu; wykorzystać istniejący pion bez równoległego trenera/rejestru.

## Out of scope

Operator GPU/trening, migracje operatora, wdrożenie, merge/push/default i nadpisywanie ręcznych korekt.

## Acceptance criteria

- [x] Wszystkie kryteria T3 planu udowodnione testami i raportem.
- [x] Ochrona historycznych wersji, danych i niezależnych kontroli zachowana.
- [ ] Opus terminal PASS, brak otwartych P0/P1, docs/map i właściwe testy.
  (Brak audytu: warunkowa rezygnacja operatora; docs/map i testy wykonane.)

## Technical notes

Przeczytać część T3 planu przed kodowaniem. Hipoteza nie jest diagnozą. Wyniki kodu, danych i jakości modelu oddzielne.

## Expected files

- `images/grid_cohort_dataset.py`: opt-in `ContentTrainingDataset` dla partial TRAIN.
- `images/grid_training_data.py`: `CohortPhotos` i `ScreenGridBatches`, osobne maski
  detektora i ekspozycji przy stałej liczbie zdjęć/kroków.
- `training_core/grid_training.py`: `screen_grid_losses`, wyłączenie partial
  z forward detektora przed aktualizacją BatchNorm.
- `images/grid_content_experiment_run.py`: `run_experiment`, użycie całego legalnego TRAIN.
- `images/grid_content_experiment_data.py`: `measure_bank`, odczyt legalnych partial.
- `training_core/grid_content_experiment.py`: zgodne historycznie piny renderu,
  warunkowego R3 i pełnej oceny eksportu; trwały stan pominiętego R3.
- `images/grid_content_consistency.py` i `training_core/grid_content_consistency.py`:
  pełny frozen A, rzeczywiste wejścia, decyzje pól i zachowanie rankingu.
- `images/grid_training_child.py`: weryfikacja przed instalacją eksportu.
- API `domain/grid_content_experiment_evidence.py`: zamknięta walidacja dowodu
  pełnego A; `application/grid_correction_learning.py`: trzy piny nowych planów.
- Testy regresyjne workera oraz raport `quality/TASK-1184_VERIFICATION.md`.

Ścieżki modułów względem `services/worker/src/game_predictor_worker/`.

## Test cases

Scenariusze i kryteria T3 oraz tabela odbioru planu. Restart i utrata odpowiedzi dla trwałych workflowów.

## Verification

Właściwy scoped pytest przez główną .venv, lint/typecheck, npm run docs:check i npm run code-map:check; dokładne komendy i wyniki w raporcie taska. Komendy mają jawny timeout.

## Risks / open questions

Brak danych operatora może blokować trening lub pomiar, nigdy zastępczy PASS jakości.

## Outcome

Commit: v1.7.604 / `5b50244c5b060a1758923ed65f3ff102feef3aea`.

### Changed

- Istniejący eksperyment R0–R3 obejmuje legalne partial TRAIN w geometrii;
  detektor i jego BatchNorm widzą wyłącznie pełne, opisane zdjęcia.
- Nowe plany przypinają full-cell0%, warunkowe R3 i kontrolę eksportu na całym A.
  Brak etykiet R3 jest trwałym jawnym pominięciem, bez nowego budżetu i bez
  zmiany interpretacji historycznych planów.
- Ocena checkpointu i eksportu współdzieli renderer i dopasowanie; raw parity
  obejmuje każde rzeczywiste wejście ONNX, a decyzje i ranking nie mogą się zmienić.

### Verification results

- Implementacja Codex (gpt-6-astra); przejęcie, niezależny przegląd odziedziczonego
  kodu (0 P0/P1, 2 P2) i integracja: claude-opus-5-5/high na polecenie operatora.
- Delivery po T2 R1: 35+37+3+6+2 testów T3 PASS, 106 powiązanych testów workera
  PASS; Ruff PASS; mypy strict w raporcie. Zastane 2 FAIL finetune identyczne na HEAD.
- Audyt Codex niewykonany — kontynuacja na polecenie operatora po wyczerpaniu
  limitu. To nie jest PASS.
- Szczegóły i komendy: `ai_docs/quality/TASK-1184_VERIFICATION.md`. Testy kodu
  nie stanowią pomiaru jakości modelu operatora.

### Not completed

- Bez treningu, pomiaru jakości, migracji operatora, restartu usług,
  publikacji, zmiany defaultu ani scalenia.
- Dane operatora (A 4/4 po T2) nie pozwalają dziś na trening pełnego eksperymentu.

### Documentation updates

Wymagania i architektura VISION_LAB: osobne sekcje TASK-1184; D-602 (T2) obejmuje T3.

### Recommended next task

TASK-1185 — publiczny kontrakt/panel i raport pełnego porównania.
