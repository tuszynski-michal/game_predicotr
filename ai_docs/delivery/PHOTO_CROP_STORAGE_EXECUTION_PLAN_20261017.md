---
title: Przycinanie zarządzanych oryginałów do siatek — plan wykonania
status: accepted
last_updated: 2026-10-17
---

# Przycinanie zarządzanych oryginałów do siatek (P2–P4)

Plan następczy po [TASK-1016](../tasks/completed/1016-photo-crop-preview.md)
i [raporcie P1](../quality/PHOTO_CROP_PREVIEW_20261014.md). Autor: Claude Code
(`claude-opus-5-5`), 2026-10-17. Status `accepted` (operator, 2026-10-17):
operator zlecił etap A (TASK-1043–1046) z audytami według tabeli i zgodził się
na jego koszt. Etapy B i C wymagają osobnego polecenia. Akceptacja planu nie
jest zgodą na migrację bazy operatora, uruchomienie jobów na danych operatora,
usuwanie oryginałów, scalenie ani push.

Etap A wykonany 2026-10-17: TASK-1043 v1.7.404, TASK-1044 v1.7.405,
TASK-1045 v1.7.406, TASK-1046 v1.7.407 (audyty Codex, po jednej rundzie
poprawek, bez otwartych P0/P1). Migracja `0167` nie jest wykonana na bazie
operatora; etapy B i C czekają na polecenie.

Rewizja 1 (2026-10-17, przed startem etapu A, bez zmiany decyzji operatora):
R2 dostaje atest cropu zapisany obok pliku cropu (sekcja R2), bo
`CanonicalSourceLoader` działa na ścieżce pliku, bez dostępu do bazy.

Rewizja 2 (2026-10-17, TASK-1045, ustalenia z kodu, bez zmiany decyzji
operatora; zmniejsza tylko pulę i zakres użycia cropów):

- Rejestracja stron (`page_geometry_registration`, wersja v1) liczy cechy ORB
  na całej klatce kotwicy, a preflight nowych importów czyta kotwice z
  `data/originals`. Kwalifikacja wyklucza więc kotwice (`PAGE_REGISTRATION_ANCHOR`):
  checksumy przypięte w dowolnym profilu kalibracji, wszystkie źródła kohorty
  profilu historycznego bez przypiętych kotwic oraz źródła z ręcznym
  override'em geometrii strony, we wszystkich grach.
- Loader przyjmuje crop tylko po jawnym `allow_crop=True`, a robią to wyłącznie
  konsumenci renderujący znane quady z kontrolą `valid_box`: trening symboli,
  ponowne rozpoznanie symboli, reinference siatek, a w API podglądy, cofnięcie
  korekty i geometria wirtualna (TASK-1046). Analiza całej klatki (pipeline
  importu, preflight, shadow siatek, kohorty i datasety V3) dostaje
  `SOURCE_ORIGINAL_CROPPED`, a nie płótno z wypełnieniem. Wiersz R4 „Budowa
  kohorty V3” zmienia się z „kopiuje plik cropu” na „odmowa
  `SOURCE_ORIGINAL_CROPPED`”.
- Wymaganie dla TASK-1048: przed usunięciem pierwszego oryginału wybór kotwic
  nowego profilu kalibracji (`domain/grid_calibration.py`) i budowa kohort V3
  muszą pomijać bloby w stanie `original_deleted`, inaczej przyszła kalibracja
  albo kohorta zakończy się błędem braku pliku.

## 1. Stan obecny

### Fakty z kodu (sprawdzone 2026-10-17 na `main` v1.7.400)

- Oryginały są adresowane treścią: `artifact_root/data/originals/<sha[:2]>/<sha>.jpg`
  (`services/worker/src/game_predictor_worker/images/source_ingestion.py`
  `ManagedOriginalStore`, `ensure_original`, `_verify_existing`). Dnia 2026-10-17
  było to 166 150 plików / 35,77 GiB. Jeden blob może należeć do wielu wierszy
  `source_images` (różne importy; unikalność `uq_source_images_job_checksum`).
- `SourceImageModel` (`services/api/src/game_predictor_api/storage/models.py`)
  przechowuje `relative_path`, `checksum_sha256`, `normalized_pixel_checksum_sha256`,
  `oriented_width/height`, `exif_orientation` i `coordinate_space`
  (CHECK `exif-normalized-rgb-pixels-v1`). Wszystkie quady geometrii (rewizje
  `ImageSourceGeometryRevisionModel`, `corners` plansz, `source_quad` komórek,
  `paddedSourceQuad` render specs, oczekujące korekty) są w pikselach pełnego
  zorientowanego oryginału i zapisują jego sumy pliku i pikseli.
