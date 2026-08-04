---
title: TASK-0163 resume cancelled image-selection rerun
status: done
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0163 — Wznowienie anulowanej selekcji bez ponownego uploadu

## Status

`done`

## Goal

Zapewnić, że akcja `Przelicz ponownie załadowane zdjęcia` rzeczywiście uruchamia
pracę, gdy run dla aktualnego fingerprintu wcześniej zakończył się statusem
`cancelled` albo `failed`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0161-rerun-image-selection-from-existing-staging.md`

## Scope

- wznowić ten sam run i job od zachowanego checkpointu,
- zachować niezmienny staging, manifest i fingerprint selektora,
- wyczyścić terminalny stan joba i pozostawić liczniki postępu,
- wyświetlić właścicielowi jednoznaczny komunikat o wznowieniu.

## Acceptance criteria

- [x] `cancelled` i `failed` wracają do `created`,
- [x] checkpoint i staging pozostają zachowane,
- [x] `finished_at`, żądanie anulowania i błąd są czyszczone,
- [x] aktywny lub ukończony run pozostaje idempotentny,
- [x] testy domeny, serwisu i kontraktu Admina potwierdzają zachowanie.

## Outcome

Endpoint rerunu blokuje istniejący terminalny job i ponownie ustawia go w
kolejce. Worker może dzięki temu przejąć go jako następną próbę i kontynuować od
ostatniego trwałego checkpointu, bez ponownego przesyłania 32 079 obrazów.
Panel odróżnia wznowienie anulowanego lub nieudanego runu od zwykłego
przywrócenia istniejącego wyniku.

Weryfikacja: 25 testów domeny/API oraz 165 testów Admina przeszło; Ruff,
formatowanie Ruff, TypeScript i ESLint również przeszły. Izolowane uruchomienie
Mypy nadal zgłasza istniejące problemy typowania importów pakietu workera oraz
wcześniejsze błędy w `local_admin.py` i `main.py`; zmiana nie dodała nowego
błędu w testowanym zachowaniu.
