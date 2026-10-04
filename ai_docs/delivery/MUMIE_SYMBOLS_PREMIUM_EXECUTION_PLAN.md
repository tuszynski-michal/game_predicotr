---
title: Gra Mumie — symbole od nowa, symbole premium i wygrane premium (plan wykonawczy)
status: proposed
last_updated: 2026-10-04
---

# Gra Mumie — symbole od nowa i symbole premium

> Aktualizacja 2026-10-04: operator uruchomił import i uczenie siatek niezależnie
> od decyzji o mechanice Super. Obowiązuje zakres
> `ai_docs/delivery/MUMIE_TRAINING_RESUME_20261004.md` (TASK-0842, TASK-0843).
> Złota ramka ujawnia symbol wybrany do supergry; poniższy opis wypłat premium
> liczonych po komórkach gdziekolwiek jest nieaktualną interpretacją. Nie wykonywać
> zadań wypłat według tego opisu. Numery TASK-0832–0839 wymagają ponownego przydziału
> przed wznowieniem pozostałych części, ponieważ inne tory zajęły część numerów.

Plan do akceptacji operatora. Realizuje D-489 (symbole dla silnika V3 są
wybierane i uczone od nowa) i wymagania premium zapisane w D-490 dla gry
Mumie. Nie zmienia danych ani działania gry 777.

## Stan obecny

Fakty z repo, dokumentów i rozmów z operatorem (2026-10-02–04):

- **Siatki.** Silnik `neural_grid` z profilem „Mumie” (TASK-0830, model po
  doszkoleniu, run 3 iteracja 3) daje siatki Mumii przyjmowane przez
  operatora bez zmian w 79% plansz. Bramka kompletności zdjęcia (D-484,
  D-485) blokuje cięcie, dopóki zdjęcie nie ma kompletu poprawnych siatek.
- **Symbole w aplikacji.** Gra ma katalog symboli (`symbols`, kod mobilny,
  kolejność), weryfikację per komórka (D-462), bibliotekę wzorców z
  propozycjami (D-464–D-466) i przypisywanie symboli w korekcie siatki
  (D-488). Modele symboli v1.1 i biblioteka wzorców uczyły się na 777.
- **D-489.** Dla V3 operator przypisuje symbole od zera po pocięciu nową
  siatką; stare etykiety wolno użyć wyłącznie po fakcie do listy
  rozbieżności, bez wpływu na trening i podpowiedzi.
- **Premium (D-490, wymagania operatora).** Symbolem premium może być
  każdy symbol gry; rozpoznaje się go wyłącznie po złotej ramce wokół
  komórki na danej planszy (czas trwania trybu nie jest regułą). Wygrana
  premium zależy od liczby symboli premium na planszy niezależnie od
  pozycji (np. 2, 3, 4, 5 sztuk → różne wartości). Obok niej liczone są
  zwykłe linie (5 linii w Mumii; 777 ma 20). Złota rama wokół całej
  planszy na części klatek to prawdopodobnie animacja przejścia. Gra ma
  przy tworzeniu przełącznik „premium”, a wypłaty premium są wpisywane w
  osobnej zakładce obok zwykłych wypłat.
- **Otwarte (operator weryfikuje):** czy symbol premium liczy się
  jednocześnie w liniach jako zwykły symbol.
- **Dane Mumii w produkcji:** gra nie ma jeszcze importu w bazie (w
  katalogu jest tylko 777). W labie jest 236 zdjęć Mumii, 20 z kompletem
  siatek zatwierdzonych przez operatora.

## Cel

Dla gry Mumie: import nowych zdjęć tnie plansze siatkami profilu „Mumie”,
każda komórka dostaje dwie niezależne odpowiedzi — symbol oraz „premium:
tak/nie” — potwierdzane przez operatora, a liczenie wygranej uwzględnia
zwykłe linie i wygraną premium według tabeli gry; aplikacja mobilna
pokazuje obie składowe.

## Zakres i reguły

- **Kolejność:** siatka całego zdjęcia zamknięta (D-484) → wycinki →
  symbole i premium → wypłaty. Zmiana siatki po przypisaniu symboli
  unieważnia wycinki według istniejących reguł (`geometry_invalidated`).
