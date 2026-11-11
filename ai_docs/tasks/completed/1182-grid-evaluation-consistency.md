---
title: Zgodność oceny checkpointu i ONNX
status: done
last_updated: 2026-11-11
---

# TASK-1182 — Zgodność oceny checkpointu i ONNX

## Status

`done`

## Goal

Zrealizować mierzalny wynik T1 zaakceptowanego planu skutecznego uczenia.

## Context

Operator zatwierdził całe T1–T4, koszt6–10h i audyty terminalowe; na końcu pytać o scalenie.

## Dependencies / entry conditions

Plan EFFECTIVE_GRID_LEARNING_PLAN_20261111.md, część T1. Najpierw diagnoza istniejącego checkpointu, bez treningu.

## Recommended execution

gpt-6-astra/high. Ryzyko i warunki według tabeli planu. Audyt Claude Code claude-opus-5-5/high.

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

Wszystkie wymagania części T1 planu; wykorzystać istniejący pion bez równoległego trenera/rejestru.

## Out of scope

Operator GPU/trening, migracje operatora, wdrożenie, merge/push/default i nadpisywanie ręcznych korekt.

## Acceptance criteria

- [x] Kryteria funkcjonalne T1 udowodnione testami i raportem; końcowa bramka poniżej.
- [x] Ochrona historycznych wersji, danych i niezależnych kontroli zachowana.
- [x] Opus terminal PASS, brak otwartych P0/P1, docs/map i właściwe testy.

## Technical notes

Przeczytać część T1 planu przed kodowaniem. Hipoteza nie jest diagnozą. Wyniki kodu, danych i jakości modelu oddzielne.

## Expected files

- Istniejące: `images/grid_training_data.py::correction_evaluator`,
  `images/grid_training_child.py::_export`,
  `images/grid_rescue_evaluation.py::torch_engine` (prefiks worker src).
- Nowe: `images/grid_correction_consistency.py`,
  `training_core/evaluation_precision.py` i test regresyjny
  `services/worker/tests/test_grid_correction_consistency.py` oraz
  `services/worker/tests/test_grid_correction_consistency_wiring.py`.
- Dokumentacja: wymagania/architektura VISION_LAB, raport T1 i mapa kodu.
- Artefakt diagnostyczny poza commitem: odtworzenie istniejących wag i ONNX,
  bez treningu lub zmian danych operatora.

## Test cases

Scenariusze i kryteria T1 oraz tabela odbioru planu. Restart i utrata odpowiedzi dla trwałych workflowów.

## Verification

Właściwy scoped pytest przez główną .venv, lint/typecheck, npm run docs:check i npm run code-map:check; dokładne komendy i wyniki w raporcie taska. Komendy mają jawny timeout.

## Risks / open questions

Brak danych operatora może blokować trening lub pomiar, nigdy zastępczy PASS jakości.

## Outcome

Commit: v1.7.602 / `3991ff749f6af3a58c4f2e0bf6c5208c1b8392cb`.

### Changed

- Odtworzono dokładnie historyczne CUDA/TF32 i ONNX na całym A13zdjęć/53plansz.
  Jeden target przekraczał NME0,02 przez TF32. Eksperyment on/off na tych samych
  wagach i wejściach potwierdził przyczynę. Tensorowa zgodność wybranych wag
  z checkpoint600 i trzy rzeczywiste odtworzenia600/1200/1800 zostały sprawdzone.
- Jawny FP32 bez TF32/autocast z przywracaniem ustawień; wspólny evaluator A;
  pełny raw+discrete guard eksportu, kontrola preferencji wobec historii,
  kontrola non-regression A względem bazy oraz trwały fail/recovery proof.
- Ranking600>1800>1200 jest ten sam po naprawie i w ONNX. Historyczne REVISE
  pozostaje: naprawa oceny nie dowodzi poprawy modelu.

### Verification results

- Koordynator: docs:check i code-map:check PASS na czystym worktree. Końcowe nowe uruchomienie: pytest test_grid_correction_consistency.py test_grid_correction_consistency_wiring.py test_grid_correction_metrics.py test_screen_correction_training.py -q --basetemp=D:/game_predicotr/artifacts/t1182-accept (prefiks services/worker/tests/):33PASS/6,52s, timeout120s. Wstępne13PASS dotyczyło wcześniejszej wersji przed rundą poprawek i nie jest liczbą końcowego zestawu.

