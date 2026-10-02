---
title: TASK-0802 — neural_grid: sieć widząca cały ekran (dwa stopnie, 5 × 3)
status: in_progress
last_updated: 2026-10-02
---

# TASK-0802 — neural_grid: sieć widząca cały ekran

## Status

`in_progress`

## Goal

Silnik `neural_grid` pod kontraktem `GeometryEngine` wykrywa na całym
zdjęciu wszystkie plansze i wyznacza dla każdej 24 węzły siatki 5 × 3;
jest wytrenowany na snapshocie produkcyjnym v2 w ramach budżetu D-481,
wyeksportowany do ONNX z potwierdzoną zgodnością PyTorch–ONNX i opisany
raportem per run z metryką nadrzędną D-483.

## Context

Etap V3-B planu (realizuje T10 / TASK-0675 dla 5 × 3; D-480–D-483). T05
(`hybrid`) tylko poprawiał propozycje baseline na 90 siatkach i nie
odzyskiwał brakujących plansz. Dane: snapshot
`production-geometry-snapshots\286f2e37…df59`
(`production-geometry-split-v2`): trening 6 000 zdjęć / 54 000 plansz,
development 600 zdjęć / 5 400 plansz, zbiór złoty 102 zdjęcia (459 plansz
G). Operator uruchomił etap 2026-10-02 z budżetem 3 runy × 4 h GPU.

## Dependencies / entry conditions

- Fakt: snapshot v2 opublikowany i zweryfikowany (TASK-0813, `v1.7.157`).
- Fakt: GPU RTX 4050 Laptop 6 GB; środowisko `.venv-vision-lab` w głównym
  checkoucie (`C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab`,
  torch z CUDA); trwały protokół runów labu (`runs.py`, `run_worker.py`,
  `run_contracts.py`, `hybrid_protocol.py`, `hybrid_training.py` jako
  wzorzec: fingerprint, `requestId`, lease, checkpoint v2, budżet trwały).
- Fakt: przegląd etykiet operatora (600 plansz) nie jest jeszcze wykonany;
  trening rusza równolegle decyzją operatora. Raport ma to odnotować.
- Zbiór złoty i holdouty D-456 (`final_test` Reels, `unseen_game` Treasure)
  nie są czytane w tym zadaniu.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Architektura dwóch stopni, trening,
ONNX i kontrakt silnika. Zatrzymaj zadanie, jeżeli smoke nie zbiega, model
nie mieści się w 6 GB albo protokół runów nie pozwala na run 4-godzinny bez
zmiany kontraktu. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (reguły, etap
  V3-B, błędy i przypadki brzegowe)
- `ai_docs/process/DECISION_LOG.md` (D-480–D-485, D-447, D-456, D-461)
- `ai_docs/architecture/VISION_LAB.md`, `ai_docs/requirements/VISION_LAB.md`
  (kontrakty silnika, protokół runów, środowisko treningowe)
- `ai_docs/quality/VISION_LAB_HYBRID_20260927.md` (T05: metryki, parity)
- `ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md`
- `ai_docs/tasks/0675-vision-lab-neural-grid.md` (zakres T10)

## Scope

- Zbiór danych i augmentacje czytające snapshot produkcyjny.
- Model dwustopniowy, strata, dekodowanie, dopasowanie siatki.
- Trening w protokole runów, trzy presety zapisane przed pierwszym runem.
- Eksport ONNX, parity, silnik `neural_grid` pod `GeometryEngine`.
- Ewaluator z metryką nadrzędną i pomocniczymi.
- Smoke (≤ 50 kroków) i uruchomienie runów w ramach budżetu.
- Raport `ai_docs/quality/` per run.

## Out of scope

- `hybrid_v3` i bramka zgodności (TASK-0803), raport porównawczy i odczyt
  zbioru złotego oraz holdoutów (TASK-0804), integracja z aplikacją
  (TASK-0805), topologia 3 × 3, symbole.
- Zmiany w aplikacji produkcyjnej i w bazie.

## Acceptance criteria

