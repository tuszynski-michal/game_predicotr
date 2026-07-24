---
title: Domain glossary
status: accepted
last_updated: 2026-07-24
---

# Słownik domenowy

## Game

Konfiguracja jednej gry. Określa wymiary planszy, dostępne symbole, koszt spinu, paylines, tabelę wypłat i uporządkowaną sekwencję layoutów.

## Symbol

Pojedynczy typ kafelka widoczny na planszy. Należy do jednej gry i ma stabilny, mały kod używany w snapshotach mobilnych. Może być zwykły albo specjalny.

## Wildcard / Joker

Symbol specjalny bez własnej wypłaty. Może zastąpić zwykły symbol podczas niezależnej oceny payline, ale ciąg złożony wyłącznie z jokerów nie wygrywa. Ten sam joker może reprezentować różne symbole w różnych paylines.

## Cell

Jedna pozycja planszy określona przez `row_index` i `column_index`. W interfejsie administratora numery wierszy są prezentowane od 1, a w kontraktach wewnętrznych są normalizowane do indeksów od 0.

## Board / Layout

Kompletna, uporządkowana tablica symboli o wymiarach określonych przez grę. Kolejność serializacji jest zawsze `row-major`: od lewej do prawej, rząd po rzędzie.

## Layout signature

Deterministyczna, stałoszeroka reprezentacja kodów symboli layoutu w kolejności `row-major`. Służy do dokładnego wyszukiwania, wyszukiwania prefiksowego i wykrywania duplikatów. Nie jest identyfikatorem rekordu.

## Sequence number

Numer pozycji layoutu w cyklicznej kolejności gry i konkretnej wersji zbioru. Jest ciągłą wartością domenową bez luk i nie może być zastąpiony technicznym `id` bazy danych.

## Dataset version

Niezmienna, wersjonowana publikacja uporządkowanych layoutów jednej gry. Zmiana layoutów tworzy nową wersję zamiast modyfikować wydaną wersję.

## Rules version

Niezmienna, wersjonowana publikacja wymiarów gry, symboli, paylines, kosztu spinu i tabeli wypłat. Zmiana reguł wymaga ponownego obliczenia payoutów.

## Mobile release

Wersjonowane wydanie łączące konkretne wersje datasetów i reguł z wygenerowanym snapshotem SQLite oraz APK. Jest instalowane ręcznie na urządzeniach testowych.

## Candidate

Rekord sekwencji zgodny z dotychczas wprowadzonym prefiksem symboli.

## Duplicate layout

Kompletny layout o sygnaturze występującej pod więcej niż jednym `sequence_number`. Aplikacja pokazuje niejednoznaczność i nie uruchamia prognozy. Użytkownik resetuje planszę i wprowadza kolejny layout jako nowe wyszukiwanie.

## Payline

Zdefiniowana ścieżka wybierająca dokładnie jedno pole w każdej kolumnie, np. `[0,1,2,1,0]` wewnętrznie dla kształtu V na planszy 3 × 5. Wartość tablicy określa indeks wiersza, a pozycja — kolumnę.

## Winning run

Nieprzerwany prefiks jednej payline, który zawsze zaczyna się w pierwszej
kolumnie i jest dopasowany do tego samego zwykłego symbolu bez luk. Musi
osiągnąć wersjonowane `minimum_match_length` danego symbolu. Zgodne komórki po
pierwszej luce ani ciągi zaczynające się w późniejszej kolumnie nie wygrywają.
Dla jednej pary payline/symbol wypłacana jest wyłącznie wartość najdłuższego
dopasowania.

## Payout rule

Reguła przypisująca liczbę kredytów do zwykłego symbolu i długości
zwycięskiego ciągu. Każdy zwykły symbol ma w wersji reguł własne
`minimum_match_length`, domyślnie 3 i konfigurowalne od 2 do liczby kolumn.
Panel wymaga payoutu dla każdej długości od tego minimum do końca payline.

## Layout payout

Łączna wypłata jednego layoutu po niezależnej ocenie wszystkich paylines i zsumowaniu prawidłowych wygranych. Jest obliczana podczas przygotowania wydania mobilnego.

## Spin 0

Jednoznacznie rozpoznany layout startowy. Nie kosztuje i jego payout nie jest liczony. Pierwszym ocenianym spinem jest następny layout w sekwencji.

## Spin cost

Koszt każdego ocenianego layoutu po spinie 0. Może mieć wartość np. 10 kredytów i jest konfigurowany dla gry.

## Cumulative payout

Suma payoutów wszystkich ocenionych spinów od pierwszego layoutu po spinie 0. Obejmuje także wypłaty uzyskane wtedy, gdy bieżący wynik netto nadal jest ujemny.

## Cumulative cost

Liczba ocenionych spinów pomnożona przez `spin_cost`.

## Net credits

`cumulative_payout - cumulative_cost`. Wynik jest dodatni wyłącznie wtedy, gdy jest większy od zera.

## Positive local peak

Pierwszy spin osiągający najwyższy dodatni `net credits` na końcu lokalnego odcinka wzrostu lub plateau, zanim wynik spadnie. Nie musi przewyższać wcześniejszego maksimum globalnego.

## Full forecast cycle

Wszystkie przyszłe pozycje cyklicznej sekwencji od layoutu następującego po spinie 0 do layoutu bezpośrednio go poprzedzającego. Dla `N` layoutów ocenianych jest `N - 1` spinów; spin 0 nie jest oceniany ponownie.

## Target forecast

Deterministyczny skan pełnego cyklu, który kumuluje payouty i koszty oraz zwraca dodatnie lokalne maksima wyniku netto w kolejności spinów.

## Job

Wznawialne lokalne zadanie administracyjne, np. import, walidacja, obliczenie payoutów, generowanie snapshotu lub przygotowanie APK. Ma status, postęp, błędy i statystyki.

## Review item

Element wymagający ręcznej decyzji administratora, ponieważ OCR, detekcja planszy lub klasyfikacja symbolu nie osiągnęła wymaganego poziomu pewności.
