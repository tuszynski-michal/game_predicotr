# Audyt TASK-1170 — Czytelny podgląd siatki i obrysów

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...f8b8a05aaaf0c5ea5e9a0833927430941d848897 oraz zmiany niezacommitowane, data 2026-11-09
Runda: 1
SHA pakietu: 4a9181ade7f4f7b7e612ee9ba13bc878b9c5ed402afe6e493a443781a2f3207a
Otwarte P0: 2
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano pion zwykłego podglądu: API, odczyt z magazynu, ochronę źródeł ślepego pomiaru, SDK, kontroler i płótno Admina, style oraz eksport HTML. Skonfrontowano go z rzeczywistym kształtem manifestów renderowania z workera. Ochrona źródeł, niezmienione 24 punkty, brak obrysu przy braku quadu i wycofanie generatora koloru są poprawne w kodzie. Główne ryzyko polega na tym, że konflikt lub częściowo pozakadrowy wycinek w manifeście kończy cały odczyt błędem i blokuje zwykły edytor. Drugi błąd blokujący to reguła CSS, przez którą siatka pól wygląda jak zakres produkcyjnego wycinka, także w trybie ślepym.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/grid_content_preview.py:143` — Footprint wykraczający poza piksele źródła, także o ułamek, zgłasza `ContentError` 409 zamiast jawnego braku. Taki manifest jest poprawny: `services/api/src/game_predictor_api/domain/image_geometry_v2.py:704-705` dopuszcza komórki częściowo widoczne, a `services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py:242-248` wprost zakłada wcięcie poza kadrem. Dla geometrii kwalifikowanej renderer toleruje też `SOURCE_SUPPORT_EPSILON` (`virtual_cell_extraction.py:250-256`).
  Podobnie zachowują się pozostałe gałęzie konfliktu (`grid_content_preview.py:107-109`, `:125-127`, `:137-140`). Wadliwe dane w `_points`, `CellContentReference.model_validate` albo brak klucza spec dają w `:115-142` nieobsłużony `ValueError` lub `KeyError`, czyli 500.
  `SqlAlchemyGridCellContentRepository.get_preview` (`services/api/src/game_predictor_api/storage/grid_cell_content.py:216-217`) liczy podgląd przed odczytem adnotacji, a `apps/admin/src/features/model-quality/grid-content-ordinary.tsx:67-72` zawsze wysyła piny. Skutkiem jest `readError`, `reference === null` i brak płótna oraz przycisków zapisu (`grid-content-ordinary.tsx:84-86`, `:167`) właśnie dla plansz z polami `out_of_frame`. Jeden taki cel przerywa też cały eksport HTML, zostawiając niepełny katalog (`scripts/export_grid_content_preview.py:135-144`, `:148`).
  Narusza to kryterium zachowania historycznych kontraktów i ręcznych korekt oraz D-594: „brak lub drift dowodu jest jawnym unavailable” (`ai_docs/process/decisions/DECISION_LOG_2026.md:29`).
  Poprawka: awaria dowodu manifestu ma dawać zwykły podgląd z zapisanymi punktami, pustymi lub częściowymi `productionCells` i kodem przyczyny, a adnotacja i edytor muszą pozostać dostępne. Komórkę poza kadrem należy pokazać z zapisanym quadem albo pominąć z jawnym kodem. Test `test_missing_manifest_does_not_fabricate_full_fields_and_changed_pin_fails` wymaga świadomego dostosowania do D-594. Trzeba dodać regresję dla częściowej komórki w produkcyjnym kształcie `[{x,y}]`.

- [P0-2] `apps/admin/src/features/model-quality/grid-correction-learning.css:116-124` — Nową regułę wstawiono w środek istniejącej listy selektorów `.gridContentLattice, .gridContentQuad`. W efekcie `.gridContentLattice` przejął styl produkcyjnego wycinka: bursztynowy kolor, kreskowanie 8/4 i wypełnienie 12%.
  Siatka pól oraz „Rzeczywiste wycinki” mają więc identyczny styl, co narusza D-594 (`ai_docs/process/decisions/DECISION_LOG_2026.md:38-39`: rozróżnienie „tekstem oraz kolorem”) i główny cel taska. Legenda (`apps/admin/src/features/model-quality/grid-content-canvas.tsx:186-191`) wskazuje kreskowanie jako cechę wycinka, więc wprowadza w błąd. Aplikacja różni się też od HTML, gdzie siatka ma własny kolor (`scripts/export_grid_content_preview.py`, reguła `.lattice`).
  Ta sama klasa jest używana przez edytowalną siatkę ślepego pomiaru (`grid-content-canvas.tsx:427`, `:438`; `apps/admin/src/features/model-quality/grid-content-blind.tsx:353-362`), więc zmienia się wygląd istniejącego workflow.
  Poprawka: przywrócić wspólny selektor `.gridContentLattice, .gridContentQuad` z `fill: none` i `stroke: #51caff`, a `.gridContentProductionCrop` zdefiniować jako osobną regułę. Testy jsdom tego nie wykryją, więc potrzebna jest asercja treści CSS albo stylu obliczonego.

