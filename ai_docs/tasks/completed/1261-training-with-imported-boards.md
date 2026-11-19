# TASK-1261 — Trening przy otwartych do korekty importach zdjęć

## Status

`done`

## Goal

Włączenie prywatnej rodziny modelu może nastąpić, gdy operator pracuje na już pociętych planszach. Import zachowuje swoje zdjęcia, siatki, rozpoznane symbole i status.

## Relevant docs

- [Wymagania uczenia](../../requirements/SUPERVISED_MODEL_IMPROVEMENT.md)
- [Decyzja D-618](../../process/decisions/DECISION_LOG_2026.md#d-618--prywatne-rodziny-cięcia-siatek-nowych-gier-v3)

## Acceptance criteria

- Oczekujący na operatora import zdjęć po wycięciu plansz, również starszy bez zapisanego pinu, umożliwia rezerwację rodziny gry od aktualnego przypisania.
- Trwający lub zakolejkowany import oraz operacje uczenia, oceny i przeliczania geometrii zachowują ochronę. Nieznany etap oczekiwania wymaga sprawdzenia.
- Rezerwacja i trening nie przeliczają importu. Późniejsze zastosowanie modelu do plansz jest oddzielną operacją.

## Outcome

Commit: v1.7.693 / `7b85d74524aa09ec6225a4607390773c602f41f0`.

Nowy test PostgreSQL przeszedł od utworzenia i przetwarzania importu przez granicę ręcznej weryfikacji do zatwierdzonego włączenia rodziny. Sprawdził niezmieniony status i etap importu po zatwierdzeniu transakcji. Test idempotencji Mumii, Ruff i mypy zmienionego modułu PASS. Starszy test współdzielonych kohort przechodzi kontrolę konkurencji i kończy błędem przy ręcznym wstawianiu fikcyjnej prywatnej wersji z manifestem bazy (`GRID_LEARNING_PRIVATE_ASSIGNMENT_CHANGED`); takie dane testowe były też na wejściowym main. Szerszy plik testów katalogu przekroczył limit czasu.
