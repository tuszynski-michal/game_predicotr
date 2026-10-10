---
title: T06a — odbiór narzędzi etykiet symboli
status: done
last_updated: 2026-09-27
---

# T06a — narzędzia etykiet symboli

## Zakres i status

Operator uruchomił etap C po T05. D-458 rozdziela narzędzia T06a od
rzeczywistego zbioru T06b. Ten raport nie zatwierdza klas, zdjęć, treningu
ani aktywacji modelu. Aktualny snapshot folderowy nie zawiera słowników
lub etykiet symboli. Akceptacja geometrii nie zastępuje tych decyzji.

Wykonawca: `gpt-6-sol`, `medium`. Niezależny audytor:
`gpt-6-sol`, `medium`. Pełny audyt kodu i końcowy odbiór UI PASS.
Commit: `v1.7.31` / `3c90363a825e160c41e2118c5a112d8be914d1b8`.
Kontrola indeksu oraz show/stat/status po commicie PASS; cudze zmiany zachowane.

## Audyt przed implementacją

PASS po jednym cyklu korekty trzech P2:

1. Nieprzepisywalna treść wersji słownika i oddzielna decyzja approval;
   brak cofania aktywnej wersji.
2. Token listy obejmuje także zmiany geometrii, rodzin i holdoutu,
   nie tylko rewizję etykiet.
3. Dokładny crop eksportu DB ma osobny podgląd tylko do odczytu;
   nie jest ponownie wycinany ani konwertowany na lokalną zgodę.

Dodatkowo doprecyzowano atomową publikację cropów, backupu i restore,
rozłączne przestrzenie wersji słowników DB/lab i `label_valid` niezależne
od `trainable`. Trening pozostaje zablokowany przez osobne bramki danych.

## Weryfikacja implementacji

- Wykonawca: 43 testy backendu PASS (17,36 s), osobna seria 39 testów
  adaptera DB i regresji API/anotacji PASS (19,72 s). Serie częściowo
  pokrywają się; nie sumujemy ich jako liczby unikalnych testów.
- Niezależnie: 73 testy backendu, 40 UI i 10 klienta PASS.
- Ruff, Mypy (8 modułów), ESLint, TypeScript UI/klienta, OpenAPI i
  zgodność wygenerowanego klienta PASS. Build produkcyjny PASS.
- Logi wykonawcy: `artifacts/vision-lab/t06a-tests-final.log`,
  `t06a-regression.log`, `t06a-ui-cycle2-final-tests.log`,
  `t06a-client-tests2.log`, `t06a-mypy-cycle1-final.log`,
  `t06a-ruff-check.log`, `t06a-generated-check.log` i `t06a-build-final.log`.

Pierwszy niezależny audyt rdzenia odtworzył dwa P2 na izolowanych fixture:
błędna wartość assignment w starszym podziale nie blokowała podglądu,
a adapter DB po inicjalizacji nie wykrywał podmiany źródłowego obrazu.
Pierwszy cykl poprawek dodał testy odtwarzające. Audytor niezależnie
uruchomił 29 testów bazowych, następnie 73 testy pełniejszego pionu — PASS.
Ponowienie osobnych reprodukcji potwierdziło `MALFORMED_SPLIT_BLOCKED_PASS`
i `DB_SOURCE_TAMPER_BLOCKED_PASS`. Oba P2 backendu zostały zamknięte.
Backup i restore przez CLI w oddzielnych nowych procesach również PASS:
jedna ważna etykieta na fixture, nadal `trainable=false`.

Podczas końcowego audytu pełnego pionu wykryto regresję testowego importu
Next Link w istniejącym `workflow-interactions.test.mjs`: 19 PASS / 1 FAIL.
Wcześniejszy raport 39 PASS nie jest dowodem dla tej nowszej rewizji plików.
Drugi cykl poprawił adapter testowy, zachowując rzeczywisty NextLink
i istniejące asercje. Nowy test potwierdza link, tekst i obsługę kliknięcia.
Niezależny retest: 40/40 PASS. Końcowy audyt pełnego pionu PASS, bez P0–P2.

## Chronione dane

Nie zatwierdzano słowników ani etykiet za operatora. Nie wykonano treningu,
aktywacji, eksportu z żywej bazy ani destrukcyjnych operacji. Testy mają
korzystać wyłącznie z izolowanych fixture. Odczyt realnego API po restarcie:
0 etykiet, 0 słowników, rewizja symboli 0, geometria 268. SHA pliku stanu
geometrii pozostał `084bc39de16502de46f6237cbc2fb453a9dc00665ab20d1319301f44f6efa314`.
Po końcowym odbiorze UI magazyn symboli nadal nie istniał, API zwracało
revision 0 / total 0, a SHA pliku geometrii pozostawał identyczny.

## Odbiór interfejsu i trwałość

Nowy proces API i nowy proces zbudowanego UI odpowiadają HTTP 200.
Pierwsze krótkie okno gotowości API nie objęło jego startu; sprawdzono
ten sam proces i logi, bez uruchamiania drugiej kopii. Powtórny odczyt PASS.
W przeglądarce: panel `/symbols`, sześć gier, wybór Blazing, pusty słownik,
aktywne kontrolki edycji i `0 z 0` PASS, bez zapisów lub dekodowania zdjęć.
Użycie skilla computer-use pozwoliło wykryć i skorygować odstęp linku.
Wąski ekran wykrył drobną P3 szerokości selecta zdjęcia; scoped CSS
otrzymał review PASS. Ponowny build i browser retest 390 px PASS:
pageWidth=clientWidth=375, aktywny pusty edytor i `0 z 0`, bez przepełnienia.
Log końcowej kompilacji: `artifacts/vision-lab/t06a-build-responsive.log`.
Nie wykonano restartu systemu ani testu fizycznego
Androida; dowód trwałości dotyczy nowych procesów i odtworzenia fixture.

## Pozostałe bramki

T06b wymaga rzeczywistych zatwierdzeń oraz właściwego pochodzenia i podziału
symboli. D-453/D-456 nie rozwiązują tych warunków. T07–T09 nie mogą
rozpocząć zależnego wykonania wyłącznie dlatego, że narzędzia T06a działają.
