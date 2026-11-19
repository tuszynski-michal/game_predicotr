# TASK-1262 — Przypisana wersja odniesienia po korekcie siatek

## Status

`done`

## Goal

Włączyć niezależny pierwszy trening z aktualnych zatwierdzeń po poprawieniu siatek użytych do dawnej oceny.

## Acceptance criteria

- Wyłącznie przy rezerwacji od bieżącego przypisania gry późniejsze zmiany jej siatek są dopuszczalne.
- Dowód publikacji, tożsamość manifestu, generacja danych i kontrola pozostałych gier nadal obowiązują.
- Kontrole publikacji, aktywacji i oceny kandydata wymagają aktualności.

## Outcome

Commit: v1.7.694 (hash dopisuje kolejny commit).

Regresja oceny przypisanej wersji, test idempotencji i ochrona usuniętego lub przeniesionego magazynu przeszły (5 przypadków). Ruff i mypy pięciu modułów przeszły. Zmiana dotyczy odczytu dotychczasowego przypisania pod blokadą rejestru i dopuszcza tylko przyrost powiadomień tej samej gry przy tej samej generacji danych.
