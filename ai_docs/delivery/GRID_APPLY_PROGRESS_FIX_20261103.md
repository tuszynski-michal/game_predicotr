# Naprawa postępu zastosowania modelu — 2026-11-03

Wąska naprawa błędu ujawnionego przy jawnym zastosowaniu nowej wersji. TASK-1152 zachowuje liczniki między lease handlera, bez zmiany zabezpieczeń i danych domenowych. Jedna runda Opus, otwarte P0/P1 blokują commit. Przed wdrożeniem osobna zgoda na merge/push i restart general worker; nie dotyczy API/Admin/GPU. Opis kryteriów i testów: tasks/completed/1152-grid-apply-progress.md.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1152 — Postęp zastosowania | gpt-6-astra | high | Mała poprawka trwałego workflow i rzeczywistej walidacji postępu | Claude Code claude-opus-5-5/high |
