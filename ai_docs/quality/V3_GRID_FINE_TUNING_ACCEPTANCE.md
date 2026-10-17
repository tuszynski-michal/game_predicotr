---
title: Doszkalanie geometrii V3 — odbiór procesu (TASK-1001)
status: active
last_updated: 2026-10-16
---

# Doszkalanie geometrii V3 — odbiór procesu

Odbiór techniczny planu
[V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md)
na gałęzi `codex/v3-grid-fine-tuning`, przed integracją do `main`. Raport podaje
wyłącznie wykonane pomiary i ich ograniczenia. Nie jest oceną jakości modeli na
danych operatora: rzeczywisty trening, publikacja i aktywacja na Mumii i 777a2
wymagają osobnego polecenia operatora po integracji.

Instrukcja operatora: [V3_GRID_FINE_TUNING_OPERATOR](../guides/V3_GRID_FINE_TUNING_OPERATOR.md).

## 1. Przebieg end-to-end (nowy test odbioru)

`services/api/tests/integration/test_v3_grid_fine_tuning_acceptance_postgres.py`
(PostgreSQL z rolą aplikacji i RLS, CUDA):

| Krok | Komponenty rzeczywiste | Wynik |
|---|---|---|
| Korekty człowieka | writer geometrii V3, 20 zdjęć, korekta zdjęcia 0 do rewizji 2 | 20 zdjęć zapisanych przez writer człowieka, 120 plansz; PASS (59 s) |
| Nagrania i kohorta | rejestr nagrań, role TRAIN/VALIDATION/REGRESSION, przygotowanie, kopiowanie, zamrożenie | trzy nagrania z rolami, kohorta `frozen` po 4 stronach kopiowania; PASS (76 s) |
| Run | serwis runu (podgląd, preset), ponowienie tym samym kluczem | jeden run z presetem podglądu, 1200 kroków; ten sam klucz zwrócił ten sam run; PASS |
| Trening GPU | lane `grid-training`, nadzorca, trener CUDA, SQL store, eksport ONNX z parity, rejestracja kandydata | 1200 kroków, 351 s pracy workera, eksport z parity D-561, kandydat `not_evaluated` zarejestrowany w rejestrze z kohortą runu; PASS |
| Ocena per gra | serwis, handler i SQL store oceny, proof aktualności; silniki ONNX oceny to atrapy | werdykt PASS, dowód aktualności `current`; ponowienie utworzenia oceny zwraca ten sam job |
| Publikacja i aktywacja | sterowanie wersjami, ponowienie obu poleceń tym samym kluczem | publikacja z raportem oceny i aktywacja dla gry; oba polecenia powtórzone tym samym kluczem zwracają te same potwierdzenia |
| Restart | nowy interpreter: resolver importu, magazyn modeli, inferencja CPU wytrenowanego modelu | nowy proces po zamknięciu połączeń rozwiązał wersję aktywną (`resolve_neural_grid_proposal`), magazyn modeli potwierdził pliki, inferencja CPU zakończyła się bez błędu; 0 wykryć na zdjęciu kontrolnym (model po 1200 krokach na danych syntetycznych) |

Wynik końcowy: 1 PASS w 464 s (przebieg 3). Dowody: `artifacts/audits/T1001_e60de9c93059/`
(`progress.json`, `result.json`, katalog runu). Przebieg 1 ujawnił usterkę z sekcji 2,
przebieg 2 przeszedł trening i eksport, a zatrzymał się na długości ścieżki pliku
tymczasowego oceny w katalogu testu (ponad 260 znaków; ścieżka produkcyjna ma ok. 170),
po czym katalog dowodów testu skrócono.

Ograniczenia: silniki ONNX oceny są deterministycznymi atrapami, więc werdykt PASS
dowodzi działania bramki i dowodów, a nie jakości kandydata (pomiar jakości to
TASK-0997 na danych operatora). Wagi bazy są świeżo zainicjalizowane, a zdjęcia
syntetyczne.

## 2. Usterka znaleziona w odbiorze (D-561)

Pierwszy pełny run odbioru (kohorta 30 plansz TRAIN, preset `grid-only-v1`, 1200
kroków, 282 s treningu) zakończył się `GRID_TRAINING_ONNX_PARITY_FAILED`. Odtworzenie
eksportu z obu zapisanych checkpointów (krok 600 i 1200) pokazało przyczynę:
wyjście `board.nodes` to współrzędne węzłów w pikselach płótna (maks. 286 px), a
bramka eksportu porównywała je z bezwzględną tolerancją 1e-4. Różnice torch/ONNX
wynosiły 1,53e-4 i 1,07e-4 px, czyli kilka ULP fp32 (względnie 8,2e-7 i 8,0e-7);
pozostałe wyjścia były w tolerancji (peak 4,2e-7, visibility 6,0e-8). Wcześniejsze
testy GPU (40 kroków) tego nie wykryły, bo wynik zależał od wag.

