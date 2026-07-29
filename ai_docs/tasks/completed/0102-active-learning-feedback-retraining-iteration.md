---
title: Active-learning feedback and retraining iteration
status: done
last_updated: 2026-07-29
---

# TASK-0102 — Active-learning feedback and retraining iteration

## Status

`done`

## Goal

Zebrać drugi, niezmienny batch jawnych etykiet z istniejącego wyboru
active-learning, a następnie zbudować nową wersję datasetu, modelu ONNX,
kalibracji i quality gate bez mutowania wersji bootstrapowej.

## Context

TASK-0075 potwierdził `manualReviewShare = 1.0` i
`massImportAllowed = false`. Aktualny `reviewed-cell-labels-v1` zawiera 416
decyzji oraz 24 kompletne plansze. TASK-0063 przygotował checksum-bound wybór
30 kompletnych pending plansz z 30 różnych źródeł, lecz lokalne narzędzie
review nie używa jeszcze jego kolejności.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_07_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/m6-symbol-active-learning-selection.json`

## Scope

### A. Review batch

- zweryfikować canonical JSON, checksum i kontrakt selection,
- zweryfikować zgodność selection z aktualnym inventory,
- priorytetyzować dokładnie 30 wybranych plansz w kolejności `selectionRank`,
- opcjonalnie ograniczyć widok wyłącznie do tego batcha,
- pokazać rank i postęp batcha bez automatycznej decyzji,
- zachować istniejące 416 decyzji byte-for-byte do pierwszej nowej akcji.

### B. Manual gate

- właściciel jawnie akceptuje, poprawia lub odrzuca wszystkie komórki 30 plansz,
- częściowa plansza pozostaje wznawialna,
- sugestia nigdy nie zapisuje etykiety bez kliknięcia.

### C. Retraining po review

- wyeksportować nową wersję labeled datasetu,
- utworzyć source-aware split bez przecieku,
- wytrenować nową wersję modelu z nowym seed-bound manifestem,
- wyeksportować i zweryfikować ONNX,
- ponownie skalibrować confidence oraz active-learning,
- wykonać vertical slice i jawnie ustawić `massImportAllowed`.

## Out of scope

- auto-akceptacja sugestii,
- modyfikacja istniejącego modelu lub datasetu in-place,
- publikacja TASK-0076 przed przejściem nowej bramki,
- Redis/Celery albo zmiana decyzji D-085,
- etykietowanie wszystkich pozostałych 359 plansz w jednym batchu.

## Acceptance criteria

- [x] selection jest weryfikowany canonical checksum i domenowo,
- [x] widok batcha ma dokładnie 30 plansz w kolejności rankingu,
- [x] istniejące etykiety nie zmieniają się przy uruchomieniu lub oglądaniu,
- [x] każda nowa decyzja pozostaje jawna, atomowa i wznawialna,
- [x] UI pokazuje pozycję w batchu active-learning,
- [x] testy obejmują kolejność, priority-only, nieznany/zdublowany board i resume,
- [x] po manual gate powstaje nowy dataset/model/ONNX/calibration/report,
- [x] stary model pozostaje odtwarzalny,
- [x] `massImportAllowed` wynika wyłącznie z nowego quality gate.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_review.py`
- `scripts/review_m6_symbol_labels.py`
- `scripts/m6_symbol_review/app.js`
- `services/worker/tests/test_whole_layout_symbol_review.py`
- nowe wersjonowane artefakty dopiero po manual gate
- dokumentacja procesu i testów

## Risks / open questions

- 30 plansz to maksymalnie 450 nowych decyzji; po retrainingu nadal może być
  potrzebna kolejna iteracja.
- Dataset ma być dzielony według źródła, więc wzrost liczby próbek nie gwarantuje
  automatycznie wymaganego precision/support każdej klasy.

## Outcome

- selection przechodzi canonical/domain validation i dokładny checksum
  `symbol-crop-inventory-v3`; lokalny review zachowuje `selectionRank`, tryb
  priority-only i wznawialność,
- samo uruchomienie zachowało 416 decyzji o SHA-256
  `2be1a4171aeee7bc75165c6f993b3aeb3cb3155163ac60f36e1a4a0a2047a61c`,
  a właściciel następnie jawnie zaakceptował 30 plansz/450 komórek,
- końcowe źródło ma 866 decyzji, 54 kompletne plansze, 4 historyczne częściowe
  plansze i SHA-256
  `066e4ed3d184308303d66f0018b7ea23995e37f9e0a74b676179f47c59638e94`,
- nowy source-aware dataset obejmuje 866 próbek z 35 zdjęć; 30-epokowy trening
  wybrał epoch 28, a held-out test osiągnął `0.68715084` accuracy i
  `0.69969465` macro recall,
- ONNX ma SHA-256
  `3010d89f36f71dde4ffb24e14d030c03ef85b4111642eb4f813942753db4c711`,
  zero top-one mismatch i maksymalny błąd prawdopodobieństwa `7.749e-7`,
- vertical slice 866 próbek przeszedł; jego pomiar całego przejrzanego korpusu
  wynosi `0.75057737` accuracy i `0.76365167` macro recall,
- iteracja jest spięta przez
  `m6-active-learning-iteration-v2-manifest.json` o SHA-256
  `f745038a7177f61505b804de5404757bf4e3de711f0f6359b8dde5226905526f`;
  stare ścieżki datasetu, modelu i raportów nie zostały zmienione,
- `bootstrapTargetMet = false`, auto-accept i `massImportAllowed` pozostają
  wyłączone. Wynik to `passed_with_more_feedback_required`, więc TASK-0076
  pozostaje zablokowany i potrzebny jest kolejny batch ukierunkowany na klasy o
  zbyt małym wsparciu.
