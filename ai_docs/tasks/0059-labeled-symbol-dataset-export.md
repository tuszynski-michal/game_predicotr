---
title: TASK-0059 Labeled symbol dataset export
status: in_progress
last_updated: 2026-07-28
---

# TASK-0059 — Labeled symbol dataset export

## Status

`in_progress`

## Goal

Wyeksportować deterministyczny, wersjonowany dataset oznaczonych wycinków
symboli z automatycznych cell crops M5, bez ręcznego wycinania obrazów i bez
uznawania niepewnego OCR za zatwierdzony numer sekwencji.

## Context

D-057 pierwotnie zaliczyła G5 w wariancie `passed_manual_review_only_ocr`.
Korpus obejmuje 43 zdjęcia i 387 przejrzanych layoutów. Pierwsza sesja
etykietowania wykazała jednak, że 5805 cell crops v1 jest systematycznie
przeciętych. D-059 poddaje ten inwentarz kwarantannie i blokuje eksport do
czasu zaakceptowania `board-cell-crops-v2`.

Etykieta komórki wynika z jednoznacznego połączenia:

1. przejrzanego `sequence_number` w golden annotations,
2. stabilnego `observationId`, indeksu row-major i dokładnego `cropSampleId`,
3. jawnej decyzji `accepted` w `reviewed-cell-labels-v1`,
4. symbolu należącego do tej samej gry.

OCR jest wyłącznie diagnostyką. Nie może tworzyć ani nadpisywać
zaakceptowanego numeru używanego do etykietowania.

W repozytorium nie ma prawdziwych rekordów layoutów 1–387 odpowiadających
zdjęciom. Dane fixture M1/M4 nie mogą być użyte jako etykiety. Pierwsza część
zadania tworzy więc kompletny inwentarz cropów, a eksport datasetu przyjmuje
wyłącznie osobne, przejrzane decyzje komórek.

Implementacja kontraktów i eksportera pozostaje użyteczna. Po TASK-0094–0096
wejściem będzie `symbol-crop-inventory-v2`; TASK-0097 dostarczy decyzje na
poziomie pełnego layoutu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-057–D-059 w `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wersjonowany inwentarz wszystkich cropów i stabilne `sampleId`,
- wersjonowany kontrakt przejrzanych decyzji symboli,
- jednoznaczne mapowanie sample → accepted label → symbol,
- eksport istniejących cell crops bez ponownego ręcznego wycinania,
- stabilne identyfikatory przykładów i ścieżki względne,
- SHA-256 źródłowego obrazu, cropu i logicznego rekordu,
- manifest wersji eksportu z wersjami pipeline’u i źródeł,
- deduplikacja dokładnie identycznej treści z zachowaniem pochodzenia,
- liczniki per symbol i lista elementów odrzuconych,
- blokada przy luce, niejednoznacznym numerze, duplikacie decyzji,
  niezgodnych wymiarach, nieznanym symbolu albo drift checksumy,
- testy deterministyczności, idempotencji i błędów granicznych.

## Out of scope

- podział train/validation/test — TASK-0060,
- trening PyTorch i eksport ONNX — TASK-0061/TASK-0062,
- ekran manual review i trwałe review items — TASK-0064/TASK-0065,
- automatyczne zatwierdzanie numeru z OCR,
- ręczne wycinanie komórek przez właściciela,
- masowy import M7,
- zmiana opublikowanego datasetu lub obrazów źródłowych.

## Acceptance criteria

- [x] Inwentarz v2 obejmuje wszystkie zweryfikowane cropy i nie przypisuje im
      automatycznych etykiet.
- [x] Eksporter przyjmuje wyłącznie przejrzane numery oraz jawne decyzje
      `accepted` z `reviewed-cell-labels-v1`.
- [x] Każdy przykład zachowuje source image, sequence number, board index,
      cell index, symbol ID/code, ścieżkę cropu i checksumy.
- [x] Te same wejścia dają ten sam logiczny manifest i identyfikatory.
- [x] Identyczna zawartość cropu nie tworzy dwóch niezależnych binariów, ale
      wszystkie wystąpienia i źródła pozostają audytowalne.
- [x] Brak decyzji pozostawia sample jako pending, a duplikat lub konflikt
      decyzji blokuje eksport zamiast wybierać pierwszy rekord.
- [x] Wynik OCR nie jest źródłem zatwierdzonej etykiety.
- [x] Raport podaje liczność i odrzucone elementy per symbol.
- [x] Oryginały, cropy M5 i opublikowane rekordy pozostają niezmienione.
- [x] Testy, format, lint i typecheck zmienionych części przechodzą.
- [x] Dokumentacja i `CURRENT_STATE.md` opisują rzeczywisty wynik.
- [ ] Powstało pierwsze źródło przejrzanych etykiet i rzeczywisty eksport ma
      co najmniej jeden zaakceptowany sample.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_dataset.py`
- `services/worker/tests/test_symbol_dataset_export.py`
- `scripts/export_m6_symbol_dataset.py`
- `ai_docs/quality/m6-symbol-crop-inventory-v2.json`
- `ai_docs/quality/m6-symbol-crop-inventory-v2.schema.json`
- `ai_docs/quality/m6-reviewed-cell-labels.schema.json`
- `ai_docs/quality/m6-symbol-dataset-export.schema.json`
- `ai_docs/quality/m6-symbol-dataset-export-report.json`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_symbol_dataset_export.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images scripts services/worker/tests
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images scripts
```

## Risks / assumptions

- Bieżący korpus dotyczy jednej gry; eksport nie jest dowodem jakości dla
  innych gier.
- Golden geometria została zainicjalizowana przez detektor i przejrzana
  wizualnie, a nie zmierzona niezależnie od algorytmu.
- Do utworzenia pierwszego rzeczywiście oznaczonego datasetu potrzebne są
  przejrzane decyzje symboli. Automatyczne cropy nie eliminują tego kroku.
- Minimalna liczność na klasę i podział źródłowy należą do TASK-0060.

## Outcome

Techniczna integracja z zaakceptowanym inwentarzem v2 została rozpoczęta
2026-07-28. Eksporter:

- przyjmuje wyłącznie `symbol-crop-inventory-v2` z
  `trainingAllowed = true` i cropperem
  `board-cell-crops-v2-calibrated-v1`,
- jawnie odrzuca historyczny inwentarz v1 objęty kwarantanną,
- przenosi do manifestu wersję inwentarza i croppera, checksumy korpusu,
  adnotacji, crop reportu, profili i raportu jakości,
- zachowuje `observationId`, `cropSampleId`, `boardId` oraz pochodzenie profilu
  kalibracji dla każdego zaakceptowanego przykładu,
- ponownie sprawdza liczniki, grupy źródłowe, kompletność plansz 5 × 3,
  geometrię i stabilne identyfikatory.

Rzeczywisty raport kontrolny
`ai_docs/quality/m6-symbol-dataset-export-report.json` ma SHA-256
`e2545da59e34b0ef0a33080579a9b85b39d40c5f00bd22e21731ca8b7f05f865`,
status `waiting_for_labels`, 5805 pozycji pending oraz zero zaakceptowanych i
odrzuconych przykładów. Nie utworzono fikcyjnych etykiet ani binariów datasetu.

Dwanaście testów eksportera i pełny powiązany pion 31 testów przechodzą.
Ruff, mypy, oba tryby `--check` oraz walidacja trzech JSON Schema przechodzą.
Finalizacja pozostaje zależna od ręcznych decyzji TASK-0097; dopiero niepusty
eksport spełni ostatnie kryterium akceptacji.
