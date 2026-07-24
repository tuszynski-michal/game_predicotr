---
title: Algorithms specification
status: accepted
last_updated: 2026-07-24
---

# Specyfikacja algorytmów

Logika jest podzielona na niezależne, deterministyczne moduły domenowe. Każdy moduł ma czyste wejścia i wyjścia oraz osobne testy. Dostęp do SQLite, UI i zadania administracyjne są adapterami poza logiką domenową.

## A. Layout matching

### Wejście

```text
game_id
symbols: [symbol_code | null] w kolejności row-major
mobile_release_version
```

### Walidacja

- długość tablicy odpowiada `rows * columns`,
- niepuste symbole należą do gry,
- po pierwszym `null` nie może wystąpić niepusty symbol, ponieważ wprowadzanie jest prefiksowe,
- gra i snapshot są aktywne oraz zgodne wersją,
- sygnatura używa tej samej zapisanej `signature_cell_width` co etap
  generowania datasetu i wydania; szerokości nie wyprowadza się z aktualnie
  wprowadzonego layoutu.

### Częściowy layout

1. Zamień wprowadzone symbole na prefiks sygnatury.
2. Wyszukaj lokalnie pozycje, których sygnatura zaczyna się od prefiksu.
3. Zwróć:
   - `candidate_count`,
   - pełny layout wyłącznie przy dokładnie jednym kandydacie,
   - `sequence_number` pojedynczego kandydata.

### Pełny layout

1. Wylicz pełną sygnaturę.
2. Znajdź wszystkie rekordy o tej sygnaturze w grze i wersji datasetu.
3. Zwróć:
   - `not_found` dla 0 rekordów,
   - `unique` dla 1 rekordu,
   - `duplicate` dla więcej niż 1 rekordu.

Nie wolno wybierać pierwszego rekordu tylko dlatego, że ma najniższy numer.

### Obsługa duplikatu

- wynik zawiera liczbę wystąpień oraz numery, jeżeli ich zwrócenie mieści się w limicie diagnostycznym,
- prognoza nie jest uruchamiana,
- nie powstaje token ani łańcuch potwierdzania,
- Reset usuwa wynik i wszystkie kandydatury,
- kolejny layout podany po Reset jest całkowicie nowym wyszukiwaniem i, jeżeli jest jednoznaczny, staje się nowym spinem 0.

## B. Payout evaluation

### Wejście

```text
game configuration
pełny layout
aktywna rules_version
aktywne paylines
aktywne payout rules
```

### Wyjście

```text
total_payout
matches[]:
  symbol_code
  payline_id
  start_column
  matched_length
  matched_cells
  joker_cells
  payout
  interpretation
```

`start_column` oraz indeksy w `matched_cells` i `joker_cells` są 0-based.
Komórki używają indeksu `row-major`: `row * columns + column`.
`interpretation` jest listą struktur
`(cell_index, as_symbol_mobile_code)`, dzięki czemu nie wymaga parsowania
tekstu.

### Payline

`row_path` ma dokładnie jeden indeks wiersza dla każdej kolumny:

```json
{
  "row_path": [0, 1, 2, 1, 0]
}
```

Walidacja odrzuca:

- długość inną niż liczba kolumn,
- indeks wiersza spoza planszy,
- duplikat identycznego `row_path` w tej samej wersji reguł.

UI administracyjne pokazuje numery wierszy od 1, ale granica API normalizuje je do indeksów od 0.

### Zwycięski ciąg

Dla każdej pary `(payline, zwykły symbol)`:

1. odczytaj po jednej komórce z kolejnych kolumn,
2. traktuj komórkę jako zgodną, gdy zawiera oceniany symbol albo joker,
3. znajdź nieprzerwane ciągi zgodnych komórek,
4. odrzuć ciąg krótszy niż 3 albo złożony wyłącznie z jokerów,
5. wybierz długość z najwyższą zdefiniowaną wypłatą dla tego ciągu,
6. zapisz użyte komórki i interpretację jokerów.

Ciąg:

- może rozpoczynać się w dowolnej kolumnie,
- nie może przeskakiwać nad niezgodną kolumną,
- dla tego samego symbolu, payline i ciągłego wystąpienia nalicza wyłącznie najdłuższą pasującą długość.

Przykład dla `row_path = [2,3,1,1,2]` w numeracji UI:

- kolumny `[x,3,1,1,x]` tworzą ciąg długości 3,
- `[2,x,1,1,x]` nie tworzy ciągu, ponieważ występuje luka.

M1 ma 5 kolumn, więc na jednej payline nie wystąpią dwa rozłączne ciągi długości co najmniej 3. Zasady dla szerszej planszy z kilkoma takimi ciągami wymagają osobnej decyzji przed publikacją tej gry.

Algorytm `payout-v1` jawnie odrzuca konfigurację szerszą niż 5 kolumn, zamiast
przyjmować ukrytą semantykę dla kilku rozłącznych ciągów.

### Joker

- zastępuje dowolny zwykły symbol,
- nie ma własnej reguły payoutu,
- ciąg złożony wyłącznie z jokerów nie wygrywa,
- dla jednej pary `(payline, symbol)` wybierana jest interpretacja o najwyższym payout,
- każda payline jest oceniana niezależnie,
- ta sama komórka jokera może reprezentować `S1` na jednej payline i `S3` na innej,
- wynik zawiera ślad interpretacji.

### Sumowanie

- sumowane są wszystkie prawidłowe pary `(payline, symbol)`,
- ten sam symbol na dwóch różnych paylines jest liczony dwa razy,
- komórka może uczestniczyć w wielu wzorcach i nie jest „zużywana”,
- wspólne komórki i jokery nie blokują innych wypłat,
- dla jednej pary i tego samego ciągu nie sumuje się wartości za długości 3, 4 i 5; wybierana jest wartość najdłuższego dopasowania.