- Wspólne dekodowanie: `decode_canonical_source_bytes`
  (`services/api/src/game_predictor_api/domain/canonical_source.py`) i
  `CanonicalSourceLoader.load`
  (`services/worker/src/game_predictor_worker/images/normalization.py`).
  Z nich korzystają: `production_workflow.py`, `grid_reinference_handler.py`,
  `grid_shadow_handler.py`, `pending_symbol_reinference.py`,
  `grid_cohort_dataset.py`, `symbols/training_dataset.py`, a w API
  `application/virtual_cell_previews.py`, `application/virtual_grid_geometry.py`,
  `application/geometry_correction_reverts.py`,
  `storage/grid_training_cohort_artifacts.py`.
- Odczyty z pominięciem wspólnego loadera: `page_geometry_preflight.py`
  (`_load_anchor_rgb`, `_load_source_rgb`), `production_workflow.py`
  (`_ManagedImageArtifacts.load_rgb`, ścieżka legacy), `keypoint_geometry/dataset.py`,
  `symbol_dataset.py`, w API `application/image_review_assets.py` (`_resolve`,
  `CHECKSUM_DRIFT`), `application/review_assets.py`,
  `application/v7_label_geometry_calibration.py`,
  `application/image_import_geometry_guard_preview.py`. Do potwierdzenia na
  starcie TASK-1045: `images/geometry.py` i `images/rectification.py`
  (`cv2.imdecode`).
- Serwowanie: `FileResponse` z cache `immutable` w `api/image_reviews.py`,
  `api/image_grid_reviews.py`, `api/board_cell_geometry_pending.py`,
  `api/image_imports.py`. Frontendy rysują nakładki w wymiarach naturalnych obrazu
  (`apps/admin/.../page-geometry-correction-panel.tsx`,
  `apps/reviewer/.../deferred-board-cell-geometry-editor.tsx`,
  `operational-review-workspace.tsx`) albo w `oriented_width/height` z DTO
  (`geometry-gaps-workspace.tsx`).
- Pełne oryginały są potrzebne przy: reprocess importu (`api/image_imports.py`,
  `application/jobs.py`), korekcie lub override geometrii strony, revert korekty,
  ponownym preflight, reinference siatek i budowie kohort V3. Kohorty kopiują
  bajty oryginału do `data/grid-training-cohorts/...`.
- Wzorzec trwałego joba z podglądem i potwierdzeniem: `storage_gc`
  (`api/image_storage.py`, `application/storage_gc.py`,
  `storage/storage_gc_repository.py`, worker `storage_gc.py`, rejestracja w
  `cli.py`). Bezpieczne usuwanie współdzielonych oryginałów:
  [TASK-1042](../tasks/completed/1042-board-source-cleanup-originals.md)
  (`storage/cleanup_repository.py`).
- `D:\game_predictor_backup` zawiera zrzuty bazy z 2026-10-10 i kopie repozytorium,
  ale nie zawiera `artifacts/data/originals`.

### Wynik pomiaru bezstratnego cropu (2026-10-17, kopie P1)

`artifacts/photo-crop-preview-20261014/measure_lossless_crop.py`, narzędzie
`jpegtran` z libjpeg-turbo 3.2.0 (`-copy all -optimize -crop`), 40 źródeł P1:

| Wariant | Bajty | Zmiana |
|---|---:|---:|
| Oryginały | 10 992 053 | — |
| P1, ponowne kodowanie | 7 845 699 | −28,62% |
| Bezstratny crop, `-copy all` | 7 646 890 | **−30,43%** |
| Bezstratny crop, `-copy none` | 7 620 175 | −30,68% |

Wszystkie 40 kadrów zawiera ramki P1; orientacja EXIF 1, próbkowanie 4:4:4 i
4:2:0, brak JPEG progresywnych. Piksele różnią się wyłącznie w zewnętrznym pasie
1 px kadru (interpolacja chrominancji na krawędzi); w 25 źródłach, łącznie
124 piksele leżące w obrębie ramek P1 z marginesem, ale żaden w odległości
mniejszej niż 49 px od chronionego quada. Próbka jest celowa; wynik nie jest
prognozą dla całej biblioteki.

## 2. Cel i decyzje operatora

