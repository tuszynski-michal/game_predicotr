---
title: Algorithms specification
status: accepted
last_updated: 2026-07-30
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
3. Odczytaj dokładny `candidate_count`.
4. Jeżeli pozostał więcej niż jeden rekord, sprawdź najwyżej dwie różne pełne
   sygnatury przez indeks `(game_id, signature)`. Dwie wystarczają do
   rozstrzygnięcia, czy treść layoutu nadal jest jednoznaczna.
5. Zwróć:
   - `candidate_count`,
   - pełny layout, gdy istnieje dokładnie jedna pełna sygnatura,
   - `sequence_number` wyłącznie przy dokładnie jednym rekordzie,
   - jawny wariant podpowiedzi `duplicate`, liczbę wystąpień i brak
     `sequence_number`, gdy kilka rekordów ma jedną pełną sygnaturę.

Kilka różnych pełnych sygnatur nie tworzy podpowiedzi. Uzupełnienie jednej
sygnatury współdzielonej przez duplikaty nie rozstrzyga pozycji sekwencji:
pełny exact match nadal zwraca `duplicate` i nie uruchamia prognozy.

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
W `payout-v2` zwycięski ciąg zawsze zaczyna się w pierwszej kolumnie, dlatego
`start_column` ma zawsze wartość `0`; pole pozostaje w audycie dla jawności
kontraktu i zgodności raportów historycznych.
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

1. odczytaj po jednej komórce z kolejnych kolumn, zaczynając zawsze od
   pierwszej kolumny,
2. traktuj komórkę jako zgodną, gdy zawiera oceniany symbol albo joker,
3. zakończ dopasowanie na pierwszej niezgodnej komórce; zgodne komórki po tej
   pozycji nie należą już do zwycięskiego ciągu,
4. odczytaj `minimum_match_length` skonfigurowane dla symbolu w aktywnej wersji
   reguł,
5. odrzuć prefiks krótszy niż `minimum_match_length` albo złożony wyłącznie z
   jokerów,
6. wybierz najdłuższą zdefiniowaną długość nieprzekraczającą długości
   dopasowanego prefiksu,
7. zapisz użyte komórki i interpretację jokerów.

Ciąg:

- musi rozpoczynać się w pierwszej kolumnie payline,
- nie może przeskakiwać nad niezgodną kolumną,
- dla tego samego symbolu i payline nalicza wyłącznie najdłuższą pasującą
  długość.

Przykłady dla symbolu `S2`:

- `[S2, S2, S2, S7, S2]` daje ciąg długości 3; ostatnie `S2` nie jest liczone,
- `[S7, S2, S2, S2, S2]` nie daje wygranej dla `S2`, ponieważ pierwsza
  kolumna nie pasuje,
- `[S2, joker, S7, S2, S2]` daje długość 2, ale wygrywa tylko wtedy, gdy
  `minimum_match_length` symbolu `S2` wynosi 2.

`payout-v2` nie szuka rozłącznych ciągów i nie ocenia ponownie payline od
drugiej ani kolejnej kolumny. Dzięki temu reguła pozostaje jednoznaczna również
dla plansz szerszych niż 5 kolumn.

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
- dla jednej pary nie sumuje się wartości za krótsze długości; wybierana jest
  wartość najdłuższego dopasowania.

### Precomputing

Konfiguracja gotowa do precomputingu:

- zawiera dokładnie jedną wersjonowaną konfigurację każdego zwykłego symbolu z
  `2 <= minimum_match_length <= columns`,
- nowa konfiguracja zwykłego symbolu otrzymuje domyślnie
  `minimum_match_length = 3` dla gry mającej co najmniej 3 kolumny,
- zawiera dokładnie jedną regułę dla każdej pary
  `(zwykły symbol, długość minimum_match_length..columns)`,
- nie zawiera aktywnej reguły dla długości mniejszej niż próg symbolu,
- nie zawiera reguły jokera,
- ma nieujemne wypłaty,
- dla danego symbolu payout rośnie ściśle wraz z długością.

Podczas przygotowania wydania:

1. oblicz payout każdego layoutu dla konkretnej `dataset_version`, `rules_version` i `algorithm_version`,
2. przerwij publikację przy brakującej lub sprzecznej regule,
3. zapisz gotowy `total_payout` w mobilnym snapshotcie,
4. zachowaj możliwość odtworzenia audytu w danych administracyjnych lub raporcie builda.

Zmiana layoutów, paylines, symboli, `minimum_match_length`, kosztu albo wypłat
wymaga ponownego obliczenia i nowego wydania.

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
