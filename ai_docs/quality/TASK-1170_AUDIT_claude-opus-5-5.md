# Audyt TASK-1170 — Czytelny podgląd siatki i obrysów

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...f8b8a05aaaf0c5ea5e9a0833927430941d848897 oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: f047b00198836ba8e41f41725f1585d084ca669b6b8f91a99f6638f6f2255135
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano zamknięcie uwag z rundy 1 oraz regresje wprowadzone poprawkami w pionie API, magazynu, SDK, Admina i eksportu HTML. Oba znaleziska P0 i znalezisko P1 zostały usunięte w kodzie i mają testy odtwarzające. Awaria dowodu manifestu nie blokuje już zwykłego edytora, style siatki i wycinka są rozdzielone, a rzeczywisty `export()` ma testy ochrony obrazów. Pozostają wyłącznie drobne ryzyka P2: niewidoczna edycja przy wyłączonych obrysach, pomijanie w HTML plansz bez zapisanych punktów oraz nieaktualny zapis w `Outcome`.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-4] `ai_docs/tasks/1170-grid-content-preview.md:161` — Ryzyko z rundy 1 pozostaje: źródło bez zapisanej sesji ślepej może zostać obejrzane, a później wybrane do pomiaru, a ochrona roli działa tylko w przekazanej kohorcie (`services/api/src/game_predictor_api/storage/grid_content_preview.py`, funkcja `ordinary_preview`). Sekcja `Accepted residual risk` jawnie je akceptuje i nie deklaruje niezależności takiego przyszłego pomiaru. Proponuję utrzymać akceptację ryzyka.
- [P2-7] `apps/admin/src/features/model-quality/grid-content-canvas.tsx:386` — Po wyłączeniu „Obrysy grafik” uchwyty znikają (`:498`), ale `onPointerDown` nadal wywołuje `place()`. Cztery kliknięcia w obraz nadpisują quad wybranego pola w stanie edytora (`:120-130`), a nowy obrys pozostaje niewidoczny. Do trwałej zmiany potrzebny jest jeszcze jawny zapis, więc to ryzyko pomyłki operatora, a nie automatyczna mutacja. Proponuję zablokować `place()` dla narzędzia `content` przy `!showOutlines` albo pokazać komunikat, oraz dodać test interakcji.
- [P2-8] `scripts/export_grid_content_preview.py:191` — Plansza bez kompletnych zapisanych punktów (`nodes === null`, stan niechroniony) wypada z galerii, choć jej aktualna adnotacja istnieje, a aplikacja nadal ją pokazuje. Powód trafia tylko do `preview.json`, natomiast tekst HTML (`:136`) wymienia jako pominięte jedynie zdjęcia chronione i role kontrolne. To częściowo odbiega od odbioru „aplikacja i HTML przedstawiają te same adnotacje”, ale dotyczy jawnego stanu zależnego od danych. Proponuję pokazać w HTML taką planszę z adnotacjami i kodem braku albo przynajmniej licznik pominiętych plansz i ich powody.
- [P2-9] `ai_docs/tasks/1170-grid-content-preview.md:148-149` — Sekcja `Not completed` podaje, że kontrole docs/map wymagają odświeżenia, a `ai_docs/quality/TASK-1170_VERIFICATION.md:130` i `TASK-1170_FIXES_R1.md` opisują je już jako wykonane po poprawkach. Podobnie zdezaktualizowany jest przejściowy zapis w `TASK-1170_VERIFICATION.md:53`. Proponuję ujednolicić `Outcome`, raport weryfikacji i `CURRENT_STATE.md` przy zamykaniu taska.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Każdy punkt T1 planu ma implementację lub jawny warunek zależny od danych | spełnione | Pion API/Admin/HTML poniżej; ograniczenie HTML opisane w P2-8 |
| Brak quadu nie daje obrysu, także przy `boxInPreview` | spełnione | `apps/admin/src/features/model-quality/grid-content-canvas.tsx:452-469`; `services/api/tests/test_grid_content_preview_export.py:56` |
| 24 zapisane punkty bez modyfikacji | spełnione | `services/api/src/game_predictor_api/domain/image_geometry_v2.py:500-510` (porządek węzłów zgodny z `_verified_footprint`); `grid-content-canvas.tsx:419-441` |
| Trzy niezależne przełączniki i legenda tekstowa | spełnione | `grid-content-canvas.tsx:51-53`, `:419`, `:442`, `:452`; `apps/admin/test-interactions/grid-content-reference.test.mjs:1681` |
| Rozróżnienie warstw kolorem i tekstem (D-594) | spełnione | `apps/admin/src/features/model-quality/grid-correction-learning.css:116-135`; test stylu: `grid-content-reference.test.mjs:1570` |
| Powiększony kadr odróżnia otoczenie od wycinka | spełnione | Sekcja `figure` w `grid-content-canvas.tsx` (podpis i osobny poligon wycinka) |
| Rewizja, pochodzenie i zatwierdzenie jawne | spełnione | `apps/admin/src/features/model-quality/grid-content-ordinary.tsx:186-217`; `scripts/export_grid_content_preview.py` (blok `provenance`) |
| Piny geometrii i konfiguracji renderowania | spełnione | `services/api/src/game_predictor_api/storage/grid_content_preview.py` (`_verified_footprint`); `services/api/src/game_predictor_api/domain/image_geometry_v2.py:675-683` zgodne z zamkniętym DTO |
| Brak lub drift dowodu daje jawny stan, bez blokady edytora | spełnione | `grid_content_preview.py:123`, `:135`; `services/api/tests/test_grid_content_preview.py:133`, `:158`, `:185`; `grid-content-reference.test.mjs:1523` |
| Wycofanie generatora koloru z domyślnego przygotowania | spełnione | `scripts/export_grid_content_preview.py` używa wyłącznie GET; wyszukiwanie nazw archiwalnych helperów trafia tylko w dokumenty audytu i taska |
| Odczyt bez zapisów adnotacji | spełnione | `services/api/src/game_predictor_api/storage/grid_cell_content.py:210-217`; obserwator SQL w `services/api/tests/integration/test_grid_content_targets_postgres.py` |
| Izolacja ślepego pomiaru | spełnione | Rzeczywisty dokument sesji zawiera `targets[].source.sourceRepresentativeSha256` (`grid_cell_content.py:372-411`), zgodnie z zapytaniem `protected_source`; kontroler ślepy nie używa `ordinaryPreview` ani odczytu reference |
| Chronione zdjęcia poza galerią | spełnione | `scripts/export_grid_content_preview.py:191`; `services/api/tests/test_grid_content_preview_export.py:139`, `:160` |
| Historyczne kontrakty i ręczne korekty zachowane | spełnione | `services/api/src/game_predictor_api/schemas/grid_cell_content.py:128-138`; odczyt bez pinów w `services/api/src/game_predictor_api/api/grid_cell_content.py` |
| Pion kontraktu API | spełnione | Backend, OpenAPI, typy, wrapper oraz `packages/admin-api-client/test/grid-cell-content-request.test.mjs` w pakiecie |
| Testy, lint, typy, docs/mapa oraz audyt i receipt | niezweryfikowane | Wyniki deklarowane w `ai_docs/quality/TASK-1170_VERIFICATION.md`; audytor ich nie uruchamiał. Raport jawnie podaje 428 PASS i 10 FAIL oraz odkłada build do T4 |

