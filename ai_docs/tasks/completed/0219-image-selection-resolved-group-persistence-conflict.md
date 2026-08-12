---
title: TASK-0219 image selection resolved group persistence conflict
status: done
release: "0.5"
last_updated: 2026-08-10
---

# TASK-0219 — Trwały zapis grupy rozstrzygniętej przez późniejszy obraz

## Goal

Usunąć regresję `IMAGE_SELECTION_PERSISTENCE_CONFLICT`, która zatrzymała realny
run v10.2 przy 864 / 32 079 zdjęć, bez cofania kontroli zgodności reprezentanta
z nazwą `seq_*`.

## Problem

V10.2 częściej pozostawia niejednoznaczną grupę do review. Późniejsza grupa może
dostarczyć wiarygodny zakres i reprezentanta, którym silnik rozstrzyga tę
wcześniejszą grupę. Dotychczas ten sam kandydat pozostawał również w
`top_candidates` późniejszej grupy oznaczonej `skipped_existing_range`. Model
danych wymaga unikalnego `run_id + order_index`, więc zapis próbował przypisać
jedno zdjęcie do dwóch grup.

Lekki rekord `manualGalleryOnly` także jest obserwacją tymczasową i musi pozwalać
na promocję dokładnie tego samego checksumu do autorytatywnego wyniku selektora.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Likely files

- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/tests/test_fast_image_selector.py`
- `services/worker/tests/test_image_selection_job.py`
- `ai_docs/process/CURRENT_STATE.md`

## Implementation

1. Odtworzyć konflikt testem domenowym v10.2.
2. Po przeniesieniu kandydatów do wcześniejszej rozstrzygniętej grupy pozostawić
   późniejszą grupę `skipped_existing_range` bez kopii tych kandydatów.
3. Pozwolić pełnemu wynikowi kandydata promować rekord `manualGalleryOnly` o tym
   samym `order_index` i checksumie; nadal odrzucać inne bajty i dwa pełne
   wyniki domenowe.
4. Uruchomić test skupiony, pełne testy selektora i workera oraz statyczne bramki
   zmienionego kodu.

## Verification

- test `280–288` odtwarza ścieżkę `manual_required → auto_selected` i potwierdza
  globalnie rozłączne indeksy kandydatów,
- konflikt innego checksumu nadal zwraca
  `IMAGE_SELECTION_PERSISTENCE_CONFLICT`,
- krótka regresja nie zmienia granic zwykłych grup ani wyboru reprezentanta,
- ponowny duży run wykonujemy dopiero po przejściu tych bramek.

## Outcome

Realny stan PostgreSQL potwierdził kilka sąsiednich grup review o zakresie
`280–288` oraz checkpoint otwartej grupy 38. Test v10.2 odtwarza rozstrzygnięcie
wcześniejszej grupy przez późniejszego kandydata i wymusza globalnie rozłączne
indeksy kandydatów. Późniejsza grupa `skipped_existing_range` nie utrzymuje już
drugiej kopii przeniesionych kandydatów. Store promuje identyczny
`manualGalleryOnly`, ale nadal odrzuca inny checksum i konflikt dwóch pełnych
wyników.

Weryfikacja: 83/83 testów selektora i joba, 3/3 skupionych testów trwałości,
Ruff format/check oraz mypy dwóch zmienionych modułów. Pełny mypy monorepo
przekroczył limit 120 sekund i został zastąpiony zawężoną kontrolą; proces nie
pozostał uruchomiony. Duży run 32 079 nie został automatycznie wznowiony.