Cel: zmniejszyć zajętość `data/originals` przez zastąpienie oryginałów
kwalifikujących się zdjęć bezstratnie przyciętym JPEG-iem, bez zmiany geometrii,
zatwierdzeń ani wyników analizy.

Decyzje operatora (2026-10-17, czat):

1. Galeria P1 zaakceptowana; margines 50 px.
2. Zapis: bezstratny crop JPEG wyrównany do siatki bloków JPEG.
3. Oryginał usuwany po weryfikacji przyciętego wariantu, **bez osobnej kopii
   zdjęć**; operator wie, że kopia na D nie zawiera zdjęć.
4. Uruchamianie z aplikacji z podglądem przed zmianami (z rozmowy P1).
5. Zdjęcia z siatkami w korekcie geometrii są wykluczone.

## 3. Zakres

W zakresie: reprezentacja przyciętego wariantu, jednolity odczyt źródła,
blokady operacji wymagających pełnego kadru, job tworzenia cropów, job usuwania
oryginałów, panel Storage, pilotaż na 40 źródłach P1.

Poza zakresem: przebieg na całej bibliotece (osobna zgoda po pilotażu),
deduplikacja kopii w kohortach V3 (osobna retencja klasy `grid_cohort_asset`),
lokalne foldery operatora, legacy pliki plansz `board_relative_path`, aplikacja
mobilna, zmiana marginesu per gra, kompresja inna niż bezstratny crop.

## 4. Kluczowe reguły i decyzje projektowe

Zostaną zapisane jako **D-562** (proponowane) w TASK-1043.

### R1. Wariant obok oryginału, współrzędne bez zmian

Nowa tabela `source_image_crops` (proponowana), jeden wiersz na blob oryginału
(klucz `original_checksum_sha256`, unikalny), bo blob jest współdzielony przez
wiersze `source_images`. Kolumny:

- tożsamość oryginału: `original_checksum_sha256`, `original_relative_path`,
  `original_size_bytes`, `original_normalized_pixel_checksum_sha256`,
  `original_oriented_width/height`, `original_exif_orientation`;
- crop: `crop_relative_path` = `originals-cropped/<sha[:2]>/<orig_sha>.jpg`
  (pod `data/`), `crop_checksum_sha256`, `crop_size_bytes`,
  `crop_normalized_pixel_checksum_sha256`, `crop_box_oriented`
  `[left, top, right, bottom]` w `exif-normalized-rgb-pixels-v1`,
  `crop_box_raw`, `protected_box_oriented` (obwiednia chronionych quadów bez
  marginesu), `margin_px`, `imcu_width/height`, `tool_version`,
  `edge_mismatch_pixels`;
- stan: `verified` → `original_deleted` (proponowany CHECK), `run_id`,
  `verified_at`, `original_deleted_at`.

Nie zmieniamy `source_images`, rewizji geometrii, zatwierdzeń, manifestów ani ich
sum. `coordinate_space` pozostaje `exif-normalized-rgb-pixels-v1`: współrzędne
nadal opisują pełny zorientowany kadr oryginału.

### R2. Jednolita ramka źródła

Nowy kontrakt `SourceFrame` (proponowany, `domain/source_frame.py` w API,
używany przez worker tak jak `canonical_source.py`):

```text
load_source_frame(source_row, crop_row | None) -> SourceFrame
  jeśli plik oryginału istnieje:
      zachowanie jak dziś (SHA-256 bajtów, dekodowanie, ewentualna kontrola pikseli)
      -> kind=original, valid_box = cały kadr
  w przeciwnym razie, jeśli crop_row.state == original_deleted (albo verified):
      sprawdź SHA-256 pliku cropu == crop_checksum_sha256
      zdekoduj z EXIF, sprawdź crop_normalized_pixel_checksum_sha256
      sprawdź, że tożsamość oryginału w crop_row == source_row
      utwórz płótno original_oriented_width × height, RGB (0,0,0)
      wklej crop w crop_box_oriented
      -> kind=crop, valid_box = crop_box_oriented
  w przeciwnym razie: SOURCE_ORIGINAL_MISSING (jak dziś)
verify_source_identity(frame, source_row)
  kind=original -> dotychczasowe porównanie normalized_pixel_checksum_sha256
  kind=crop     -> tożsamość oryginału z crop_row + suma pikseli cropu
require_inside_valid_box(frame, quads) -> SOURCE_REGION_UNAVAILABLE, gdy quad wychodzi poza valid_box
```

