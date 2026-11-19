# TASK-1263 — Wznowienie prywatnego treningu przy zamykaniu zestawu

## Status

`done`

## Goal

Zamknąć przygotowany zestaw bez oczekiwania na blokadę własnego procesu i ponownie sprawdzić przypisanie gry pod blokadą zapisującej transakcji.

## Acceptance criteria

- Proces nadrzędny zwalnia blokadę przed zamykaniem zestawu w odrębnym połączeniu.
- Zmiana przypisania gry nadal blokuje zatwierdzenie.
- Zapisane strony oraz klucz wznowienia podlegają dotychczasowej kontroli.

## Outcome

Commit: v1.7.695 (hash dopisuje kolejny commit).

Regresja na osobnej bazie PostgreSQL sprawdziła możliwość przejęcia blokady przez drugie połączenie i niezmieniony klucz komendy. Ruff PASS. Mypy wykazał dwie uwagi w istniejącej metodzie resume (odczyt pins), poza zmienionym krokiem.