Poprawka D-561: różnica każdego wyjścia jest dzielona przez max(1, |wyjście torch|),
z tą samą tolerancją 1e-4; NaN i nieskończoność zawsze odrzucają, a nieudane parity
zapisuje pomiar w `parity-failed.json` runu. Drugi run tego samego testu (1200
kroków, 269 s, najlepszy krok 600) wyeksportował kandydata: `board.nodes` 1,22e-4 px
bezwzględnie (stara reguła odrzuciłaby i ten run), 1,03e-6 względnie — PASS. Test
jednostkowy `test_export_parity_is_relative_to_the_output_magnitude` pilnuje, że
błąd 0,05 px przy 286 px i 2e-4 na wyjściu jednostkowym nadal odrzucają.

## 3. Regresje

Wszystkie wyniki na gałęzi po scaleniu `main` v1.7.385 (v1.7.391) i TASK-1000
(v1.7.392); dowody w `artifacts/audits/TASK-1001_REGRESSION/` i
`artifacts/audits/TASK-1001_PGFULL/`.

| Zakres | Wynik |
|---|---|
| API bez PostgreSQL | 3261 PASS, 484 skip, 0 FAIL (5 części i katalog `integration` bez PG) |
| Worker | 3040 PASS, 43 skip, 17 FAIL — ta sama klasa środowiskowa co w TASK-0997: testy laboratorium uruchamiające podproces importują kod `main` przez dowiązanie `.venv` worktree; brak porażek w zmienionych modułach |
| GPU | `test_grid_training_lane_gpu_e2e_postgres.py` i `test_grid_shared_training_gpu_e2e_postgres.py` PASS z regułą D-561 (402 s) |
| Admin | unit 772/772; interakcje 281/291 — dokładnie te same 10 nazw porażek supergier co baseline [HEAD380](TASK-1003_BASELINE_HEAD380.md), 0 nowych; tsc, ESLint (0 błędów), Prettier, build PASS |
| Reviewer | unit 279/279, geometria 95/95, ESLint, tsc, build PASS |
| Klient API | 129/129, `openapi:check` PASS |
| PostgreSQL, pełny zestaw | 506 testów w pierwszym przebiegu: 20 FAIL i 1 ERROR (sklasyfikowane niżej); po poprawkach powtórzenie 26 dotkniętych plików: 241 testów, 236 PASS, 4 skip, 1 FAIL (znana usterka resetu gry) |

Klasyfikacja porażek PostgreSQL, sprawdzona przebiegiem tych samych testów na
czystym `main` v1.7.387 (27 testów, 3 FAIL własne `main`):

- **Nieaktualne testy po migracjach V3 (poprawione, wyłącznie testy).** Testy
  „bieżącego” manifestu importowały v15/v16, a migracja 0166 dopuszcza w
  `game_storage_locations` tylko v17: 16 plików przestawiono na v17 (tak jak TASK-1009
  dla v15), a testy baseline i izolacji gier sprawdzają zgodność z wersją routingu.
  Literały bieżącego manifestu v14/v16 po `upgrade head` (scalanie compact/super
  game, cofanie korekt 0154, seria super game, retencja kohort), oczekiwany head po
  odrzuconym cofnięciu (pomiar jakości, rejestr nagrań — Alembic wycofuje cały
  przebieg), cztery nowe wyzwalacze V3 w `game_data_v2` (routing), capability przed
  0161 w teście paneli wyszukiwarki, wymagany `idempotencyKey` tworzenia gry
  (TASK-1004) w akceptacji M2, dwie głowice Alembic poniżej 0164 w cyklu baseline,
  oraz bramka dopuszczenia jobów gry z TASK-0999 w sześciu testach
  `test_image_batch_store.py`, które modelują kilka importów naraz (fixtura
  `no_job_admission`; bramkę sprawdzają jej własne testy). Test statystyk
  ponownego rozpoznania wybierał grę losowo po UUID i trafiał scenariusz z jedną
  planszą; wybór jest teraz deterministyczny.
- **Współbieżność harnessu:** przekroczenia czasu `DROP DATABASE` przy trzech
  równoległych częściach na jednym klastrze — w przebiegu sekwencyjnym PASS.
- **Stare porażki `main`, na gałęzi PASS:** cykl baseline (`main`: odmowa 0155),
  migracja serii super game i migracja 0154 (`main`: niedopasowany wzorzec odmowy).
- **Znana usterka produktu sprzed V3 (bez zmian, osobne zadanie):** `reset_game`
  usuwa `image_review_items` przed zależnymi wierszami (m.in.
  `image_symbol_review_cells`, `image_board_geometry_pending`) i odmawia z
  `RestrictViolation` dla każdej gry po prawdziwym imporcie, a pliki zarządzane
  usuwa wcześniej niż bazę. Dotyczy `cleanup_reset` (zapisane jako FAIL od TASK-0999)
  i jednego testu retencji kohort; identyczne na `main`. Akcji „usuń dane układu gry”
  w Adminie nie należy używać do czasu poprawki.

