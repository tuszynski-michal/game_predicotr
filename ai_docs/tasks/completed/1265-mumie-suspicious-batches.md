---
status: done
---

# TASK-1265 — Partie podejrzanych siatek Mumii A2

## Status

`done`

## Goal

Przetworzyć kolejkę operatora według malejącego wyniku filtru, z deterministyczną kolejnością przy remisach. Wyjątek dotyczy wyłącznie wersji 9404ced0 w Mumii A2. Po 100 plansz na partię, wznowienie po utracie odpowiedzi, pauza między partiami, ponowne rozpoznanie 15 pól oraz ochrona decyzji człowieka. Wdrożenie i uruchomienie produkcyjne osobno.

## Relevant docs

- requirements/IMAGE_INGESTION.md
- architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md

## Zakres zmian

Polecenie operatorskie, istniejący magazyn i worker ponownego rozpoznawania, dokumentacja i testy. Lista obejmuje jeden skan, pominięcia i konflikty są rozliczane osobno. Operator może sprawdzić wynik i zatrzymać kolejkę. Wyszukiwarka otrzymuje tylko zatwierdzone transakcje.

## Outcome

Commit: v1.7.697 (hash dopisuje kolejny commit).

Kolejka przelicza zarezerwowane plansze w partiach po 100 według wyniku filtru. Wyjątek obejmuje wyłącznie kandydata 9404ced0 i tę kolejkę. Geometria, 15 klasyfikacji oraz dane wyszukiwania są zapisywane razem. Worker pomija plansze chronione ręczną decyzją. Przerwanie i wznowienie zachowuje kolejność oraz rozliczenie partii.

Przeszło 68 testów jednostkowych i pięć scenariuszy PostgreSQL. Dodatkowy przebieg sprawdził zmianę poprzednio przypisanych symboli i ich kodów w wyszukiwarce. Dwa błędy istniejących testów mocka repozytorium potwierdzono także na main. Ruff i mypy dla zmienionych modułów przeszły. Odczyt próbki produkcyjnej wykazał 99 kwalifikujących się plansz i jedną z ręczną decyzją. Publikacja i uruchomienie przetwarzania czekają na zgodę operatora.
