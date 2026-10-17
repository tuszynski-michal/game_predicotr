# Audyt TASK-1044 - Migracja `source_image_crops` i kwalifikacja blobów

Werdykt: REVISE  
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`  
Wykonawca: `claude-opus-5-5`, reasoning `high` — według briefu  
Zakres: HEAD...415b093d79b7fb2fb71949b73509d1d29b1fc965 oraz zmiany niezacommitowane TASK-1044, data 2026-10-17  
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono migrację, manifest v18, ORM, repozytorium, klasyfikator, zbieranie geometrii oraz testy względem R1, R5, R6 i kolektora P1. Kwalifikacja pomija aktywne joby poza importem oraz może ukryć brak geometrii jednej planszy przez geometrię pozostałych. Brakuje wymaganego raportu porównawczego dla 40 źródeł, a część wymaganych testów PostgreSQL zastąpiono testami klasyfikatora.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/source_image_crop_repository.py:85` — zapytanie sprawdza wyłącznie status joba importu wskazanego przez `s.import_job_id`. Nie wykrywa innych aktywnych jobów odwołujących się do tego źródła lub importu. Zakończony import z trwającym ponownym przetwarzaniem może więc otrzymać `eligible=True`, wbrew R5. Odłożenie kontroli do etapu B, zapisane w `ai_docs/tasks/1044-source-image-crops-table-and-eligibility.md:156`, nie realizuje obecnego kontraktu kwalifikacji. Należy sprawdzać powiązane aktywne joby i zwracać jawny powód wykluczenia; nierozstrzygalne powiązanie powinno blokować kwalifikację.

- [P0-2] `services/api/src/game_predictor_api/storage/source_image_crop_repository.py:182` oraz `services/api/src/game_predictor_api/domain/source_crop_eligibility.py:126` — dokumenty geometrii są łączone dla całego bloba, a brak quadów sprawdzany dopiero po połączeniu. Przy dwóch planszach, z których jedna ma quady, a druga puste dokumenty i brak manifestu, blob może zostać zakwalifikowany z obszarem chroniącym tylko pierwszą planszę. Same statusy kompletności i zatwierdzenia nie sprawdzają zawartości tych dokumentów. Kolektor P1 odrzucał źródło przy braku quadów dowolnej planszy (`D:/game_predicotr/artifacts/photo-crop-preview-20261014/collect_preview_sources.py:183`). Należy zachować identyfikatory źródeł i plansz, sprawdzić geometrię każdej aktywnej planszy, a dopiero potem obliczać sumę quadów.

- [P0-3] `ai_docs/tasks/1044-source-image-crops-table-and-eligibility.md:132` — zamiast wymaganego porównania wyników dla 40 źródeł przedstawiono mapowanie warunków i przeniesiono sprawdzenie na TASK-1050. Nie spełnia to kryterium planu wymagającego raportu zgodności z manifestem P1 z wyjaśnieniem różnic. Artefakt istnieje w `D:/game_predicotr/artifacts/photo-crop-preview-20261014/manifest.json`. Należy przygotować porównanie na zapisanych danych, bez dostępu do bazy operatora; brakujących faktów nie wolno zastępować założeniem kwalifikacji.

### P1

- [P1-1] `ai_docs/tasks/1044-source-image-crops-table-and-eligibility.md:56` oraz `services/api/tests/integration/test_source_image_crops_postgres.py:345` — zmieniono kryterium akceptacji, usuwając wymóg integracyjnego sprawdzenia `grid_issue`, wykluczenia strony, aktywnego joba i niekompletnej geometrii. Test PostgreSQL nie tworzy takich przypadków; nie tworzy również oczekującej propozycji. Ustawienie liczników w `CropSourceFacts` sprawdza klasyfikator, lecz nie poprawność filtrów i powiązań SQL. Samo wykonanie podzapytań na pustych tabelach tego nie zastępuje. Należy przywrócić wymagane kryterium i dodać rzeczywiste rekordy oraz asercje wykluczenia w testach integracyjnych.

### P2

