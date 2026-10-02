---
title: TASK-0800 — inwentaryzacja i eksport geometrii produkcyjnej 777 (tylko odczyt)
status: done
last_updated: 2026-10-02
---

# TASK-0800 — inwentaryzacja i eksport geometrii produkcyjnej 777

## Status

`done` (poza commitem i wpisem w `CURRENT_STATE.md`, które należą do orkiestratora)

## Goal

Eksporter tylko do odczytu zapisuje dla gry 777 manifest kandydatów
treningowych geometrii (zdjęcie → plansze → 24 węzły siatki 5 × 3, poziom
etykiety G/S/B, rodzina źródła, metryki trudności) oraz raport liczności,
zgodny z zapytaniami kontrolnymi, bez kopiowania obrazów i bez zapisu do
bazy.

## Context

Etap V3-A planu `GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (D-480: zatwierdzona
geometria produkcyjna 777 może być danymi uczącymi; poziom G służy do
oceny). T05 uczył się z 90 siatek; w produkcji jest ok. 138 tys. plansz z
zatwierdzoną geometrią. To zadanie tylko inwentaryzuje i opisuje dane —
wybór próbek, kopia obrazów i podział to TASK-0801.

## Dependencies / entry conditions

- Fakt: etap V3-0 wdrożony (`v1.7.149`), head Alembic `0139`; zdjęcia mają
  trwały stan `geometry_completeness_status`. Stan 777: 56 812 zdjęć, 55 499
  `geometry_complete`, 60 `geometry_incomplete`, 1 253 poza bramką
  (zastąpione nowszym importem).
- Fakt: istnieje eksporter `scripts/vision_lab_export.py` (D-447: tylko
  odczyt, rola właściciela, laboratorium nie importuje `storage` ani
  `psycopg`) i przewodnik `ai_docs/guides/VISION_LAB_EXPORT.md`.
- Fakt: reguła izolacji per gra — każde zapytanie filtruje po `game_id` i
  działa po związaniu gry.

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`. Eksport tylko do odczytu według
istniejącego wzorca; ryzyko ograniczone do poprawności liczności i
wyliczenia węzłów. Eskalacja do `claude-opus-5-5` `high`, jeżeli 24 węzłów
nie da się wyliczyć jednoznacznie z zapisanej geometrii albo liczności nie
zgadzają się z kontrolą. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (sekcje „Zakres i
  reguły”, etap V3-A, tabela poziomów etykiet)
