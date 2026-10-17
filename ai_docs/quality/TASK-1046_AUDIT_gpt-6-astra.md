# Audyt TASK-1046 - Crop-aware source frame in the API, serving and gates

Werdykt: REVISE
Audytor: Codex, gpt-6-astra / medium (oznaczenie według briefu)
Wykonawca: claude-opus-5-5 / high
Zakres: HEAD...279a22cec42feac3fa9e42b992d914b8ef3c16a9 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-17
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano serwowanie pełnego kadru, użycie loadera przyciętych źródeł, blokady operacji i nowe testy. Stwierdzono kolizję klucza cache oraz niezgodny status HTTP przy korekcie poza zachowanym kadrem. Brakuje wymaganych testów żądań i interakcji, a opis zachowania ETag nie odpowiada implementacji.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/application/image_review_assets.py:249` — Cache pełnego kadru jest identyfikowany wyłącznie sumą bajtów cropu. Dwa różne oryginały mogą mieć identyczny crop, ale inne wymiary pełnego obrazu lub położenie cropu. Drugie żądanie wykorzysta wtedy płótno pierwszego źródła, przez co obraz będzie miał błędne wymiary albo przesunięte nakładki. Założenie z komentarza, że crop należy dokładnie do jednego oryginału, nie wynika z adresowania treścią. Klucz powinien uwzględniać atest lub tożsamość i geometrię pełnego kadru. Dodać regresję dla identycznych bajtów cropu z dwoma różnymi atestami.

- [P0-2] `services/api/src/game_predictor_api/application/virtual_grid_geometry.py:1551` — `SOURCE_REGION_UNAVAILABLE` jest opakowywany w `ImageGridReviewError`, którego handler w `services/api/src/game_predictor_api/main.py:2643` domyślnie zwraca 422. Kod nie znajduje się na liście konfliktów 409. Podgląd i zapis korekty poza cropem naruszają więc wymaganie R4: HTTP 409. Ten sam mechanizm występuje przy renderowaniu zbiorczym w `virtual_grid_geometry.py:1268`. Uzupełnić mapowanie i sprawdzić rzeczywiste odpowiedzi endpointów.

### P1

- [P1-1] `services/api/tests/test_source_crop_api.py:253` — Test blokady reprocess wywołuje bezpośrednio funkcje pomocnicze; nie wywołuje `JobService.create_managed_image_reprocess_job` ani endpointu. Podobnie test z linii 182 sprawdza sam renderer, bez ścieżki korekty, propozycji i revertu. Brakuje wymaganych testów żądań potwierdzających status, kopertę błędu i brak zapisu po odmowie. Dodać testy HTTP z rzeczywistym cropem; dla reprocess potwierdzić również brak utworzenia joba.

- [P1-2] `ai_docs/tasks/1046-source-frame-api.md:115` — Pominięto wymagane przez zaakceptowany plan testy interakcji Admina i Reviewera. Asercja rozmiaru obrazu w teście resolvera nie weryfikuje pozycjonowania nakładek ani współrzędnych wysyłanych po edycji. Dodać testy z fixture cropu zgodnie z kryterium planu w `ai_docs/delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md:387`. Sam zapis odstępstwa w `Outcome` nie dokumentuje akceptacji usunięcia tego wymagania.

- [P1-3] `ai_docs/architecture/API_CONTRACT.md:5051` — Deklaracja, że wszystkie endpointy zachowują ETag równy `source_checksum_sha256`, jest niezgodna z kodem. Przykładowo `services/api/src/game_predictor_api/api/image_grid_reviews.py:231` tworzy `FileResponse` bez jawnego ETag; Starlette wylicza go z czasu modyfikacji i rozmiaru pliku. Przejście na plik podglądu, a także jego regeneracja, może zmienić ten nagłówek. Jawny checksum jest ustawiany w endpointzie pending (`services/api/src/game_predictor_api/api/board_cell_geometry_pending.py:203`). Ujednolicić implementację z uzgodnionym kontraktem, poprawić `Outcome` i dodać testy nagłówków dla wszystkich czterech rodzajów źródła.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Bez cropów odpowiedzi pozostają bajtowo identyczne | niezweryfikowane | `services/api/tests/test_source_crop_api.py:124` sprawdza bajty pliku jednego resolvera, nie wszystkie odpowiedzi HTTP. |
| Crop jest serwowany w oryginalnych zorientowanych wymiarach | niespełnione | `services/api/src/game_predictor_api/application/image_review_assets.py:249`; kolizja cache opisana w P0-1. |
| ETag pozostaje zgodny z deklarowanym kontraktem | niespełnione | `services/api/src/game_predictor_api/api/image_grid_reviews.py:231`; P1-3. |
| Reprocess i korekty poza kadrem są odrzucane zgodnie z R4 | niespełnione | `services/api/src/game_predictor_api/main.py:2643`; korekta zwraca 422 zamiast 409. Bramka reprocess istnieje w `application/jobs.py:1273`. |
| Poprawne nakładki Admina i Reviewera potwierdzone testami interakcji | niespełnione | `ai_docs/tasks/1046-source-frame-api.md:115`; testy pominięto. |
| Lint, mypy, testy API i kontrola OpenAPI przechodzą | niezweryfikowane | Wyniki zadeklarowano w `ai_docs/tasks/1046-source-frame-api.md:124`; audyt nie uruchamiał kontroli. |

## Listy zamknięte i otwarte

Zamknięte: Brak. Runda 1.

Otwarte: P0-1, P0-2, P1-1, P1-2, P1-3.

## Proponowane testy

- W `services/api/tests/test_source_crop_api.py`: dwa źródła o identycznych bajtach cropu, ale różnych płótnach; sprawdzenie obu obrazów także po ponownym utworzeniu loadera.
- W tym samym pliku: żądania HTTP dla serwowania, korekty, propozycji, revertu i reprocess; asercje statusów, kodów, ETag oraz braku skutków odmowy. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_crop_api.py`.
- W testach interakcji Admina i Reviewera: fixture pełnego kadru z cropem, kontrola nakładek i współrzędnych edycji. Uruchomić właściwe skrypty testowe obu aplikacji po dodaniu tych przypadków.

## Zakres przeglądu i ograniczenia

Przeczytano brief, dokumenty startowe, TASK-1046, odpowiednie fragmenty planu, D-562, wymagań i kontraktu API. Przejrzano wskazany diff, cały nowy moduł testów oraz powiązane ścieżki loadera, renderowania, endpointów i obsługi wyjątków.

Nie uruchamiano testów, usług, lintowania ani generatorów. Wyniki wykonawcy traktowano jako deklaracje, nie niezależnie potwierdzone pomiary. Nie oceniano jobów przycinania ani Storage UI z etapu B.