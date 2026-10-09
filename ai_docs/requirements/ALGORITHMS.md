---
title: Algorithms specification
status: accepted
last_updated: 2026-10-09
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
count_matches[]:        # payout-v4-wild-count; puste dla v2/v3
  symbol_code
  count
  matched_cells
  payout
```

`joker_cells` zachowuje historyczną nazwę pola: oznacza komórki z symbolem
Wild (dawniej „Joker”, D-535).

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
2. traktuj komórkę jako zgodną, gdy zawiera oceniany symbol albo Wild,
3. zakończ dopasowanie na pierwszej niezgodnej komórce; zgodne komórki po tej
   pozycji nie należą już do zwycięskiego ciągu,
4. odczytaj `minimum_match_length` skonfigurowane dla symbolu w aktywnej wersji
   reguł,
5. odrzuć prefiks krótszy niż `minimum_match_length` albo złożony wyłącznie z
   Wildów,
6. wybierz najdłuższą zdefiniowaną długość nieprzekraczającą długości
   dopasowanego prefiksu,
7. zapisz użyte komórki i interpretację Wildów.

Ciąg:

- musi rozpoczynać się w pierwszej kolumnie payline,
- nie może przeskakiwać nad niezgodną kolumną,
- dla tego samego symbolu i payline nalicza wyłącznie najdłuższą pasującą
  długość.

Przykłady dla symbolu `S2`:

- `[S2, S2, S2, S7, S2]` daje ciąg długości 3; ostatnie `S2` nie jest liczone,
- `[S7, S2, S2, S2, S2]` nie daje wygranej dla `S2`, ponieważ pierwsza
  kolumna nie pasuje,
- `[S2, Wild, S7, S2, S2]` daje długość 2, ale wygrywa tylko wtedy, gdy
  `minimum_match_length` symbolu `S2` wynosi 2.

`payout-v2` nie szuka rozłącznych ciągów i nie ocenia ponownie payline od
drugiej ani kolejnej kolumny. Dzięki temu reguła pozostaje jednoznaczna również
dla plansz szerszych niż 5 kolumn.

`payout-v3-unknown-prefix-stop` zachowuje tę samą kolejność i reguły dla
znanych symboli, ale zarezerwowany kod layoutu `0` kończy analizowany prefiks.
Nie jest Wildem ani niezgodnym symbolem: pozycje po nim są ignorowane, a
prefiks przed nim może wygrać, jeśli sam spełnia minimalną długość. Kod `0` w
pierwszej kolumnie daje prefiks długości zero. Historyczne obliczenia v2
pozostają odtwarzalne i nadal odrzucają kod `0`.

### `payout-v4-wild-count` (D-535, TASK-0932)

Gra, której katalog ma co najmniej jeden symbol uruchamiający supergrę
(`symbols.super_game_trigger_count` różne od `null`), jest liczona wersją
`payout-v4-wild-count`. Gra bez takiego symbolu nadal raportuje
`payout-v3-unknown-prefix-stop` i ma wyniki identyczne bajt w bajt z v3
(777 i 777 v2 bez zmian). Wersję wybiera się per gra z konfiguracji
symboli reguł, a nie z parametru wywołania.

- **Linie:** reguły v3 bez zmian, z jednym wyjątkiem: symbol uruchamiający
  nie jest zwykłym symbolem liniowym. Symbol uruchamiający, który jest też
  Wildem (Mumia), nadal zastępuje inne symbole na liniach; symbol
  uruchamiający bez roli Wild kończy prefiks jak każdy niezgodny symbol.
- **Sztuki na planszy:** dla każdego symbolu uruchamiającego liczy się jego
  komórki w dowolnym miejscu planszy (pozycja i kolejność nie mają
  znaczenia). Wypłaca się regułę dla największej skonfigurowanej liczby
  sztuk nie większej niż wynik liczenia (`payout_rules.match_length` symbolu
  uruchamiającego oznacza liczbę sztuk, zakres `2..rows × columns`, wypłaty
  ściśle rosnące, nie każda liczba musi mieć regułę). Brak takiej reguły (np.
  2 sztuki przy regułach od 3) albo brak reguł symbolu daje brak wypłaty za
  sztuki, bez błędu.
- **Nieznane pola:** kod `0` nigdy nie jest liczony jako sztuka. Na planszy
  częściowej liczba sztuk jest więc dolnym ograniczeniem, a wypłata za sztuki
  rośnie z liczbą sztuk, dlatego pozostaje bezpiecznym dolnym ograniczeniem
  prawdziwej wypłaty (§D).
- **Suma:** `total_payout = suma wypłat linii + suma wypłat za sztuki`.
  Wypłata za sztuki jest osobnym dopasowaniem (`count_matches`), nie udaje
  linii i nie ma `payline_id`.

Przykład (Mumia = Wild i symbol uruchamiający, reguły Mumii 3→20):

```text
[10, Mumia, 10, 10, J]     linia górna:   10 ×4 (Mumia jako 10)
[K,  K,  Mumia, Q,  Q]     linia środkowa: K ×3 (Mumia jako K)
[Mumia, A, A,  A,  10]     linia dolna:   A ×4 (Mumia jako A; ciąg kończy 10)
Mumia na planszy: 3 sztuki → 20
total = payout(10, 4) + payout(K, 3) + payout(A, 4) + 20
```

Złote przypadki obu języków (`packages/domain-fixtures/payout-golden-cases.json`,
sekcja `wildCountScenario`) wykonują ewaluator workera i jego lustrzany
odpowiednik w `packages/shared-ts` (`evaluatePayout`).

Prekomputacja wydań (`layout_payouts`, snapshot mobilny) nie obsługuje
jeszcze `payout-v4-wild-count`: zadanie payout odrzuca zlecenie v2/v3 dla gry
z symbolem uruchamiającym (`PAYOUT_ALGORITHM_GAME_MISMATCH`), aby wynik v4
nigdy nie został zapisany pod etykietą v3.

### Plansza w serii supergry `wild_super_spins` (D-537, TASK-0936)

Pozycja sekwencji objęta opublikowaną serią supergry jako jej spin
(`trigger + 1 … trigger + length`, TASK-0933) jest liczona oceną planszy
serii rodzaju gry (`evaluate_series_board(board, super_symbol, rules)`,
`services/worker/.../domain/super_games/wild_super_spins.py`). Plansza
wyzwalająca serię jest w trybie bazowym. Dla rodzaju `wild_super_spins` i
super symbolu `X` (zwykły symbol liniowy wybrany przez operatora):

1. `k` = liczba kolumn planszy **oryginalnej**, w których występuje `X`
   (kolumny nie muszą sąsiadować). Gdy `k < minimum_match_length(X)`,
   plansza nie jest przekształcana: linie (z Wildem) i sztuki liczy się
   dokładnie jak w trybie bazowym.
2. Gdy `k ≥ minimum_match_length(X)`: każda z tych `k` kolumn jest w całości
   wypełniona `X` — przykrycie usuwa symbole pod spodem, także Wildy
   (plansza rozwinięta).
3. Linie liczy się na planszy rozwiniętej (Wild nadal podmienia), sztuki
   symbolu uruchamiającego na planszy **oryginalnej**. Wygrane liniowe `X` z
   planszy rozwiniętej są **zastąpione** (nie sumują się) wartością
   rozwinięcia `payout_line(X, k) × liczba aktywnych linii`; wygrane linii
   innych symboli z planszy rozwiniętej zostają.
4. Koszt spinu = 0. Plansza serii z co najmniej `N` symbolami
   uruchamiającymi dostaje wypłatę za sztuki i przedłuża serię
   (wyprowadzanie serii, TASK-0933).

`total = linie innych symboli (plansza rozwinięta) + sztuki (plansza
oryginalna) + rozwinięcie`. Wynik ma osobne składowe: linie, sztuki i
rozwinięcie (`symbol`, kolumny, `k`, `payout_line(X, k)`, liczba linii,
wypłata).

Przykład (Mumie, `X = K`, minimum 3, `payout_line(K, 3) = 10`, 5 linii):
K w kolumnach 2, 4 i 5 → `k = 3` → rozwinięcie `10 × 5 = 50`; kolumny 1 i 3
nie mają znaczenia. K w kolumnach 2 i 4 → `k = 2 < 3` → bez rozwinięcia,
linie liczone normalnie. Sarkofag (minimum 2) w jednej kolumnie → bez
rozwinięcia, w dwóch → `payout_line(Sarkofag, 2) × 5`.

**Wynik dokładny albo prowizoryczny.** Wynik planszy serii jest `exact`
wyłącznie dla planszy w pełni znanej, ze zdefiniowanym super symbolem i przy
świeżej generacji serii (`superGameState.fresh = true`). Każdy inny przypadek
jest `provisional`: brak super symbolu (system liczy linie z Wildem i sztuki,
ale nie zna rozwinięcia, które może zarówno dodać wygraną, jak i przykryć
wygrane innych symboli), nieaktualna generacja serii albo **jakakolwiek**
nieznana komórka — nieznana komórka poza kolumnami `X` może dodać kolumnę,
przekroczyć próg i przykryć wcześniejszą wygraną, a nieznana komórka w
kolumnie już przykrytej nie zmienia linii, ale nadal może zmienić wypłatę za
sztuki i retrigger (sztuki liczone są na planszy oryginalnej). Wynik
prowizoryczny nie jest dolnym ograniczeniem; `confirmed_minimum` w trybie
`super` nie występuje. Super symbol, który w liczonej wersji reguł nie jest
zwykłym symbolem liniowym (np. zmieniona rola w drafcie), jest traktowany
jak niezdefiniowany.

Złote przypadki obu języków (`payout-golden-cases.json`, sekcja
`wildSuperSpinsScenario`) wykonuje ewaluator workera i lustrzany
`evaluateSeriesBoard` w `packages/shared-ts`.

### Wild

Dawniej „Joker”; kolumna `symbols.is_wildcard` i pola audytu `joker_cells`
zachowują historyczne nazwy.

- zastępuje dowolny zwykły symbol,
- nie ma własnej reguły payoutu liniowego (Wild, który jest też symbolem
  uruchamiającym, ma wyłącznie wypłaty za sztuki na planszy),
- ciąg złożony wyłącznie z Wildów nie wygrywa jako linia,
- dla jednej pary `(payline, symbol)` wybierana jest interpretacja o najwyższym payout,
- każda payline jest oceniana niezależnie,
- ta sama komórka Wilda może reprezentować `S1` na jednej payline i `S3` na innej,
- wynik zawiera ślad interpretacji.

### Sumowanie

- sumowane są wszystkie prawidłowe pary `(payline, symbol)`,
- ten sam symbol na dwóch różnych paylines jest liczony dwa razy,
- komórka może uczestniczyć w wielu wzorcach i nie jest „zużywana”,
- wspólne komórki i Wildy nie blokują innych wypłat,
- wypłaty za sztuki na planszy (`payout-v4-wild-count`) dodają się do sumy
  linii; komórka symbolu uruchamiającego może jednocześnie liczyć się jako
  sztuka i jako Wild na liniach,
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
- nie zawiera reguły liniowej Wilda; symbol uruchamiający supergrę nie ma
  `minimum_match_length`, a jego reguły są wypłatami za liczbę sztuk
  `2..rows × columns` o ściśle rosnących wartościach,
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
target_scan_limit
spin_cost
sequence_payouts[]:
  sequence_number
  payout_credits
```