- **Premium to cecha komórki, nie klasa symbolu.** Nie tworzymy symboli
  „sfinks premium”; komórka ma `symbol` i osobne `premium: bool` z
  własnym stanem weryfikacji. Dzięki temu katalog symboli i linie wypłat
  zostają bez zmian, a przełącznik gry decyduje, czy pole premium w ogóle
  istnieje.
- **Wycinek komórki z marginesem.** Ramka premium leży przy krawędzi
  komórki; wycinek do rozpoznania premium ma margines (proponowany 8%
  szerokości komórki z każdej strony), żeby ramka nie została ucięta przy
  przesunięciu siatki o kilka pikseli. Wycinek symbolu pozostaje jak
  dotąd.
- **Symbole od nowa (D-489).** Zbiór symboli Mumii zakłada operator w
  katalogu gry. Etykiety powstają przez grupowanie: wycinki są grupowane
  automatycznie (cechy obrazu, bez starych etykiet), operator nazywa grupy
  i poprawia wyjątki; potem model symboli Mumii uczy się na potwierdzonych
  etykietach. Premium operator oznacza w tym samym przeglądzie (klawisz).
- **Stare etykiety tylko po fakcie.** Dla Mumii starych etykiet nie ma;
  reguła porównania po fakcie dotyczy przyszłych gier 777 v2+.
- **Izolacja gier:** wszystkie nowe dane są w tabelach gry (partycje
  `LIST (game_id)`); model symboli Mumii jest osobnym artefaktem z wersją,
  wskazywanym przez grę, jak profil siatek (TASK-0830).
- **Wypłaty premium:** tabela „liczba symboli premium na planszy → wartość”
  w wersji reguł gry, obok linii; obliczenie wygranej = suma linii +
  wygrana premium. Jeżeli operator potwierdzi, że premium nie liczy się w
  liniach, reguła linii pomija komórki premium — decyzja przed zadaniem
  wypłat.

## Decyzje do potwierdzenia przez operatora

1. Premium jako osobna cecha komórki (nie osobne symbole w katalogu).
2. Przełącznik „Gra premium” przy tworzeniu gry i zakładka „Wypłaty
   premium” w wersji reguł; na razie jeden wariant reguł (Mumie).
3. Czy symbol premium liczy się także w liniach (otwarte).
4. Przypisywanie symboli przez grupowanie wycinków z nazywaniem grup przez
   operatora; szacowany koszt: kilkadziesiąt minut na kilkaset zdjęć,
   pomiar na pierwszych 20.
5. Margines wycinka premium 8% (do korekty po pierwszych próbach).

## Etapy i zadania

Każdy etap wymaga jawnego uruchomienia; po etapie STOP z raportem. Numery
TASK-0832–0839 są zarezerwowane dla tego planu.

### Etap M-A — model danych i reguły

- **TASK-0832 — przełącznik premium gry i wypłaty premium.** Pole gry
  (migracja), tabela wypłat premium w wersji reguł (tabela gry albo
  rozszerzenie istniejących reguł — wybór po analizie modelu reguł),
  walidacja (rosnące liczby sztuk, wartości ≥ 0), Admin (przełącznik,
  zakładka), API pionem. Kryteria: gra bez premium działa jak dotąd; test
  PG wersji reguł z premium.
- **TASK-0833 — cecha premium komórki.** Kolumny stanu premium w komórkach
  weryfikacji (wartość, źródło, stan, autor), zdarzenia, liczniki; tylko
  dla gier z przełącznikiem. Kryteria: zmiana siatki unieważnia premium
  razem z symbolem; test PG.
- **TASK-0834 — liczenie wygranej z premium.** Ewaluator: linie + premium;
  złote przypadki w `packages/domain-fixtures` (Python i TS); snapshot
  mobilny niesie premium; aplikacja mobilna pokazuje obie składowe.
  Wymaga decyzji 3.

### Etap M-B — import i siatki

- **TASK-0835 — import Mumii profilem siatek „Mumie”.** Pipeline importu
  używa modelu profilu gry (TASK-0830) dla gier z tym profilem; bramka
  kompletności bez zmian; bez zmian dla 777. Kryteria: import testowy 10
  zdjęć Mumii daje komplet siatek albo jawne braki w kolejce.

