---
title: TASK-0801 — snapshot treningowy geometrii produkcyjnej, filtr zgodności symboli, zamrożony podział i przegląd etykiet
status: done
last_updated: 2026-10-02
---

# TASK-0801 — snapshot treningowy geometrii produkcyjnej

## Status

`done` (poza commitem i wpisem w `CURRENT_STATE.md`, które należą do orkiestratora)

## Goal

W katalogu laboratorium istnieje zamrożony, odtwarzalny snapshot zdjęć 777
z siatkami produkcyjnymi (trening, development, zbiór złoty) z polityką
podziału `production-geometry-split-v1`, a operator ma narzędzie do
przeglądu 600 losowych plansz, którego wynik daje odsetek błędnych etykiet.

## Context

Etap V3-A planu (D-480, D-483). TASK-0800 wyeksportował 499 460
plansz-kandydatów (`production-geometry-777-20261002`): G 459 plansz na 101
zdjęciach (22 zdjęcia w całości G; 76 zdjęć miesza 261 plansz G z 425
niesklasyfikowanymi), S 137 473 na 15 275 zdjęciach, B 361 103 na 40 123
zdjęciach, 24 rodziny źródeł, 2 grupy współdzielonego SHA. Etykiety S
pochodzą z hybrydowej reweryfikacji i mogą powielać jej błędy — dlatego
przed treningiem operator ocenia próbkę.

## Dependencies / entry conditions

- TASK-0800 ukończony (`v1.7.153`); manifest kandydatów w
  `C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry\production-geometry-777-20261002\`.
- Pliki zdjęć: `C:\Users\tuszy\Documents\game_predicotr\artifacts` (ścieżki
  względne z manifestu) — tylko odczyt.
- Zamrożony pilot D-456 (walidacja Mumie, `final_test` Reels, `unseen_game`
  Treasure) pozostaje nietknięty; to zadanie go nie czyta do wyboru danych
  i nie zmienia.
- Bez zapisu do bazy produkcyjnej; baza jest potrzebna najwyżej do odczytu
  kontrolnego.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Polityka podziału, przeciek rodzin i
filtr jakości etykiet decydują o wiarygodności całego wyniku V3. Zatrzymaj
zadanie, jeżeli po filtrze nie da się zebrać założonych liczności albo
podział rodzin nie daje rozłącznego developmentu. Audyt zawieszony decyzją
operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` („Zakres i
  reguły”, etap V3-A, ryzyka)
- `ai_docs/process/DECISION_LOG.md` (D-480, D-483, D-484, D-456, D-447)
- `ai_docs/quality/GRID_V3_PRODUCTION_GEOMETRY_INVENTORY_20261002.md`
- `ai_docs/tasks/completed/0800-production-geometry-inventory-export.md`
- `ai_docs/architecture/VISION_LAB.md`, `ai_docs/requirements/VISION_LAB.md`
  (snapshoty, polityki podziału, publikacja atomowa T01, przegląd zdjęć T03d)
- `ai_docs/guides/VISION_LAB_LOCAL.md`

## Scope

- Czysta logika filtra, losowania warstwowego i podziału w pakiecie labu
  (bez `storage`/`psycopg`).
- Skrypt budujący snapshot: wybór, kopia obrazów z kontrolą SHA, manifesty,
  publikacja atomowa, tryb podglądu bez kopiowania.
- Narzędzie przeglądu etykiet dla operatora (600 plansz) z trwałym zapisem
  decyzji i raportem odsetka błędów.
- Testy, raport w `ai_docs/quality/`, wpis w przewodniku labu.
- Uruchomienie budowy snapshotu na danych rzeczywistych (raz).

## Out of scope

- Trening, modele, ONNX (TASK-0802), zmiany zamrożonego pilota D-456,
  zapis do bazy produkcyjnej, zmiany aplikacji Admin/Reviewer.
- Sama ocena 600 plansz — wykonuje ją operator po zadaniu (STOP V3-A).

## Acceptance criteria

- [x] Snapshot opublikowany atomowo w nowym katalogu labu: obrazy z
      potwierdzonym SHA, manifest próbek (zdjęcie → plansze → 24 węzły,
      poziom, rodzina, rola w podziale), manifest podziału z sumami
      kontrolnymi; ponowne uruchomienie z tym samym ziarnem daje identyczny
      manifest (test).
- [x] Podział spełnia reguły z „Technical notes”; test rozłączności:
      żadne zdjęcie, SHA ani rodzina developmentu nie występuje w treningu;
      żadne zdjęcie ani SHA zbioru złotego nie występuje w treningu ani
      developmencie.
- [x] Zdjęcie wchodzi do treningu albo developmentu tylko w całości i tylko
      gdy wszystkie jego plansze przechodzą filtr (jednostką jest zdjęcie,
      D-484).
