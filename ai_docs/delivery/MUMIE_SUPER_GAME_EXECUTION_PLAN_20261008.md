---
title: Gra Mumie — Wild, supergra „Wild super spins” i proces audytu krzyżowego (plan wykonawczy)
status: proposed
last_updated: 2026-10-08
---

# Gra Mumie — Wild, supergra i super symbol

Plan do akceptacji operatora. Analiza wykonana bez zmian w aplikacji i danych.
Zastępuje część „wypłaty premium” planu
`MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md` (nieaktualna według D-490).
Decyzje operatora z 2026-10-08 są wpisane; pozostała jedna otwarta (D-1).

## Słownik planu

- **Wild** — dotychczasowy „Joker” (`symbols.is_wildcard`). Nazwa w UI i
  dokumentach zmienia się na „Wild”; nazwa kolumny w bazie zostaje.
- **Uruchamia supergrę** — cecha symbolu: `N` sztuk tego symbolu na pociętej
  planszy (dowolne pozycje i kolejność, `N` ∈ {3, 4, 5}) uruchamia supergrę.
- **Rodzaj supergry** — cecha gry wybierana z listy przy tworzeniu i edycji
  gry; mechanika każdego rodzaju jest zaszyta w kodzie w rozszerzalnej
  kategorii. Pierwszy rodzaj: **Wild super spins** (kod `wild_super_spins`).
- **Super symbol** — zwykły symbol wylosowany przez automat na start serii;
  w zdjęciach widoczny jako złota ramka komórki; w serii rozwija się na całą
  kolumnę, w której wystąpił.
- **Seria** — przedział kolejnych pozycji sekwencji w trybie supergry.

## Stan obecny (fakty z repo i bazy, 2026-10-08)

- Silnik `payout-v3-unknown-prefix-stop`
  (`services/worker/src/game_predictor_worker/domain/payout.py`) ocenia każdą
  parę `(linia, zwykły symbol)` niezależnie; komórka Wild pasuje do każdego
  zwykłego symbolu, więc jeden Wild liczy się jako `10` na linii A i jako `K`
  na linii D, z wypłatą danego symbolu dla danej linii. Ciąg z samych Wildów
  nie wygrywa.
- Ten sam kalkulator (`PreparedPayoutEvaluator`) napędza modal linii
  (`application/board_search_board_detail.py`), przybliżoną wygraną
  (`application/board_search_approximate_win.py`) i stawki panelu zarządzania.
- Reguły (`domain/rules.py`): Wild nie może mieć `minimumMatchLength`
  (`WILDCARD_MINIMUM_NOT_ALLOWED`) ani wypłat (`WILDCARD_PAYOUT_NOT_ALLOWED`);
  rola nie zmienia się po utworzeniu wpisu `rules_version_symbols`
  (`requirements/ADMIN_APP.md`). Katalog symboli w Adminie
  (`apps/admin/src/features/symbols/symbol-catalog.tsx`) ma pole „Joker”.
- Gra `mumie`, `draft`, `expected_layout_count = 500000`, reguły `v1` `draft`,
  3 × 5, `spin_cost = 100`, 5 linii (A–C poziome, D `[0,1,2,1,0]`,
  E `[2,1,0,1,2]`). Symbole w kolejności: 10, J, Q, K, A, Sarkofag, Ra, Faraon,
  Sfinks, **Mumia** (`display_order 9`, `is_wildcard = false`, reguły liniowe
  3/4/5 → 20/200/2000, minimum 3). Dziś Mumia **nie** podmienia się na linii.
- Gra `777` ma `is_wildcard = false` u wszystkich symboli i nie może zmienić
  zachowania.
- Skróty: `DIGIT_SHORTCUT_LIMIT = 9` (`apps/admin/src/lib/keyboard-shortcuts.ts`
  i kopia w `packages/board-search-ui/src/keyboard-shortcuts.ts`); dziesiąty
  symbol bez skrótu. W wyszukiwaniu plansz `0` i `?` = „nieznany”.