### Precomputing

Konfiguracja gotowa do precomputingu:

- zawiera dokładnie jedną regułę dla każdej pary
  `(zwykły symbol, długość 3..columns)`,
- nie zawiera reguły jokera,
- ma nieujemne wypłaty,
- dla danego symbolu payout rośnie ściśle wraz z długością.

Podczas przygotowania wydania:

1. oblicz payout każdego layoutu dla konkretnej `dataset_version`, `rules_version` i `algorithm_version`,
2. przerwij publikację przy brakującej lub sprzecznej regule,
3. zapisz gotowy `total_payout` w mobilnym snapshotcie,
4. zachowaj możliwość odtworzenia audytu w danych administracyjnych lub raporcie builda.

Zmiana layoutów, paylines, symboli, kosztu albo wypłat wymaga ponownego obliczenia i nowego wydania.

## C. Target forecast

### Wejście

```text
mobile_release_version
snapshot_checksum
dataset_version
rules_version
algorithm_version
start_sequence_number
layout_count
spin_cost
sequence_payouts[]:
  sequence_number
  payout_credits
```

`sequence_payouts` zawiera dokładnie `layout_count - 1` rekordów już
uporządkowanych cyklicznie przez adapter danych. Czysty engine weryfikuje każdy
oczekiwany numer sekwencji; nie ufa długości ani kolejności wejścia.

### Warunki startu

- pełny layout ma dokładnie jeden `sequence_number`,
- snapshot ma ciągłe numery od 1 do `layout_count`,
- gra ma nieujemny, jawnie skonfigurowany koszt spinu,
- każdy layout ma obliczony payout dla wersji wydania.

### Zakres pełnego cyklu

Rozpoznany layout jest spinem 0 i nie jest oceniany. Dla datasetu z `N` layoutami algorytm ocenia dokładnie `N - 1` kolejnych pozycji:

```text
spin 1: pozycja bezpośrednio po spinie 0
...
spin N - 1: pozycja bezpośrednio przed spinem 0
```

Numer pozycji zawija się cyklicznie z `N` do `1`. Spin 0 nie jest oceniany ponownie.

### Kumulacja

Ustaw:

```text
cumulative_payout = 0
cumulative_cost = 0
net[0] = 0
```

Dla każdego ocenianego spinu `n`:

```text
sequence_number = ((start_sequence_number - 1 + n) mod N) + 1
payout[n] = precomputed_payout[sequence_number]
cumulative_payout += payout[n]
cumulative_cost += spin_cost
net[n] = cumulative_payout - cumulative_cost
```

Każdy payout jest dodawany do całości, również gdy nie wystarcza do wyjścia na plus. Nie odejmuje się wygranej ani nie zeruje wyniku po słabym spinie.

Przykład: po 100 ocenionych spinach o koszcie 10, przy łącznym payoucie 900:

```text
cumulative_cost = 1000
cumulative_payout = 900
net = -100
```

Taki punkt nie jest dodatni i nie trafia do tabeli.

### Dodatnie lokalne maksimum

Tabela nie pokazuje każdego dodatniego spinu ani wyłącznie nowych rekordów globalnych.

Lokalny szczyt jest określany na przebiegu `net[1..N-1]`:

1. znajdź odcinek, na którym wynik wzrósł ponad wartość poprzedzającą,
2. jeżeli po wzroście występuje plateau, traktuj całe plateau jako jeden szczyt,
3. zapisz pierwszy spin plateau, gdy po nim wynik spada albo odcinek kończy się na granicy pełnego cyklu,
4. zapisz punkt tylko wtedy, gdy jego `net > 0`,
5. po spadku szukaj kolejnego lokalnego szczytu niezależnie od wysokości poprzedniego.

Przykład:

```text
net: 5, 10, 15, 25, 20
wynik tabeli: pierwszy spin z wartością 25
```

```text
net: 10, 25, 25, 25, 20
wynik tabeli: pierwszy spin z wartością 25
```

Późniejszy lokalny szczyt 18 jest pokazywany nawet wtedy, gdy wcześniej wystąpił szczyt 25.

### Wyjście

```text
start_sequence_number
evaluated_spin_count = layout_count - 1
spin_cost
mobile_release_version
snapshot_checksum
dataset_version
rules_version
algorithm_version
final_cumulative_payout
final_cumulative_cost
final_net_credits
positive_local_peaks[]:
  spin_number
  sequence_number
  spin_payout
  cumulative_payout
  cumulative_cost
  net_credits
```

Wiersze są uporządkowane rosnąco według `spin_number`.

### Wydajność

- mobile skanuje lokalnie gotowe payouty, bez oceny reguł dla każdego spinu,
- nie wykonuje osobnego otwarcia ani przygotowania zapytania SQL na każdy layout,
- przetwarza dane strumieniowo lub partiami i nie ładuje całych rekordów domenowych do UI,
- czysty engine wykrywa szczyty w jednym przebiegu i nie materializuje tablicy
  wszystkich wartości `net`,
- długie obliczenie można przenieść poza główny wątek JS po pomiarach,
- tabela używa wirtualizacji,
- wynik jest deterministyczny dla tej samej wersji wydania.

## Wersjonowanie algorytmu

Każdy raport przygotowania wydania i wynik diagnostyczny zawiera:

- `mobile_release_version`,
- `dataset_version`,
- `rules_version`,
- `algorithm_version`,
- checksum snapshotu.

Pozwala to odtworzyć wynik po zmianie danych lub reguł.
