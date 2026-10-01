---
title: Hybrydowy silnik siatek V3 — plan wykonawczy (dane produkcyjne, sieć węzłów, bramka zgodności)
status: accepted
last_updated: 2026-10-01
---

# Hybrydowy silnik siatek V3

Plan zaakceptowany przez operatora 2026-10-01 (D-480–D-484). Uzupełnia etap
D (`T10`, TASK-0675) i poprzedza etap E zaakceptowanego
[VISION_LAB_EXECUTION_PLAN.md](VISION_LAB_EXECUTION_PLAN.md) (D-447). Nie
zmienia etapu C (symbole, T06b–T09), który pozostaje zablokowany i nie jest
warunkiem geometrii (D-461, D-482). Każdy etap wymaga jawnego uruchomienia;
2026-10-01 operator uruchomił etap V3-0.

## Stan obecny

Fakty z repo, raportów i bazy operatora (2026-10-01, tylko `SELECT`):

- **Silnik produkcyjny** 777: `structured_opencv_v1`
  (`structured-opencv-independent-board-refinement-v2-pinned-preflight-v1`,
  polityka importu `structured_lattice_v3` / `virtual_default`). Znane
  błędy (`GRID_ENGINE_V3_NEURAL_EXECUTION_PLAN.md`, zastąpiony): ręka i
  odblask, wspólny przechył prawej kolumny, przeskok o kolumnę lub rząd
  (okresowość symboli), skrajne plansze. Silnik nie „widzi” planszy, której
  nie wykrył.
- **Laboratorium** (`services/worker/src/game_predictor_worker/vision_lab`,
  API `127.0.0.1:8102`, UI `apps/vision-lab` `127.0.0.1:3102`, dane poza
  repo `C:\Users\tuszy\Documents\game_predictor_vision_data`): kontrakty
  `GeometryEngine` / `GeometryResult` (`vision_lab/contracts.py`), silniki
  `baseline` i `hybrid` (`hybrid_*.py`), trwały protokół runów
  (`runs.py`, `run_worker.py`), izolowane środowisko GPU
  (`.venv-vision-lab`, `scripts/setup_vision_lab.ps1`,
  `scripts/check_vision_lab_gpu.py`), eksporter tylko do odczytu
  (`scripts/vision_lab_export.py`).
- **Wynik T05** (`ai_docs/quality/VISION_LAB_HYBRID_20260927.md`): hybryda
  `MobileNetV3-Small` poprawiająca propozycje baseline, 20 epok / 200
  kroków. Development 32 zdjęcia / 90 siatek, validation 11 / 30. Wynik
  image-macro (mniej = lepiej): DEV 0,1536 vs baseline 0,1565; VAL 0,04699
  vs 0,04613 — walidacja gorsza o 1,85%, najlepsza epoka = 1. Baseline nie
  znalazł 15/90 i 1/30 plansz; hybryda poprawia tylko istniejące
  propozycje, więc braków nie odzyskuje. Brak promocji, STOP B.
- **Dane geometrii w produkcji 777** (`game_data_v2`): 56 816 zdjęć
  źródłowych, 510 416 plansz `virtual_source`. Zatwierdzona geometria
  (`approved_geometry_revision`): 138 186 plansz, z czego 137 439 rewizji
  zapisał `system:grid-reverify-777-v1` (hybrydowa reweryfikacja 777,
  zaakceptowana w przeglądzie dry-run: operator wskazywał tylko plansze
  odrzucone), 461 narysował Reviewer (`reviewer-operator`), 135 poprawił
  `local-admin`. 371 806 plansz ma automatyczną geometrię silnika bez
  osobnej zgody człowieka; 108 plansz jest częściowych (`pending_partial`).
  Geometria źródła jest w `image_source_geometry_revisions.board_geometries`
  (15 650 rewizji `manual_v1`, 41 161 `auto accepted`, 15 526
  `auto needs_review`), render każdej komórki w `board_render_manifests`.
