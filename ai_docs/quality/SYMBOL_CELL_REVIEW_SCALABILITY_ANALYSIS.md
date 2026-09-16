---
title: Symbol cell review scalability analysis
status: accepted
last_updated: 2026-09-07
---

# Teoretyczna analiza skali masowej weryfikacji symboli

## Cel i granica odbioru

Dokument zamyka część analityczną TASK-0294 bez uruchamiania fizycznego
benchmarku, generatora miliona rekordów ani dodatkowego workera na komputerze
operatora. Jest to świadoma decyzja właściciela z 2026-08-26: bieżący komputer
wykonuje importy i review, więc sztuczne obciążenie mogłoby zakłócić właściwą
pracę.

Analiza potwierdza ograniczenia algorytmiczne i zakres pamięci procesu. Nie
jest pomiarem czasu. W szczególności nie dowodzi bramki `p95 <= 250 ms`; taka
bramka wymaga kiedyś jawnie zleconego pomiaru na odizolowanej bazie PostgreSQL
o znanej konfiguracji. Do tego czasu nie wolno przedstawiać jej jako zaliczonej
ani uruchamiać benchmarku automatycznie.

## Model referencyjny 2 mln komórek

Aktualna plansza ma zawsze dokładnie 15 komórek. Dlatego literalne `2 000 000`
nie jest poprawnym fixturem pełnych plansz: pozostawia pięć komórek bez
rodzica. Najmniejszy poprawny profil co najmniej dwóch milionów to:

| Wielkość | Wyliczenie | Wynik |
| --- | --- | ---: |
| komórki | `133 334 * 15` | `2 000 010` |
| aktualne plansze | `2 000 010 / 15` | `133 334` |
| strony API po 60 | `ceil(2 000 010 / 60)` | `33 334` |
| maksymalny jawny wybór | kontrakt API/UI | `10 000` komórek |
| duży snapshot filtra | `6 667 * 15` | `100 005` komórek |
| checkpointy dla tego snapshotu | `ceil(6 667 / 100)` | `67` planszowych partii |

`2 000 010` zastępuje w przyszłym teście skrót „2 mln”, nie zmienia domeny i
nie dopuszcza niepełnej planszy wyłącznie po to, aby pasowała okrągła liczba.

## Odczyt i pamięć

`SqlAlchemySymbolCellReviewQueryRepository.list_items` pobiera co najwyżej
`limit + 1` wierszy. Domyślny limit API to 60, zatem samo pobranie strony ma
górną granicę 61 rekordów. Sprawdzenie poprzedniej/następnej strony jest
oddzielnym zapytaniem z `LIMIT 1`, a nie offsetowym przeskokiem przez wszystkie
wcześniejsze komórki.

Kursor używa stabilnego porządku
`(sequence_number, cell_index, review_item_id)`. Widoczny read path łączy
`image_symbol_review_cells` z
`image_board_search_fast_documents` po aktualnym właścicielu logicznej planszy
oraz z aktualną rewizją geometrii. To wyklucza z listy superseded, alternatywne
i stare cropy bez tworzenia listy wszystkich wyników w procesie API.

Indeksy modeli odpowiadają dwóm podstawowym filtrom:

- `ix_image_symbol_review_cells_game_symbol_sequence` dla gry i symbolu,
- `ix_image_symbol_review_cells_game_symbol_state_sequence` dla gry, symbolu i
  stanu,
- porządek obu indeksów kończy się kluczem keysetu.

Admin utrzymuje maksymalnie trzy strony metadanych: poprzednią, bieżącą i
następną. Przy stronie 60 oznacza to najwyżej 180 rekordów workspace’u. Assety
są pobierane leniwie, a zaznaczenie całego filtra zawiera tylko snapshot
rewizji katalogu oraz wykluczenia; nie przenosi do przeglądarki wszystkich
identyfikatorów. Jawne zaznaczenie ma twardy limit 10 000 checksum-bound
tożsamości.

### Pomiar i optymalizacja liczników

TASK-0500 wykonał odczytowe pomiary na bieżącej bazie operatora: 7 518 540
komórek łącznie, w tym 6 304 230 dla największej gry i 6 220 575 widocznych
komórek jej aktualnego właściciela. Historyczne zapytanie szerokiego licznika
łączyło `recognized_boards` dla każdej komórki i sortowało wynik przed
`GROUP BY`; `EXPLAIN (ANALYZE, BUFFERS)` osiągnął około 28,7 s na zimniejszym
przebiegu, a kontrolny przebieg wartości około 18,1 s.