Efektywna liczba spinów wynosi:

```text
evaluated_spin_count = min(target_scan_limit, layout_count - 1)
```

`sequence_payouts` zawiera dokładnie `evaluated_spin_count` rekordów już
uporządkowanych cyklicznie przez adapter danych. Czysty engine weryfikuje każdy
oczekiwany numer sekwencji; nie ufa długości ani kolejności wejścia.

Od wersji 0.3 `target_scan_limit` jest konfigurowany przez użytkownika w
przedziale 1 000–500 000, domyślnie 10 000. Dla testów domenowych i mniejszych
fixture engine może otrzymać mniejszy jawny limit, ale produkcyjny UI egzekwuje
powyższy zakres.

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

### Zakres ograniczony

Jeżeli `target_scan_limit < N - 1`, algorytm ocenia pierwsze
`target_scan_limit` przyszłych pozycji według tej samej cyklicznej kolejności i
kończy przed powrotem do spin 0. Zwiększenie limitu do co najmniej `N - 1`
odtwarza definicję pełnego cyklu. Limit nie zmienia `sequence_number`, payoutu
ani kosztu pojedynczego spinu; ogranicza wyłącznie okno prognozy.

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

Lokalny szczyt jest określany na przebiegu
`net[1..evaluated_spin_count]`:

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
target_scan_limit
evaluated_spin_count = min(target_scan_limit, layout_count - 1)
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