- Brak w domenie pojęć: tryb gry, darmowy spin, wypłata za liczbę sztuk,
  rozwijany symbol, seria. Koszt spinu jest stały w §C/§D `ALGORITHMS.md`.
- Weryfikacja symboli nie ma cechy „złota ramka”. Nie wiadomo, czy wycinki V3
  obejmują ramkę (otwarte od D-489). Korekty Mumia→Sarkofag: 15 (TASK-0888).
- `CURRENT_STATE.md` ma 11 774 linie (853 KB), `DECISION_LOG.md` 11 300 linii
  (791 KB); obowiązkowy odczyt całości jest niewykonalny.
- `codex` i `claude` CLI nie są na PATH (operator używa aplikacji desktop).

## Wymagania operatora (2026-10-08, rozstrzygnięte)

1. Wild podmienia się pod symbol konkretnej linii; na trzech liniach może być
   trzema różnymi symbolami z wypłatą każdego z nich.
2. Operator sam steruje rolami w Adminie, per gra i per symbol, w sekcji
   „Symbole”: checkbox **Wild** (dawny Joker) i checkbox **Uruchamia
   supergrę** z selectem „Trzy symbole / Cztery symbole / Pięć symboli”.
   Żadnych reguł wpisywanych przez agenta.
3. Po włączeniu Wild symbol działa jako Wild od razu (testy operatora).
4. Rodzaj supergry wybierany przy tworzeniu i edycji gry z listy; 777
   zostaje grą bez supergry; Mumie dostają „Wild super spins”. Mechanika
   zaszyta w kodzie, w osobnej kategorii do rozszerzeń.
5. Supergra: 10 darmowych spinów (koszt 0), kolejne pozycje tej samej
   sekwencji; ≥N symboli uruchamiających w serii przedłuża ją o 10 bez
   nowego symbolu. Sekwencja startuje w trybie bazowym.
6. Brakująca plansza w serii liczy się jako pusta plansza bez wygranej i
   zużywa spin.
7. Super symbol rozwija się na całą kolumnę i **przykrywa** symbole pod sobą.
   Liczy się liczba kolumn z super symbolem (niesąsiednie też, np. 2, 4, 5 =
   trzy), próg = `minimum_match_length` tego symbolu (np. J od 3), wypłata =
   wypłata liniowa symbolu dla tej liczby × liczba linii (Mumie: 5).
8. Wypłaty Mumii 3/4/5 → 20/200/2000 to wypłata za liczbę sztuk na planszy
   w kredytach bezwzględnych (operator: „chyba tak”; weryfikacja na
   pierwszej serii).
9. Do progu liczą się komórki z przypisanym symbolem (predykcja modelu albo
   decyzja człowieka); plansza musi być pocięta siatką. Zatwierdzenie nie
   jest wymagane. Seria z triggera opartego na niezatwierdzonych komórkach
   jest oznaczona jako niezweryfikowana.
10. Klawisz `0` dla dziesiątego symbolu w weryfikacji symboli.
11. Aplikacja mobilna poza zakresem (rozwój za kilka miesięcy).
12. Proces: audyt po każdym zadaniu przez drugą rodzinę modeli; `AGENTS.md`
    wymaga aktualizacji pod ten proces.

## Model domenowy (decyzje planu)

### Role symbolu (katalog, per gra)

| Pole | Typ | Znaczenie |
|---|---|---|
| `is_wildcard` (istnieje) | boolean | Wild; etykieta UI „Wild” |
| `super_game_trigger_count` (nowe) | smallint nullable | `null` = nie uruchamia; 3/4/5 = liczba sztuk |

Zasady:

- Symbol może być jednocześnie Wild i uruchamiający (Mumia).
- Symbol uruchamiający ma wypłaty **za liczbę sztuk**: istniejące
  `payout_rules` tego symbolu są interpretowane jako `liczba sztuk → kredyty`
  (`match_length` = liczba sztuk, zakres `2…rows×columns`, wypłaty rosnące).
  Bez nowej tabeli i bez przepisywania danych Mumii; zmienia się etykieta
  w zakładce reguł („sztuk na planszy”) i walidacja.
- Wild bez roli uruchamiającej: jak dziś (brak wypłat, brak minimum). Wild
  z rolą uruchamiającą: wypłaty za sztuki dozwolone, `minimum_match_length`
  nadal `null`.
- Zmiana roli jest dozwolona, dopóki symbol nie występuje w **opublikowanej**
  wersji reguł. Mumie mają tylko `draft`, więc operator zmienia role sam.
- Gotowość do precomputingu: symbol uruchamiający wymaga, by gra miała
  rodzaj supergry różny od `none`; symbol bez tej roli ma wyłącznie reguły
  liniowe jak dziś.

### Rodzaj supergry (gra)

- `games.super_game_kind` (text enum, domyślnie `none`). Pierwszy rodzaj:
  `wild_super_spins`, etykieta UI „Wild super spins”. Select w formularzu
  tworzenia i edycji gry.
- Kategoria w kodzie: proponowany moduł
  `services/worker/src/game_predictor_worker/domain/super_games/`
  (`registry.py`, `wild_super_spins.py`) z interfejsem: `series_length`,
  `retrigger_extension`, `free_spin_cost`,
  `evaluate_series_board(board, super_symbol, rules)`. Dodanie rodzaju =
  nowy moduł + pozycja w rejestrze + opcja w selekcie. API eksponuje listę
  rodzajów z rejestru, więc Admin nie trzyma własnej kopii.

### Supergra jako stan sekwencji

- Seria: `trigger_sequence_number`, `start = trigger + 1`,
  `length = 10 + 10 × retriggery`, `retrigger_sequence_numbers[]`,
  `super_symbol_id` (null do definicji), `status` ∈
  {`pending_symbol`, `defined`, `incomplete`},
  `trigger_verification` ∈ {`verified`, `unverified`}, `revision`.
- Wyprowadzanie: jedno przejście po pozycjach `1…expected_layout_count` w
  trybie bazowym na starcie. Pocięta plansza w trybie bazowym z ≥N
  komórkami o przypisanym symbolu uruchamiającym otwiera serię; w serii ≥N
  przedłuża bieżącą. Brak planszy w serii = pusta plansza, spin zużyty.
  Seria, której koniec wypada poza ostatnią znaną planszę, ma status
  `incomplete` (pokazywany, liczony jako dolne ograniczenie).
- `trigger_verification = verified`, gdy wszystkie komórki liczone do progu
  mają decyzję człowieka; inaczej `unverified` (widoczne w UI, liczone).
- Super symbol pochodzi wyłącznie od operatora (zdjęcia ze złotą ramką).

**„Dolne ograniczenie”:** dla planszy w serii bez znanego super symbolu
system liczy linie z Wildem i wypłaty za sztuki, ale nie liczy wygranej z
rozwinięcia, bo nie wie, który symbol się rozwija. Pokazana suma jest więc
**nie większa** niż prawdziwa i jawnie oznaczona „super symbol
niezdefiniowany”. Po definicji wynik rośnie albo zostaje, nigdy nie maleje.
To ta sama zasada, którą §D stosuje dla plansz z nieznanymi komórkami.

### Wypłata planszy w serii (rodzaj `wild_super_spins`)

1. Zbuduj planszę rozwiniętą: każda kolumna zawierająca super symbol X
   zostaje w całości wypełniona X (przykrycie).
2. Policz linie na planszy rozwiniętej jak w trybie bazowym (Wild podmienia;
   sztuki symbolu uruchamiającego liczone na planszy **oryginalnej**, bo
   przykrycie nie dodaje sztuk Mumii).
