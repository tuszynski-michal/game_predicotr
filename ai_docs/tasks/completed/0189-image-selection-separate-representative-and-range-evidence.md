---
title: TASK-0189 separate representative assessment and range evidence
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0189 — Separate representative assessment and range evidence

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` — D-162
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0188-image-selection-range-evidence-without-forced-continuity.md`

## Goal

Wybierać najlepszy JPEG według jakości plansz i geometrii niezależnie od klatki
użytej do odczytania numeru.

## Problem

Obecny verifier traktuje skuteczny fallback OCR jak dowód kompletnej geometrii i
pełnego kadru. Czytelny numer nie dowodzi, że wszystkie plansze są dobre do
późniejszego cięcia.

## Likely files

- `services/worker/src/game_predictor_worker/images/selection/contracts.py`
- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- testy selektora, adapterów i joba

## Proposed solution

- wydzielić wynik oceny reprezentanta od `range evidence`,
- nie ustawiać `geometry_complete/full_frame_visible` na podstawie samego OCR,
- zachować top-12 całej grupy i ranking jakości,
- pozwolić zakresowi grupy pochodzić z innego kandydata niż wybrany JPEG.

## Verification

- najlepszy kadr bez czytelnej etykiety może zostać reprezentantem,
- inna klatka może dostarczyć zgodny zakres,
- czytelny numer przy przyciętych planszach nie wygrywa rankingu jakości,
- brak zmian API, jeśli istniejący kontrakt grupy jest wystarczający.

## Dependencies

- TASK-0188.

## Open questions

Brak pytań blokujących; preferowane jest zachowanie obecnego API grupy bez
migracji bazy, jeżeli kontrakt domenowy na to pozwoli.

## Outcome

Wewnętrzny kontrakt `CandidateVerification` został rozdzielony na
`RepresentativeAssessment` i `RangeEvidence`. Ocena reprezentanta przechowuje
rzeczywistą geometrię, kompletność kadru oraz liczbę plansz, natomiast dowód
zakresu zawiera wyłącznie wynik i powody OCR.

Verifier v10.1 nie ustawia już `geometry_complete` ani `full_frame_visible` na
podstawie skutecznego fallbacku OCR. Historyczne manifesty zachowują poprzednie
sprzężone zachowanie. Ranking v10.1 ignoruje confidence OCR i wybiera JPEG według
geometrii oraz metryk obrazu. Brak numeru na najlepszym kadrze nie blokuje go,
jeżeli zgodny zakres dostarczy inna klatka. `RANGE_CONFLICT` pozostaje blokadą
całej grupy.

Nie zmieniono publicznego API, schematu bazy ani kontraktu zapisanego wyniku
grupy.

Weryfikacja 2026-08-08:

- regresja: najlepszy reprezentant bez etykiety używa zakresu z innej klatki,
- regresja: czytelny numer na niepełnym kadrze nie wygrywa rankingu,
- regresja adaptera: fallback OCR nie promuje geometrii v10.1,
- Ruff: passed,
- mypy czterech zmienionych modułów: passed,
- pełny zestaw selektora, adapterów, joba i benchmarku: 108 passed,
- końcowe regresje rozdzielenia odpowiedzialności: 2 passed,
- `git diff --check`: passed z istniejącymi ostrzeżeniami LF/CRLF.

Nie uruchamiano profilu 200 ani runu 5000/32 000.