- [x] Raport liczności: per rola, poziom, rodzina, przedział trudności;
      liczba zdjęć odrzuconych przez filtr z powodem; błędy integralności
      plików (brak pliku, inne SHA) jako wykluczenia z powodem, bez
      przerywania.
- [x] Narzędzie przeglądu pokazuje 300 losowych plansz S i 300 B (ziarno
      zapisane), każdą jako wycinek zdjęcia z naniesioną siatką 5 × 3,
      pozwala oznaczyć „dobra / zła / nie da się ocenić”, zapisuje decyzje
      trwale (wznowienie po zamknięciu) i liczy odsetek błędów z przedziałem
      ufności per poziom.
- [x] Laboratorium nadal nie importuje `storage` ani `psycopg`.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

### Filtr zgodności symboli (rozstrzygnięte)

Plansza przechodzi filtr, gdy nie ma żadnej komórki bez decyzji człowieka z
jakością predykcji ≤ 0,80 (`cellsBelowFilter == 0` w manifeście TASK-0800;
próg zapisany w manifeście snapshotu). Zdjęcie przechodzi, gdy przechodzą
wszystkie jego plansze-kandydaci i ma komplet oczekiwanych plansz. Plansze
niesklasyfikowane (U) nie są etykietami: zdjęcie z planszą U nie wchodzi do
treningu ani developmentu.

### Role (rozstrzygnięte)

1. **Zbiór złoty (pierwszy):** wszystkie zdjęcia z co najmniej jedną planszą
   G (101 zdjęć). Celami oceny są wyłącznie plansze G; plansze U i inne na
   tych zdjęciach są zapisane jako „bez etykiety oceny”. Zdjęcia złote i
   wszystkie zdjęcia o tym samym SHA są wyłączone z treningu i
   developmentu. Manifest zapisuje dla każdego zdjęcia złotego, czy jego
   rodzina występuje w treningu (`familySeenInTraining`), żeby TASK-0804
   raportował oba podzbiory osobno — rodziny złote nie są wyłączane w
   całości, bo G występuje w 13 z 24 rodzin.
2. **Development:** całe rodziny wybrane deterministycznie (ziarno), tak aby
   po filtrze dawały co najmniej 600 zdjęć z udziałem S i B; z tych rodzin
   losowanie warstwowe 600 zdjęć. Rodziny developmentu nie występują w
   treningu.
3. **Trening:** 6 000 zdjęć z pozostałych rodzin po filtrze: 3 000 zdjęć,
   których plansze są S, i 3 000 zdjęć z planszami B, warstwowane po
   rodzinie i trudności (kwantyle skośności i pola quada z manifestu);
   limit udziału jednej rodziny 25%. Jeżeli warstwa nie ma dość zdjęć,
   weź wszystkie i odnotuj.

Rodziny dwóch importów współdzielących katalog są jedną rodziną. Grupy
współdzielonego SHA trafiają w całości do jednej roli (pierwszeństwo:
złoty, development, trening).

Liczności 6 000 / 600 są propozycją planu; jeżeli pomiar pokaże, że kopia
przekracza ok. 3 GB albo warstwy są puste, zatrzymaj się z liczbami zamiast
po cichu zmieniać cel.

### Snapshot

Wzorzec publikacji i checksum z T01 (przeczytaj istniejący kod snapshotów
labu i użyj go; nie twórz równoległego formatu, jeżeli istniejący pomieści
siatki produkcyjne — jeżeli nie pomieści, uzasadnij nowy schemat z wersją).
Obrazy kopiowane bez przekodowania; SHA pliku musi równać się
`checksum_sha256` z manifestu. Zdjęcia w orientacji zapisanej w źródle;
węzły są w przestrzeni `exif-normalized-rgb-pixels-v1` — zapisz w manifeście
orientację EXIF i sprawdź w teście na rzeczywistym pliku, że siatka trafia
w plansze (kontrola wizualna jednej próbki do raportu). Uzupełnij metrykę
„niski kontrast” z pikseli dla skopiowanych zdjęć (prosta, deterministyczna
miara; opisz definicję).

### Przegląd etykiet

Najpierw sprawdź istniejący przegląd zdjęć labu (`photo_review.py`, UI
`apps/vision-lab`). Jeżeli da się w nim pokazać próbkę z siatkami
produkcyjnymi bez przebudowy modelu danych labu — użyj go. W przeciwnym
razie zbuduj najmniejsze samodzielne narzędzie lokalne (strona serwowana
przez istniejące API labu albo statyczny podgląd + mały endpoint zapisu),
działające wyłącznie na `127.0.0.1`, z klawiaturą (dobra / zła / pomiń,
wstecz), zapisem decyzji do pliku w katalogu snapshotu (atomowy zapis,
historia) i podsumowaniem. Próbka: 300 plansz S i 300 B losowanych z całego
manifestu kandydatów po filtrze (nie tylko z wybranych do treningu), po
jednej planszy na zdjęcie. Raport: odsetek „zła” z przedziałem Wilsona 95%
per poziom; decyzja o przydatności S/B należy do operatora.