3. Rozwinięcie: `k` = liczba kolumn z X na planszy oryginalnej. Jeśli
   `k ≥ minimum_match_length(X)`: `payout_line(X, k) × liczba aktywnych
   linii`. Wygrane liniowe X z kroku 2 są wtedy **zastąpione** tą wartością
   (nie sumują się), bo opisują to samo rozwinięcie; wygrane innych symboli
   zostają.
4. Koszt spinu = 0. Plansza serii z ≥N symbolami uruchamiającymi dostaje
   wypłatę za sztuki i przedłuża serię.

Przykład (Mumie, X = K, min 3, `payout_line(K, 3) = 10`): K w kolumnach 2, 4, 5
→ `k = 3` → rozwinięcie `10 × 5 = 50`; kolumny 1 i 3 bez znaczenia. K w
kolumnach 2 i 4 → `k = 2 < 3` → bez rozwinięcia; linie liczone normalnie.

### Projekcja per pozycja

`mode` (`base` | `super`), `super_symbol_id`, `remaining_spins`,
`spin_cost_credits` (0 w `super`), `payout_credits`, `is_lower_bound`.
Przybliżona wygrana §D i stawki panelu sumują koszt per pozycja. Dla gry z
`super_game_kind = none` projekcja ma wszędzie `base` i stały koszt —
wyniki 777 identyczne (bramka regresji).

## Założenia i niewiadome

- Z-1: wypłaty za sztuki w kredytach bezwzględnych (wymaganie 8) — do
  potwierdzenia na pierwszej zdefiniowanej serii.
- N-1: widoczność złotej ramki w wycinkach V3.
- N-2: skala: ~2 500–5 000 serii w pełnym cyklu 500 000 pozycji (szacunek);
  obecne plansze to ułamek.
- N-3: numer wpisu `DECISION_LOG.md` dla tego planu: D-534 zajmuje
  TASK-0928 (niezacommitowany w głównym checkoucie); wpis planu dostaje
  następny wolny numer przy akceptacji.

## Etapy i zadania

Numery TASK-0929–0939 sprawdzone na wierzchołku
`v1.1-vision-lab-hybrid-geometry` (v1.7.259). Każde zadanie: osobny worktree,
implementacja, **niezależny audyt drugą rodziną modeli** (tabela na końcu),
poprawki, commit `vX.Y.N`, `Outcome`, `CURRENT_STATE.md`. Raport audytu:
`ai_docs/quality/TASK-09xx_AUDIT_<model>.md`. STOP po każdym etapie.

### Etap P — proces (może iść równolegle z S-0)

- **TASK-0929** — skill audytu krzyżowego (`/audit-task`, skrypt PowerShell,
  lustrzany skill Codex) i sekcja „Audyt krzyżowy” w `AGENTS.md`; nazewnictwo
  „Wild” w dokumentach. Warunek operatora: instalacja i logowanie obu CLI.

### Etap S-0 — ergonomia

- **TASK-0930** — klawisz `0` dla dziesiątego symbolu w weryfikacji symboli.

### Etap S-A — role w Adminie i ewaluator (po nim operator testuje Wild)

- **TASK-0931** — migracja `super_game_trigger_count` i `super_game_kind`,
  walidacje domeny, rejestr rodzajów, API/OpenAPI/klient, formularze Adminu
  (Wild, Uruchamia supergrę + select, select rodzaju w grze), etykieta
  „sztuk na planszy” w regułach; Outcome z instrukcją operatora.
- **TASK-0932** — ewaluator `payout-v4-wild-count`: symbol uruchamiający poza
  liniami, dopasowanie `count`, wersja per gra, golden cases w Pythonie i TS,
  modal linii i przybliżona wygrana.

### Etap S-B — serie i definicja super symbolu

