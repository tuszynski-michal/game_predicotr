---
title: TASK-0232 durable manual image-selection output
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0232 — Trwały zapis ręcznych wyborów selekcji

## Goal

Zapobiec sytuacji, w której decyzja manualna zostaje zapisana w PostgreSQL, ale
wybrany JPEG nie trafia do katalogu wynikowego po przełączeniu historycznego
runu albo utracie uchwytu File System Access API.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0230-image-selection-v105-quality-recovery.md`

## Implementation

- uchwyt katalogu wynikowego jest zapisywany w IndexedDB per `gameId + runId`,
- przed otwarciem review panel odzyskuje uprawnienie albo wymaga ponownego
  wskazania katalogu,
- pełne uzgodnienie odtwarza brakujące zakończone grupy przed dalszą pracą,
- modal czeka na zapis JPEG-a przed przejściem do następnej grupy,
- nieudany zapis można ponowić tym samym idempotentnym zatwierdzeniem.

## Outcome

Admin zapisuje uchwyty katalogów, sprawdza uprawnienie `readwrite`, uzgadnia
historyczny run i nie zamyka bieżącej decyzji przed zapisem pliku. Nadal nie ma
cichego nadpisania: identyczna checksum jest pomijana, a inna zawartość kończy
się widocznym błędem. Przeszło 188 testów Admina oraz typecheck.
