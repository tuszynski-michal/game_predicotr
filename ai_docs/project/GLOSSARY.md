---
title: Domain glossary
status: proposed
last_updated: 2026-07-23
---

# Słownik domenowy

## Game

Konfiguracja jednej gry. Określa rozmiar planszy, dostępne symbole, koszt spinu, reguły wygranych i uporządkowaną sekwencję layoutów.

## Symbol

Pojedynczy typ kafelka widoczny na planszy. Symbol należy do jednej gry. Może być zwykły albo specjalny.

## Wildcard / Joker

Symbol specjalny, który może zastępować inny symbol według reguł danej gry. Dokładne ograniczenia zastępowania wymagają decyzji.

## Cell

Jedna pozycja planszy określona przez `row_index` i `column_index`, indeksowane od zera w kodzie.

## Board / Layout

Kompletna, uporządkowana tablica symboli o wymiarach określonych przez grę. Kolejność serializacji jest zawsze `row-major`: od lewej do prawej, rząd po rzędzie.

## Layout signature

Deterministyczny tekst reprezentujący wszystkie symbole layoutu w kolejności `row-major`, np. `1,2,3,1,2,...`. Służy do wyszukiwania i wykrywania duplikatów. Nie jest identyfikatorem rekordu.

## Sequence number

Numer pozycji layoutu w kolejności gry. Jest wartością domenową widoczną użytkownikowi. Nie może być zastąpiony automatycznym `id` bazy danych.

## Candidate

Rekord sekwencji zgodny z dotychczas wprowadzonym prefiksem symboli.

## Ambiguous match

Sytuacja, w której podany layout lub sekwencja layoutów pasuje do więcej niż jednej pozycji.

## Confirmation chain

Kolejne layouty podane przez użytkownika w celu rozstrzygnięcia duplikatu. Przykład: layout występuje pod numerem 100 i 20 000; następny layout pozwala ustalić właściwy kandydat.

## Payline

Zdefiniowana ścieżka po jednym polu w każdej kolumnie, np. `[0,1,2,1,0]` dla kształtu V na planszy 3 × 5.

## Consecutive-columns rule

Reguła, w której ten sam symbol ma występować w kolejnych kolumnach, a rząd może być dowolny. Jest to osobny typ reguły od `Payline`.

## Payout rule

Reguła przypisująca liczbę kredytów do symbolu, liczby kolejnych kolumn oraz opcjonalnie typu lub identyfikatora wzorca.

## Spin cost

Koszt przejścia do następnego layoutu w sekwencji.

## Net credits

Skumulowane wygrane pomniejszone o skumulowane koszty kolejnych spinów.

## Target forecast

Analiza kolejnych layoutów od jednoznacznie ustalonej pozycji, maksymalnie do skonfigurowanego limitu, domyślnie 100 000.

## High-water mark

Nowy najwyższy dodatni wynik `net credits`. Tylko takie rekordy mają być prezentowane w skróconej tabeli wyników, o ile właściciel produktu nie zdecyduje inaczej.

## Import job

Wznawialne zadanie przetwarzające folder zdjęć. Ma status, postęp, błędy i statystyki.

## Review item

Element wymagający ręcznej decyzji administratora, ponieważ OCR, detekcja planszy lub klasyfikacja symbolu nie osiągnęła wymaganego poziomu pewności.