## D. Przybliżona wygrana w Adminie

Podsekcja „Przybliżona wygrana” w „Wyszukaj plansze” (panel administracyjny)
liczy ostrożne, dolnoograniczone oszacowanie payoutu dla `N` kolejnych pozycji
sekwencji po wybranej planszy `S`. Wykorzystuje ten sam kalkulator co §B
(`payout-v3-unknown-prefix-stop`, a dla gry z symbolem uruchamiającym
`payout-v4-wild-count`; `PreparedPayoutEvaluator`) i tę samą
definicję pełnego cyklu z zawijaniem co §C (mobilna prognoza celu), ale
liczy z żywych danych projekcji wyszukiwania plansz, nie z prekomputowanego
snapshotu — jest to operacja wyłącznie do odczytu, bez cache serwerowego.

### Zakres

Dla planszy startowej o `sequence_number = S`:

- `S` jest punktem startowym i nie wchodzi do zakresu,
- analizowany zakres to `S+1…S+N`,
- `evaluated_spin_count = min(N, sequence_length − 1)`, gdzie
  `sequence_length = games.expected_layout_count`,
- numer pozycji zawija się cyklicznie z `sequence_length` do `1`, dokładnie
  jak w §C.

### Kategoryzacja i naliczanie

Każda pozycja zakresu trafia do dokładnie jednej z trzech rozłącznych
kategorii, sumujących się do `evaluated_spin_count`:

