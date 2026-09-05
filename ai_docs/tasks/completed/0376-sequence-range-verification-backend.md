---
title: TASK-0376 — Backend weryfikacji zakresów seq_*
status: done
version: 0.10
---

# TASK-0376 — Backend weryfikacji zakresów seq_*

## Goal

Udostępnić trwałą, range-only weryfikację, czy zakres zapisany w nazwie
`seq_<start>-<end>.jpg` zgadza się z bezpośrednim dowodem OCR na obrazie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Dodać jawny tryb `filename_verification` przy tworzeniu runu.
- Przypiąć go do pełnego skanu historycznie odtwarzalnym adapterem v2.
- Utrwalić w diagnostyce bezpośrednie dowody pozycyjne OCR.
- Dodać stronicowany odczyt wyników, klasyfikujący pięć kotwic obrazu:
  lewy/prawy górny róg, środek oraz lewy/prawy dolny róg.
- Nazwa pliku jest wyłącznie wartością oczekiwaną; nie jest dowodem OCR.
- Zachować zachowanie i fingerprinty runów v1–v5.

## Out of scope

- UI i usuwanie lokalnych plików.
- Nowy model OCR, geometria plansz, cropper i klasyfikator symboli.
- Migracja bazy.

## Acceptance criteria

- [x] Pewny wynik wymaga co najmniej trzech zgodnych kotwic z odpowiednim
  rozrzutem przestrzennym.
- [x] Niezgodny zakres, nieczytelny obraz i zła nazwa są jawnie odróżnione.
- [x] Wyniki można czytać podczas runu wyłącznie do trwałego checkpointu.
- [x] Historyczne runy wybierają niezmienione adaptery.

## Expected commit

`v0.10.78 - add durable sequence range verification`

## Outcome

Dodano jawny tryb `filename_verification`, który przypina pełny skan v2 bez
zmiany fingerprintów historycznych runów. Diagnostyka zawiera bezpośrednie,
pozycyjne dowody OCR, a nowy stronicowany endpoint porównuje je z nazwą pliku.
Pewny wynik wymaga co najmniej trzech z pięciu kotwic z pokryciem obu osi i
środkiem albo parą przeciwległych narożników. Odczyt jest ograniczony do
obserwacji zatwierdzonych trwałym checkpointem.

Weryfikacja: 21 skoncentrowanych testów API/workera, Ruff oraz mypy przeszły.
