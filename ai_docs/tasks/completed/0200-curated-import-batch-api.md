---
title: TASK-0200 curated import batch API
status: done
release: "0.5"
last_updated: 2026-08-09
---

# TASK-0200 — Curated import batch API

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md

## Goal

Udostępnić idempotentną rejestrację źródła, postęp i utworzenie kolejnej partii
o zadanej liczbie zdjęć.

## Verification

API zwraca pełne agregaty i tworzy po partiach 10 oraz 20 rozłączne zakresy
0–10 i 10–30.

## Dependencies

TASK-0199.

## Outcome

Dodano game-scoped API rejestracji źródła, odczytu postępu, historii partii i
atomowego utworzenia następnych N zdjęć. Utworzony job zawiera dokładny wycinek
manifestu i idempotency key; OpenAPI oraz typowany klient Admina zostały
wygenerowane ponownie i przechodzą kontrolę driftu.