Rejestr [obowiązków regresyjnych z TASK-1002](V3_BACKEND_REGRESSION_OBLIGATIONS_20261015.md)
jest zamknięty: izolacja trzech tabel i granica 0158 przechodzą (TASK-1018 oraz
powyższy przebieg).

## 4. Kryteria akceptacji

| Kryterium (TASK-1001) | Wynik | Dowód |
|---|---|---|
| Proces działa po restarcie i utracie odpowiedzi | spełnione | sekcja 1: ponowienie runu, oceny, publikacji i aktywacji tym samym kluczem; nowy interpreter używa aktywnej wersji; trwałość poleceń w Adminie (TASK-1000, testy remount/retry) |
| Obie gry i nowa gra zachowują izolację symboli | spełnione | `test_per_game_isolation_new_game.py` na manifeście v17 (sekcja 3); modele symboli nie są częścią przebiegu (D-549) |
| Stara 777 ma regresję | spełnione | resolver i aktywacja odmawiają gry kodu `7` (`GRID_MODEL_HISTORICAL_GAME_PROTECTED`, testy resolvera, publikacji i snapshotów w zestawie API); `test_historical_grid_acceptance_postgres.py::test_operation_cannot_cross_game_and_legacy_7_is_excluded`; raporty historyczne kodu 7 w Adminie (`v3-classical-ui-removal`) |
| Rzeczywiste liczby i ograniczenia bez domniemanych wyników | spełnione | sekcje 1–3 podają tylko zmierzone wartości; jakość modeli na danych operatora jest poza odbiorem (sekcja 5) |
| Kontrole, audyt i ograniczenia w Outcome; dokumentacja zgodna z zachowaniem | w tasku | `tasks/completed/1001-v3-grid-fine-tuning-acceptance.md`, instrukcja operatora |

## 5. Czego odbiór nie obejmuje

- Rzeczywistego treningu, oceny, publikacji i aktywacji na danych Mumii i 777a2:
  wymagają polecenia i budżetu operatora po integracji (TASK-1006 eksperyment).
- Odbioru w przeglądarce na działającej aplikacji: po integracji i restarcie usług.
- Problemu pominiętych zdjęć importu 777a2 (staging 60a7bc4d, 1962 zdjęć bez
  przypisania plansz): ścieżka importu nie należy do tego planu; osobna propozycja.

## 6. Integracja do `main` i test po migracji (2026-10-16)

Za zgodą operatora (migracja oryginalnej bazy, zatrzymanie i wznowienie usług;
kopia `D:\game_predictor_backup` jako plan awaryjny):

- Gałąź scaliła `main` v1.7.389 (TASK-1040/1041, v1.7.395); preflight: fast-forward
  możliwy, `main` = `origin/main`, checkout czysty. Zatrzymano worker `general`
  (skryptem lane), API, Admin i Reviewer; aktywnych jobów nie było.
- `main` przesunięto fast-forward do v1.7.395 `660b6415` i wypchnięto; potem
  poprawka v1.7.396 `b263c738` (niżej). Zależności npm bez zmian (tylko skrypty),
  więc `npm install` nie był potrzebny; klient API jest używany ze źródeł.
- `npm run db:migrate`: capability, Alembic `0155_board_search_panels` →
  `0166_grid_model_evaluation` (13 s), uprawnienia roli aplikacji zgodne. Wszystkie
  4 lokalizacje gier mają manifest v17; przypisania Mumii, 777a2 i 777v2 zachowane.
- Restart z `main`: API 8000 (`/api/v1/health` ok), Admin 3000 (`next dev`), build i
  start Reviewera 3001, worker `general` (7 wątków) i lane `grid-training` z
  interpreterem `.venv-vision-lab` z checkoutu C (parametr skryptu); oba lane mają
  aktualny heartbeat w `worker_lane_runtime`, logi bez błędów.
- Test na `main`: odczyty V3 API (wersje, domyślna, przypisania, kohorty, runy,
  nagrania, historia, pomiary) dla Mumii i 777a2 — 200; sekcja „Geometria V3” w
  Adminie renderuje się na danych operatora. Wykryto i naprawiono (v1.7.396):
  panele prosiły o 100 kohort i 200 nagrań na stronę, ponad maksima API (50 i 100),
  więc trening pokazywał błąd odczytu, a formularz kohorty brak nagrań; rozmiary
  stron są stałymi sprawdzanymi testem z maksimami OpenAPI; po przeładowaniu
  wszystkie odczyty 200. 17 testów worker, które w worktree padały środowiskowo,
  na `main` przechodzi (17/17).
- Nie wykonano: rzeczywistego treningu, publikacji ani aktywacji (decyzje operatora),
  usunięcia worktree i gałęzi roboczej (osobna zgoda), trwałego ustawienia zmiennej
  `GAME_PREDICTOR_GRID_TRAINING_PYTHON`.
