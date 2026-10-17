# Audyt TASK-1045 - Ramka źródła z cropem w workerze

Werdykt: REVISE  
Audytor: Codex `gpt-6-astra`, reasoning `high`  
Wykonawca: Claude `claude-opus-5-5`, reasoning `high`  
Zakres: HEAD...a07276127b83a9954f69062a7fdcbe973587089e oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-17  
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano loader cropów, weryfikację atestu, konsumentów workera, wykluczanie kotwic oraz testy i dokumentację. Implementacja zachowuje pierwszeństwo oryginału i sprawdza tożsamość odtwarzanego płótna. Dwa problemy blokują akceptację: trening symboli odrzuca brakujący oryginał przed użyciem loadera, a odtwarzanie zapisanych komórek pomija kontrolę `valid_box`.

## Znaleziska

### P0

- [P0-1] `services/worker/src/game_predictor_worker/symbols/training_dataset.py:418` — `_parse_virtual_crop_source` nadal przekazuje ścieżkę oryginału do `_managed_crop`. Ta funkcja wymaga `resolve(strict=True)` i odczytu bajtów oryginału (`:377`). Po usunięciu oryginału budowa datasetu kończy się `TRAINING_DATASET_CROP_MISSING`, nawet gdy istnieją poprawny crop i atest. Nowe `allow_crop=True` w `:1099` nie zostaje wykorzystane. Należy rozdzielić walidację ścieżki od wymagania obecności oryginału i sprawdzać źródło wirtualne przez loader obsługujący crop, zachowując kontrolę ścieżki i proweniencji.

- [P0-2] `services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py:397` — `render_persisted_virtual_cell_rgb` przekazuje `paddedSourceQuad` bezpośrednio do warpu, bez `require_inside_valid_box`. Kontrola dodana w `VirtualCellRenderer._prepare` nie obejmuje tej funkcji, używanej przez ponowne rozpoznanie symboli i trening. Quad poza zachowanym regionem zwróci błąd sumy pikseli zamiast wymaganego `SOURCE_REGION_UNAVAILABLE`; jeśli usunięte piksele były czarne, kontrola sumy może nawet przepuścić render z wypełnienia. Przed warpem należy sprawdzić zapisane `sourceQuad` i `paddedSourceQuad`, tak samo jak przy renderowaniu nowych komórek.

### P1

Brak.

### P2

- [P2-1] `ai_docs/delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md:234` — tabela R4 nadal wymienia „shadow siatek” jako operację korzystającą z R2 bez zmiany wyników, choć poprzedni wiersz nakazuje odmowę `SOURCE_ORIGINAL_CROPPED`. Implementacja odpowiada odmowie z rewizji 2. Należy usunąć shadow z ostatniego wiersza, aby kontrakt nie zawierał sprzecznych instrukcji.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Oryginał obecny: niezmienione render specs i sumy komórek | spełnione | Statycznie zachowana ścieżka oryginału; `services/worker/tests/test_virtual_cell_extraction.py:291`, `services/worker/tests/test_source_crop_frame.py:122`. |
| Crop dla orientacji 1 i 6: identyczne piksele oraz rendery komórek | niezweryfikowane | `services/worker/tests/test_source_crop_frame.py:122` sprawdza piksele dla braku tagu EXIF i orientacji 6; `:235` osobno sprawdza render syntetycznej ramki. Brakuje połączonego scenariusza dekodowania i renderowania dla obu wskazanych orientacji. |
| Quad poza `valid_box` daje `SOURCE_REGION_UNAVAILABLE` | niespełnione | Test `services/worker/tests/test_source_crop_frame.py:248` obejmuje nowy renderer, lecz ścieżka zapisanych render specs pomija kontrolę — P0-2. |
| Uszkodzony crop lub atest daje stabilny błąd | spełnione | Kontrole w `services/api/src/game_predictor_api/domain/canonical_source.py:252`; scenariusze uszkodzeń w `services/worker/tests/test_source_crop_frame.py:179`. Ocena statyczna. |
| Pokrycie odczytów zarządzanych oryginałów w workerze | niespełnione | Trening symboli nadal wymaga obecności oryginału przed loaderem — `services/worker/src/game_predictor_worker/symbols/training_dataset.py:418`, P0-1. |
| Lint, mypy i testy zmienionych modułów przechodzą | niezweryfikowane | Wyniki zadeklarowano w `ai_docs/tasks/1045-source-frame-worker.md:135`, z opisanymi wyjątkami. Audyt nie uruchamiał kontroli. |

## Listy zamknięte i otwarte

Zamknięte: Brak. Runda 1.

Otwarte: P0-1, P0-2, P2-1.

## Proponowane testy

- W `services/worker/tests/test_verified_training_dataset.py` rozszerzyć scenariusz wirtualnej kohorty: usunąć oryginał, pozostawić poprawny crop i atest, zbudować dataset oraz porównać piksele z wynikiem sprzed usunięcia. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_verified_training_dataset.py -k virtual`.
- W `services/worker/tests/test_source_crop_frame.py` sprawdzić `render_persisted_virtual_cell_rgb` dla quadów wewnątrz i poza cropem, również gdy brakujący region oryginału był czarny. Wymagać `SOURCE_REGION_UNAVAILABLE` przed warpem. Dodać dekodowanie i renderowanie komórek dla jawnych orientacji EXIF 1 i 6. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_source_crop_frame.py`.
- Dodać scenariusz ponownego rozpoznania symboli z brakującym oryginałem do `services/worker/tests/test_pending_symbol_reinference.py`, aby objąć rzeczywiste wywołanie zapisanego render specu. Komenda: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_pending_symbol_reinference.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, odpowiednie wymagania i architekturę, plan z rewizją 2, D-562, wskazany diff oraz nowy plik testowy. Prześledzono powiązane ścieżki treningu symboli, renderowania zapisanych komórek, reinference, preflightu, kohort i odczytów legacy.

Nie uruchamiano testów, lintowania, mypy, usług ani operacji na bazie. Wyniki wykonawcy potraktowano jako deklaracje, bez niezależnego potwierdzenia. Serwowanie i blokady API pozostają zakresem TASK-1046.