### P1

- [P1-1] `scripts/export_grid_content_preview.py:128` — Żaden test nie wywołuje `export()`. `services/api/tests/test_grid_content_preview_export.py:53-78` sprawdza wyłącznie czyste `preview_html`. Tymczasem tylko `export()` decyduje, czy JPEG i `preview.json` trafią na dysk (`:151`, `:161`, `:176`).
  Niesprawdzone pozostają: wymóg „Chronione zdjęcia nie trafiają do pomocniczej galerii”, deklaracja `ai_docs/architecture/VISION_LAB.md` o pomijaniu źródeł przed pobraniem assetów, limity bajtów i czasu, kontrola SHA assetu oraz brak innych żądań niż GET. Regresja w `export()` zapisałaby na dysk chronione piksele przy zielonych testach.
  Poprawka: dodać test `export()` z podstawionym `urlopen`, obejmujący A, B, REG, protected TRAIN i niezgodny SHA. Test ma potwierdzić brak żądania assetu oraz brak pliku JPEG i rekordu, wyłącznie GET, a także zachowanie przy limicie bajtów.

### P2

- [P2-1] `services/api/tests/test_grid_content_preview.py:55-56` — Fixture używa quadów `[[x,y]]`, a produkcja zapisuje `[{x,y}]` (`services/api/src/game_predictor_api/domain/image_geometry_v2.py:464-465`). Test PostgreSQL ma tylko asercję `state != "protected"` (`services/api/tests/integration/test_grid_content_targets_postgres.py:210`), więc ścieżka rzeczywistego manifestu nie ma pokrycia end-to-end. Proponuję fixture zbudowany przez kontrakt renderera oraz wiersz `board_render_manifests` w teście PostgreSQL.
- [P2-2] `apps/admin/test-interactions/grid-content-reference.test.mjs:184-187` — Mock zapisuje argumenty, ale asercje (`:460`, `:482`) liczą tylko wywołania. Nikt nie sprawdza, że `GridContentOrdinary` przekazuje parę pinów (`apps/admin/src/features/model-quality/grid-content-ordinary.tsx:71`). Bez tego podgląd mógłby zniknąć niepostrzeżenie. Proponuję asercję czwartego argumentu.
- [P2-3] `apps/admin/src/features/model-quality/grid-content-canvas.tsx:498-515` — Po wyłączeniu „Obrysy grafik” uchwyty wybranego quadu pozostają widoczne, więc warstwa nie znika całkowicie. To można świadomie zaakceptować jako narzędzia edycji albo ukryć razem z warstwą.
- [P2-4] `services/api/src/game_predictor_api/storage/grid_content_preview.py:184-188` — Ochrona roli działa tylko w przekazanej kohorcie, a TRAIN/A są chronione dopiero po zapisaniu sesji ślepej. Operator może więc zobaczyć siatkę i wycinki źródła, które później trafi do ślepego pomiaru. D-594 ogranicza ochronę do zapisanych sesji, więc proponuję akceptację ryzyka z zapisem w `Outcome`.
- [P2-5] `services/api/src/game_predictor_api/schemas/grid_cell_content.py:135` — `ContentWriteResponse` dziedziczy `ordinaryPreview` i publikuje je w OpenAPI, choć zapis nigdy tego pola nie zwraca. Proponuję przenieść pole do osobnego modelu odpowiedzi odczytu albo zaakceptować nadmiar kontraktu.
- [P2-6] `ai_docs/quality/TASK-1170_VERIFICATION.md:37` — Raport podaje uruchomienie dwóch plików przez tsx, a sekcja `Verification` taska wskazuje `npm run test:geometry --workspace @game-predictor/admin`. Proponuję wykonać wskazaną komendę po poprawkach albo jawnie zapisać to odstępstwo. Build z planu także nie jest raportowany.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Każdy punkt T1 planu ma implementację lub jawny warunek zależny od danych | niespełnione | P0-1, P0-2 |
| Brak quadu nie daje obrysu, także przy `boxInPreview` | spełnione | `apps/admin/src/features/model-quality/grid-content-canvas.tsx:452-469`; `services/api/tests/test_grid_content_preview_export.py:53-61` |
| 24 zapisane punkty bez modyfikacji | spełnione | `services/api/src/game_predictor_api/storage/grid_content_preview.py:50-62`; `grid-content-canvas.tsx:419-441` |
| Trzy niezależne przełączniki | spełnione | `grid-content-canvas.tsx:160-185`, `:419`, `:442`, `:452` |
| Czytelne rozróżnienie warstw kolorem i tekstem (D-594) | niespełnione | `apps/admin/src/features/model-quality/grid-correction-learning.css:116-124` (P0-2) |
| Rewizja i pochodzenie jawne w aplikacji i HTML | spełnione | `grid-content-ordinary.tsx:170-193`; `scripts/export_grid_content_preview.py` (blok `provenance`) |
| Wycofanie generatora koloru z domyślnego przygotowania | spełnione | Wyszukiwanie `prepare_proposals`/`build_review.py` trafia tylko w plik taska; helper używa wyłącznie GET |
| Odczyt bez zapisów adnotacji | spełnione | `services/api/src/game_predictor_api/api/grid_cell_content.py:115-137`; `services/api/tests/integration/test_grid_content_targets_postgres.py` (obserwator SQL, odczyt statyczny) |
| Izolacja ślepego pomiaru w API i UI | spełnione | `grid_content_preview.py:184-193`; `grid-content-blind.tsx:353-362` (brak propu `ordinaryPreview`) |
| Chronione zdjęcia poza galerią | niezweryfikowane | Kod poprawny (`scripts/export_grid_content_preview.py:151`, `:161`), brak testu `export()` (P1-1) |
| Historyczne kontrakty i ręczne korekty zachowane | niespełnione | Odczyt bez pinów bez zmian (`grid_cell_content.py:131-132` w API), ale zwykły edytor blokowany przez P0-1 |
| Testy, lint, typy, docs/mapa oraz audyt i receipt | niezweryfikowane | Wyniki deklarowane w `ai_docs/quality/TASK-1170_VERIFICATION.md`; audytor ich nie uruchamiał |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P0-2, P1-1, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- `services/api/tests/test_grid_content_preview.py`: komórka częściowa z `paddedSourceQuad` poza kadrem oraz konflikty manifestu dają odpowiedź z podglądem i kodem przyczyny, a adnotacja pozostaje dostępna. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_content_preview.py`.
- `services/api/tests/test_grid_content_preview_export.py`: `export()` z podstawionym `urlopen` dla A, B, REG, protected TRAIN, niezgodnego SHA i limitu bajtów, z asercją braku pliku JPEG. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_content_preview_export.py`.
- `services/api/tests/integration/test_grid_content_targets_postgres.py`: rzeczywisty wiersz `board_render_manifests` w kształcie produkcyjnym i asercja `productionCells`, z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`.
- `apps/admin/test-interactions/grid-content-reference.test.mjs`: asercja przekazania pinów, kontrola odrębnych reguł CSS siatki i wycinka oraz scenariusz błędu podglądu bez utraty edytora. Komenda: `npm run test:geometry --workspace @game-predictor/admin`.

## Zakres przeglądu i ograniczenia

Przeczytano zamrożony pakiet oraz niezbędny kod: `AGENTS.md`, `grid_content_preview.py`, `grid_cell_content.py` (storage i API), `grid_cell_content_targets.py`, `grid_quality_observations.py`, `board_render_manifests.py`, `board_render_manifest_reader.py`, `grid_visibility_contract.py`. Przeczytano też fragmenty `image_geometry_v2.py`, `virtual_cell_extraction.py`, `production_workflow.py` i `local_admin.py`, a także płótno, kontroler i style Admina oraz fragmenty testu interakcji.

Nie uruchamiano testów, lintu, typecheck, usług, bazy ani eksportu. Wyniki i receipty deklarowane przez wykonawcę nie były sprawdzane. Liczby rzeczywistych plansz operatora dotkniętych P0-1 nie da się ustalić statycznie; znalezisko wynika z kontraktu renderera i przepływu sterowania. Wygląd warstw w P0-2 oceniono na podstawie reguł CSS, bez renderowania w przeglądarce.