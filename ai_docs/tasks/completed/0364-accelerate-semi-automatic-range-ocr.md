---
title: TASK-0364 Accelerate semi-automatic range OCR
status: done
release: "0.10"
last_updated: 2026-09-01
---

# TASK-0364 — Przyspieszenie półautomatycznego OCR zakresów

## Goal

Osiągnąć co najmniej 2 JPEG/s na wymagającym rzeczywistym wejściu i 3–6 JPEG/s
na typowych seriach powtórzeń bez osłabienia lokalnego dowodu zakresu.

## Scope

- niezmienny OCR i proof v2 dla każdej wykonanej próby;
- wersjonowany adapter/run v3;
- tani deskryptor wyglądu wybierający próby OCR;
- obowiązkowa próba najwyżej co pięć źródeł oraz dodatkowa próba na mocnej
  zmianie wyglądu;
- pominięty JPEG jest wyłącznie `unproven` i nigdy nie otrzymuje zakresu;
- trwały checkpoint schedulera i bounded checkpointy SQL co 10 źródeł;
- zachowanie odtwarzalności runów v1/v2.

## Out of scope

- geometria, cropper, symbole i ocena jakości plansz;
- równoległe instancje Paddle, nowy worker albo usługa;
- osłabienie wymogu trzech zgodnych pozycji;
- domyślne włączenie feature flagi.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V2_ACCEPTANCE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Acceptance

- golden 10/100 zachowuje odpowiednio co najmniej 5/10 i 50/100 exact oraz
  zero błędnych przypisań;
- rzeczywisty strumień z powtarzającymi się ekranami osiąga minimum 2 JPEG/s;
- OCR nie jest wykonywany ponownie po restarcie dla zatwierdzonego checkpointu;
- pominięty obraz nie może utworzyć automatycznej kandydatury;
- v1/v2 zachowują fingerprinty i zachowanie.

## Outcome

- dodano wersjonowany kontrakt `semi-automatic-range-only-ocr-v3`, zachowujący
  recognizer i proof v2 dla każdej wykonanej próby;
- scheduler używa wyłącznie deskryptora wyglądu do zaplanowania OCR, wymusza
  próbę najwyżej co pięć źródeł i zapisuje trwały checkpoint co 10 źródeł;
- obrazy pominięte przez scheduler pozostają jawnie `unproven` i nie mogą
  utworzyć kandydatury zakresu;
- golden 10/100 dał `7/10` i `68/100` exact przy zerze fałszywych przypisań;
- pomiar pełnej ścieżki dał `3,30 JPEG/s` dla kosztownej serii czytelnych
  powtórzeń oraz `7,30 JPEG/s` dla rzeczywistego fragmentu surowego katalogu;
- projekcja 42 000 zdjęć wynosi około `3 h 32 min` w wolniejszym zmierzonym
  przypadku oraz `1 h 36 min` w szybszym;
- 66 testów pionu, Ruff i mypy zakończyły się powodzeniem; globalny
  `format:check` pozostał czerwony wyłącznie dla wcześniejszych plików
  frontendowych spoza zakresu zadania;
- szczegóły pomiarów zapisano w
  `ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V3_PERFORMANCE.md`.