Atest (rewizja 1): obok `originals-cropped/<sha[:2]>/<orig_sha>.jpg` leży
`<orig_sha>.json`, czyli kanoniczny JSON z tożsamością oryginału, tożsamością
cropu, `crop_box_oriented`, wersją narzędzia i polem `attestationSha256` (SHA-256
kanonicznego JSON pozostałych pól). Loader plikowy (`CanonicalSourceLoader`,
`decode_canonical_source_bytes`) wyprowadza ścieżkę cropu i atestu z brakującej
ścieżki oryginału, a nie z bazy. Wiersz `source_image_crops` zapisuje
`attestation_sha256`, a joby porównują go z plikiem. `CanonicalSourceFrame`
dostaje opcjonalne pole `crop` (atest i `valid_box`). Dla ramki z cropu
`source` niesie tożsamość oryginału poświadczoną atestem, a niezmiennik pikseli
sprawdza płótno względem sumy płótna zapisanej w ateście. Konsument
porównujący sumę pikseli z bazą przechodzi tylko dzięki jawnemu atestowi, a
każdy odczyt poza `valid_box` musi sprawdzić `frame.crop`.

Dzięki temu wymiary, quady i renderowanie komórek działają bez zmian.
Kontrole `oriented_width/height` przechodzą. Dotychczasowe porównania pełnej sumy
pikseli zastępuje `verify_source_identity`. Oryginał ma pierwszeństwo, więc
ponowny import tego samego pliku przywraca pełny kadr bez dodatkowej logiki.

### R3. Serwowanie obrazu bez zmian w frontendach

Gdy źródło ma `kind=crop`, endpointy serwujące źródło zwracają JPEG pełnego kadru
złożony z płótna R2: jakość 92, bez EXIF, bo płótno jest już zorientowane.
Plik pochodny trafia do cache roboczego
`data/working/source-frame-previews/<crop_sha>.jpg` (istniejąca klasa GC dla
plików roboczych). ETag = `crop_checksum_sha256`. `_resolve` w
`image_review_assets.py` przestaje zwracać `CHECKSUM_DRIFT` dla brakującego
oryginału z ważnym cropem. Frontendy dostają ten sam rozmiar naturalny co dziś.
Margines poza cropem jest czarny. Stara wersja z cache przeglądarki (`immutable`)
to pełny oryginał w tych samych współrzędnych, więc jest nieszkodliwa.

### R4. Blokady operacji wymagających pełnego kadru

| Operacja na źródle z `original_deleted` | Reakcja |
|---|---|
| Reprocess importu zawierającego takie źródło | 409 `SOURCE_ORIGINAL_CROPPED`, bez joba |
| Korekta/override geometrii strony, propozycja siatki, reinference | dozwolone, jeśli wszystkie nowe quady (z `paddedSourceQuad`) mieszczą się w `valid_box`; inaczej 409 / błąd joba `SOURCE_REGION_UNAVAILABLE` |
| Revert korekty geometrii | jak wyżej, kontrola quadów przywracanej rewizji |
| Ponowny preflight strony (klasyczny i neuronowy) | błąd `SOURCE_ORIGINAL_CROPPED` (preflight szuka plansz w całym kadrze) |
| Budowa kohorty V3 i dataset geometrii | odmowa `SOURCE_ORIGINAL_CROPPED` (rewizja 2: trening geometrii analizuje całą klatkę) |
| Shadow siatek, pipeline importu, rejestracja z kotwicą | odmowa `SOURCE_ORIGINAL_CROPPED` (rewizja 2) |
| Trening symboli, ponowne rozpoznanie symboli, podglądy komórek | R2 z `allow_crop=True`, bez zmiany wyników |

Kwalifikacja (R5) wyklucza źródła w trakcie korekty, więc te blokady chronią
głównie przed przyszłymi korektami.

### R5. Kwalifikacja bloba (czysta funkcja + zapytanie tylko do odczytu)

Blob kwalifikuje się, gdy **każdy** wiersz `source_images` z tą sumą spełnia
wszystkie warunki:

- `geometry_completeness_status` kompletne (bramka D-484, `image_geometry_completeness.py`);
- każdy slot ma bieżącą rewizję geometrii zatwierdzoną, a numer zatwierdzonej
  rewizji jest równy bieżącemu;
- brak oczekujących korekt (`board_cell_geometry_pending`), brak oczekujących
  `grid_issue` i propozycji siatek (`grid_reinference.py`, `grid_geometry_proposals.py`);