- `ai_docs/process/DECISION_LOG.md` (D-480, D-484, D-485, D-447, D-456)
- `ai_docs/guides/VISION_LAB_EXPORT.md`
- `ai_docs/architecture/VISION_LAB.md` (kontrakty, izolacja)
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md` (role, wiązanie gry)

## Scope

- Tryb geometrii w `scripts/vision_lab_export.py` (albo osobny skrypt obok,
  jeżeli istniejący eksporter ma niezgodny kontrakt wyjścia — rozstrzygnij
  po przeczytaniu kodu i opisz).
- Czysty moduł wyliczający 24 węzły siatki 5 × 3 z zapisanej geometrii
  planszy (proponowane `vision_lab/production_geometry.py`, bez importu
  `storage`/`psycopg`).
- Manifest kandydatów i raport liczności w katalogu danych labu.
- Test jednostkowy węzłów i test PG eksportu na bazie `*_test`.
- Raport `ai_docs/quality/` z licznościami i uzupełnienie przewodnika.

## Out of scope

- Kopiowanie obrazów, losowanie próbek, podział, filtr zgodności symboli
  jako bramka (TASK-0801) — tu tylko zapis sygnałów potrzebnych filtrowi.
- Trening, zmiany w labie poza modułem węzłów, zapis do bazy, migracje.
- Inne gry niż wskazana parametrem (domyślnie 777).

## Acceptance criteria

- [x] Eksport działa w transakcjach `REPEATABLE READ READ ONLY`, partiami,
      wznawialnie; nie wykonuje żadnego zapisu do bazy.
- [x] Manifest zawiera każdą żywą planszę zdjęć `geometry_complete` gry z
      polami wymienionymi w „Technical notes”; plansze i zdjęcia wykluczone
      mają powód i licznik, eksport się na nich nie zatrzymuje.
- [x] Liczności raportu zgadzają się z niezależnymi zapytaniami kontrolnymi
      wykonanymi w tej samej chwili (zapytania i wyniki w `Outcome`).
- [x] 24 węzły wyliczone z geometrii planszy odtwarzają 15 quadów komórek z
      manifestu renderu z dokładnością opisaną w teście; plansze, dla
      których to nie zachodzi, są wykluczone z powodem.
- [x] Laboratorium nadal nie importuje `storage` ani `psycopg` (istniejący
      test izolacji przechodzi).
- [x] Raport w `ai_docs/quality/` i wpis w `VISION_LAB_EXPORT.md`.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

### Zakres danych

Jednostką jest zdjęcie (D-484). Do manifestu wchodzą zdjęcia gry o stanie
`geometry_complete`; zdjęcia `geometry_incomplete`, `geometry_exception` i
poza bramką są liczone w raporcie i pomijane z powodem. Plansze `rejected`
nie są kandydatami.

### Poziom etykiety (źródło prawdy: tabela w planie)

| Poziom | Warunek |
|---|---|
| G | geometria planszy zatwierdzona, a rewizję zapisał człowiek: Reviewer (`reviewer-operator`) albo `local-admin` |
| S | geometria zatwierdzona po reweryfikacji `system:grid-reverify-777-v1` (i inne zatwierdzenia systemowe — wypisz aktorów z danych i sklasyfikuj jawnie; nieznany aktor → osobna kategoria w raporcie, nie zgadywanie) |
| B | automatyczna geometria silnika zaakceptowana bez zatwierdzenia człowieka |

Ustal z danych (tylko `SELECT`), które kolumny niosą autora zatwierdzenia i
rewizji (`geometry_approved_by`, autor rewizji geometrii planszy i źródła),
i opisz regułę w `Outcome` z licznościami. Kontrola z 2026-10-01: ok.
138 186 zatwierdzonych plansz (137 439 reweryfikacja, 461 Reviewer, 135
`local-admin`), ok. 370 tys. automatycznych.

### Pola wiersza manifestu (JSON Lines, jeden wiersz na planszę)

Identyfikatory (gra, zdjęcie, plansza, import), `checksum_sha256` i ścieżka
względna zdjęcia, wymiary zorientowane, pozycja na zdjęciu, numer
sekwencji, liczba oczekiwanych plansz zdjęcia, poziom G/S/B, aktor
zatwierdzenia, silnik i wersja geometrii, quad planszy i 24 węzły w
pikselach zdjęcia (`exif-normalized-rgb-pixels-v1`), kwalifikacja częściowa
(maska niedostępnych komórek), rodzina źródła (job importu + katalog
nagrania z nazwy/ścieżki pliku importu — ustal z danych, jak rozpoznać
nagranie, i opisz), sygnały dla filtra symboli (liczba komórek z decyzją
człowieka, liczba komórek z predykcją ≤ 0,80, minimalna jakość predykcji —
ta sama definicja co w raporcie kompletności TASK-0806), metryki trudności
(skrajna kolumna/wiersz na ekranie, plansza częściowa, liczba plansz na
zdjęciu, pole i skośność quada). Metryka „niski kontrast” wymaga pikseli —
poza tym zadaniem; odnotuj jako pole do uzupełnienia w TASK-0801.

### Wydajność i izolacja

510 tys. plansz i 7,5 mln komórek: agregaty komórek licz w SQL per plansza
partiami po zdjęciach (kursor po `id` zdjęcia), bez wczytywania komórek do
Pythona. Nie uruchamiaj eksportu równolegle z testami PG (limit 8 GB VM).
Zmierz czas pełnego eksportu i wpisz do `Outcome`.

### Niedozwolone skróty

- Żadnych zapisów do bazy ani tabel tymczasowych w bazie deweloperskiej.
- Nie zgaduj węzłów: jeżeli geometria planszy nie pozwala wyliczyć 24
  węzłów zgodnych z manifestem renderu, plansza jest wykluczona z powodem.
- Błąd integralności pojedynczej próbki nie przerywa eksportu.

## Expected files

- Istniejące: `scripts/vision_lab_export.py`, `package.json` (wpis npm, jeśli
  wzorzec tego wymaga), `ai_docs/guides/VISION_LAB_EXPORT.md`.
- Nowe (proponowane):
  `services/worker/src/game_predictor_worker/vision_lab/production_geometry.py`,
  testy w `services/worker/tests/` i `services/api/tests/integration/`,
  `ai_docs/quality/GRID_V3_PRODUCTION_GEOMETRY_INVENTORY_20261002.md`.

## Test cases

- Węzły: prostokąt, quad perspektywiczny, plansza częściowa; zgodność z 15
  quadami komórek; quad zdegenerowany → wykluczenie.
- Eksport PG: zdjęcie kompletne z planszami G, S i B; zdjęcie niekompletne
  pominięte z powodem; plansza `rejected` pominięta; wznowienie po
  przerwaniu nie dubluje wierszy; druga gra nie przecieka.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "production_geometry or vision_lab_isolation"
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/<nowy plik> -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check services scripts
```