### Niedozwolone skróty

- Żadnego odczytu `final_test` ani `unseen_game`.
- Nie mieszaj plansz jednego zdjęcia między rolami.
- Nie nadpisuj istniejących danych labu; nowy katalog snapshotu.

## Expected files

- Nowe (proponowane): moduły w
  `services/worker/src/game_predictor_worker/vision_lab/` (podział, filtr,
  snapshot produkcyjny, przegląd etykiet), skrypt w `scripts/`, testy w
  `services/worker/tests/`, ewentualnie widok w `apps/vision-lab`, raport
  `ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md`.
- Istniejące: `ai_docs/guides/VISION_LAB_LOCAL.md`.

## Test cases

- Filtr: zdjęcie z jedną planszą poniżej progu odpada w całości; zdjęcie z
  planszą U odpada.
- Podział: rozłączność rodzin developmentu, SHA, zdjęć złotych; determinizm
  ziarna; grupa SHA w jednej roli; limit udziału rodziny.
- Snapshot: zły SHA i brak pliku → wykluczenie z powodem; publikacja
  atomowa; ponowne uruchomienie nie zmienia opublikowanego snapshotu.
- Przegląd: zapis i wznowienie decyzji, cofnięcie, podsumowanie z
  przedziałem ufności.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "production_split or production_snapshot or label_review or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

Limit 120 s na testy; budowa snapshotu na danych rzeczywistych do 900 s,
uruchamiana raz. Testy są planowane.

## Risks / open questions

- Zbiór złoty jest mały (459 plansz) i w większości leży w rodzinach
  widzianych w treningu; raport musi to pokazać wprost.
- Trening ma preferować środowisko `.venv-vision-lab` — to zadanie nie
  potrzebuje GPU.

## Outcome

Wypełnia agent po pracy.

### Changed

- Nowe moduły laboratorium (bez importu `storage`/`psycopg`):
  `services/worker/src/game_predictor_worker/vision_lab/production_split.py` (czysty
  filtr zgodności symboli, polityka `production-geometry-split-v1`, przydział
  warstwowy z limitem rodziny, kontrola rozłączności),
  `.../vision_lab/production_snapshot.py` (strumieniowy odczyt manifestu, kontrola
  integralności, kopia bajt w bajt, metryka kontrastu, kontrola wizualna, publikacja
  atomowa, `verify_snapshot`), `.../vision_lab/label_review.py` (próbka 300 S + 300 B,
  wycinki, magazyn decyzji z historią, raport Wilsona, strona na `127.0.0.1:8103`).
- Nowy skrypt `scripts/vision_lab_production_snapshot.py` (`preview`, `build`,
  `label-review`); domyślne ziarno 801.
- Testy: `services/worker/tests/test_vision_lab_production_split.py` (11),
  `test_lab_production_snapshot.py` (9 + 1 opcjonalny na plikach rzeczywistych),
  `test_vision_lab_label_review.py` (7), pomocnik `lab_production_fixtures.py`.
- Raport `ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md`, sekcja w
  `ai_docs/guides/VISION_LAB_LOCAL.md`.
