---
title: Approximate mobile snapshot from every board
status: proposed
last_updated: 2026-09-30
---

# Plan: przybliżony snapshot mobilny ze wszystkich plansz

Status: **propozycja do akceptacji operatora**. Plan wymaga nowej decyzji
(proponowane D-463), bo zmienia zasadę D-462/P4, według której snapshot
mobilny korzysta wyłącznie z plansz domkniętych.

## 1. Wymaganie operatora (2026-09-30)

- Wszystkie plansze biorą udział w wyliczeniach, także w aplikacji mobilnej,
  również gdy są niepełne albo niepewne (niezweryfikowane).
- Za każdy spin liczony jest koszt, także gdy planszy brakuje.
- Plansza przycięta z prawej z widoczną wygraną ma pokazać, że wygrywa, nawet
  jeśli to nie cała wygrana.

## 2. Stan obecny (fakty z kodu i odczytu bazy 2026-09-30)

| # | Fakt | Źródło |
|---|---|---|
| F1 | Snapshot mobilny czyta `layouts` + `layout_payouts` jednej wersji datasetu i reguł. | `services/worker/src/game_predictor_worker/snapshots/store.py::SqlAlchemyProductionSnapshotStore` |
| F2 | Wersja datasetu powstaje tylko z importu pliku layoutów (CSV) albo z generatora testowego; brak ścieżki „plansze ze zdjęć → dataset”. | `storage/layout_import_report_repository.py`, `storage/dataset_repository.py::add_mock_dataset` |
| F3 | `image_layout_staging_rows` powstają wyłącznie z plansz rozstrzygniętych; gra `777` ma dziś 0 takich plansz i 0 wersji datasetu. | `DATA_MODEL.md` `image_layout_staging_rows`, odczyt |
| F4 | Projekcja wyszukiwania ma dokument dla każdej z 500 000 pozycji gry `777` (po TASK-0730): predykcja modelu + zweryfikowane komórki (D-462), pola nieznane = `null`. | `image_board_search_fast_documents`, TASK-0730 |
| F5 | „Przybliżona wygrana” liczy koszt każdego spinu, a wypłatę regułą `payout-v3-unknown-prefix-stop` (`confirmed_minimum` dla planszy niepełnej). | `domain/board_search_approximate_win.py` |
| F6 | Kod `0` jest sentinelem „nieznane” w layoutach, snapshocie v4 i payout v3 (D-247); użytkownik nie może go wpisać. | D-247 |
| F7 | Aplikacja dopasowuje wpisaną planszę **dokładnie** po sygnaturze (indeks `idx_layouts_game_signature`); Target używa zapisanej wypłaty każdego layoutu. | `apps/mobile/src/data/local-layout-repository.ts` |
| F8 | Gra `777`: reguły v2 opublikowane (3 × 5, koszt spinu 100). | odczyt `rules_versions` |

Wniosek: dziś aplikacja mobilna nie liczyłaby żadnej planszy `777`, a sama
zmiana D-462/P4 nie wystarczy — brakuje całej ścieżki danych ze zdjęć do
datasetu oraz dopasowania odpornego na pola nieznane i błędy predykcji.

## 3. Proponowana decyzja D-463 (do akceptacji)

- **Źródło:** przybliżony dataset gry powstaje z projekcji wyszukiwania
  (ta sama, co „Przybliżona wygrana”): zweryfikowana komórka = pewny symbol,
  niezweryfikowana = predykcja modelu, pole bez dowodu = nieznane (`0`),
  pozycja bez planszy = layout samych nieznanych.
- **Klasa dowodu layoutu:** `verified` (15/15 dowodów), `predicted`
  (co najmniej jedna predykcja, bez nieznanych), `partial` (co najmniej jedno
  nieznane), `missing` (brak planszy). Klasa trafia do snapshotu i UI.
- **Wypłata:** `payout-v3-unknown-prefix-stop`; dla `partial` wynik jest
  „potwierdzonym minimum”, dla `missing` 0; koszt spinu zawsze.
- **Dopasowanie w aplikacji:** pole nieznane pasuje do każdego symbolu;
  pole zweryfikowane musi się zgadzać; na polach z predykcją dopuszczalne
  są różnice do limitu (patrz Q2). Wynik wskazuje liczbę różnic i klasę
  dowodu; kandydat niejednoznaczny działa jak dzisiejszy „duplicate”.
- **Rozdział:** przybliżony dataset jest osobnym rodzajem wersji
  (`generator_version` projekcji); przyszły dataset „pewny” z plansz
  domkniętych (D-462) pozostaje osobny. Layout, trening i target desktopowy
  z plansz domkniętych bez zmian.
- **Zastępuje:** zdanie D-462 „snapshot mobilny … korzystają wyłącznie z
  planszy domkniętej” i P4 — wyłącznie dla przybliżonego snapshotu.

### Pytania do operatora (z rekomendacją)

| # | Pytanie | Rekomendacja |
|---|---|---|
| Q1 | Źródło danych przybliżonych | Projekcja wyszukiwania (spójność z „Przybliżoną wygraną”). |
| Q2 | Ile różnic na polach z predykcją dopuścić przy dopasowaniu? | Do 2 różnic; wynik zawsze pokazuje liczbę różnic; przy remisie kandydatów — „duplicate”. Limit do potwierdzenia pomiarem (T6). |
| Q3 | Czy pokazywać plansze `missing` w Target jako wiersz? | Nie; liczą koszt, a podsumowanie pokazuje ich liczbę. |
| Q4 | Jak często budować snapshot? | Ręcznie z Admina (jak dziś), każda budowa = nowa wersja. |