- **Decyzje człowieka o symbolach** (D-462, D-464–D-466): komórki mają
  `assigned_symbol_id` i stan weryfikacji; biblioteka wzorców daje
  predykcję z głosami. To niezależny sygnał jakości cięcia: plansza, której
  15 cropów zgadza się z zatwierdzonymi symbolami, jest prawie na pewno
  dobrze pocięta.
- **Ograniczenia dotychczasowych decyzji:** D-453 dopuszcza historyczne 777
  do nauki geometrii wyłącznie przez nowe ręczne siatki labu (30 siatek);
  D-456 zamroził pilot całymi grami (90/30/30/30); budżet T05/T10: jeden
  trening do 20 epok lub 30 minut.

- **Kompletność zdjęć po imporcie** (zgłoszenie operatora 2026-10-01):
  import 777 przeszedł, plansze z siatką trafiły do cięcia i weryfikacji
  symboli, a dopiero później okazało się, że wiele plansz z części zdjęć
  nie miało siatki. Pipeline traktuje każdą planszę osobno: plansza z
  siatką idzie dalej, plansza bez siatki staje się wierszem
  `image_board_geometry_pending` (historycznie 20 577 odroczonych plansz,
  20 567 rozwiązanych ręcznie albo reweryfikacją, 10 otwartych). Stan na
  dziś: 56 709 zdjęć ma 9/9 plansz, 91 zdjęć ma 0/9, 4 zdjęcia są
  niepełne. Nie istnieje bramka na poziomie zdjęcia ani widok, który
  zaraz po imporcie pokazałby zdjęcia z brakującymi siatkami, więc błąd
  silnika wyszedł na jaw dopiero w weryfikacji symboli i nie dało się go
  wcześnie wychwycić ani poprawić silnika na świeżych przykładach.
- **Wnioski z czytania i weryfikacji symboli** (D-462, D-464–D-466,
  TASK-0749–0751): jakość rozpoznania symbolu zależy wprost od cięcia —
  błędna albo przesunięta siatka daje cropy, które model i biblioteka
  wzorców oceniają nisko albo błędnie, a człowiek poprawia potem pojedyncze
  komórki zamiast jednej siatki. Weryfikacja per komórka i przedziały
  jakości (≤ 80%, 80–99%, ≥ 99%) pokazały, że niska jakość skupia się na
  konkretnych zdjęciach i planszach; rozkład jakości predykcji na planszy
  i zdjęciu jest więc użytecznym, tanim detektorem złej siatki. Decyzje
  człowieka o symbolach i przebiegi biblioteki zakładają stabilną
  geometrię: każda późniejsza zmiana siatki unieważnia cropy i wymaga
  ponownego rozpoznania (zdarzenia `geometry_invalidated`), dlatego
  geometria całego zdjęcia powinna być zamknięta, zanim zacznie się praca
  nad symbolami.

Wniosek (hipoteza, nie diagnoza): T05 nie miał z czego się uczyć — 90
siatek wobec 138 tys. zatwierdzonych w produkcji — i z konstrukcji nie
mógł naprawić brakujących plansz.

## Cel

Kandydat silnika siatek 5 × 3, który na zamrożonej walidacji i zbiorze
złotym jest mierzalnie lepszy od silnika produkcyjnego w trzech wymiarach:
odzysk brakujących plansz, dokładność węzłów oraz zgodność symboli po
cięciu; z bramką niepewności kierującą wątpliwe plansze do przeglądu.
Wynik trafia do aplikacji wyłącznie jako review/shadow (D-461), bez
automatycznej aktywacji.

## Zakres i reguły

- **Reguła kompletności zdjęcia (nadrzędna).** Jednostką geometrii jest
  zdjęcie źródłowe, nie plansza. Zdjęcie ma oczekiwaną liczbę plansz
  (`active_board_slots` rewizji geometrii źródła, wynikającą z zakresu
  numerów sekwencji; dla 777 zwykle 9). Dopóki każda oczekiwana plansza
  zdjęcia nie ma poprawnie oznaczonej siatki (zaakceptowanej przez silnik
  bez zastrzeżeń albo zatwierdzonej przez człowieka), **żadna** plansza
  tego zdjęcia nie jest cięta na symbole, nie trafia do weryfikacji
  symboli ani do wyszukiwarki. Zdjęcie niekompletne ma jawny stan i trafia
  do kolejki siatek całym zdjęciem. Wyjątek wymaga jawnej decyzji
  operatora dla konkretnego zdjęcia (np. plansza fizycznie poza kadrem,
  kwalifikacja częściowa D-449) i zostaje zapisany z autorem.