- **TASK-0933** — tabela `super_game_series`, wyprowadzanie serii, job, API.
- **TASK-0934** — sekcja „Supergry” w Adminie z karuzelą i zapisem CAS.
- **TASK-0935** — złote oznaczenie serii w wyszukiwaniu plansz (Admin,
  Reviewer, panel zarządzania tylko znacznik).

### Etap S-C — wypłaty serii i prognoza w Adminie

- **TASK-0936** — rozwinięcie super symbolu, koszt per pozycja w §D i
  stawkach panelu, aktualizacja `ALGORITHMS.md` i `DECISION_LOG.md`.

### Etap S-D — automatyzacja złotej ramki (warunkowy)

- **TASK-0937** — pilot wykrywania złotej ramki (pomiar, raport).

### Etap T — oszczędność tokenów bez utraty jakości (niezależny)

Zasada operatora: oszczędzać tokeny, ale nie kosztem jakości. Dlatego etap
zaczyna się od pomiaru i od usunięcia największego, bezspornego kosztu
(dokumenty procesu), a narzędzia nawigacji po kodzie wchodzą jako pilot
z pomiarem na tym repozytorium, nie na obietnicach producenta.

- **TASK-0938** — okno kroczące `CURRENT_STATE.md` i indeks `DECISION_LOG.md`
  (największy koszt: 853 KB + 791 KB czytane na start sesji).
- **TASK-0939** — zestaw narzędzi tokenowych z pomiarem: (1) mapa kodu
  `ai_docs/architecture/CODE_MAP.md` generowana skryptem (funkcja → pliki i
  symbole), (2) pilot Serena MCP (narzędzia symbolowe dla Pythona i TS
  zamiast czytania całych plików), (3) pilot Graphify (graf repo lokalnie,
  eksport Obsidian) w osobnym venv i katalogu ignorowanym, (4) hook
  `PreToolUse` blokujący odczyt pliku > 200 KB bez zakresu linii, (5) reguła
  w `AGENTS.md`: eksploracja subagentem na tańszym modelu, briefy audytu
  tylko z taskiem i diffem. Każdy element ma pomiar „przed/po” na trzech
  typowych zadaniach (tokeny wejścia, czas, jakość wyniku oceniona przez
  audytora); do stałego użytku wchodzi tylko to, co obniża tokeny bez
  spadku jakości.

Szczegóły każdego zadania: pliki `ai_docs/tasks/0929…0939`.

## Mapa wymaganie → zadanie → kryterium

| Wymaganie | Zadania | Kryterium |
|---|---|---|
| Wild podmienia się per linia | 0932 | golden case Wild na dwóch liniach |
| Checkbox Wild / Uruchamia supergrę + select 3–5 | 0931 | formularz, walidacja, test API |
| Rodzaj supergry per gra, 777 = brak | 0931 | select gry, rejestr, 777 bez zmian |
| Wypłaty Mumii za sztuki | 0931, 0932 | etykieta reguł, golden case |
| Klawisz `0` | 0930 | test klawiatury |
| ≥N → seria 10, retrigger +10, brak planszy = pusta | 0933 | testy wyprowadzania |
| Komórki z predykcją liczą się, oznaczenie niezweryfikowane | 0933, 0934 | pole `trigger_verification`, UI |
| Ręczna definicja super symbolu z karuzelą | 0934 | zapis CAS |
| Złote oznaczenie w wyszukiwaniu | 0935 | znacznik w projekcji, test UI |
| Rozwinięcie kolumn, niesąsiednie, × linie, koszt 0 | 0936 | golden cases, §D |
| Audyt krzyżowy po każdym tasku | 0929 | raporty w `ai_docs/quality/` |
| Mniejsze zużycie tokenów bez utraty jakości | 0938, 0939 | rozmiar plików procesu; pomiar przed/po |

## Ryzyka

