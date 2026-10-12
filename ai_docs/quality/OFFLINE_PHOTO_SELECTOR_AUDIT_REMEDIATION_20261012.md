---
title: Dowody poprawek selektora po audycie operatora
status: in_progress
last_updated: 2026-10-12
---

# Dowody poprawek selektora po audycie operatora

To raport wykonawcy, nie niezależny audyt. Werdykt oryginalnego audytu pozostaje
REVISE; operator ponownie sprawdza poprawki po zakończeniu0980–0982.

Źródło: [oryginalny raport](OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md),
SHA-256 `feeb4aafa04d9d3d6ffd0062614934fe5da4871b00da8bc72c7e16548a566158`.
Plik wejściowy pozostaje niezmieniony. Zakres i przyjęte ograniczenia opisuje
[zaakceptowany plan](../delivery/OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_PLAN_20261012.md).

| Ustalenie | Odpowiedź w rundzie | Dowód / pozostałe ograniczenie |
|---|---|---|
| P1: start PowerShell na każdym kroku | Jeden worker, świeże kontrole każdego żądania | Testy natywne15/15; mały fixture3JPEG: NAV88ms, preview15ms, accept133ms; bez dodatkowych startów po rozgrzaniu |
| P1: rozmiar dziennika i receiptów NAV | Format oraz pełna retencja zachowane | Koszt rośnie z inwentarzem i historią; nowy protokół trwałości poza tą rundą |
| P2: zamknięcie po LOCK_LOST | Bezpieczny close bez usuwania cudzej blokady | Backendowe regresje PASS; rzeczywiste okno jeszcze do sprawdzenia |
| P2: brak seq JPEG | Nowe decyzje blokowane, instrukcja odtworzenia zgodnej kopii | Missing→skip/accept→reopen→zła/dobra kopia→resume; bez automatycznego repair |
| P2: pominięty zakres | Skipped nie blokuje późniejszej akceptacji | Accepted konflikt i ponowny source nadal chronione; regresje projektu48/48 PASS |
| P2: podwójny scan open i SHA | Jeden zweryfikowany scan źródła; wszystkie SHA pozostają | Duży wynik nadal kosztowny przy open; nie stosujemy stale cache dowodów |
| P3: recovery guard | Fail-closed z diagnostyką | Pusta blokada nie dowodzi właściciela; bez automatycznego przejęcia |
| P3: scroll | Debounce250ms, wspólny pending Promise i flush | UI4/4; burst50 daje jeden atomowy zapis ostatniego widoku |
| P3: nośnik wymienny | Właściwy kod i komunikat | USB nadal poza pilotażem; brak zmiany zasad przechowywania |
| P3: pickSource | Martwy kanał usunięty | Scoped lint/typecheck PASS; smoke jeszcze pending |
| P3: komunikat po NAV | Oddzielny komunikat nawigacji | Wymaga potwierdzenia rzeczywistym EXE |
| P3: commit bez TASK ID | Nowe commity zawierają numery0980–0982 | Historia poprzednich commitów nie jest przepisywana |
| Pozostałe: esbuild, retry UI, desktop.ini/Thumbs.db | Bez przebudowy zależności; instrukcja doprecyzowana | Idempotencja dotyczy tego samego operationId; obce pliki nadal blokują wynik |

## Weryfikacja i paczka

Wyniki końcowych grup regresji i ZIP0.1.1 zostaną wpisane po wykonaniu.
Stare109/109 z audytu dotyczą0.1.0 i nie są testami tej rundy.
Fizyczny odbiór TASK-0979, restart Windows na komputerze odbiorcy i końcowy
audyt operatora pozostają pending.
