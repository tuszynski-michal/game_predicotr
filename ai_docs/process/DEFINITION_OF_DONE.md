---
title: Definition of Done
status: active
last_updated: 2026-07-31
---

# Definition of Done

Zadanie jest ukończone, gdy wszystkie właściwe punkty są spełnione.

## Funkcjonalność

- kryteria akceptacji zadania są spełnione,
- zachowanie brzegowe jest obsłużone,
- brak ukrytego rozszerzenia zakresu,
- wartości domenowe nie są mylone z identyfikatorami technicznymi.

## Kod

- kod jest czytelny i podzielony zgodnie z architekturą,
- nie ma zbędnego duplikowania,
- nie ma martwego kodu ani tymczasowych obejść bez oznaczenia,
- logika domenowa nie zależy od UI lub frameworka HTTP,
- konfiguracja środowiskowa nie jest hardkodowana,
- naprawa problemu usuwa jego przyczynę trwale w repozytorium albo profilu
  użytkownika i została sprawdzona w nowym procesie; zmiana tylko bieżącej sesji
  nie spełnia Definition of Done.

## Dane

- zmiana schematu ma migrację,
- migracja ma bezpieczną ścieżkę uruchomienia,
- seedy są idempotentne,
- kolejność sekwencji jest chroniona constraintem lub walidacją,
- duplikaty signature są obsługiwane świadomie.

## Kontrakt

- OpenAPI odzwierciedla implementację,
- klient TypeScript został zregenerowany, gdy zmieniło się API,
- błędy mają stabilny kod,
- zmiana breaking jest jawnie odnotowana.

## Testy i narzędzia

- testy nowego zachowania istnieją,
- właściwe testy zostały uruchomione,
- lint/format/typecheck przeszły dla zmienionych modułów,
- wynik komend jest zapisany w Outcome zadania.

## UX

Dla zmian UI:

- loading, empty i error mają stan,
- interakcja działa na Android,
- brak przypadkowego podwójnego submitu,
- elementy dotykowe są wystarczająco duże,
- ważna informacja nie jest przekazywana wyłącznie kolorem.

## Dokumentacja

- aktywne zadanie ma wypełniony Outcome,
- `CURRENT_STATE.md` jest aktualny,
- wymagania/architektura są zaktualizowane, jeśli potrzeba,
- istotna decyzja ma wpis w `DECISION_LOG.md`,
- instrukcje uruchomienia są aktualne.

## Raport końcowy

Agent podaje:

1. zmienione elementy,
2. weryfikację,
3. znane ograniczenia,
4. następne zalecane zadanie.
