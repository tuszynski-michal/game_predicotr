# Audyt TASK-1166 — ocena zawartości produkcyjnych wycinków

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: nieokreślony w pakiecie
Zakres: 450f9ef11bc08aae5b9e9e5fbba89d1408a020ed oraz zamrożone zmiany niezacommitowane, data 2026-11-08
Runda: 1
SHA pakietu: d072fa83c3ac9ba694640988c129b4c399a84acbfd646523e3009d4792b844e4
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano geometrię, bramkę, obserwator, replay, wiązanie NNinput, odczyt świeżości, SQL v9, migrację 0183 oraz zmianę limitu audytu. Nie znaleziono ścieżki fałszywego PASS. Jeden błąd blokuje jednak prawidłową świeżą regresję na danych z kopiami lub zdjęciami bez etykiet. Pozostałe uwagi to P2.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/worker/src/game_predictor_worker/images/production_cell_run.py:188` — `actual_reg == set(selected["sourceIds"])` zakłada, że każde wybrane źródło jest używane w REG. `sourceIds` obejmuje jednak całe komponenty, także kopie i zdjęcia bez etykiet (`services/api/src/game_predictor_api/domain/grid_content_sampling.py:100-102`). Kopia niereprezentatywna dostaje `blocked` (`services/api/src/game_predictor_api/storage/grid_correction_split.py:517-522`), więc `used=false` (`grid_training_cohort_evidence.py:474-475`). `indexed()` zwraca wyłącznie źródła używane (`services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py:519`). Wyzwalacz: wybrany komponent zawiera dokładną kopię albo zdjęcie bez plansz. Skutek: `freshRegression=false`, `CONTENT_FRESH_REGRESSION_REQUIRED` (`domain/production_cell_evaluation.py:183-184`) i trwałe `not_evaluable` mimo ≥5 pełnych świeżych zdjęć. Błąd działa fail-closed, ale narusza kryterium 4, a fixture ma tylko jedno wybrane źródło (`test_production_cell_frozen_pipeline.py:153-157`). Poprawka: porównać `actual_reg` z `sourceIds` zawężonym do pinów `photoSplit.sources` z `representative` i `eligibleBoards>0`, oraz dodać test z kopią i zdjęciem bez etykiet.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/production_cell_reference.py:161` — pełny replay (dekodowanie A/REG, rendery, JSON do 96 MB na rolę) wykonuje się przy każdym `_evidence`, także w statusie (`grid_recognition_status.py:89`) i przy każdym źródle importu (`production_workflow.py:738`). Skutek: koszt rośnie z każdym odczytem. Poprawka: cache procesu dla samego replayu, kluczowany SHA raportu i detali; `current_render_configuration` wykonywać zawsze.
- [P2-2] `services/api/src/game_predictor_api/storage/production_cell_reference.py:148` — replay czyta `detail["path"]`, a `finish` (`production_cell_run.py:168`) osobno czyta ścieżkę pochodną, bez SHA. Wyzwalacz: podmiana pliku między odczytami lub różne ścieżki. Poprawka: wymusić równość z `detail_path` i przekazać do `finish` zweryfikowane dokumenty.
- [P2-3] `services/worker/src/game_predictor_worker/images/full_board_calibration_observations.py:180` — krawędź `verified_content` powstaje także dla dopasowania bez `bound` lub z remisem, choć obserwator zawartości daje wtedy `inputEvidence=None`. Etykieta trafia do progu A. Poprawka: podnosić rodzaj referencji tylko przy `bound` i `matchAmbiguous=false`.
- [P2-4] `services/api/src/game_predictor_api/domain/production_cell_evaluation.py:175-176` — minimum 5 zdjęć i 15 plansz obejmuje też A, a D-591 definiuje minimum tylko dla REG. Próg nie występuje w `POLICY`. Poprawka: zapisać go w polityce lub ograniczyć do REG.
- [P2-5] `services/worker/src/game_predictor_worker/images/production_cell_evaluation.py:134` — suma kosztów z wartownikiem 1e9 ma krok około 1,2e-7, a tolerancja wynosi około 1e-14. Wyzwalacz: nieobsłużona etykieta i dokładny remis mogą dać różnicę zaokrągleń, więc remis nie zostanie wykryty; ryzyko ogranicza kontrola slotów. Poprawka: `math.fsum` albo osobne liczenie wartowników.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| 1. Wspólny mianownik, renderer, float32→float64, u, ε | spełnione | `images/production_cell_evaluation.py:95-117`, `domain/production_cell_geometry.py:13,166` |
| 2. Stany, missing, valid_box, odrębne NNinput | spełnione | `domain/production_cell_geometry.py:180-212`, `images/production_cell_input.py:87-115` |
| 3. Macierz, wiązanie, brak kompensacji | spełnione | `domain/production_cell_geometry.py:224-276`, `images/production_cell_run.py:251-265` |
| 4. Bramka per gra, świeży REG | niespełnione | P1-1 |
| 5. Niezależne przeliczenie A przed B | spełnione | `images/production_cell_input.py:162-230`, `images/full_board_calibration_run.py:220` |
| 6. v6, para gate/rule, dyspozycja | spełnione | `domain/grid_model_publication.py:173-177`, `storage/source_recording_sql_v9.py:26-33` |
| 7. Świeżość cropu, replay, READ ONLY | spełnione | `storage/production_cell_reference.py:22-33,95-174` |
| 8. Pion API/SDK, migracja, regresje | niezweryfikowane | Przeczytano migrację i DTO; bez generowanego SDK i wykonania testów |
| Limit 1800/1860 s, idle 60 s | spełnione | `scripts/run_claude_audit.py:634,646`, `scripts/audit_task.ps1:103-104` |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `services/worker/tests/test_production_cell_frozen_pipeline.py`: REG z kopią niereprezentatywną i zdjęciem bez plansz daje `freshRegression=true`, a brak wybranego źródła kwalifikowanego daje `false`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_production_cell_frozen_pipeline.py -k fresh`.
- Ten sam plik: pozytywna ścieżka `manifest_input_context` z `rescue` i `board_only`, porównująca `geometry` z recepturą pakietu.

## Zakres przeglądu i ograniczenia

Przeczytano funkcje z pakietu, grupy A i B, `TASK-1166_R1_RETRY_WIRING.diff`, D-591 oraz potrzebny kod próbkowania, datasetu, resolvera i `rescue`. Nie czytano `TASK-1166_R1_RETRY_MECHANICAL.diff` ani generowanego SDK. Testów nie uruchamiano, a wyniki weryfikacji pochodzą z pakietu. Brak dowodu kwalifikacji rzeczywistego modelu.