- **Kompletność widoczna od razu.** Każdy import i każdy przebieg silnika
  raportuje liczbę zdjęć kompletnych i niekompletnych oraz listę zdjęć z
  brakującymi albo niepewnymi siatkami, zanim zacznie się jakakolwiek
  praca na symbolach; licznik jest widoczny w panelu importu i w kolejce
  siatek.
- **Kompletność jako miara silnika.** Podstawową miarą jakości silnika
  jest odsetek zdjęć, na których wszystkie oczekiwane plansze mają
  poprawną siatkę (zdjęcie zaliczone tylko przy komplecie), obok miar
  per plansza.
- Topologia 5 × 3 (24 węzły). 3 × 3 pozostaje w labie bez zmian i poza tym
  planem.
- Dane produkcyjne czytamy tylko do odczytu, rolą właściciela, przez
  eksporter; laboratorium nie importuje `storage` ani `psycopg` (reguła
  D-447 bez zmian). Żadnych zapisów do `game_data_v2`.
- Poziomy etykiet (źródło prawdy dla kwalifikacji próbki):

  | Poziom | Źródło | Użycie |
  |---|---|---|
  | G (złoty) | ręczne siatki labu (180), rezolucje Reviewera (461), korekty `local-admin` (135) | walidacja, zbiór złoty, test; nigdy jedyne źródło treningu |
  | S (srebrny) | plansze zatwierdzone po reweryfikacji 777 (137 439) | trening i development |
  | B (brązowy) | automatyczna geometria silnika (371 806) | tylko po filtrze zgodności symboli; inaczej wyłączone |

- Filtr zgodności symboli (dla S i B): plansza kwalifikuje się, gdy
  wszystkie dostępne komórki mają decyzję człowieka albo predykcję o
  jakości ≥ progu zapisanego w manifeście przed pomiarem; próg i liczności
  raportuje zadanie danych, nie plan.
- Podział grupuje całe rodziny źródeł (job importu i katalog nagrania),
  duplikaty SHA i powiązania; walidacja Mumie, `final_test` Reels i
  `unseen_game` Treasure z D-456 pozostają nietknięte do odbioru.
- Trening wyłącznie w izolowanym środowisku GPU przez istniejący protokół
  runów (fingerprint, `requestId`, lease, checkpoint v2, budżet trwały).
- Pamięć hosta: VM WSL ma limit 8 GB; trening GPU i ciężkie operacje bazy
  nie biegną równolegle; testy sekwencyjnie.
- Audyty per zadanie są zawieszone decyzją operatora (2026-10-01); każde
  zadanie kończy się własnym przeglądem diffu, commitem, Outcome i wpisem
  w `CURRENT_STATE.md`.

## Decyzje operatora

Wszystkie pięć zaakceptowane 2026-10-01: 1 → D-480, 2 → D-481, 3 → D-482,
4 → D-483, 5 → D-484. Treść obowiązującą zawiera `DECISION_LOG.md`; poniżej
brzmienie z propozycji.

1. **Geometria produkcyjna jako dane uczące.** Zatwierdzone plansze 777
   (poziom S) i plansze po filtrze zgodności symboli (B) mogą być targetami
   treningu geometrii; poziom G służy do oceny. Zastępuje ograniczenie
   D-453 („tylko nowe ręczne siatki labu”) w zakresie treningu; bramki
   symboli i role źródeł bez zmian. Bez tej decyzji plan kończy się na
   zadaniu TASK-0800 (raport danych).
2. **Budżet treningu.** Zamiast „20 epok lub 30 minut”: na zadanie modelu
   do 3 runów, każdy do 4 godzin GPU, z góry zapisanym presetem; kolejne
   runy wymagają nowej zgody. Smoke do 50 kroków bez zmian.