- [ ] `neural_grid` implementuje ten sam kontrakt `GeometryEngine` /
      `GeometryResult` co `baseline` i `hybrid`; test zamiany silnika bez
      zmiany odbiorcy przechodzi.
- [ ] Stopień „ekran” nie zakłada 9 plansz: liczba plansz wynika z
      detekcji; test na zdjęciu z 5 i z 9 planszami.
- [ ] Trzy presety z fingerprintami zapisane w repo przed pierwszym runem;
      każdy run trwa najwyżej 4 h GPU (twardy limit czasu w kodzie), jest
      wznawialny z checkpointu, a budżet (3 runy) jest trwały.
- [ ] Wybór checkpointu wyłącznie na zbiorze development snapshotu v2;
      zbiór złoty i holdouty nietknięte (test/strażnik odmawiający ich
      odczytu w tym kodzie).
- [ ] Raport per run: odsetek zdjęć kompletnych i poprawnych, image-macro z
      kosztem braku = 1, odzysk plansz, NME mediana i p95, fałszywe plansze,
      czas treningu, krzywe; te same miary dla silnika produkcyjnego
      (etykiety snapshotu jako odniesienie są z definicji jego wynikiem albo
      korektą — opisz, co to znaczy dla porównania).
- [ ] ONNX wyeksportowany dla najlepszego checkpointu, parity PyTorch–ONNX
      w tolerancji jak w T05, wnioskowanie ONNX na CPU zmierzone (czas na
      zdjęcie).
- [ ] Laboratorium nadal nie importuje `storage` ani `psycopg`.
- [ ] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

### Architektura (z planu; szczegóły do rozstrzygnięcia przez wykonawcę)

1. **Ekran:** zdjęcie skalowane do dłuższego boku 768 px; szkielet
   `MobileNetV3-Large` (wagi ImageNet z torchvision, jeżeli są dostępne
   offline w środowisku — sprawdź; pobieranie wag z sieci wymaga zgody,
   więc przy ich braku trenuj od zera i odnotuj); głowica map ciepła:
   środki plansz i 4 narożniki (TL, TR, BR, BL) z polami powiązań albo
   regresją offsetów narożników od środka — wybierz prostszy wariant, który
   dekoduje quady bez założenia liczby plansz; próg i NMS zapisane w
   presecie.
2. **Plansza:** wycinek wokół quada z marginesem 15%, prostowany do 320 px
   na dłuższym boku; głowica 24 map węzłów (albo regresja sub-pikselowa
   soft-argmax) + maska widoczności 15 komórek; dopasowanie siatki
   projekcyjnej (homografia 6 × 4 węzłów) z odrzuceniem odstających
   (RANSAC albo iteracyjne ważenie); reszta dopasowania zwracana jako miara
   pewności — potrzebna TASK-0803.

Oba stopnie w jednym silniku; stopień 2 trenowany na wycinkach z quadów
etykiet z losowym zaburzeniem (żeby znosił niedokładność stopnia 1).
Augmentacje: perspektywa, rozmycie, szum/kompresja JPEG, odblask (jasna
plama), zasłonięcie prostokątem i kształtem „ręki”, zmiana barwy i
jasności. Dla zasłonięć etykiety pozostają (sieć ma dociągać siatkę z
kontekstu).

Pamięć: 6 GB VRAM — mieszana precyzja, rozmiar wsadu dobrany w smoke;
ładowanie danych bez kopiowania całego snapshotu do RAM.

### Metryki (D-483, zamrożone przed treningiem — zapisz w kodzie i raporcie)

- Dopasowanie predykcji do etykiet: przypisanie węgierskie po IoU quadów,
  próg IoU 0,5.
- Plansza poprawna: NME węzłów (średni błąd węzła / przekątna quada)
  ≤ 0,02 **i** maksymalny błąd węzła ≤ 0,05 przekątnej. Jeżeli T05 używa
  innej normalizacji, zachowaj jego definicję dla miary image-macro i podaj
  obie.
