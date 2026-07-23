---
title: Algorithms specification
status: proposed
last_updated: 2026-07-23
---

# Specyfikacja algorytmów

Logikę należy podzielić na trzy niezależne algorytmy. Każdy ma być czystym modułem domenowym z osobnymi testami.

## A. Layout matching

### Wejście

```text
game_id
symbols: [symbol_id | null] w kolejności row-major
confirmation_chain: opcjonalna lista poprzednich pełnych layoutów/kandydatów
```

### Walidacja

- długość tablicy odpowiada `rows * columns`,
- niepuste symbole należą do gry,
- po pierwszym `null` w MVP nie może wystąpić kolejny niepusty symbol, ponieważ wprowadzanie jest prefiksowe,
- gra jest aktywna.

### Częściowy layout

1. Zamień wprowadzone symbole na prefiks sygnatury.
2. Znajdź pozycje sekwencji, których sygnatura zaczyna się od prefiksu.
3. Zwróć:
   - `candidate_count`,
   - pełny layout tylko wtedy, gdy istnieje dokładnie jeden kandydat,
   - `sequence_number` pojedynczego kandydata.

### Pełny layout

1. Wylicz pełną sygnaturę.
2. Znajdź wszystkie rekordy o `(game_id, signature)`.
3. Zwróć:
   - `not_found` dla 0 rekordów,
   - `unique` dla 1 rekordu,
   - `ambiguous` dla więcej niż 1 rekordu.

### Rozstrzyganie duplikatu

Dla kandydatów `C = [c1, c2, ...]` i kolejnego podanego layoutu:

1. dla każdego kandydata pobierz layout o `sequence_number = candidate.sequence_number + offset`,
2. porównaj z kolejnym layoutem użytkownika,
3. zachowaj tylko zgodne kandydaty,
4. zwiększ `offset`, jeżeli nadal istnieje więcej niż jeden kandydat,
5. po jednym kandydacie zwróć jego pierwotną pozycję oraz długość confirmation chain,
6. przy 0 kandydatach zgłoś sprzeczność danych lub błędnie podany następny layout.

Nie wolno wybierać pierwszego rekordu tylko dlatego, że ma najniższy numer.

## B. Payout evaluation

### Wejście

```text
game configuration
pełny layout
aktywne patterns
aktywne payout rules
```

### Wyjście

```text
total_payout
matches[]:
  symbol_id
  pattern_id lub pattern_type
  matched_columns
  matched_cells
  payout
```

### PAYLINE

Payline jest tablicą indeksów rzędów dla kolejnych kolumn, np.:

```json
{
  "type": "PAYLINE",
  "row_path": [0, 1, 2, 1, 0]
}
```

Algorytm czyta symbole od lewej do prawej w wyznaczonych komórkach. Dopasowanie kończy się przy pierwszym symbolu, którego nie można uzgodnić z symbolem bazowym z uwzględnieniem jokera.

### CONSECUTIVE_COLUMNS_ANY_ROW

Dla każdej kolumny sprawdzane jest wystąpienie symbolu w dowolnym rzędzie. Semantyka wielu wystąpień w jednej kolumnie pozostaje otwartym pytaniem Q-008.

### Joker

Do czasu zamknięcia Q-009 implementacja produkcyjna jokera jest zablokowana. MVP może mieć jawnie ograniczoną regułę testową:

- joker zastępuje zwykły symbol,
- nie tworzy samodzielnej wygranej,
- nie posiada własnej wypłaty,
- przy niejednoznaczności wybierana jest interpretacja dająca najwyższą wypłatę, ale wynik zawiera ślad interpretacji.

### Sumowanie

Domyślna propozycja:

- różne symbole i różne paylines sumują się,
- dla tego samego symbolu i tej samej ścieżki liczy się tylko najwyższa osiągnięta długość,
- wynik zawiera listę wszystkich naliczonych pozycji, aby dało się go audytować.

## C. Target forecast

### Warunki startu

- `sequence_number` jest jednoznaczny,
- gra ma koszt spinu,
- dane kolejnych layoutów są dostępne,
- reguły wypłat są kompletne.

### Domyślna interpretacja

Rozpoznany layout jest punktem startowym `spin 0`. Pierwszy analizowany layout to `sequence_number + 1`.

Dla `n` od 1 do `limit`:

```text
next_sequence_number = start_sequence_number + n
cumulative_cost += spin_cost
payout = evaluate(layout[next_sequence_number])
cumulative_payout += payout
net_credits = cumulative_payout - cumulative_cost
```

### Rekordy tabeli

Tabela skrócona zawiera rekord, gdy:

```text
net_credits > 0 AND net_credits > best_positive_net_so_far
```

To oznacza, że pokazujemy pierwszy wynik dodatni oraz każdy kolejny nowy rekord dodatni.

### Przykład

Przy koszcie 10:

| Spin | Payout | Cumulative cost | Cumulative payout | Net | Pokazać |
|---:|---:|---:|---:|---:|---|
| 1 | 0 | 10 | 0 | -10 | nie |
| 2 | 30 | 20 | 30 | 10 | tak |
| 3 | 0 | 30 | 30 | 0 | nie |
| 4 | 50 | 40 | 80 | 40 | tak |
| 5 | 0 | 50 | 80 | 30 | nie |
| 6 | 30 | 60 | 110 | 50 | tak |

### Zatrzymanie

Algorytm kończy się, gdy:

- osiągnięto limit, domyślnie 100 000,
- osiągnięto koniec sekwencji, jeżeli sekwencja nie jest cykliczna,
- wykryto brak layoutu w wymaganym numerze,
- przerwano operację.

### Wydajność

- nie wykonuj jednego zapytania SQL na każdy spin,
- pobieraj layouty zakresami lub strumieniem,
- obliczaj wypłaty w procesie backendu,
- rozważ precomputing payout per layout dopiero po pomiarach i ustabilizowaniu reguł,
- wynik ma być deterministyczny dla tej samej wersji danych i reguł.

## Wersjonowanie algorytmu

Wynik prognozy powinien zawierać:

- `dataset_version`,
- `rules_version`,
- `algorithm_version`,
- `calculated_at`.

Pozwala to odtworzyć wynik po zmianie reguł.
