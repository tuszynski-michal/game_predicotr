---
title: TASK-0188 image selection range evidence without forced continuity
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0188 — Range evidence without forced continuity

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` — D-162
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`

## Goal

Usunąć nadpisywanie wyniku OCR przewidywanym kursorem i zachować poprawne skoki
zakresów bez zmiany kolejności źródeł.

## Problem

V10 może po rozpoznaniu kolejnej grupy zastąpić jej rzeczywisty zakres wartością
`previous.end + 1`. Jest to sprzeczne z dozwolonym skokiem, np.
`19–27 -> 400–408`, i wykonuje kosztowny OCR, którego wynik następnie ignoruje.

## Likely files

- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/tests/test_fast_image_selector.py`
- `services/worker/tests/test_image_selection_adapters.py`
- dokumentacja IMAGE_SELECTION

## Proposed solution

- zakres grupy pochodzi z jawnej kotwicy pierwszej grupy albo z dowodu OCR,
- `first_sequence_number` nie przewiduje dalszych grup,
- wykryty duplikat zachowuje dotychczasowe pomijanie bez przesuwania danych,
- dodać regresje ciągłości, skoku oraz kierunku malejącego.

## Verification

- test `1–9 -> 10–18` zachowuje wynik,
- test `19–27 -> 400–408` nie tworzy `28–36`,
- konflikt OCR nie jest ukrywany przez cursor,
- deterministyczny wynik dla dwóch uruchomień.

## Dependencies

- D-162,
- TASK-0178–0187.

## Open questions

Brak pytań blokujących. Jawny skok zakresu jest zaakceptowaną częścią domeny.

## Outcome

Wprowadzono nowy domyślny, wersjonowany manifest
`fast-image-selector-v10.1`. Historyczny manifest v10 i jego fingerprint
pozostają rozwiązywalne i zachowują dawną projekcję cursora, dzięki czemu
wznowienie starego runu nie zmienia wyniku.

Dla v10.1 `first_sequence_number` kotwiczy wyłącznie pierwszą grupę. Każda
kolejna grupa zachowuje zakres wynikający z konsensusu OCR; jawny skok, np.
`10–18 -> 400–408`, nie jest zastępowany przewidywanym zakresem. Niezgodność
kotwicy pierwszej grupy z OCR oraz nierozstrzygnięty konflikt OCR prowadzą do
`manual_required` z `RANGE_CONFLICT` zamiast ukrycia rozbieżności.

Weryfikacja 2026-08-08:

- Ruff dla zmienionych modułów: passed,
- mypy dla `manifest.py`, `engine.py` i `benchmark.py`: passed,
- regresje v10/v10.1: 8 passed,
- pełny zestaw selektora, adapterów i joba: 95 passed,
- testy API selekcji i importu obrazów: 28 passed,
- `git diff --check`: passed; ostrzeżenia dotyczyły wyłącznie konwersji LF/CRLF
  w istniejącym brudnym worktree,
- pełny mypy backendu przerwano po ponad 60 sekundach bez wyniku; zawężona
  kontrola zmienionych modułów zakończyła się poprawnie.

Nie uruchamiano profilu 200 ani runu 5000/32 000; należą do kolejnych zadań i
końcowej bramki właściciela.