3. **Kolejność etapów.** Etap D (sieć węzłów) rusza bez ukończenia C
   (symbole) — T09 nie jest warunkiem T10 dla geometrii.
4. **Metryka nadrzędna** (zamrożona przed treningiem): odsetek zdjęć
   kompletnych i poprawnych (wszystkie oczekiwane plansze z siatką w
   tolerancji) na walidacji; druga w kolejności image-macro z T05 z
   kosztem braku = 1; pomocnicze: odzysk plansz, NME p95, zgodność symboli
   po cięciu. Wybór modelu tylko na walidacji.
5. **Bramka kompletności zdjęcia w aplikacji.** Reguła z sekcji „Zakres i
   reguły” staje się wymaganiem produktu (wpis w
   `requirements/IMAGE_INGESTION.md`): cięcie i weryfikacja symboli
   dopiero dla zdjęć kompletnych. Dotyczy nowych importów i ponownych
   przebiegów; istniejące dane 777 są oceniane raportem, bez cofania
   wykonanej pracy.

## Etapy i zadania

Każdy etap wymaga jawnego uruchomienia; po etapie STOP z raportem.

### Etap V3-0 — bramka kompletności zdjęcia (pierwszy, niezależny od sieci)

- **TASK-0806 — raport kompletności i kolejka zdjęć niekompletnych
  (tylko odczyt + UI; „bez decyzji”).** Zapytanie i endpoint Admina
  zwracające per import i per gra: liczbę zdjęć, zdjęcia z kompletem
  plansz, zdjęcia z brakami (ile plansz brakuje, które pozycje, powód:
  odroczona, nierozpoznana, częściowa, bez geometrii źródła), zdjęcia z
  planszami niskiej jakości symboli (odsetek komórek ≤ 80% na planszy
  powyżej progu z konfiguracji — sygnał złej siatki z wniosków o
  symbolach). Widok w Adminie: lista zdjęć niekompletnych z podglądem
  całego zdjęcia i naniesionymi siatkami, licznik w panelu importu.
  Źródła prawdy: `image_source_geometry_revisions.active_board_slots`,
  `recognized_boards`, `image_board_geometry_pending`, stan komórek.
  Kryteria: liczby zgodne z zapytaniem kontrolnym wykonanym w tej samej
  chwili (kontrola 2026-10-01 przy starcie etapu: 56 816 zdjęć, 56 710 z
  kompletem rozpoznanych plansz, 99 bez plansz, 7 niepełnych, 4 z otwartą
  odroczoną geometrią); test PG; kontrakt pionem (OpenAPI, klient, test).
- **TASK-0807 — egzekwowanie bramki w pipeline (wymaga decyzji 5).**
  Stan zdjęcia `geometry_complete | geometry_incomplete |
  geometry_exception` (proponowany, kolumna albo tabela gry przez
  Alembic); writer importu i ręczna geometria przeliczają go w tej samej
  transakcji co zapis planszy; materializacja komórek weryfikacji,
  projekcja wyszukiwarki i przeliczanie symboli pomijają plansze zdjęć
  niekompletnych (jawny powód, nie ciche pominięcie) i dołączają je po
  skompletowaniu; kolejka siatek pracuje całymi zdjęciami; wyjątek
  operatora per zdjęcie z autorem i powodem. Zdjęcia historyczne dostają
  stan z backfillu bez cofania materializacji (raport rozbieżności).
  Kryteria: test PG — import zdjęcia z 8/9 siatek nie tworzy żadnej
  komórki weryfikacji; po dorysowaniu dziewiątej wszystkie 135 komórek
  pojawia się jedną operacją; wyjątek dopuszcza 8/9; brak regresji dla
  zdjęć kompletnych. **STOP V3-0:** raport kompletności 777 i działająca
  bramka.

### Etap V3-A — dane (bez treningu)