- [P2-1] `services/api/alembic/versions/0167_source_image_crops.py:102` — CHECK pudełek nie wyklucza elementów `NULL`, nie sprawdza porządku granic `protected_box`, a dla `raw_crop_box` sprawdza jedynie liczbę elementów. Przykładowo czteroelementowa tablica z samymi `NULL` może przejść CHECK przez wynik SQL `UNKNOWN`. Walidacja `SourceCropAttestation` ogranicza ryzyko przy obecnym zapisie przez repozytorium, ale baza nie zapewnia deklarowanej integralności samodzielnie. Zalecane są ograniczenia wymiarów i indeksów tablic, braków wartości oraz poprawności granic, wraz z testami negatywnymi.

- [P2-2] `services/api/src/game_predictor_api/storage/source_image_crop_repository.py:152` oraz `services/api/src/game_predictor_api/storage/source_image_crop_repository.py:181` — fakty i geometria pochodzą z osobnych zapytań, bez wymogu wspólnej migawki transakcyjnej. Przy `READ COMMITTED` zatwierdzona geometria może zmienić się między odczytami, dając wynik złożony ze starych warunków kwalifikacji i nowej geometrii. Należy zapewnić spójną migawkę albo jawnie wymagać jej od wywołującego. Ryzyko można odnotować tylko z wyraźnym kontraktem późniejszej ponownej kontroli pod blokadą.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Upgrade/downgrade na `*_test`, ograniczenia R1 | niezweryfikowane | Test istnieje: `services/api/tests/integration/test_source_image_crops_postgres.py:251`; wynik wykonania pochodzi wyłącznie z deklaracji wykonawcy. Ograniczenia pudełek: P2-1. |
| Kwalifikacja wszystkich źródeł współdzielonego bloba zgodnie z R5 | niespełnione | `services/api/src/game_predictor_api/storage/source_image_crop_repository.py:85`; brak kontroli innych aktywnych jobów — P0-1. |
| Wymagane scenariusze PostgreSQL | niespełnione | `services/api/tests/integration/test_source_image_crops_postgres.py:345`; braki opisane w P1-1. |
| Ochrona narożników, komórek, padded quadów i etykiet sekwencji | niespełnione | Obsługiwane klucze: `services/api/src/game_predictor_api/domain/source_crop.py:124`; brak kontroli kompletności per plansza — P0-2. |
| Raport zgodności dla 40 źródeł P1 | niespełnione | `ai_docs/tasks/1044-source-image-crops-table-and-eligibility.md:132`; P0-3. |
| Lint, mypy i testy zmienionego pionu | niezweryfikowane | `ai_docs/tasks/1044-source-image-crops-table-and-eligibility.md:137` zawiera deklaracje testów i Ruff; nie zawiera wyniku mypy. Kontroli nie uruchamiano. |

## Listy zamknięte i otwarte

Zamknięte: Brak. Runda 1.

Otwarte: P0-1, P0-2, P0-3, P1-1, P2-1, P2-2.

## Proponowane testy

- W `services/api/tests/integration/test_source_image_crops_postgres.py` dodać zakończony import z osobnym aktywnym jobem, rzeczywisty `grid_issue`, wykluczenie strony, oczekującą propozycję i niekompletną geometrię. Sprawdzić również wpływ drugiej gry współdzielącej blob.
- W tym samym pliku dodać dwie plansze, z których tylko jedna ma quady, oraz negatywne przypadki ograniczeń tablic. Dla spójności odczytu dodać scenariusz zmiany rewizji między zapytaniami.
- Uruchomić powyższe wyłącznie na dedykowanych bazach `*_test`: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`, następnie `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_source_image_crops_postgres.py`.
- Po poprawkach uruchomić testy domenowe: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_crop_eligibility.py services/api/tests/test_source_crop.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, dokumenty startowe, task, odpowiednie fragmenty planu, D-562 i D-484, dokumentację modelu danych oraz pliki implementacji i testów wskazane w briefie. Sprawdzono także powiązane zmiany importów manifestu, modele używane przez SQL, zapis etykiet sekwencji, kolektor P1 i fragment manifestu P1 z głównego checkoutu.

Nie uruchamiano testów, migracji, usług ani zapytań do bazy. Nie potwierdzono deklarowanych wyników wykonania ani pełnej zgodności 40 źródeł. Nie zmieniono, nie utworzono ani nie usunięto żadnego pliku.