- Dane (poza repozytorium, nowe katalogi; nic istniejącego nie zmieniono):
  - snapshot `C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry-snapshots\3ff448c620a71f3a28e467cfdfeb77c7e46325e73ca25eaabcb35a56e0b7727d\`
    (6 707 plików, 1 826 221 577 B, obrazy 1 727 878 802 B);
  - próbka przeglądu `...\production-geometry-snapshots\label-review-seed801\`
    (`sample.json` + 600 wycinków, 50,6 MB, `sampleId` `e25c5bee…2121`), bez decyzji.
- Wynik podziału (ziarno 801): trening 6 000 zdjęć (3 000 S + 3 000 B, 54 000 plansz,
  21 rodzin, największy udział rodziny 8,73% przy limicie 25%), development 600 (300 S
  + 300 B, 5 400 plansz, rodziny `c0932585`, `c4c066f8`, `c2547b09`), zbiór złoty 102
  zdjęcia (101 z G, 459 plansz G jako cele oceny, 1 bliźniak SHA z 8 planszami S).
  Filtr odrzucił 5 670 zdjęć (5 669 `SYMBOL_FILTER_BELOW_THRESHOLD`: S 3 177, B 2 492;
  1 `INCOMPLETE_BOARD_SET`); wykluczenia integralności 0; braki warstw 0. Wszystkie 102
  zdjęcia złote leżą w rodzinach widzianych w treningu (`familySeenInTraining = true`).
- Przyjęte rozstrzygnięcia: (1) nowy format `production-geometry-snapshot-v1`, bo
  `vision-lab-folder-v1` nie pomieści geometrii, ról ani podziału; wzorzec publikacji
  T01/T02 bez zmian; (2) limit 25% stosowany per poziom (750 z 3 000), co daje ≤ 25%
  całego treningu; (3) development wymaga puli ≥ 300 S i ≥ 300 B i losuje 300 + 300;
  (4) trudność = tercyle globalne skośności (największe odchylenie kąta na zdjęciu) i
  skali (dolna mediana pola quada); (5) zdjęcie bliźniacze SHA zdjęcia złotego trafia do
  roli złotej bez celów oceny; (6) próg niskiego kontrastu = 10. percentyl plansz
  treningu i developmentu (0,133142); (7) narzędzie przeglądu jest samodzielne, bo
  przegląd zdjęć T03d wymaga stanu anotacji labu; strona nie pokazuje poziomu (ślepy
  przegląd); (8) katalog przeglądu leży obok snapshotu, nie w nim, bo opublikowany
  snapshot ma zamknięty inwentarz plików.

### Verification results

- `pytest services/worker/tests -k "production_split or production_snapshot or label_review or no_production_storage_imports"`:
  37 passed, 1 skipped (selekcja obejmuje także istniejący `test_production_snapshot.py`
  aplikacji mobilnej i test izolacji `test_lab_has_no_production_storage_imports`;
  pominięty jest test plików rzeczywistych bez zmiennej środowiskowej).
- Z `VISION_LAB_PRODUCTION_SNAPSHOT` ustawionym na opublikowany snapshot test
  `real_files`: 1 passed (25 zdjęć: SHA, orientacja EXIF, rozmiar po orientacji, węzły w
  obrazie).
- `ruff check services scripts`: tylko wcześniejsze E501 w
  `services/worker/tests/test_page_geometry_preflight.py`; `ruff format --check` nowych
  plików: czyste; `mypy --strict` nowych modułów i skryptu: brak błędów.
- Podgląd (33,5 s) i budowa (320,5 s, jednorazowo) dały ten sam ID snapshotu;
  `verify_snapshot` opublikowanego katalogu: 6 706 sum zgodnych. Niezależny skrypt na
  `samples.jsonl`: 0 wspólnych zdjęć, SHA i rodzin między rolami, 0 SHA złotych w
  treningu/developmencie, 0 zdjęć treningu/developmentu łamiących filtr lub regułę
  jednostki, 0 węzłów poza obrazem. Kontrola wizualna `checks/visual-training.jpg` i
  `checks/visual-gold.jpg`: siatki leżą na wszystkich 9 planszach.
- Narzędzie przeglądu end-to-end (2026-10-02): serwer uruchomiony w tle na
  `127.0.0.1:8103`, strona otwarta w przeglądarce, `Z` zapisało „zła” dla 0001
  (rewizja 1), `←` + `U` cofnęło (rewizja 2); po zatrzymaniu serwera `report` odtworzył
  stan z historii. Pliki testowe decyzji usunięto; procesy zatrzymane, port wolny.

### Not completed

- Commit, wpis w `CURRENT_STATE.md` i przeniesienie pliku do `completed/` — należą do
  orkiestratora.
- Ocena 600 plansz — wykonuje operator (STOP V3-A); odsetek błędów etykiet jeszcze nie
  istnieje.
- Ścieżki orientacji EXIF ≠ 1 i wykluczeń integralności nie wystąpiły w danych
  rzeczywistych (wszystkie 6 702 zdjęcia mają orientację 1, 0 wykluczeń); pokrywają je
  testy na syntetycznych plikach.
- Podzbiór złota z rodzin niewidzianych w treningu jest pusty; jego utworzenie wymaga
  decyzji operatora o wyborze rodzin developmentu.

### Documentation updates

- `ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md` (nowy raport).
- `ai_docs/guides/VISION_LAB_LOCAL.md`: sekcja „Snapshot treningowy geometrii
  produkcyjnej i przegląd etykiet (TASK-0801)”.
- `CURRENT_STATE.md` i `DECISION_LOG.md` nie zostały zmienione (polecenie
  orkiestratora). Nowa polityka podziału i format snapshotu są w zakresie zatwierdzonego
  planu (D-480, D-484); ewentualny wpis decyzji o złocie w rodzinach treningu należy do
  operatora.

### Recommended next task

- STOP V3-A: operator ocenia 600 plansz w narzędziu przeglądu i uruchamia `report`;
  na podstawie odsetka „zła” per poziom decyduje o użyciu S/B i o tym, czy wymusić
  rodzinę z G w developmencie przed TASK-0802.