- **kompletna** — wszystkich 15 symboli logicznej planszy jest znanych;
  payout jest identyczny z wynikiem `payout-v3-unknown-prefix-stop` dla
  pełnej planszy,
- **częściowa** — co najmniej jeden symbol jest nieznany (`?`, brak dowodu
  albo ucięta geometria); plansza pozostaje częściowa również wtedy, gdy
  udało się dla niej naliczyć potwierdzoną wypłatę,
- **brakująca** — brak zapisanej planszy dla tej pozycji sekwencji; koszt
  spinu jest doliczany, rozpoznana wypłata wynosi 0, a kalkulator payoutu w
  ogóle nie jest wywoływany dla tej pozycji.

**Dlaczego naliczenie z widocznego prefiksu planszy częściowej jest zawsze
bezpiecznym dolnym ograniczeniem prawdziwej wypłaty:** dla każdej pary
`(payline, symbol)` `payout-v3-unknown-prefix-stop` buduje prefiks ze
znanych komórek od lewej strony i zatrzymuje się na pierwszej nieznanej
komórce (§B). Nieznana komórka może więc tylko *wydłużyć* albo *zakończyć w
tym samym miejscu* prawdziwy prefiks — nigdy go skrócić. Ponieważ payout
danego symbolu rośnie ściśle wraz z długością dopasowania (wymóg
precomputingu, §B), a symbol obecny w krótszym potwierdzonym prefiksie jest
obecny również w każdym dłuższym prefiksie go zawierającym, wypłata policzona
z widocznego prefiksu nigdy nie przekracza prawdziwej wypłaty dla faktycznie
kompletnej planszy. Wszystkie pary `(payline, symbol)` są sumowane
niezależnie (§B „Sumowanie”), więc nieznane komórki mogą co najwyżej dodać
kolejne, jeszcze nienaliczone wypłaty — nigdy nie usuwają już potwierdzonej.
To samo dotyczy Wildów: prefiks złożony wyłącznie z Wildów nadal nie
wygrywa (§B „Wild”), więc nieznana komórka nigdy nie zamienia przegranego
prefiksu w wygrany przez zgadywanie. Ta własność jest wewnętrzna dla
`payout-v3-unknown-prefix-stop` (nie jest osobnym trzecim algorytmem) i nie
wymaga zmiany reguł domenowych.

Wypłaty za sztuki symbolu uruchamiającego (`payout-v4-wild-count`) zachowują
tę własność: nieznana komórka nigdy nie jest liczona jako sztuka, więc liczba
sztuk na planszy częściowej może tylko wzrosnąć po rozpoznaniu brakujących
pól, a wypłata za sztuki rośnie wraz z liczbą sztuk. Wiersz zakresu i modal
linii pokazują wypłatę za sztuki w osobnej liście (`countMatches`), już
wliczonej do wypłaty wiersza; plansza częściowa z wypłatą za sztuki pozostaje
`confirmed_minimum`.

