---
title: TASK-0650 — Sieć siatek v3: narzędzie kuracji danych
status: todo
---

# TASK-0650 — Narzędzie kuracji danych uczących

## Status

`todo`

## Goal

Użytkownik szybko akceptuje/odrzuca kandydatów (klawisze A/R/S), a jego decyzje trwale trafiają do manifestu datasetu bez utraty i bez ponownego liczenia.

## Dependencies / entry conditions

- TASK-0649 `done`.

## Recommended execution

`claude-sonnet-5`, reasoning `high`; review importu decyzji: `claude-opus-5-5`, reasoning `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md`

## Scope

- `scripts/grid_nn_dataset.py curation-pack` — pakiety po 200 plansz jako samodzielny HTML (obrazy base64): wycinek planszy z siatką 5 × 3 cienką linią + miniatura całego zdjęcia, klawisze A/R/S i strzałki nawigacji, licznik, zapis stanu w `localStorage` (tylko wygoda), przycisk „Pobierz decyzje” (plik JSON z identyfikatorem pakietu i checksumą).
- `scripts/grid_nn_dataset.py import-decisions` — idempotentny import JSON do manifestu (ostatnia decyzja wygrywa, historia zachowana), odrzuca plik niepasujący do pakietu.
- Kolejność: najpierw zbiór złoty, potem pakiety treningowe (trudne przed łatwymi).
- Opcja hurtowej akceptacji łatwych przypadków po zaakceptowaniu losowej próbki pakietu.

## Out of scope

- Zmiany w Reviewerze/Adminie i API.

## Acceptance criteria

- [ ] Test: odrzucone i pominięte plansze nie trafiają do eksportu treningowego.
- [ ] Test: ponowny import tego samego pliku nie zmienia manifestu.
- [ ] Pakiet działa offline w przeglądarce, bez serwera.

## Outcome

Wypełnia agent po pracy.
