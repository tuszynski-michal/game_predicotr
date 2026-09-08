---
title: TASK-0516 acceptance and independent review
status: accepted
last_updated: 2026-09-08
---

# Odbiór implementacji TASK-0516

Zakres: kod mechanizmu; **nie jest to zgoda na usuwanie danych ani migracje**.
Nie jest to odbiór partycjonowania `game_data_v2` ani benchmark wielomilionowy.

## Niezależny audyt

Wykonany przez niezależnego agenta `gpt-6-astra high`, tylko odczytowo.
Końcowa ocena po poprawkach: brak otwartych P0/P1; odbiór zależny od testów.

Naprawione ustalenia:

- wcześniejszy purge obejmował wiele porcji jedną transakcją;
- kolejka wymaga review-before-queue i obsługi efektów triggerów;
- incoming FK i ownership keyset wymagały indeksów;
- pośredni właściciel mógł zmienić się między jego odczytem a aktywacją fence;
- osobna transakcja dla każdego leaf-parenta dawałaby nadmierną liczbę commitów;
- zapis archiwum SQLite wymagał dowodu kompletności względem bazy, nie tylko
  wewnętrznie spójnego licznika;
- restart po `DELETE games` wymaga terminalnego receiptu w tym samym commicie;
- fingerprint musi przetrwać restart także dla constraints, funkcji i triggerów;
- downgrade indeksów wymaga timeoutów i kontroli dokładnej definicji.

## Uruchomione kontrole

- Izolowana, unikalnie nazwana baza PostgreSQL, pełny upgrade do 0104 oraz
  scenariusz dwóch gier: po 3 źródła, 12 plansz i 180 komórek, queue review,
  globalne executions. Baza testowa usuwana przez fixture; baza aplikacji nie
  jest resetowana ani migrowana.
- Test sprawdza indeksy, cursor po JSON roundtrip między porcjami, blokadę
  zmiany parent owner, fence bezpośredniego/pośredniego zapisu, rollback
  DELETE przed checkpointem, utratę odpowiedzi, wznowienie i terminalny restart.
- Końcowa seria PostgreSQL + podstawowe policy + prerequisite 0102:
  **6 passed, 77.39 s**. Następnie pełne policy tests rozszerzone o byte-cut
  i oversized record: **6 passed, 3.17 s**. Łącznie 8 różnych testów.
- Ruff dla nowych modułów/migracji/CLI/testów: passed.
- Scoped mypy (`MYPYPATH=services/api/src`, `--follow-imports=silent`): passed.
- Ruff format oraz Prettier zmienionych dokumentów: passed.
- Nie uruchamiano pełnego zestawu web/worker ani buildów; brak zmian UI, API
  HTTP, OpenAPI i silnika geometrii. Cudze dirty zmiany nie są częścią odbioru.

## Zachowane archiwum — odczyt rzeczywistego materiału

- Plik: `artifacts/legacy-chat-search/777-v0.1-layouts.sqlite3`.
- Liczba układów: 414705; topology 3×5; rozmiar 19808256 bajtów.
- SHA-256 pliku:
  `0e1d18a6f9ffe22860c6956f8f5761909df45021465643817c8cbf2426314c5e`.
- Fingerprint układów:
  `7d429e4b0ab0098cb4d97976ec7440df27446859063d001af5887e483de720e2`.
- SHA-256 katalogu symboli:
  `0dbbbbba4cb4bdbe28a9731a6387f39b465a22b342d639fb90c47f6a5eda67d0`.
- Weryfikacja SQLite i strumieniowe porównanie PostgreSQL wykonane read-only.
  Wykonawca musi powtórzyć weryfikację przed aktywacją; ten dokument nie jest
  tokenem autoryzującym usunięcie.

## Ograniczenia / następna bramka

0103/0104 nie zastosowano w bazie aplikacji. Nie wykonano fizycznego GC,
kasowania starej gry, kompaktowania WSL/VHDX ani migracji `new-siedem`.
Czas i koszt dyskowy 136 indeksów na obecnych danych nie zostały zmierzone;
wdrożenie wymaga oceny pojemności i okna utrzymaniowego. Nie deklarujemy czasu
całego purge na podstawie małego fixture'a. Wersja wymaga PostgreSQL 18 używanego
przez lokalne środowisko (w tym limitu czasu całej transakcji).

TASK-0517 rozpoczyna się od aktualnego preview zakresu i osobnego potwierdzenia.
