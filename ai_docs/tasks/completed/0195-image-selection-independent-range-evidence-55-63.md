---
title: TASK-0195 independent range evidence for difficult image-selection groups
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0195 — Independent range evidence for difficult image-selection groups

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/completed/0194-image-selection-v101-first-200-performance-and-quality-gate.md`

## Goal

Uzyskać poprawny, niezależny dowód OCR zakresu dla trudnej grupy indeksów
159–180, której widoczny zakres to 55–63, bez korzystania z kursora ciągłości i
bez zakładania, że następna grupa musi mieć kolejny numer.

## Problem

V10.1 zachowuje poprawne granice i wybór reprezentanta, ale żadna z prób OCR nie
dostarcza kompletnego dowodu zakresu tej grupy. Historyczny wynik 55–63 pochodził
z odziedziczonego kursora, który jest niepoprawny dla dozwolonych skoków, np.
19–27 do 400–408.

## Changed files

- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/tests/test_image_selection_adapters.py`
- `services/worker/tests/test_fast_image_selector.py`
- `scripts/profile_image_selection_slice.py`

## Proposed solution

- utrwalić problematyczną grupę jako checksum-bound przypadek regresyjny,
- zapisać diagnostykę cropa, geometrii i surowych kandydatów OCR,
- poprawić ogólną kompletność etykiety lub ranking odczytów, nie dodając
  wyjątku dla liczby 55 ani dla konkretnego pliku,
- zachować pełną obsługę nieciągłych skoków numerów,
- nie zmieniać uploadu ani grupowania, które zachowało poprawne granice.

## Verification

- problematyczna grupa zwraca zakres 55–63 z dowodu obrazu,
- przypadki nieciągłych skoków nadal nie używają kursora,
- dotychczasowe osiem poprawnych zakresów pozostaje bez regresji,
- skupione testy workera, Ruff i mypy przechodzą,
- pełny run 5000/32 000 nie startuje automatycznie.

## Dependencies

- TASK-0194 zakończony decyzją `optimize`.

## Open questions

Brak pytań produktowych. Jeżeli obraz nie zawiera wystarczającego dowodu,
wynik ma pozostać `manual_required`, a nie zostać odgadnięty.

## Outcome

Przyczyną nie był błędny OCR wszystkich etykiet. Zdjęcie o checksumie
`2ea1a6bf2708d384537ddcf2ce11cad80c6d5c8fa7c45da959242447af9b4037`
dostarczało siedem poprawnych odczytów `55, 56, 57, 58, 59, 60, 62`, lecz
adapter v5 wymagał jednocześnie obu skrajnych etykiet 55 i 63.

Dodano adapter `visible-sequence-label-range-v6`. Rozstrzyga on niepełną siatkę
wyłącznie przy co najmniej siedmiu inlierach RANSAC, widocznej przynajmniej
jednej pozycji brzegowej i pokryciu wszystkich trzech wierszy oraz kolumn. Nie
używa cursora ani sąsiednich grup. Remis hipotez i brak lokalnego dowodu nadal
kończą się fail-closed. Nowy fingerprint to
`286b652ea8f19e3afb73017b54f096c0eb5dff828f0020f0b7454e9e42b76f40`;
historyczny manifest v5 pozostaje rozwiązywalny.

Dodano checksum-bound fixture oraz regresję porównującą v5 z v6. Cold profile
22 rzeczywistych zdjęć z indeksów 159–180 zakończył się w 25,701488 s, wybrał
`1/1_010522.jpg` i zwrócił `auto_selected`, 55–63. Profil nie publikował pliku
wynikowego ani nie zapisywał stanu domenowego.

Weryfikacja: Ruff, mypy, 117 skupionych testów workera oraz 28 testów kontraktu
API przeszły. Pełny run 5000/32 000 pozostał wstrzymany zgodnie z zakresem
zadania.
