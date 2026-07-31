---
title: Version 0.1 release plan
status: accepted
last_updated: 2026-07-31
---

# Plan wydania 0.1 — reprezentatywna aplikacja offline z 500 000 layoutów

## Cel

Zamknąć pierwszą kompletną wersję demonstracyjną jako instalowalne APK dla
Google Pixel 10 Pro XL. Wydanie ma pokazać rzeczywisty interfejs symboli,
matching, obsługę duplikatów oraz pełny Target na 500 000 layoutów, bez
oczekiwania na docelowy automatyczny import wszystkich zdjęć i pełny hardening
operacyjny `0.2`.

## Zamrożony zakres

- jedna gra oparta na obecnym katalogu i ponad 100 planszach zatwierdzonych
  przez człowieka,
- reprezentatywne grafiki symboli wybrane z zatwierdzonych cropów oraz podpisane
  nazwami z katalogu gry, np. `lemon`, `orange`, `watermelon`, `seven`,
- dokładnie 500 000 deterministycznie uporządkowanych layoutów,
- zatwierdzone layouty zachowane jako kanoniczny, chroniony podzbiór,
- brakujące pozycje dopełnione deterministycznym generatorem pseudolosowym;
  seed, wersja generatora i checksum muszą znaleźć się w raporcie,
- duplikaty sygnatur pozostają dozwolone i raportowane,
- 10 wzorców PAYLINE: trzy poziome oraz siedem jawnie zapisanych wariantów,
  w tym warianty typu V, odwrócone V i zygzak/krzyż zgodne z zasadą jednej
  komórki na kolumnę,
- deterministyczne testowe minima symboli i payouty; „losowe” oznacza
  wygenerowane raz z zapisanym seedem, a nie zmienne między buildami,
- precomputed payout dla wszystkich 500 000 layoutów,
- zweryfikowany snapshot SQLite, manifest i prywatny APK bez uprawnienia
  `INTERNET`,
- paczka artefaktów przygotowana bez wymagania podłączonego telefonu.

## Zadania

### TASK-0118 — Representative 500k offline release candidate

Następne zadanie. Obejmuje wybór grafik symboli, utworzenie testowych reguł,
paylines i payoutów, wygenerowanie/dopełnienie 500 000 layoutów, precomputing,
snapshot, APK i statyczny raport weryfikacji. Nie instaluje APK, dopóki telefon
pozostaje odłączony.

### TASK-0119 — Pixel 10 Pro XL release acceptance

Po powrocie właściciela i podłączeniu telefonu: aktualizacja lub instalacja APK,
tryb offline, unique/duplicate/not_found, pełny Target, płynność tabeli,
restart aplikacji oraz zapis końcowego czasu i rozmiaru. To zadanie zamyka
bramkę wydania `0.1`.

## Bramka V0.1

- APK instaluje się lub aktualizuje na Pixelu 10 Pro XL,
- działa po odłączeniu sieci i nie ma uprawnienia `INTERNET`,
- snapshot zawiera dokładnie 500 000 layoutów wybranej gry,
- manifest wiąże wersje gry, reguł, datasetu, generatora i algorytmu,
- grafiki i nazwy symboli są czytelne w mobile,
- duplicate nie uruchamia Target,
- unique uruchamia pełny cykl `499 999` spinów,
- tabela wyników pozostaje płynna,
- brak błędu blokującego podstawowy przepływ.

## Świadomie odłożone do 0.2

- przebudowa informacji i nawigacji panelu Admin,
- docelowy folderowy import zdjęć i automatyczne budowanie katalogu symboli,
- automatyczna publikacja 500 000 rzeczywistych layoutów ze zdjęć,
- stabilny produkcyjny klucz podpisujący i pełna odtwarzalność release,
- backup/restore, recovery uszkodzonego snapshotu i formalny rollback,
- rozszerzona macierz urządzeń oraz finalna dostępność,
- retencja/usuwanie wydań, jobów i artefaktów.

Zdalny Reviewer, ochrona lokalnego Admina i test Pixela wykonane przed tym
planem pozostają częścią `0.1`; nie są cofane przez zmianę zakresu.