Limit 120 s (test PG 300 s; pełny eksport na bazie deweloperskiej do 900 s,
uruchamiany raz, sam). Testy są planowane.

## Risks / open questions

- Etykiety S pochodzą z hybrydowej reweryfikacji i mogą powielać jej błędy;
  to zadanie tylko je liczy, ocena należy do TASK-0801.
- Rozpoznanie „katalogu nagrania” może nie być możliwe z samych danych
  importu; wtedy rodzina = job importu i jest to zapisane jako ograniczenie.

## Outcome

Wypełnia agent po pracy.

### Changed

- Nowe: `services/worker/src/game_predictor_worker/vision_lab/production_geometry.py`
  (czysta derywacja 24 węzłów, zgodność z manifestem renderu, metryki trudności,
  reguła poziomu G/S/B/U; bez importu `storage`/`psycopg`),
  `scripts/vision_lab_geometry_export.py` (eksport tylko do odczytu),
  `services/worker/tests/test_production_geometry.py` (29 testów),
  `services/api/tests/integration/test_vision_lab_geometry_export_postgres.py` (4 testy),
  `ai_docs/quality/GRID_V3_PRODUCTION_GEOMETRY_INVENTORY_20261002.md`.
- Zmienione: `ai_docs/guides/VISION_LAB_EXPORT.md` (sekcja „Eksport geometrii
  produkcyjnej”), niniejszy plik zadania.