- źródło nie jest wykluczone z geometrii strony (`ImagePageSourceExclusionModel`);
- brak aktywnych jobów odwołujących się do źródła lub jego importu;
- import w stanie końcowym (nie staging, nie reprocess).

Oczekujące zatwierdzenie symboli nie wyklucza zdjęcia (ustalenie P1). Kryteria
kolektora P1 (`artifacts/photo-crop-preview-20261014/collect_preview_sources.py`)
są punktem odniesienia; TASK-1044 porównuje z nimi wynik na tych samych 40 źródłach.

### R6. Obszar chroniony i kadr (czysta funkcja)

```text
quads = suma po wierszach bloba: corners plansz, symbolGridQuad, source_quad i
        paddedSourceQuad komórek, regiony etykiet sekwencji zapisane dla źródła
protected = obwiednia(quads)                 # float, przestrzeń zorientowana
box = floor(protected.l - 50), floor(protected.t - 50),
      ceil(protected.r + 50),  ceil(protected.b + 50), przycięte do kadru
raw = mapuj(box, exif_orientation)            # orientacje 1, 3, 6, 8; inne -> UNSUPPORTED_ORIENTATION
raw = (floor(l/iMCU_w)*iMCU_w, floor(t/iMCU_h)*iMCU_h, min(W, ceil(r/iMCU_w)*iMCU_w), min(H, ceil(b/iMCU_h)*iMCU_h))
crop_box_oriented = mapuj_odwrotnie(raw)
```

`iMCU` z próbkowania: 4:4:4 → 8×8, 4:2:2 → 16×8, 4:2:0 → 16×16. Przykłady
(muszą być testami): P1 `bbox [43,0,775,478]`, 1080×589, 4:2:0 → raw
`[32,0,784,480]`; orientacja 6 z niezerowym offsetem; bbox dotykający prawego
brzegu; JPEG progresywny (dozwolony, ten sam algorytm).

Gdy crop nie daje co najmniej 5% oszczędności bajtów, blob dostaje status
podglądu `not_beneficial` i nie jest przetwarzany.

### R7. Weryfikacja cropu

Crop zostaje oznaczony `verified` tylko wtedy, gdy:

1. `jpegtran` zakończył się kodem 0, a wersja narzędzia jest równa skonfigurowanej;
2. wymiary zdekodowanego cropu (po EXIF) są równe `crop_box_oriented`;
3. zdekodowany crop jest identyczny z tym samym obszarem zdekodowanego oryginału,
   poza pasem 1 px przy krawędziach kadru, które nie są krawędziami oryginału;
4. każdy chroniony quad leży co najmniej 8 px od tego pasa;
5. tag EXIF Orientation jest zachowany.

Niespełnienie któregokolwiek warunku daje błąd elementu `SOURCE_CROP_VERIFICATION_FAILED`
z diagnostyką. Plik cropu jest usuwany, oryginał pozostaje, a job przechodzi do
kolejnego bloba (częściowy sukces jest raportowany).

### R8. Dwa joby, dwie zgody

- `source_crop` (nieniszczący): podgląd → token → potwierdzenie → przebieg.
  Tworzy pliki cropów i wiersze `verified`. Oryginały pozostają, a loader
  nadal ich używa.
- `source_original_deletion` (niszczący): osobny podgląd z listą blobów,
  bajtami i ostrzeżeniem, że nie ma kopii zdjęć. Wymaga tokenu i jawnego
  potwierdzenia. Przed usunięciem każdego oryginału job ponownie sprawdza R5
  dla wszystkich wierszy bloba, sumę pliku cropu, stan `verified`, brak
  aktywnych jobów i sumę oryginału. Potem usuwa plik (bez kwarantanny, zgodnie
  z decyzją operatora) i ustawia `original_deleted` w tej samej jednostce
  zapisu. Zmiana stanu następuje po udanym `unlink`; przy restarcie plik
  nieobecny przy stanie `verified` jest uzgadniany jako `original_deleted` tylko
  po ponownej weryfikacji cropu.

Oba joby: lane `general`, checkpoint co 100 blobów, wznowienie po restarcie bez
powtórzenia zakończonych blobów, limit czasu `jpegtran` 30 s na plik. Brak
narzędzia daje błąd joba `JPEGTRAN_UNAVAILABLE`, zanim powstanie jakikolwiek plik.

### R9. Narzędzie