- **TASK-0800 — inwentaryzacja i eksport geometrii produkcyjnej (tylko
  odczyt; „bez decyzji”).** Rozszerzenie `scripts/vision_lab_export.py` o
  tryb geometrii: dla 777 czyta zdjęcia źródłowe, bieżącą geometrię
  źródła i plansz, zatwierdzenia, autora rewizji, kwalifikację częściową,
  manifest renderu (24 węzły wyliczane z quada i topologii — proponowane
  `vision_lab/production_geometry.py`), stan komórek (decyzja, jakość
  predykcji). Wynik: manifest kandydatów z poziomem G/S/B, rodziną źródła,
  SHA zdjęcia, metrykami trudności (skrajna kolumna, plansza częściowa,
  liczba plansz na zdjęciu, niski kontrast) oraz raport liczności per
  poziom, rodzina i trudność. Bez kopiowania obrazów, bez zapisu do bazy.
  Kryteria: liczności zgodne z zapytaniami kontrolnymi (510 416 plansz,
  138 186 zatwierdzonych); krótkie transakcje `REPEATABLE READ READ ONLY`;
  test na bazie `*_test`. Błąd integralności (brak manifestu, niezgodne
  SHA) oznacza próbkę jako wykluczoną z powodem, nie przerywa eksportu.
- **TASK-0801 — snapshot treningowy, filtr zgodności i zamrożony podział
  (wymaga decyzji 1 i 4).** Losowanie warstwowe z manifestu TASK-0800:
  proponowane 6 000 zdjęć treningowych (S + B po filtrze), 600 development,
  cały poziom G jako zbiór złoty; kopia zarządzanych obrazów do katalogu
  labu z kontrolą SHA (ok. 2 GB), publikacja atomowa jak w T01. Polityka
  podziału `production-geometry-split-v1` (nowa, obok istniejących):
  rodzina = job importu + katalog nagrania, komponenty przecieku po SHA i
  powiązaniach z pełnego katalogu, zbiór złoty wyznaczany pierwszy i
  wyłączony z treningu, holdouty D-456 bez zmian. Kontrola jakości
  etykiet: galeria 300 losowych plansz S i 300 B w UI labu (istniejący
  szybki przegląd zdjęcia) — operator oznacza błędne; odsetek błędów
  wchodzi do raportu. **STOP V3-A:** raport danych, odsetek błędów
  etykiet, zamrożony manifest i podział.

### Etap V3-B — model i bramka

- **TASK-0802 — `neural_grid`: sieć widząca cały ekran (wymaga decyzji 2
  i 3; realizuje T10 / TASK-0675 dla 5 × 3).** Dwa stopnie pod jednym
  `GeometryEngine`:
  1. *Ekran:* zdjęcie zmniejszone (dłuższy bok 768 px), wspólny szkielet
     `MobileNetV3-Large` z głowicą map ciepła narożników i środków plansz
     (bez założenia 9 plansz; obecność wynika z detekcji), dekodowanie do
     quadów.
  2. *Plansza:* wycinek wokół quada z marginesem 15% (320 px), głowica 24
     map węzłów + maska widoczności komórek (plansze częściowe z
     kwalifikacji), dopasowanie siatki projekcyjnej do węzłów z odrzuceniem
     odstających.
  Augmentacje: perspektywa, rozmycie, odblask, zasłonięcie prostokątem i
  „ręką”, zmiana barwy. Trening i eksport ONNX w protokole runów; parity
  PyTorch–ONNX jak w T05. Preset i fingerprint zapisane przed pierwszym
  runem. Kryteria: ten sam kontrakt i odbiorcy co `baseline`/`hybrid`;
  smoke; do 3 runów; raport per run z metryką nadrzędną i pomocniczymi na
  development i walidacji; brak dotknięcia holdoutów.