- Audyt R1: REVISE,0P0/2P1. Jedna runda poprawek i focused R2: **PASS**,0P0/0P1, terminal claude-opus-5-5/high; SHA5b73993a533f42a2719db2ef62696678a0e4297201a63b412076d9c7e5a91f4a. Raport i receipt TASK-1182_AUDIT_claude-opus-5-5 w quality; R1 zachowany osobno.
- P1-1: testuje rzeczywiste `torch_engine.screen_runner` i `board_runner`:
  flagi TF32/autocast wyłączone wewnątrz obu grafów, przywrócone po sukcesie
  i wyjątku. Bez uruchamiania CUDA lub optymalizatora.
- P1-2: świeży `_export` publikuje proof przy sukcesie, a przy porażce nie
  publikuje katalogu, usuwa własny staging i zapisuje trwały raport; `_train`
  przekazuje właściwy evaluator tylko dla grid-only, osobno testowany screen.
- Po poprawkach:33PASS (consistency+wiring+metrics+screen), timeout120s;
  Ruff check/format PASS; mypy silent wszystkich5modułów T1 PASS w50s
  z diagnostyką postępu i timeout120s. Dwie wcześniejsze próby przerwał
  limit60s podczas analizy zewnętrznego Torch; procesy zakończone i sprawdzone.
- Przed R1:23PASS: consistency, correction_metrics i screen_correction_training.
- 9PASS: grid_training_child (w tym rzeczywisty mały fixture ONNX).
- 6PASS: correction_evaluation_pipeline, w tym restart i role partial/full.
- Ruff format/check PASS; nowy-process CUDA FP32/raw+discrete na całym A PASS.
- Mypy: nowe2moduły skip-imports PASS; wszystkie5modułów silent PASS.
- Wszystkie dłuższe procesy z timeoutem≤120s; szczegóły prób i ograniczeń
  środowiskowych w raporcie. Niedostępny Temp i zbyt długie ścieżki testowe
  rozwiązano własnym krótkim basetemp, bez zmiany testowanego kodu.

### Not completed

- P2-5: przyjęte niskie ryzyko zarządzanego niezmiennego katalogu bazy: tożsamość grafów i bundle jest chroniona po pierwszym odczycie/recovery, lecz nie ma osobnego powiązania bundle bazy z weightsSha256 spec przed pierwszym eksportem. Nie deklarujemy takiego dowodu.
- P2-6: poza zakresem pozostają niekorekcyjne ewaluatory; wymagania doprecyzowano do oceny korekt.
- P2-7: końcową komendę i33PASS podano wyżej zamiast niejednoznacznego wstępnego13PASS.
- DoD T1: diagnoza/testy/runtime proof/dokumentacja/audyt gotowe; bez operacji operatora.
- P2-1 naprawione: dowód przypina bundle SHA i SHA obu grafów bazy;
  loader otrzymuje dokładne bytes i expected SHA; recovery wykrywa zmianę bazy.
  Nie zmienia to historycznych bundle ani nie wymaga nowego opt-in.
- P2-2 przyjęte ograniczenie:17,5s zmierzono dla jednej gry/13zdjęć A.
  Koszt kilku gier nie został zmierzony i rośnie wraz z całym A; trzy przebiegi
  plus raw parity oraz recovery zużywają istniejący budżet watchdoga.
  Bez rezerwy może on wyczerpać się po treningu. TASK-1184 otrzymał temat
  rezerwy czasu; jego wykonawca potwierdził pomiar/rezerwę pełnego A w preflight
  (osobny odbiór T3). T1 nie podnosi limitów i nie deklaruje wykonalności multi-game.
- Bez treningu operatora, nowego REG, wdrożenia/defaultu, migracji, restartu usług.
- Guard eksportu nie odtwarza automatycznie innych checkpointów: sprawdza
  preferencję wybranego wobec zapisanej historii. Wszystkie3historyczne kroki
  odtworzono osobno w tej diagnozie. Workflow content rozszerza TASK-1184.

### Documentation updates

- Wymagania i architektura VISION_LAB: sekcje TASK-1182.
- `ai_docs/quality/GRID_EVALUATION_CONSISTENCY_20261111.md` i dowód JSON
  z SHA lokalnych pełnych artefaktów diagnozy.

### Recommended next task

TASK-1183 zgodnie z zaakceptowanym planem, po odbiorze i zamknięciu T1.