**Podgląd wersji roboczej (D-535, TASK-0932).** W lokalnym Adminie
kalkulator zakresu i modal linii mogą liczyć z wybranej wersji reguł tej
samej gry (`draft` albo `published`, parametr `rulesVersionId`); domyślnie,
bez wyboru, liczą z najnowszej opublikowanej wersji. Udostępniony panel
online, panel zarządzania i proxy Reviewera nigdy nie przekazują tego
parametru, a API odrzuca go na tych powierzchniach. Podgląd służy testom
ról Wild i symbolu uruchamiającego przed publikacją reguł.

Symbol spoza aktywnych symboli opublikowanej wersji reguł (błąd
integralności danych, nie normalny brak dowodu) przerywa całą kalkulację
zakresu jako błąd zamiast po cichu pomijać jedną planszę.

### Tryb pozycji i koszt per pozycja (D-537, TASK-0936)

Każda pozycja zakresu ma projekcję `mode` (`base` | `super`),
`super_symbol_id` (w API kod symbolu), `remaining_spins`,
`spin_cost_credits`, `payout_credits` i `payout_kind` (`exact` |
`confirmed_minimum` | `provisional`). Projekcja powstaje z tego samego
odczytu znaczników supergry co oznaczenia wierszy i `superGameState`
(jedno zapytanie, jeden snapshot). Pozycja objęta opublikowaną serią jako
jej spin jest w trybie `super`: koszt darmowego spinu rodzaju gry (0), ocena
planszy serii z §B z super symbolem tej serii (brak symbolu → wynik
prowizoryczny). Każda inna pozycja, także plansza wyzwalająca serię, jest w
trybie `base` z kosztem `spin_cost` reguł. Brakująca plansza w serii zużywa
darmowy spin (koszt 0, wypłata 0). Przy `superGameState.fresh = false`
**każda** oceniona plansza gry jest prowizoryczna, także w trybie bazowym, bo
nowy trigger mógł już objąć ją serią (decyzja leada po audycie TASK-0936,
zgodna z planem). Reguły, plansze, znaczniki i stan generacji są czytane w
jednej migawce `REPEATABLE READ`, więc publikacja generacji w trakcie odczytu
nie łączy starych plansz z nową generacją. Podsumowanie niesie dokładne
zakresy darmowych spinów (`superSpinRanges`, `superSpinCost`), z których
klient liczy koszt i bilans dowolnego spinu. Gra bez rodzaju supergry (777) ma wszędzie
tryb `base` i stały koszt, więc jej wyniki, odcisk danych i zamrożone wyniki
panelu zarządzania są bajt w bajt takie jak przed projekcją (bramka
regresji).

### Podsumowanie i wiersze

Wynik rozdziela trzy wartości: rozpoznane wypłaty (suma naliczonych
payoutów `exact` i `confirmed_minimum`), koszt spinów (suma kosztu
wszystkich `evaluated_spin_count` pozycji według ich trybu, w tym
brakujących) i bilans (wypłaty minus koszt) — bilans może
pozostać ujemny mimo występujących wypłat i nigdy nie jest nazywany
„zyskiem”. Wypłaty `provisional` (plansze serii supergry) są pokazywane
osobno: liczba takich pozycji i ich suma; nie wchodzą do rozpoznanych
wypłat, narastających sum ani bilansu, bo po definicji super symbolu,
przeliczeniu serii albo uzupełnieniu planszy mogą wzrosnąć albo zmaleć. Tabela wyników pokazuje wyłącznie spiny z dodatnią wypłatą, z
narastającą sumą wypłat/kosztu/bilansu obejmującą wszystkie wcześniejsze
spiny zakresu — również te bez własnego wiersza w tabeli.

## Wersjonowanie algorytmu

Każdy raport przygotowania wydania i wynik diagnostyczny zawiera:

- `mobile_release_version`,
- `dataset_version`,
- `rules_version`,
- `algorithm_version`,
- checksum snapshotu.

Pozwala to odtworzyć wynik po zmianie danych lub reguł.