- **TASK-0803 — `hybrid_v3`: bramka zgodności dwóch silników.** Silnik
  łączy wynik produkcyjny (`baseline`) i `neural_grid`: plansza „pewna”,
  gdy oba dają quady o IoU ≥ progu i węzły w tolerancji; plansza tylko z
  sieci (odzysk) albo niezgodna → `needs_review` z powodem; wybór węzłów
  przy zgodzie według reguły zapisanej przed pomiarem (proponowane: węzły
  sieci, gdy dopasowanie siatki ma resztę < progu, inaczej produkcyjne).
  Kalibracja progów wyłącznie na walidacji; raport krzywej pokrycie–błąd.
  Kryteria: brak cichych odrzuceń (każda plansza ma wynik albo powód),
  test zamiany silnika bez zmiany odbiorcy, ONNX na CPU.

### Etap V3-C — ocena i STOP

- **TASK-0804 — raport porównawczy i rekomendacja.** Na zamrożonej
  walidacji, zbiorze złotym i development: metryka nadrzędna, odzysk
  plansz, NME mediana/p95, zgodność symboli po cięciu (crop z siatki
  kandydata klasyfikowany biblioteką wzorców i porównany z decyzją
  człowieka), taksonomia błędów (ręka, odblask, skrajna kolumna, przeskok
  okresu, plansza częściowa), koszt czasu na zdjęcie (CPU ONNX). Trzy
  silniki: produkcyjny, `neural_grid`, `hybrid_v3`. Dopiero po zamrożeniu
  modelu i progów jednorazowy odczyt `final_test` i `unseen_game`.
  **STOP V3-C:** raport w `ai_docs/quality/` i rekomendacja: promować do
  shadow, zbierać dane (konkretna lista braków) albo zakończyć.

### Etap V3-D — shadow w aplikacji (osobne uruchomienie po STOP V3-C)

- **TASK-0805 — integracja review/shadow 5 × 3.** Zakres T11 (TASK-0676)
  z doprecyzowaniem D-461: kandydat liczony równolegle dla tego samego SHA
  zdjęcia 777, wynik i wersja zapisane osobno (proponowana tabela gry
  `image_geometry_shadow_results` przez Alembic i manifest magazynu v5),
  bez nadpisania geometrii produkcyjnej i decyzji człowieka; widok
  porównawczy w Adminie. Przed masowym przetwarzaniem obowiązuje brama
  skali z planu Vision Lab. Szczegółowy kontrakt powstaje po STOP V3-C;
  ten wiersz rezerwuje zakres, nie upoważnia do wykonania.

## Błędy i przypadki brzegowe

| Sytuacja | Zasięg | Reakcja |
|---|---|---|
| Zdjęcie bez pliku albo z innym SHA | próbka | wykluczona z powodem w manifeście; eksport trwa |
| Plansza bez manifestu renderu przy dostępnych komórkach | próbka | wykluczona; licznik w raporcie |
| Rodzina przecinająca podział | manifest | odmowa zamrożenia; błąd z listą |
| Run przerwany | run | wznowienie z checkpointu v2; budżet nie wraca |
| Zdjęcie ma mniej poprawnych siatek niż oczekiwanych plansz | zdjęcie | stan `geometry_incomplete`; żadna plansza zdjęcia nie idzie do symboli; kolejka siatek |
| Plansza fizycznie poza kadrem albo częściowa | zdjęcie | wyjątek operatora per zdjęcie (`geometry_exception`) z autorem; dopiero wtedy cięcie dostępnych plansz |
| Sieć nie zwraca planszy, którą ma produkcja | plansza | wynik produkcyjny + `needs_review` z powodem |
| Sieć zwraca planszę bez odpowiednika | plansza | `needs_review`, nigdy „pewna” |
| Brak GPU | etap B | stop z komunikatem; bez treningu na CPU |

## Mapa wymaganie → zadanie → kryterium