- Wynik eksportu (poza repozytorium):
  `C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry\production-geometry-777-20261002\`
  (`candidates.jsonl` 1 587 136 303 B, 499 460 wierszy; `exclusions.jsonl` pusty;
  `report.json`; `export_manifest.json`; `image_ids.txt`; `progress.json`).
- Rozstrzygnięcie zakresu: osobny skrypt zamiast trybu w `vision_lab_export.py`, bo
  tamten eksporter ma niezgodny kontrakt (manifest wejściowy do 1000 źródeł, zamrożona
  tożsamość wierszy, kopie obrazów); nowy skrypt importuje z niego tylko
  `_read_transaction`, więc rola właściciela, wiązanie gry i przypięcie generacji są
  te same. Bez wpisu npm (stary eksporter go nie ma).
- Przyjęte założenia: (1) „zatwierdzona” = `approved_geometry_revision =
  geometry_revision`; (2) 261 plansz z geometrią zapisaną przez `reviewer-operator` i
  przeniesioną konwersją legacy (bez zapisu zatwierdzenia) to poziom G z osobną
  podstawą `human_saved_revision_via_legacy_conversion`; (3) 36 zatwierdzeń
  `system:import-qualified-manual-geometry` to poziom S z jawną podstawą; (4) 425
  plansz ręcznej geometrii źródła z konwersji legacy bez autora to poziom `U`
  (niesklasyfikowane); (5) rodzina = katalog wyboru z zadania importu, bo obrazy są
  adresowane treścią i nazwa nagrania nie jest zapisana.

### Verification results

- `pytest services/worker/tests -k "production_geometry or vision_lab_isolation or no_production_storage_imports"`:
  30 passed (29 testów węzłów i poziomów + istniejący test izolacji laboratorium
  `test_lab_has_no_production_storage_imports`; nazwa „vision_lab_isolation” z zadania
  nie istnieje, test izolacji nazywa się inaczej); `test_vision_lab_export.py`:
  11 passed (bez zmian).
- `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest services/api/tests/integration/test_vision_lab_geometry_export_postgres.py`:
  4 passed w ok. 10 s (poziomy G/S/B/U i aktorzy, wykluczenia z powodem, uzgodnienie
  kandydaci + wykluczone = żywe plansze zdjęć kompletnych, zdjęcie niekompletne i
  poza bramką pominięte, plansza `rejected` pominięta, druga gra nie przecieka,
  wznowienie po przerwaniu i po „urwanym” zapisie nie dubluje wierszy, zapis w
  transakcji eksportu jest odrzucony, liczniki tabel bez zmian).
- `ruff format --check` i `ruff check` zmienionych plików: czyste; `ruff check services
  scripts`: 1 wcześniejsze E501 w `services/worker/tests/test_page_geometry_preflight.py`
  (poza zakresem). `mypy --strict` na dwóch nowych plikach: brak błędów w nich (27
  wcześniejszych błędów w innych plikach).
- Pełny eksport na bazie deweloperskiej (jednorazowo): 489,9 s pracy, 8 min 14 s
  łącznie, 555 partii po 100 zdjęć, 4 wątki odczytu, `SHOW transaction_read_only = on`,
  0 wykluczeń, 0 wznowień, 499 460 kandydatów na 55 499 zdjęciach.
- Zapytania kontrolne (niezależny SQL) wykonane o 09:08:53–09:09:15 UTC, zaraz po
  eksporcie (09:08:47): wszystkie liczności zgodne co do jednej planszy.

| Wielkość | Eksport | Kontrola SQL |
|---|---|---|
| Zdjęcia `geometry_complete` / `geometry_incomplete` / poza bramką | 55 499 / 60 / 1 253 | 55 499 / 60 / 1 253 |
| Żywe plansze na zdjęciach `geometry_complete` | 499 460 | 499 460 |
| Poziom B / G / S / U | 361 103 / 459 / 137 473 / 425 | 361 103 / 459 / 137 473 / 425 |
| Zdjęcia z planszą B / G / S / U | 40 123 / 101 / 15 275 / 76 | 40 123 / 101 / 15 275 / 76 |
| `system:grid-reverify-777-v1` / `local-admin` / `system:import-qualified-manual-geometry` | 137 437 / 198 / 36 | 137 437 / 198 / 36 |
| `reviewer-operator` (rewizja przeniesiona konwersją legacy) | 261 | 261 |
| Plansze `rejected` (łącznie / na zdjęciach kompletnych) | 10 390 / 4 | 10 390 / 4 |
| Plansze częściowe w manifeście | 0 | 0 |
| Rodziny / zadania importu | 24 / 25 | 24 / 25 |
| Plansz na zdjęciu 9 / 8 / 7 / 5 / 2 / 1 | 55 492 / 2 / 1 / 1 / 1 / 2 | 55 492 / 2 / 1 / 1 / 1 / 2 |
| B bez komórki ≤ 0,80 / G / S / U | 358 123 / 401 / 133 475 / 414 | 358 123 / 401 / 133 475 / 414 |

  Weryfikacja węzłów: odchyłka od manifestu renderu 0,0 px w każdym wierszu (ta sama
  funkcja projekcyjna co renderer), 600 losowych wierszy po zapisie do pliku (węzły
  zaokrąglone do 4 miejsc) zgadza się z manifestami w bazie do 7,0e-5 px; test
  jednostkowy porównuje z niezależną homografią OpenCV.

### Not completed

- Commit, wpis w `CURRENT_STATE.md` i przeniesienie pliku do `completed/` — zgodnie z
  poleceniem należą do orkiestratora.
- Metryka „niski kontrast” — wymaga pikseli; pole do uzupełnienia w TASK-0801.
- Ścieżki wykluczeń i plansz częściowych nie wystąpiły w danych produkcyjnych (0
  wykluczeń, 0 plansz częściowych w zdjęciach kompletnych); pokrywają je tylko testy.
- Katalog nagrania w sensie pojedynczego pliku wideo nie jest rozpoznawalny z danych
  importu (obrazy adresowane treścią); rodzina = katalog wyboru z zadania importu.
- Poziom G jest niejednorodny (261 z 459 plansz bez zapisu zatwierdzenia), a 425
  plansz `U` nie ma ustalonego autora — decyzja o ich użyciu należy do TASK-0801.
- W drzewie roboczym worktree jest 180 zmodyfikowanych plików
  `ai_docs/quality/*.json` (różnice końców linii) niezwiązanych z tym zadaniem; nie
  zostały zmienione ani przygotowane.

### Documentation updates

- `ai_docs/guides/VISION_LAB_EXPORT.md`: sekcja „Eksport geometrii produkcyjnej
  (TASK-0800)” (polecenie, parametry, wznawianie, pliki wyniku, reguły węzłów,
  rodziny i sygnałów).
- `ai_docs/quality/GRID_V3_PRODUCTION_GEOMETRY_INVENTORY_20261002.md`: raport liczności
  z uzgodnieniem z zapytaniami kontrolnymi, regułą poziomów, rozkładami i wnioskami
  dla TASK-0801.
- `CURRENT_STATE.md` i `DECISION_LOG.md` nie zostały zmienione (polecenie
  orkiestratora); zmiana nie zmienia modelu domenowego.

### Recommended next task

- TASK-0801 (snapshot treningowy, filtr zgodności i podział) na podstawie
  `candidates.jsonl`: ustalić próg filtra przed pomiarem, zdecydować o statusie
  podstaw `human_saved_revision_via_legacy_conversion` (261 G) i `U` (425), zbiór
  złoty zbudować z 22 zdjęć w całości G i pozostałych 79, a podział oprzeć na 24
  rodzinach i 2 parach zdjęć o tym samym SHA.
