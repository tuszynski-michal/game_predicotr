---
title: TASK-0207 model quality grid workspace
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0207 — Model quality grid workspace

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Rozszerzyć Jakość rozpoznawania o niezależny stan oraz akcje symboli i siatki.

## Verification

Błąd jednej ścieżki nie blokuje drugiej, a aktywacje wymagają osobnego
potwierdzenia.

## Dependencies

TASK-0205–0206.

## Outcome

Sekcja `Jakość rozpoznawania` ma niezależny panel kalibracji siatki z własnym
loadingiem i obsługą błędów. Pokazuje mean/p95 baseline i kandydata, wynik
bramki, aktywną wersję oraz jawne akcje utworzenia, aktywacji i rollbacku.
Awaria ścieżki modelu symboli nie blokuje kalibracji siatki i odwrotnie.