`jpegtran.exe` z libjpeg-turbo 3.2.0 w
`.tooling/libjpeg-turbo-3.2.0/bin/` (nieśledzone przez Git), ścieżka
konfigurowalna przez `GAME_PREDICTOR_JPEGTRAN_PATH`. Instalator
`libjpeg-turbo-3.2.0-vc-x64.exe`, SHA-256
`662761D8BA8DAE04AEC74023EBAECEB856C2B56B9B59CFD180759D26300DDA42`, podpis
SignPath Foundation; instrukcja operatorska w TASK-1047. Bez nowej zależności
Pythona.

### R10. Cleanup i ponowny import

Cleanup źródeł gry (TASK-1042, `cleanup_repository.py`) usuwa także plik cropu
i wiersz `source_image_crops`, gdy znika ostatni wiersz `source_images` bloba.
Obowiązują te same reguły współdzielenia. Ponowny import pliku z usuniętym
oryginałem kopiuje oryginał jak dziś (`ensure_original`), a loader znów używa
pełnego kadru.

## 5. Zadania

Numeracja: TASK-1043–1050 i D-562 były wolne na `main` (v1.7.400) i na otwartych
gałęziach 2026-10-17. Przed utworzeniem plików tasków sprawdź ponownie.

### Etap A — bez zmian zachowania dla istniejących danych

#### TASK-1043 — Decyzja D-562, dokumentacja i czyste funkcje kadru

- Goal: D-562 i wymagania opisują przycięty wariant, a czyste funkcje R5–R7
  mają testy z przykładami.
- Scope: wpis D-562 (`DECISION_LOG.md`, `decisions/DECISION_LOG_2026.md`);
  `requirements/IMAGE_INGESTION.md` (punkty o niezmiennym managed original,
  sekcja 2), `architecture/DATA_MODEL.md`, `architecture/SYSTEM_ARCHITECTURE.md`
  (tożsamość managed original); nowy `domain/source_crop_region.py` (proponowany):
  obwiednia, margines, mapowanie orientacji 1/3/6/8, wyrównanie iMCU, reguła
  `not_beneficial`, reguła maski weryfikacji R7 (na tablicach numpy, bez IO).
- Acceptance: przykłady R6 jako testy; orientacje 2/4/5/7 → `UNSUPPORTED_ORIENTATION`;
  kadr zawsze zawiera obwiednię + margines albo brzeg obrazu.
- Tests: `services/api/tests/test_source_crop_region.py` (proponowany).

#### TASK-1044 — Migracja `source_image_crops` i zapytanie kwalifikacji

- Goal: tabela R1 i zapytanie R5 tylko do odczytu, zgodne z P1 na 40 źródłach.
- Scope: migracja `0167_source_image_crops` (proponowana; numer po sprawdzeniu
  głowy Alembic), model ORM, repozytorium (`storage/source_image_crop_repository.py`,
  proponowane), zapytanie kwalifikacji z grupowaniem po blobie i powodem
  wykluczenia.
- Acceptance: migracja upgrade/downgrade na `*_test`; test integracyjny
  PostgreSQL dla blobów współdzielonych, korekty w toku, `grid_issue`,
  wykluczenia i aktywnego joba; zestawienie zgodności z manifestem P1 jako
  raport (różnice wyjaśnione, nie ukryte).
- Zgoda: migracja bazy operatora poza tym taskiem, w przejściu stop usług →
  scalenie → `db:migrate` → start.

#### TASK-1045 — `SourceFrame` i odczyty w workerze

- Goal: każdy odczyt źródła w workerze przechodzi przez R2.
- Scope: `domain/source_frame.py` (proponowany); migracja konsumentów z sekcji 1
  (wspólny loader i odczyty bezpośrednie workera), `require_inside_valid_box` w
  renderowaniu komórek i reinference; potwierdzenie `geometry.py` i
  `rectification.py`; blokada preflight `SOURCE_ORIGINAL_CROPPED`; kohorty V3
  (`grid_cohort_dataset.py`) przez R2.
- Acceptance: test regresyjny „oryginał obecny” daje bajtowo te same wyniki co
  przed zmianą (render specs, sumy komórek); fixture z cropem (orientacja 1 i 6)
  daje identyczne piksele komórek; quad poza `valid_box` → `SOURCE_REGION_UNAVAILABLE`.
- Tests: worker `test_source_frame*.py`, istniejące testy konsumentów.

#### TASK-1046 — `SourceFrame` w API, serwowanie i blokady

