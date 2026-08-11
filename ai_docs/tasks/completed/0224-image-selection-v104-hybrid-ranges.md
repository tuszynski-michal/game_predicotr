---
title: TASK-0224 image selection v10.4 hybrid ranges
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0224 — Hybrydowe zakresy v10.4

## Goal

Łączyć kotwicę właściciela, dokładny lub fuzzy OCR dwóch zdjęć i wyłącznie
ściśle domknięte luki bez przesuwania wszystkich kolejnych nazw.

## Relevant docs

- `ai_docs/tasks/completed/0223-image-selection-v104-label-lattice.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`

## Verification

Jedna błędna albo brakująca cyfra może zostać skorygowana tylko przez spójną
siatkę; konflikt kotwic zawsze kończy się `manual_required`.

## Outcome

Silnik łączy obowiązkową kotwicę pierwszej grupy, dokładny konsensus i bounded
fuzzy consensus dwóch kandydatów. Cursor może wypełnić wyłącznie dokładnie
domkniętą lukę; nie zastępuje lokalnego OCR ani nie przesuwa późniejszych skoków.
Konflikt pozostaje `manual_required`.
