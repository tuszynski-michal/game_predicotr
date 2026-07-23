---
title: Analysis of an existing Windows reference application
status: proposed
last_updated: 2026-07-23
---

# Analiza istniejącej aplikacji Windows

## Co można sprawdzić bez kodu źródłowego

Tak, zbudowaną aplikację można analizować jako system referencyjny, ale nie oznacza to odzyskania dokładnego kodu ani pełnej logiki.

### Black-box analysis

Najbezpieczniejsza metoda:

- spisać wszystkie ekrany i stany,
- nagrać scenariusze działania,
- sprawdzić walidacje i komunikaty,
- przygotować zestaw wejść i oczekiwanych wyników,
- zmierzyć czasy odpowiedzi,
- porównać przypadki duplikatów i graniczne.

Wynikiem powinna być specyfikacja zachowania, nie kopia interfejsu 1:1.

### Analiza plików lokalnych

Za zgodą właściciela można sprawdzić:

- katalog instalacji,
- pliki konfiguracyjne,
- lokalne bazy SQLite lub inne jawne pliki danych,
- logi,
- foldery cache i eksporty,
- informacje o wersji i użytych bibliotekach.

Nie należy modyfikować ani omijać zabezpieczeń aplikacji.

### Analiza ruchu sieciowego

Jeżeli aplikacja komunikuje się z serwerem i właściciel zezwala na test:

- można obserwować domeny, endpointy i formaty danych,
- szyfrowany ruch nie powinien być przechwytywany przez obchodzenie zabezpieczeń bez wyraźnej zgody,
- dane logowania i dane osobowe należy chronić.

### Inspekcja techniczna pliku wykonywalnego

Czasem można ustalić framework, zależności i ogólną strukturę. Możliwość dekompilacji zależy od technologii:

- aplikacje .NET zwykle ujawniają więcej struktury,
- Electron może zawierać spakowane zasoby JavaScript,
- natywny C/C++ jest znacznie trudniejszy,
- obfuskacja i zabezpieczenia ograniczają analizę.

Nawet gdy dekompilacja jest technicznie możliwa, nie daje gwarancji poprawnego kodu źródłowego i może naruszać licencję lub prawa właściciela.

## Zalecany proces

1. Uzyskaj zgodę właściciela na analizę.
2. Pracuj na kopii w odizolowanym środowisku.
3. Zacznij od black-box testów.
4. Zapisuj scenariusze w tabeli: wejście → działanie → wynik.
5. Wykorzystaj aplikację jako źródło przypadków testowych dla własnej implementacji.
6. Nie kopiuj nazw, grafik ani chronionych elementów, jeśli nie masz praw.

## Artefakt do przygotowania

```text
reference-app/
  SCREEN_INVENTORY.md
  USER_FLOWS.md
  BEHAVIOR_TEST_CASES.md
  DATA_IMPORT_OBSERVATIONS.md
  ALGORITHM_EXAMPLES.md
  DIFFERENCES_FROM_NEW_PRODUCT.md
```

## Największa wartość

Najbardziej użyteczne będzie zebranie rzeczywistych przykładów wejść i wyników algorytmu. Pozwoli to stworzyć golden tests bez konieczności odtwarzania wewnętrznego kodu aplikacji.
