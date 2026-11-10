---
title: Przygotowanie pilota 777 A2 — diagnoza timeoutu i weryfikacja poprawki
status: active
last_updated: 2026-11-10
---

# Przygotowanie pilota 777 A2

## Diagnoza

Cztery istniejące piloty zakończyły się `failed`, bez wybranych i przetworzonych
pól. Błąd jobów: `JOB_EXECUTION_FAILED`, `OperationalError`. Trzy wykonania
trwały około 32 s. Ograniczone odtworzenie pierwotnego zapytania w transakcji
READONLY na roli aplikacji potwierdziło `SQLSTATE 57014` (statement timeout).
Plan przegląda około 7,19 mln pól i 479 tys. plansz, a następnie sortuje pełne
snapshoty przed zwróceniem pierwszego wiersza.

## Zakres poprawki TASK-1180

Pilot wybiera metadane partiami źródeł, w tej samej kolejności hashy i rang
co poprzednio. Snapshoty są pobierane dopiero dla partii do 250 pól. Osobna
próbka kontrolna używa kolejnych prefiksów hashy 00–ff, zachowując poprzednią
losową kolejność i pełne warunki kwalifikacji. Pusta historia podmian jest
sprawdzana raz pod istniejącą blokadą własności sekwencji; niepusta zachowuje
poprzedni warunek aktualności. Heartbeat odnawia dzierżawę między partiami.

Nie zmieniono limitu zapytania 30 s, kwot, seedów, podziałów rodzin, modelu,
schematu ani API. Pobieranie jest nadal częścią jednej transakcji.

## Weryfikacja

| Sprawdzenie | Wynik |
|---|---|
| Dotychczasowa selekcja i detektor | 39 PASS |
| Jednostkowe testy nowych iteratorów | 6 PASS |
| Nowy test zgodności na PostgreSQL | 1 PASS |
| Dotychczasowe testy PostgreSQL readability | 4 PASS |
| Ruff format/check | PASS |
| Mypy trzech plików produkcyjnych | PASS |
| Cztery skrypty bramki docs:check | PASS |
| Regeneracja i sprawdzenie mapy kodu | PASS |

Test zgodności porównuje wszystkie snapshoty i ich kolejność dla trzech seedów,
pilota i audytu oraz obu ścieżek warunku aktualności. Mała, izolowana baza testu
zawiera 60 pól; partia dwóch źródeł wymusza przejścia między partiami i rangami. Po audycie dodano rozróżniające scenariusze retired, reserved, restored, rejected, niezgodnej geometrii i wcześniej oznaczonego RGB; pełne listy nadal są zgodne.
Testy jednostkowe obejmują pobieranie maksymalnie 250 snapshotów, wcześniejsze
zamknięcie, nieaktualny cel, późne filtrowanie nadzbioru audytu i remisy hashy oraz odmowę bez blokady gry.

Ograniczone odczyty na istniejących danych gry, bez uruchamiania joba:

| Odczyt | Czas | Liczba zwróconych pól |
|---|---:|---:|
| Pilot, pierwsza partia | 1,843 s | 250 |
| Próbka kontrolna, pierwsza partia | 18,204 s | 250 |

Oba odczyty używały limitu 25 s. Wcześniejsza próba samego globalnego sortowania
ID nadal przekraczała ten limit i została zastąpiona obecną implementacją.
Lokalne dowody diagnozy: `artifacts/readability-pilot-20261110/` w głównym
checkout (pliki `diagnosis.json`, `first-page.json`, `audit-first-page.json`).

## Ograniczenia i odbiór

Nie wykonano pełnego pilota na danych operatora. Czas pierwszej partii nie jest
czasem ukończenia selekcji ani przetwarzania obrazów. Audyt Opus 5.5
zakończył rundę 2 wynikiem PASS (0 P0 / 0 P1); raport i receipt są obok.
Drobne ryzyka P2 i późniejszy odbiór po wdrożeniu zapisano w Outcome taska. Żadne zdjęcia,
plansze ani historyczne failed piloty nie zostały zmienione lub usunięte.
Nie uruchamiano modelu, treningu, nowego pilota ani restartu usług.