- Pomyłki Mumia↔Sarkofag przy liczeniu komórek z predykcją → fałszywe lub
  brakujące triggery; stąd pole `trigger_verification` i ponowne
  wyprowadzanie po każdej korekcie symboli.
- Interpretacja `payout_rules` zależna od roli symbolu: wymaga jawnego
  wersjonowania algorytmu i testów gotowości wydania; historyczne wyniki
  777 muszą się odtwarzać.
- Koszt per pozycja dotyka przybliżonej wygranej i stawek panelu; regresja
  777 jest bramką S-C.
- Skille audytu wymagają obu CLI i logowań po stronie operatora; bez nich
  audyt pozostaje ręczny (sesja w drugiej aplikacji).

## Zakres wyłączony

Aplikacja mobilna i snapshot, trening modelu złotej ramki, zmiana wycinków
V3, gry 777/777 v2/Blazing/Gang, migracje danych produkcyjnych bez osobnej
zgody, zmiany sygnatury layoutu, inne rodzaje supergry.

## Decyzje operatora

- D-1 (otwarta): kolejność etapu T względem S-A — operator wskazał, że
  oszczędność tokenów jest potrzebna; plan proponuje TASK-0938 przed S-B
  (najwięcej sesji dopiero przed nami), TASK-0939 równolegle z S-B.
- Rozstrzygnięte 2026-10-08: nazwa rodzaju „Wild super spins”; checkbox
  „Uruchamia supergrę”; komórki z predykcją liczą się do progu, plansza
  musi być pocięta.

## Przypisanie modeli do zadań

Dostępność potwierdzona w tym środowisku: Claude — `claude-fable-5-1`,
`claude-opus-5-5`, `claude-sonnet-5-5` (low/medium/high/xhigh/max); Codex —
`gpt-6-astra` (konfiguracja użytkownika, `high`), `gpt-6.1-sol` (`high`).
Audytor zawsze z drugiej rodziny niż wykonawca.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0929 | claude-sonnet-5-5 | high | Skrypt PowerShell, dwa skille, edycja `AGENTS.md`; brak logiki domenowej. | Wymagany: gpt-6.1-sol, high |
| TASK-0930 | claude-sonnet-5-5 | medium | Mała zmiana TS z testem jednostkowym. | Wymagany: gpt-6.1-sol, high |
| TASK-0931 | claude-opus-5-5 | high | Migracja, walidacje domeny, rejestr rodzajów, kontrakt API pionem, formularze Adminu. | Wymagany: gpt-6-astra, high |
| TASK-0932 | gpt-6.1-sol | high | Ewaluator w Pythonie i TS, golden cases, regresja 777. | Wymagany: claude-opus-5-5, high |
| TASK-0933 | claude-opus-5-5 | high | Tabela partycjonowana, wyprowadzanie z przypadkami brzegowymi, job, API. | Wymagany: gpt-6-astra, high |
| TASK-0934 | gpt-6.1-sol | high | Nowy ekran Adminu na istniejących komponentach, CAS. | Wymagany: claude-opus-5-5, medium |
| TASK-0935 | claude-sonnet-5-5 | high | Znacznik w projekcji i współdzielonym UI, trzy konsumenty. | Wymagany: gpt-6.1-sol, high |
| TASK-0936 | gpt-6-astra | high | Logika rozwinięcia, koszt per pozycja, regresja 777, dokumenty. | Wymagany: claude-opus-5-5, high |
| TASK-0937 | claude-sonnet-5-5 | medium | Skrypt pomiarowy i raport. | Wymagany: gpt-6.1-sol, medium |
| TASK-0938 | claude-sonnet-5-5 | medium | Przeniesienie treści bez zmian merytorycznych, kontrola linków. | Wymagany: gpt-6.1-sol, medium |
| TASK-0939 | claude-sonnet-5-5 | high | Konfiguracja narzędzi, hook, skrypt mapy kodu i pomiar; brak logiki domenowej. | Wymagany: gpt-6.1-sol, high |