Dowody zamknięcia uwag z rundy 1:

- P0-1: footprinty poza kadrem zachowują dokładne współrzędne i kod przyczyny (`grid_content_preview.py:145-152`). Błędy czystej walidacji nie przerywają odczytu (`:135`), a API nadal propaguje błędy infrastruktury.
- P0-2: reguła `.gridContentProductionCrop` jest oddzielona od `.gridContentLattice, .gridContentQuad` (`grid-correction-learning.css:116-131`).
- P1-1: testy rzeczywistego `export()` są w `test_grid_content_preview_export.py:139`, `:167` i `:177`.
- P2-1: fixture używa `SourceQuad.to_dict()` (`test_grid_content_preview.py:59`), a test PostgreSQL sprawdza kształt `[{x,y}]` (`test_grid_content_targets_postgres.py:220`).
- P2-2: asercja pełnych argumentów, w tym pary pinów (`grid-content-reference.test.mjs:377`).
- P2-3: uchwyty znikają razem z warstwą (`grid-content-canvas.tsx:498`). Pozostałą ścieżkę edycji opisuje nowe znalezisko P2-7.
- P2-5: `ContentWriteResponse` dziedziczy po bazie bez `ordinaryPreview` (`grid_cell_content.py:138`; test: `test_grid_content_preview.py:219`).
- P2-6: wskazana komenda `test:geometry` została według raportu wykonana, a odstępstwo dotyczące builda jest zapisane jawnie.

## Listy zamknięte i otwarte

Zamknięte: P0-1, P0-2, P1-1, P2-1, P2-2, P2-3, P2-5, P2-6.

Otwarte: P2-4, P2-7, P2-8, P2-9.

## Proponowane testy

- `apps/admin/test-interactions/grid-content-reference.test.mjs`: po wyłączeniu „Obrysy grafik” kliknięcia w obraz nie zmieniają quadu wybranego pola. Komenda: `npm run test:geometry --workspace @game-predictor/admin`.
- `services/api/tests/test_grid_content_preview_export.py`: plansza TRAIN bez zapisanych punktów, ale z aktualną adnotacją, jest jawnie widoczna w HTML jako brak. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_content_preview_export.py`.
- `services/api/tests/test_grid_content_preview.py`: manifest z mniej niż 15 poprawnymi wpisami i bez wpisów błędnych daje oczekiwany stan oraz kod `CONTENT_PRODUCTION_CELLS_PARTIAL`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_content_preview.py`.
- `services/api/tests/test_grid_content_preview.py`: podanie tylko jednego pinu kończy się odpowiedzią 422 z kodem `CONTENT_PREVIEW_PINS_REQUIRED`, z zarejestrowanym handlerem aplikacji.

## Zakres przeglądu i ograniczenia

Przeczytano zamrożony pakiet oraz niezbędny kod: `AGENTS.md`, `grid_cell_content.py` (magazyn i początek routera API), `grid_cell_content_targets.py`, `grid_visibility_contract.py`, fragmenty `grid_quality_observations.py`, `grid_reinference.py`, `image_geometry_v2.py` i `virtual_cell_extraction.py`. Sprawdzono też płótno, kontroler i style Admina oraz fragmenty testów i `CROSS_AUDIT.md`.

Nie uruchamiano testów, lintu, typecheck, usług, bazy ani eksportu; deklarowane wyniki, logi i receipt wykonawcy nie zostały potwierdzone. Wygląd warstw oceniono na podstawie reguł CSS i kodu, bez renderowania w przeglądarce. Nie da się statycznie ustalić, ile rzeczywistych plansz operatora ma brak zapisanych punktów.

Stan gita podany w kontekście sesji oznacza jako zmodyfikowane także inne pliki w `packages/admin-api-client/src/generated/`, spoza zakresu pakietu. Nie były one audytowane, więc przed dodaniem plików do commita trzeba potwierdzić, czy należą do tego taska.