| Wymaganie | Zadania | Kryterium |
|---|---|---|
| Brak cięcia na symbole, dopóki zdjęcie nie ma kompletu siatek | TASK-0806, 0807 | test PG 8/9 → 0 komórek; raport zdjęć niekompletnych zaraz po imporcie |
| Błędy siatek widoczne wcześnie, na świeżych przykładach | TASK-0806 | licznik i lista w panelu importu; sygnał niskiej jakości symboli per plansza |
| Silnik widzi planszę zamiast wnioskować z sąsiadów | TASK-0802 | odzysk plansz i odsetek zdjęć kompletnych na walidacji > baseline |
| Odporność na rękę, odblask, przechył, okresowość | TASK-0802, 0804 | taksonomia błędów per kategoria |
| Hybryda zamiast zastąpienia | TASK-0803 | krzywa pokrycie–błąd, powody `needs_review` |
| Dane wybiera i kontroluje operator | TASK-0801 | przegląd 600 plansz, odsetek błędów etykiet |
| Brak przecieku i nietknięte holdouty | TASK-0801, 0804 | test rozłączności rodzin; jeden odczyt holdoutów |
| Bez wpływu na produkcję | wszystkie | tylko odczyt bazy; shadow dopiero w V3-D |

## Odbiór całego przepływu

Po STOP V3-C: raport porównawczy, ONNX kandydata z parity, galeria labu
pokazuje trzy silniki na tym samym zdjęciu, testy i kontrakt OpenAPI labu
w `quality`, zamrożone manifesty i podział odtwarzalne z checksum, brak
zmian w `game_data_v2`.

## Ryzyka

- Bramka kompletności wstrzymuje symbole dla całego zdjęcia przez jedną
  trudną planszę; łagodzi to wyjątek operatora per zdjęcie i kolejka
  siatek pracująca zdjęciami — koszt jest świadomy i mniejszy niż późne
  wykrycie braków.
- Etykiety S pochodzą z hybrydy i mogą powielać jej błędy (wspólny
  przechył kolumny); łagodzi to filtr zgodności symboli i pomiar na
  poziomie G — odsetek błędów z przeglądu TASK-0801 rozstrzyga, czy S
  nadaje się do treningu.
- Zbiór złoty jest mały (776 plansz) i skupiony na trudnych przypadkach;
  raport podaje przedziały ufności.
- Inne gry mają tylko siatki labu (150); przewaga na 777 nie dowodzi
  uogólnienia — walidacja Mumie i `unseen_game` to mierzą.
- Trening wielogodzinny konkuruje o pamięć z bazą; okno bez ciężkich
  operacji bazy.

## Zakres wyłączony

Symbole (etap C, T06b–T09, T12), topologia 3 × 3 w aplikacji, aktywacja
produkcyjna i masowe przetwarzanie v3, zmiany `game_data_v2` poza V3-D,
push/merge poza gałęzią integracyjną, usuwanie v1.1.

## Przypisanie modeli do zadań

Dostępność potwierdzona w bieżącym środowisku (Fable 5.1, Opus 5.5,
Sonnet 5.5, Haiku 4.5). Kolumna review opisuje konfigurację na wypadek
wznowienia audytów; obecnie audyty są zawieszone decyzją operatora.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0806 | claude-sonnet-5-5 | high | Raport i widok tylko do odczytu na istniejących tabelach; kontrakt pionem. | Zawieszony; przy wznowieniu claude-opus-5-5, medium |
| TASK-0807 | claude-opus-5-5 | high | Zmiana przepływu importu i materializacji komórek, migracja stanu zdjęcia, backfill. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0800 | claude-sonnet-5-5 | high | Eksport tylko do odczytu według istniejącego wzorca; ryzyko ograniczone do poprawności liczności. | Zawieszony; przy wznowieniu claude-opus-5-5, medium |
| TASK-0801 | claude-opus-5-5 | high | Polityka podziału, przeciek rodzin i filtr jakości etykiet decydują o wiarygodności całego wyniku. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0802 | claude-opus-5-5 | high | Architektura dwóch stopni, trening, ONNX i kontrakt silnika. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0803 | claude-opus-5-5 | high | Reguły bramki i kalibracja bez przecieku z walidacji do testu. | Zawieszony; przy wznowieniu claude-opus-5-5, medium |
| TASK-0804 | claude-opus-5-5 | high | Ocena dowodów, jednorazowy odczyt holdoutów, rekomendacja. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0805 | claude-opus-5-5 | high | Zmiana schematu i przepływu produkcyjnego w trybie shadow; kontrakt po STOP V3-C. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