- Zdjęcie kompletne i poprawne: każda oczekiwana plansza ma poprawną
  predykcję i nie ma fałszywych plansz (predykcja bez etykiety o IoU < 0,5
  z każdą etykietą).
- Wybór checkpointu: maksimum odsetka zdjęć kompletnych i poprawnych na
  development; remis → niższe image-macro.

### Presety (zapisane przed runem 1)

Trzy presety o różnych, z góry opisanych hipotezach (np. A: bazowy; B:
silniejsze augmentacje zasłonięć i odblasków; C: wyższa rozdzielczość
stopnia 2 albo dłuższy harmonogram z niższym LR). Run 2 i 3 uruchamia
orkiestrator po obejrzeniu wyniku poprzedniego; wolno pominąć run, nie
wolno zmienić presetu po fakcie (nowy preset = nowa zgoda).

### Uruchamianie runów

Run trwa do 4 h — musi działać jako trwały, odłączony proces protokołu
runów (przeżywa zamknięcie sesji agenta), pisać postęp i checkpointy do
katalogu runu w danych labu oraz kończyć się plikiem wyniku. Wykonawca:
implementuje, robi smoke, **uruchamia run 1 (preset A) jako odłączony
proces** i kończy pracę raportem z dokładnymi komendami: sprawdzenie stanu,
wznowienie, zatrzymanie, ewaluacja i eksport ONNX po zakończeniu. Nie czeka
4 godziny. Ewaluacja po runie i eksport są osobnymi komendami, które
orkiestrator uruchomi.

Trening nie może biec równolegle z ciężkimi operacjami bazy ani testami PG
(limit 8 GB VM WSL; host 31 GB RAM).

### Niedozwolone skróty

- Żadnego odczytu roli `gold`, `final_test`, `unseen_game`.
- Żadnego założenia „9 plansz” w dekodowaniu.
- Żadnego treningu na CPU przy braku GPU — stop z komunikatem.
- Nie zmieniaj istniejących silników `baseline` / `hybrid` ani ich testów.

## Expected files

- Nowe (proponowane) w
  `services/worker/src/game_predictor_worker/vision_lab/`: `neural_grid_data.py`,
  `neural_grid_model.py`, `neural_grid_training.py`, `neural_grid_metrics.py`,
  `neural_grid_onnx.py`, `neural_grid_inference.py`, presety (JSON) i wpis w
  protokole runów; testy w `services/worker/tests/`; raport
  `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`.
- Istniejące: rejestr silników labu, `ai_docs/guides/VISION_LAB_LOCAL.md`.

## Test cases

- Dekodowanie: syntetyczne mapy ciepła dla 5 i 9 plansz → poprawne quady.
- Dopasowanie siatki: węzły z szumem i 3 odstającymi → siatka w tolerancji.
- Metryki: zdjęcie z 8/9 poprawnych → niezaliczone; fałszywa plansza →
  niezaliczone; przypisanie węgierskie.
- Strażnik ról: próba wczytania `gold` → błąd.
- Smoke: 50 kroków na GPU zmniejsza stratę; checkpoint i wznowienie.
- ONNX: parity na próbce development.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "neural_grid or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

Testy wymagające torch uruchamiaj interpreterem `.venv-vision-lab` według
wzorca testów T05. Limit 120 s na testy, smoke do 600 s.

## Risks / open questions

- Etykiety S/B nie są jeszcze ocenione przez operatora; błędy etykiet
  ograniczają osiągalny wynik.
- Development pochodzi z rodzin podobnych do treningu (jedno nagranie) —
  operator przyjął to jako cechę danych.
- Sieć uczona na 777 może nie uogólniać na inne gry; mierzy to dopiero
  TASK-0804.

## Outcome

Stan na 2026-10-02 (wykonawca claude-opus-5-5, worktree `grid-engine-v3`, bez
commita — commit, `CURRENT_STATE.md` i przeniesienie taska należą do
orkiestratora po runach). Status `in_progress`: implementacja, presety, smoke i
start runu 1 gotowe; runy i ocena po runach trwają.