## 4. Etapy i taski (proponowane)

### Etap A — decyzja i dane

- **T1 / TASK-0731** — D-463, `MOBILE_APP.md`, `ALGORITHMS.md`,
  `DATA_MODEL.md` (klasa dowodu, dopasowanie tolerancyjne, rodzaj datasetu).
- **T2 / TASK-0732** — Alembic: klasa dowodu layoutu (`layouts.evidence_class`
  albo tabela pomocnicza — decyzja w tasku po sprawdzeniu indeksów) i rodzaj
  wersji datasetu. Bez zmiany istniejących wierszy.
- **T3 / TASK-0733** — job budowy przybliżonego datasetu z projekcji
  wyszukiwania: preview (liczności klas, luki, checksum) → jawne
  utworzenie wersji `staging` w partiach; walidacja ciągłości 1..N.
- **T4 / TASK-0734** — wypłaty `payout-v3-unknown-prefix-stop` dla tej wersji
  z rodzajem wypłaty (`exact` / `confirmed_minimum`), korzystając z
  istniejącego joba wypłat.

### Etap B — snapshot i aplikacja

- **T5 / TASK-0735** — snapshot schema v5: klasa dowodu, rodzaj wypłaty,
  maska pól zweryfikowanych; generator, walidator, manifest, kodek
  `packages/shared-ts`.
- **T6 / TASK-0736** — aplikacja: dopasowanie tolerancyjne (nieznane =
  dowolny symbol, pola zweryfikowane dokładnie, limit różnic z Q2), bez
  blokowania UI; benchmark na 500 000 layoutach jako bramka (wzorzec
  `m35`). Na liście wyników i w Target oznaczenia klasy dowodu i
  „potwierdzonego minimum”.
- **T7 / TASK-0737** — Admin: podgląd i budowa przybliżonego snapshotu gry,
  wydanie APK (istniejący przepływ release).

### Etap C — odbiór

- **T8 / TASK-0738** — odbiór na grze `777`: dataset 500 000 layoutów z
  klasami, snapshot v5, APK bez `INTERNET`, scenariusze dopasowania
  (pełna zgodność, 1–2 różnice, plansza przycięta z prawej z wygraną,
  pozycja `missing`), zgodność wyniku Target z „Przybliżoną wygraną”.

## 5. Mapa wymaganie → task → test

| Wymaganie | Task | Test / kryterium |
|---|---|---|
| Wszystkie plansze w aplikacji | T3, T5 | dataset i snapshot mają N layoutów, każda pozycja 1..N |
| Niepewne plansze liczone | T3, T6 | predykcja w layoucie; dopasowanie z różnicami |
| Koszt każdego spinu | T4, T6 | Target = koszt × spiny, także dla `missing` |
| Plansza przycięta z prawej wygrywa | T4, T6 | `confirmed_minimum` > 0 w Target dla planszy `partial` |
| Spójność z Admin | T8 | Target mobilny = „Przybliżona wygrana” dla tego samego zakresu |

## 6. Ryzyka i poza zakresem

- Błędna predykcja może dopasować układ do złej pozycji; ograniczają to
  pola zweryfikowane, limit różnic i jawna liczba różnic w UI.
- Wydajność dopasowania tolerancyjnego na urządzeniu (500 000 × 15 pól) —
  bramka benchmarku w T6; fallback: dopasowanie na blokach pól.
- Rozmiar snapshotu rośnie o klasę i maskę — mierzone w T5.
- Poza zakresem: zmiana treningu, kalibracji, layoutu kanonicznego i
  datasetu z plansz domkniętych; połączenie aplikacji z API (nadal offline).

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-0731 | claude-opus-5-5 | high | Zmiana decyzji domenowej i wymagań trzech dokumentów. | Tak: claude-opus-5-5, high |
| T2 / TASK-0732 | claude-opus-5-5 | high | Migracja schematu na dużych tabelach, zgodność wstecz. | Tak: claude-opus-5-5, high |
| T3 / TASK-0733 | claude-opus-5-5 | high | Budowa 500 000 layoutów z projekcji, partie, preview. | Tak: claude-opus-5-5, high |
| T4 / TASK-0734 | claude-sonnet-5-5 | high | Rozszerzenie istniejącego joba wypłat o rodzaj wypłaty. | Tak: claude-opus-5-5, high |
| T5 / TASK-0735 | claude-opus-5-5 | high | Nowa wersja schematu snapshotu, kodek współdzielony. | Tak: claude-opus-5-5, high |
| T6 / TASK-0736 | claude-opus-5-5 | high | Algorytm dopasowania i wydajność na urządzeniu. | Tak: claude-opus-5-5, high |
| T7 / TASK-0737 | claude-sonnet-5-5 | medium | UI Admina na istniejących wzorcach. | Tak: claude-opus-5-5, high |
| T8 / TASK-0738 | claude-opus-5-5 | high | Odbiór end-to-end na żywych danych. | Tak: claude-opus-5-5, high |
