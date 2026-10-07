---
title: Fast model quality overview and independent grid controls
status: done
last_updated: 2026-10-07
---

# Szybki panel jakości bez przygotowywania treningu

## Stan, cel i zakres

TASK-0898 nadal przygotowuje dokładną kohortę przy otwieraniu panelu (39,843 s
dla Mumii) i dopiero potem montuje sekcję siatki. Użytkownik odrzucił
45-sekundowy timeout i zlecił usunięcie przyczyny opóźnienia.

TASK-0899 dostarcza szybki odczyt metadanych zatwierdzeń i niezależne
sterowanie siatką. Przygotowanie dokładnej kohorty następuje po kliknięciu
„Ulepsz rozpoznawanie”; trening nadal wymaga potwierdzenia jej manifestu.

## Kontrakt i kolejność

1. Istniejący GET model-quality otrzymuje opcjonalne view=overview.
   Bez parametru zachowuje dokładny ModelQualityResponse. Nowy, jawny typ
   ModelQualityOverviewResponse podaje zatwierdzenia bieżącego właściciela
   planszy dla aktywnych symboli, liczbę plansz/źródeł, pokrycie symboli,
   ostatnią kohortę i stan ciężkiego joba. Nie deklaruje checksumy ani
   kwalifikacji treningowej. Odczyt wykonuje wyłącznie agregację SQL i
   metadane rejestru, bez renderowania i odczytów zdjęć.
2. UI otwiera overview. Sekcja siatki jest montowana niezależnie od wyniku
   i czasu odczytu symboli, także przy błędzie i podczas preview treningu.
3. „Ulepsz rozpoznawanie” pobiera istniejący dokładny GET, otrzymuje
   counts/delta/exclusions/checksum, a potem pokazuje potwierdzenie.
   Freeze i trening zachowują dotychczasowy kontrakt oraz ponowną kontrolę
   aktualnych pikseli, rewizji i źródeł chronionych.
4. Usuwamy arbitralny timeout z odczytów UI. Zachowujemy anulowanie po
   zmianie gry/zamknięciu, ignorowanie spóźnionych wyników i retry
   rzeczywistego błędu połączenia. Preview nie zapisuje danych.
5. Generujemy OpenAPI i klienta; testujemy oba tryby, request wrapper,
   brak ciężkich wywołań przy wejściu i dostępność siatki.

## Granice i weryfikacja

Nie zmieniamy geometrii użytkownika, kwalifikacji treningowej, limitów
próbek ani schematu DB. Brak migracji, treningu, aktywacji, usuwania danych,
automatycznego wdrożenia, restartów, merge i push. Ograniczony odczyt
rzeczywistych danych w transakcji read-only potwierdzi szybkość w nowym
procesie. Testy modułowe/żądania/interakcji, lint, typy, OpenAPI drift i
znany build Admina mają jawny limit 120 s.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0899 — szybki overview i niezależna siatka | gpt-6.1-sol | high | Spójna zmiana API/SQL/UI z ochroną manifestu i anulowaniem odczytu. | Samokontrola kontraktu i DoD; brak delegowania. |
