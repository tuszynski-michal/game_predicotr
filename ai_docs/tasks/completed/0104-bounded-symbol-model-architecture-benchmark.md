---
title: Bounded symbol model architecture and augmentation benchmark
status: done
last_updated: 2026-07-29
---

# TASK-0104 — Bounded symbol model architecture and augmentation benchmark

## Status

`done`

## Goal

Porównać niewielką liczbę lokalnych wariantów klasyfikatora na zamrożonym
dataset/split v3, wybrać wariant wyłącznie na validation, a test otworzyć
dokładnie raz dopiero dla wybranego checkpointu.

## Context

TASK-0103 osiągnął target minimum 100 próbek każdej klasy, ale model
`small-symbol-cnn-v1` nie wygenerował żadnego validation threshold candidate
spełniającego wymagania precision. Kolejny batch etykiet nie jest obecnie
uzasadniony bez sprawdzenia, czy ograniczeniem jest utrata informacji
przestrzennej przez global average pooling albo brak bezpiecznej augmentacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/m6-active-learning-iteration-v3-manifest.json`
- `ai_docs/quality/m6-symbol-dataset-split-report-v3.json`

## Scope

- zachować dokładnie dataset i source-aware split v3,
- użyć raportu modelu v3 jako control bez ponownego strojenia na test,
- porównać najwyżej dwa nowe warianty:
  - spatial CNN zachowujący mapę cech przed klasyfikatorem,
  - ten sam spatial CNN z bounded train-only augmentation,
- każdy kandydat ma osobny seed-bound checkpoint i validation-only report,
- wybór używa kolejno: validation macro recall, accuracy, niższy loss,
- raport selekcji musi odrzucać metryki testowe w raportach kandydatów,
- dopiero po zamrożeniu wyboru wykonać jeden test wybranego checkpointu,
- pojedyncza komenda treningowa ma limit 120 sekund.

## Out of scope

- pretrained weights i pobieranie modeli z internetu,
- zmiana datasetu albo splitu,
- użycie testu do wyboru wariantu lub hiperparametrów,
- eksport ONNX i produkcyjne przełączenie przed wynikiem benchmarku,
- kolejny manual-review batch.

## Acceptance criteria

- [x] benchmark ma control i najwyżej dwa nowe warianty,
- [x] raporty kandydatów nie zawierają metryk testowych,
- [x] augmentacja działa wyłącznie na train,
- [x] każdy kandydat jest deterministyczny i checksum-bound,
- [x] wybór wynika wyłącznie z validation,
- [x] test jest oceniony tylko dla zamrożonego zwycięzcy,
- [x] raport końcowy zawiera per-class precision/recall i rekomendację,
- [x] wynik nie zmienia `massImportAllowed` bez osobnej kalibracji/vertical slice.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_model_benchmark.py`
- `scripts/benchmark_m6_symbol_model_variant.py`
- `scripts/select_m6_symbol_model_candidate.py`
- `services/worker/tests/test_symbol_model_benchmark.py`
- `ai_docs/quality/m6-symbol-model-benchmark-*.json`
- dokumentacja procesu

## Risks / open questions

- Spatial head zwiększy liczbę parametrów i czas inferencji; wynik musi pozostać
  akceptowalny dla lokalnego CPU.
- Validation ma tylko 300 próbek, dlatego próg auto-accept nadal może wymagać
  większej jakości nawet po wzroście accuracy.

## Outcome

- benchmark objął historyczny control v3 oraz dokładnie dwa nowe warianty:
  `spatial` i `spatial_augmented`,
- oba raporty kandydatów są validation-only i nie zawierają pól testowych;
  augmentacja jest deterministyczna, zależna od sample/seed/epoch i używana
  wyłącznie przez train dataset,
- control osiągnął `0.71` validation accuracy i `0.76183103` macro recall,
- oba warianty spatial osiągnęły `0.97666667` validation accuracy i
  `0.97769454` macro recall; `spatial` wygrał przez niższy loss
  `0.22006203` wobec `0.22051564`,
- checksum-bound selection ma SHA-256
  `1c8d2c0ebb38bf84163ac459068e390e52af43e2f079056d1fcec65b00362618`
  i został odtworzony przed otwarciem testu,
- tylko wybrany `spatial` został oceniony na 313 próbkach testowych, osiągając
  `0.96166134` accuracy i `0.95484094` macro recall; raport testowy ma SHA-256
  `0e0ddcba28880b49aa0c74c246b4ab32576b3fece575994d0e4c2a2787dec60c`,
- oba kandydaty odtworzyły identyczne logiczne checkpointy i raporty,
- raport decyzji ma SHA-256
  `9f3b1cabe4ab04824a8c93787e426f492191f0b1a8f68062ffb02b6d79ce2a3c`,
- `massImportAllowed` pozostaje `false`; następny task ma przenieść wybrany
  wariant do wersjonowanego artefaktu produkcyjnego, ONNX, kalibracji i
  dynamicznego vertical slice.