- Goal: API serwuje pełny kadr dla cropów i blokuje operacje z R4.
- Scope: `image_review_assets._resolve` i endpointy z sekcji 1 (R3, cache
  `source-frame-previews`), `virtual_cell_previews.py`, `virtual_grid_geometry.py`,
  `geometry_correction_reverts.py`, `grid_training_cohort_artifacts.py`,
  `v7_label_geometry_calibration.py`, `review_assets.py`,
  `image_import_geometry_guard_preview.py`; blokady reprocess i korekt (R4);
  kody błędów w OpenAPI, regenerowany klient, testy żądań.
- Acceptance: obraz serwowany dla cropu ma wymiary oryginału, a nakładki w
  Adminie i Reviewerze są poprawne (test interakcji z fixture); bez cropów
  odpowiedzi są bajtowo jak dziś.

### Etap B — joby i panel

#### TASK-1047 — Job `source_crop` (podgląd i przebieg)

- Goal: trwały job tworzy i weryfikuje cropy według R6–R8 bez zmiany oryginałów.
- Scope: typ joba, endpointy `/admin/image-storage/source-crop-previews` i
  `/source-crop-runs` (proponowane, wzorzec `storage_gc`), adapter `jpegtran`
  (R9), handler workera z checkpointem, podgląd z liczbą kwalifikujących się
  blobów, szacunkiem bajtów i powodami wykluczeń, instrukcja instalacji narzędzia
  w `guides/LOCAL_OPERATION_GUIDE.md`; pion API: backend, OpenAPI, klient,
  wrapper, test żądania.
- Acceptance: restart workera w połowie przebiegu kończy job bez duplikatów;
  błąd weryfikacji jednego bloba nie przerywa przebiegu; oryginały mają
  niezmienione SHA-256, rozmiar i mtime.

#### TASK-1048 — Job `source_original_deletion` i cleanup

- Goal: usuwanie oryginałów zweryfikowanych cropów z podglądem, potwierdzeniem
  i ponowną weryfikacją R8, plus spójny cleanup R10.
- Scope: typ joba, endpointy podglądu i przebiegu, handler, rozszerzenie
  `cleanup_repository.py` o pliki i wiersze cropów, testy integracyjne.
- Acceptance: blob z nowym niekwalifikującym się wierszem nie jest usuwany;
  przerwanie po `unlink` przed zapisem stanu jest uzgadniane po restarcie;
  cleanup gry usuwa crop tylko przy ostatniej referencji.

#### TASK-1049 — Panel Storage: przycinanie i usuwanie oryginałów

- Goal: operator uruchamia oba joby z panelu Storage z podglądem i postępem.
- Scope: `apps/admin/src/features/storage/storage-workspace.tsx` i nowe
  komponenty sekcji „Przycinanie zdjęć” (proponowane): zakres (gra / wszystkie),
  podgląd z listą i wykluczeniami, potwierdzenie, postęp, wynik; osobny,
  wyraźnie ostrzegający krok usuwania oryginałów („brak kopii zdjęć”).
- Acceptance: testy stanu i interakcji; dotychczasowe zachowanie inventory i GC
  bez zmian (test regresyjny).

### Etap C — pilotaż

#### TASK-1050 — Pilotaż na 40 źródłach P1 i odbiór

- Goal: zmierzony wynik na danych operatora dla 40 blobów P1 i decyzja o
  pełnym przebiegu.
- Kroki, każdy z osobną zgodą operatora: migracja `0167`; `source_crop` dla
  40 blobów; kontrola Admina i Reviewera na tych źródłach (nakładki, podglądy
  komórek, trening/kohorta w trybie odczytu); `source_original_deletion` dla
  40 blobów; ponowna kontrola; raport w `ai_docs/quality/` z bajtami, czasem
  na bloba i ekstrapolacją czasu dla całej kwalifikującej się puli.
- Poza zakresem: przebieg na całej bibliotece (osobna zgoda po raporcie).

## 6. Mapa wymaganie → task → weryfikacja

| Wymaganie | Task | Weryfikacja |
|---|---|---|
| Kadr obejmuje wszystkie siatki + 50 px | 1043, 1047 | testy R6, kontrola zawierania w R7 |
| Bezstratność w obszarze chronionym | 1043, 1047 | R7 punkty 3–4 na fixture i w pilotażu |
| Bez zmian geometrii i zatwierdzeń | 1045, 1046 | regresja „oryginał obecny”, identyczne render specs |
| Wykluczenie siatek w korekcie | 1044 | testy integracyjne R5 |
| Uruchamianie z aplikacji z podglądem | 1047–1049 | testy endpointów i UI |
| Usunięcie oryginałów po weryfikacji | 1048, 1050 | testy integracyjne, raport pilotażu |
| Brak regresji Admin/Reviewer | 1046, 1049, 1050 | testy interakcji, kontrola ręczna w pilotażu |