Szeroki licznik całej gry bez confidence wykorzystuje teraz zweryfikowany stan
projekcji `ready`, nadal łączy kanonicznego właściciela z
`image_board_search_fast_documents`, lecz pomija redundantny per-cell lookup
geometrii. Dwa `COUNT(*) FILTER` wyliczają stany bez `GROUP BY`. Rzeczywisty
odczyt przez produkcyjny `bounded_read` zakończył się w 4,669 s i zwrócił
6 220 575 wszystkich, 38 542 zatwierdzone oraz 6 182 033 oczekujące komórki,
czyli identyczne wartości jak zapytanie kontrolne i poniżej limitu 15 s.

Nie rozszerzono tego uproszczenia na symbol, `?`, confidence ani aktywną
kohortę. Pomiary pokazały, że ich selektywne plany z pełnym joinem geometrii są
równie szybkie lub szybsze; przykładowy filtr confidence bez niego wzrósł z
około 10,4 s do około 15,0 s. Lista, assety i mutacje nadal zawsze sprawdzają
bieżącą rewizję planszy. Osobny read model, cache i migracja nie są obecnie
uzasadnione.

## Operacje masowe i recovery

Start operacji z filtrem wykonuje snapshot przez bazowe `INSERT ... SELECT`
do `image_symbol_review_bulk_targets`; nie materializuje ponad 100 tys.
targetów w pamięci API. Target przechowuje tylko identyfikatory, rewizje i
checksumy — bez binariów cropów.

Worker istniejącego general lane grupuje targety deterministycznie po planszy
i przetwarza najwyżej 100 plansz na checkpoint. W modelu `100 005` targetów
praca ma 67 transakcji planszowych, nie jedną transakcję globalną. Każda plansza
ponownie weryfikuje właściciela, crop, rewizje i aktywność symbolu, po czym
zapisuje komórki, decyzję pełnej planszy, canonical/staging oraz projekcję
wyszukiwania atomowo.

Awaria wycofuje wyłącznie bieżącą planszę. Targety wcześniejszych partii mają
trwały wynik, a świeży worker wybiera ponownie tylko `pending`. Idempotency key
wiąże tę samą grę z kanoniczną komendą, więc retry nie tworzy drugiej operacji
ani nowych eventów dla pozycji już `applied`.

## Integralność i bezpieczeństwo

- Każde zatwierdzenie jest związane z `cropSampleId`, SHA-256 i rewizją
  geometrii. Nie da się automatycznie zatwierdzić `?` ani komórki z flagą
  `has_grid_issue`.
- Dopiero 15 aktualnych `approved` bez `?` i bez błędu siatki domyka planszę;
  w przeciwnym razie pełna decyzja pozostaje otwarta.
- Zmiana geometrii resetuje komplet 15 komórek. Zmiana symbolu lub geometria
  podczas pracy masowej daje kontrolowany `conflict`, a nie częściowy zapis.
- Odczyty, assety i operacje masowe są wyłącznie lokalnym Admin API. Token
  zdalnego Reviewera nie otrzymuje tych endpointów ani danych cropów.
- Baza nie przechowuje binariów obrazów; asset ponownie kontroluje aktualnego
  właściciela, bezpieczną ścieżkę i SHA-256 przed wysłaniem pliku.

Powyższe własności są pokryte testami domenowymi, API i izolowanymi testami
PostgreSQL. Nie zastępują pomiaru przepustowości sprzętu.

## Kontrole wykonane bez benchmarku

Przed zamknięciem TASK-0294 wykonywane są lekkie, istniejące kontrole:

- domena: statusy, `?`, flaga siatki, agregacja 15 komórek,
- API: keyset next/previous, scope cursorów, filtry, aktualny właściciel i
  checksum-bound asset,
- PostgreSQL: idempotentny snapshot, board-atomic recovery po checkpointcie i
  brak zdublowanych eventów przy retry,
- Admin: bounded cache trzech stron, zaznaczenie snapshotu i sekwencyjny
  polling operacji,
- OpenAPI/generowany klient dla listy oraz operacji.

Nie uruchamia się fixture 2 000 010 komórek, operacja 100 005 targetów ani
kontrolowany crash na środowisku operatora.

## Przyszły, jawny test po zgodzie właściciela

Jeżeli zostanie zlecony osobny test po odciążeniu komputera lub na izolowanym
hoście, ma on użyć oddzielnej scratchowej bazy PostgreSQL i profilu
`2 000 010` komórek. Musi zmierzyć pierwszą, środkową i poprzednią stronę
łącznie z licznikami, zapisać konfigurację hosta/PostgreSQL i raport p50/p95,
utworzyć snapshot `100 005` targetów, wymusić kontrolowane zatrzymanie po
checkpointcie oraz potwierdzić resume bez podwójnych eventów. Test wymaga
wyraźnego polecenia użytkownika i cleanupu wyłącznie własnej scratchowej bazy.
