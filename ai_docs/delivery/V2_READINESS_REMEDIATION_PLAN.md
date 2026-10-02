---
title: Plan naprawczy po no-go T08
status: accepted
last_updated: 2026-09-26
---

# Plan naprawczy po no-go T08

## Stan i cel

T08 wykazał `no-go` na izolowanym head 0125. Szczegółowe wyniki są w
`quality/LEGACY_PUBLIC_STORE_RELEASE_READINESS.md`. Celem jest przywrócenie
wiarygodnej bramki testowej, zapis niezwiązanych rozjazdów kontraktów i
ponowienie właściwego smoke T08. Użytkownik zlecił naprawy blokerów w ramach
wykonania całego pozostałego planu; TASK-0695 pozostaje odrębnym backlogiem.

## Zakres, kolejność i decyzje

0. [TASK-0697](../tasks/completed/0697-v2-worker-upsert-keys.md): poprawić rzeczywiste
   klucze konfliktu trzech upsertów workera (raw, normalized, payout). Każdy
   klucz V2 zawiera `game_id`; naprawa nie zmienia schematu ani API. Osobny
   commit poprzedza domknięcie napraw samych fixture.
1. [TASK-0694](../tasks/0694-v2-0125-integration-suite.md): przejrzeć
   faktyczne awarie 28 plików; naprawić fixture i asercje game-owned zgodnie
   z manifestem. Public catalog/control/shared zachowuje dotychczasowe
   asercje. Każdy test uruchamia się na izolowanej bazie z limitem czasu.
2. [TASK-0695](../tasks/0695-unrelated-integration-contract-drift.md):
   rozstrzygnąć niezwiązane z V2 rozjazdy kontraktów i zgrupowane znaleziska. Właścicielskim
   źródłem jest wymaganie i OpenAPI; nie zmieniać asercji tylko dla zieleni.
TASK-0694 i TASK-0695 mogą być wykonane osobno. Wcześniejsze TASK-0696
wycofano: `.venv` działa z Pythonem 3.12.10 poza sandboxem, więc rozpoznanie
brakującego interpretera było błędne. T08 ponawia właściwy smoke i zapisuje
nowy wynik; T09 nadal wymaga osobnego preflightu i approval.

## Granice i ryzyka

Niezależny audit wykrył krytyczny konflikt D-038 z bindingiem V2 jednej gry
per transakcja. [TASK-0698](../tasks/0698-global-v2-routing-transaction-decision.md)
jest propozycją rozstrzygnięcia, nie zaakceptowaną zmianą architektury.
Wykonanie zależnej części zatrzymano do jawnej decyzji użytkownika.

Plan nie zmienia migracji 0125, danych użytkownika ani aktywnych location.
Nie obejmuje apply, wdrożenia, GC ani martwego kodu T11. Rozmiar test suite
nie jest pretekstem do sztucznych fixture na danych użytkownika: używa się
małych, odtwarzalnych baz izolowanych. Jeśli test ujawni błąd produkcyjny,
zatrzymać odpowiedni task i rozstrzygnąć kontrakt przed poprawką.

## Odbiór przepływu

Mapowanie: wiarygodny head 0125 → TASK-0694 → pełny wynik integracyjny;
kontrakt HTTP/domeny → TASK-0695 → dwa zielone scenariusze. T08 wymaga
własnego smoke API i workera, nie ukończenia całego historycznego workflow M2.
To są kryteria planowane, a nie wyniki wykonanych testów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0697 | `gpt-6-sol` | `high` | Klucze konfliktu muszą odpowiadać V2 i zachować retry workera. | `gpt-6-astra`, `medium` |
| TASK-0694 | `gpt-6-sol` | `high` | Wiele fixture i granica własności 65 tabel wymagają dokładnego audytu. | `gpt-6-astra`, `medium` |
| TASK-0695 | `gpt-6-sol` | `high` | Trzeba odróżnić dryf testu od zmiany kontraktu produktu. | `gpt-6-astra`, `medium` |
| TASK-0698 (propozycja; blocked) | `gpt-6-astra` | `high` | Sprzeczność atomowości release i izolacji V2 wymaga decyzji przed implementacją. | `gpt-6-sol`, `high` |