### Etap M-C — symbole i premium od nowa

- **TASK-0836 — grupowanie wycinków i nazywanie grup.** Cechy obrazu
  (bez starych etykiet), grupowanie, ekran operatora: nazwa grupy →
  symbol z katalogu, wyjątki, klawisz premium; zapis jako decyzje
  człowieka. Pomiar czasu na 20 zdjęciach.
- **TASK-0837 — model symboli i premium Mumii.** Trening na potwierdzonych
  etykietach (dwie głowice: symbol, premium), walidacja na odłożonych
  zdjęciach, ONNX, rejestr modelu gry; budżet treningu do ustalenia przy
  akceptacji.
- **TASK-0838 — predykcja i weryfikacja w aplikacji.** Model symboli
  Mumii daje propozycje w istniejącej weryfikacji symboli; premium jako
  osobne pole w widoku komórki.

### Etap M-D — odbiór

- **TASK-0839 — odbiór end to end.** Import → siatki → symbole i premium →
  wygrana → snapshot mobilny na zbiorze testowym Mumii; raport.

## Błędy i przypadki brzegowe

| Sytuacja | Reakcja |
|---|---|
| Ramka premium częściowo zasłonięta ręką | premium „nie da się ocenić”, komórka do przeglądu |
| Złota rama całej planszy (klatka animacji) | nie jest premium; model uczony na przykładach z ramą |
| Gra bez przełącznika premium | pole premium nie istnieje; wypłaty tylko z linii |
| Zmiana siatki po przypisaniu | symbol i premium unieważnione razem |
| Plansza bez kompletu siatek zdjęcia | brak cięcia (D-484) |

## Mapa wymaganie → zadanie → kryterium

| Wymaganie | Zadania | Kryterium |
|---|---|---|
| Premium rozpoznawane po ramce, niezależnie od symbolu | 0833, 0836, 0837 | osobne pole premium, model z dwiema głowicami |
| Wygrana premium wg liczby sztuk | 0832, 0834 | złote przypadki, test ewaluatora |
| Przełącznik premium przy tworzeniu gry | 0832 | Admin, test regresji gry bez premium |
| Symbole od nowa bez starych etykiet (D-489) | 0836, 0837 | dane uczące wyłącznie z decyzji operatora |
| Siatki Mumii z profilu „Mumie” | 0835 | import testowy |
| Izolacja gier | wszystkie | tabele gry, model per gra |

## Ryzyka

- Ramka premium jest cienka; rozmycie i odblask mogą ją ukryć — margines
  wycinka i stan „nie da się ocenić”.
- Mało danych Mumii w produkcji; pierwsze modele symboli będą słabe —
  pętla jak przy siatkach (porcja, doszkolenie, pomiar).
- Reguła linii przy premium nieznana do czasu decyzji 3.

## Zakres wyłączony

Gry 777 i 777 v2 (bez premium), Gang i Blazing, zmiany istniejących danych
777, warianty premium innych gier.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0832 | claude-opus-5-5 | high | Migracja, model reguł i kontrakt API pionem. | Zawieszony; przy wznowieniu claude-opus-5-5, medium |
| TASK-0833 | claude-opus-5-5 | high | Zmiana tabel komórek i unieważniania przy zmianie siatki. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0834 | claude-opus-5-5 | high | Ewaluator wypłat, złote przypadki w dwóch językach, snapshot mobilny. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0835 | claude-opus-5-5 | high | Zmiana pipeline importu (wybór silnika per gra). | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0836 | claude-opus-5-5 | high | Grupowanie bez starych etykiet i narzędzie operatora. | Zawieszony; przy wznowieniu claude-opus-5-5, medium |
| TASK-0837 | claude-opus-5-5 | high | Trening dwóch głowic, walidacja, ONNX. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0838 | claude-sonnet-5-5 | high | Podłączenie predykcji do istniejącej weryfikacji. | Zawieszony; przy wznowieniu claude-opus-5-5, medium |
| TASK-0839 | claude-opus-5-5 | high | Odbiór end to end i raport. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