### Changed

- Nowe moduły w `services/worker/src/game_predictor_worker/vision_lab/`:
  `neural_grid_protocol.py` (presety i fingerprinty, `METRIC_DEFINITION`,
  strażnik ról, kontrakt `NeuralGridRunRequest` ≤ 14 400 s, budżet
  `admit_run`), `neural_grid_data.py` (odczyt snapshotu za strażnikiem,
  geometria, augmentacje, cele), `neural_grid_model.py` (MobileNetV3-Large + FPN,
  dwa stopnie, straty), `neural_grid_metrics.py` (D-483, Hungarian),
  `neural_grid_inference.py` (dekodowanie, dopasowanie siatki, `NeuralGridEngine`
  pod `GeometryEngine`, ewaluator, silnik ONNX), `neural_grid_training.py`
  (rundy w protokole runów, heartbeat, checkpoint v2 z najlepszym stanem),
  `neural_grid_onnx.py` (eksport, parity, czas CPU), `neural_grid_runs.py` (CLI:
  start/status/resume/stop/evaluate/export/timing/reference, odłączony worker);
  presety `neural_grid_presets/{A,B,C}.json`.
- `runs.py`: opcjonalne `state_type` i `admit` w `RunManager` (domyślnie bez
  zmian zachowania).
- Testy: `services/worker/tests/test_vision_lab_neural_grid.py` (18 testów).
- Dokumentacja: raport `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`
  (metryki i presety zapisane przed runem 1), sekcja w
  `ai_docs/guides/VISION_LAB_LOCAL.md`.

### Verification results

- `pytest services/worker/tests -k "neural_grid or no_production_storage_imports"`:
  19 passed. Regresja protokołu: `test_vision_lab_runs.py`,
  `test_vision_lab_hybrid.py`, `test_vision_lab_training_core.py` — 33 passed.
  `ruff check` labu i testu: czysto; `mypy --strict` nowych modułów i `runs.py`:
  bez błędów w `vision_lab` (zgłoszenia tylko w niezwiązanych modułach `images/`
  z braku `game_predictor_api` w cienkim venv).
- Smoke A na GPU (`be7e9a0a…`): 40 kroków, strata 16,92 → 3,08, 2,1–2,4
  kroku/s, 5,08 GB VRAM, checkpointy rund zapisane, `succeeded`. Wznowienie
  (`c075281a…`): proces zabity w rundzie 2, `failed/RUN_LEASE_EXPIRED`, `resume`
  z checkpointu rundy 1 → `succeeded` (48 kroków ≤ 50).
- Próba eksportu ONNX na checkpoincie smoke: parity PASS (surowe ≤ 6e-7, węzły
  0,089 px).
- Run 1 (preset A) uruchomiony 2026-10-02 12:57:25 jako odłączony proces:
  run `43933ac8d7d443c8b9079630a83de2e6`, request `ng-train-a-20261002`,
  worker PID 19808 (odłączony od sesji); o 13:00:33 GPU 99%, 2,25 kroku/s,
  strata 7,68 → 1,33 w krokach 50–150; oczekiwany koniec ok. 16:40.

### Not completed

- Wynik runu 1 (ok. 3,7 h), wybór najlepszej rundy, `evaluate`, `export`
  (ONNX + parity najlepszego stanu), `timing` CPU — komendy w raporcie.
- Runy 2 (B) i 3 (C) — decyzja orkiestratora po runie 1.
- Pełne odniesienie baseline labu na 600 zdjęciach (`reference
  --screen-layout-limit 600`, ok. 1,75 h CPU); policzono tylko próbkę 3 zdjęć.
- Uzupełnienie raportu wynikami, commit, `CURRENT_STATE.md`, przeniesienie taska.

### Documentation updates

- `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md` (szkielet z metrykami,
  presetami, smoke i komendami), `ai_docs/guides/VISION_LAB_LOCAL.md`.

### Recommended next task

- Po runie 1: `evaluate`, `export`, `timing`, decyzja o runie 2 (B); potem
  TASK-0803.