## 7. Odbiór całego przepływu

Na danych operatora, po TASK-1050: 40 blobów P1 ma `original_deleted`, pliki
oryginałów nie istnieją, a crop ma zweryfikowane sumy. Podglądy komórek tych plansz
są identyczne jak przed pilotażem (porównanie sum zapisanych przed i po).
Reviewer i Admin wyświetlają źródła z poprawnymi nakładkami. Reprocess importu z
tymi źródłami zwraca `SOURCE_ORIGINAL_CROPPED`. Zajętość `data/originals`
zmalała o zmierzoną liczbę bajtów.

## 8. Ryzyka i niewiadome

- **Nieodwracalność:** po usunięciu oryginału nie da się odzyskać obszaru poza
  kadrem ani pełnej sumy pikseli. Przyszła korekta geometrii poza kadrem jest
  niemożliwa. Ryzyko przyjęte przez operatora; ograniczają je R5, R8 i pilotaż.
- **Pokrycie konsumentów:** odczyt z pominięciem R2 zadziała na brakującym
  oryginale błędem, a nie po cichu, bo plik nie istnieje. Ryzyko dotyczy
  plików pozostawionych w stanie `verified`. TASK-1045 zawiera wyszukiwanie
  `rg` wszystkich otwarć `data/originals` jako kryterium.
- **Regiony etykiet sekwencji (V7):** nie ustalono, czy wszystkie regiony
  OCR etykiet są zapisane per źródło. TASK-1044 ustala źródło tych quadów albo
  oznacza źródła bez nich jako niekwalifikujące się.
- **Czas pełnego przebiegu:** nieznany; mierzy go TASK-1050.
- **Szacunek oszczędności:** −30% dotyczy próbki P1; podgląd joba podaje
  rzeczywistą pulę kwalifikujących się blobów.
- **Scalanie:** kod etapu A wymaga migracji `0167`. Zgodnie z AGENTS.md nie
  scalać do `main` przed jej wykonaniem na bazie operatora (osobna zgoda).
- **Koszt:** etapy A–C to duża zmiana wielomodułowa (migracja, ok. 25 plików
  workera i API, 2 joby, UI, testy integracyjne). Wymaga zgody na koszt przed
  uruchomieniem etapu.

## 9. Przypisanie modeli do zadań

Dostępność modeli Codex do audytu sprawdza skill `audit-task`
(`scripts/audit_task.ps1`) w chwili audytu; przy niedostępności obowiązuje jego
procedura zastępcza i aktualizacja tej tabeli.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1043 | `claude-opus-5-5` | `high` | Decyzja zmieniająca wymaganie niezmienności oryginałów i geometria kadru z orientacjami. | Tak: Codex `gpt-6-astra` / `high` |
| TASK-1044 | `claude-opus-5-5` | `high` | Migracja i zapytanie kwalifikacji decydują o tym, co zostanie nieodwracalnie usunięte. | Tak: Codex `gpt-6-astra` / `high` |
| TASK-1045 | `claude-opus-5-5` | `high` | Wiele konsumentów workera, regresja bajtowa wyników. | Tak: Codex `gpt-6-astra` / `high` |
| TASK-1046 | `claude-opus-5-5` | `high` | Pion API, serwowanie i blokady operacji geometrii. | Tak: Codex `gpt-6-astra` / `medium` |
| TASK-1047 | `claude-opus-5-5` | `high` | Trwały job z checkpointem i narzędziem zewnętrznym. | Tak: Codex `gpt-6-astra` / `high` |
| TASK-1048 | `claude-opus-5-5` | `xhigh` | Jedyny krok niszczący dane bez kopii; wyścigi i restart. | Tak: Codex `gpt-6-astra` / `high` |
| TASK-1049 | `claude-sonnet-5-5` | `high` | UI według istniejącego wzorca panelu Storage; eskalacja do `claude-opus-5-5`, gdy potrzebna zmiana API. | Nie |
| TASK-1050 | `claude-opus-5-5` | `high` | Operacje na danych operatora z kolejnymi zgodami i raportem. | Nie |
