---
title: TASK-0804 — V3-C: raport porównawczy silników siatek i rekomendacja
status: done
last_updated: 2026-10-04
---

# TASK-0804 — V3-C: raport porównawczy i rekomendacja

## Status

`done`

## Goal

Raport w `ai_docs/quality/` porównuje silnik produkcyjny, `neural_grid`
(run 1, run 2, model doszkolony na Mumiach) i `hybrid_v3` na zamrożonym
development, zbiorze złotym 777 oraz — jednorazowo — na holdoutach innych
gier, i kończy się rekomendacją: promować do trybu shadow, zbierać dane
(konkretna lista) albo zakończyć.

## Context

Etap V3-C planu. Stan: run 1 (preset A, `43933ac8…e2e6`, eksport
`exports\2cd19738367121e6-round3`) i run 2 (preset B, `ff03b1d7…f31d`, bez
oceny i eksportu) — oba ok. 92% na development 777; run 3 = doszkalanie na
Mumiach (`5bc98156…aedc`, eksport iteracji 3
`exports\iteration03-f896da7196431be2`); bramka `hybrid_v3` skalibrowana dla
runu 1 (`RUN1_DEVELOPMENT_THRESHOLDS`). Przegląd etykiet operatora: S 2,0%
ścisłe / 0,3% luźne błędne, B 0%. Analiza runu 1: większość „błędnych”
plansz S to błędy etykiet.

## Dependencies / entry conditions

- Snapshot 777 v2 `production-geometry-snapshots\286f2e37…df59` z rolą
  `gold` (102 zdjęcia, 459 plansz G; 249 w rodzinach niewidzianych w
  treningu).
- Zdjęcia Mumii: 4 zdjęcia holdoutu doszkalania (ledger
  `neural-grid-runs\finetune-D\ledger.json`).
- Holdouty D-456 w labie: Reels (`final_test`) i Treasure (`unseen_game`) z
  ręcznymi siatkami labu (częściowymi: ok. 30 siatek każda, kilka na
  zdjęcie). Nie były nigdy czytane przez kod V3.
- GPU wolne (żaden run nie trwa); budżet treningu nie jest potrzebny.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Ocena dowodów, jednorazowy odczyt
holdoutów, rekomendacja z ograniczeniami. Audyt zawieszony decyzją
operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (V3-C, ryzyka)
- `ai_docs/process/DECISION_LOG.md` (D-483, D-484, D-480–D-490)
- `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`,
  `GRID_V3_HYBRID_GATE_20261002.md`, `GRID_V3_TRAINING_SNAPSHOT_20261002.md`,
  `VISION_LAB_HYBRID_20260927.md`

## Scope

1. Ocena i eksport ONNX runu 2 (istniejące komendy `evaluate`, `export`).
2. **Pierwotny wynik silnika produkcyjnego dla zdjęć S** (propozycja z
   TASK-0803): rozszerzenie eksportera TASK-0800 o plik
   `production-originals.jsonl` — dla zdjęć roli `development` i `gold`
   snapshotu v2 ostatnia automatyczna rewizja geometrii źródła
   `structured_opencv_v1` sprzed pierwszej rewizji ręcznej, z węzłami per
   plansza i jawnym brakiem; odczyt bazy wyłącznie `READ ONLY`.
3. Ocena na development i na `gold` (D-483, te same definicje) dla:
   silnika produkcyjnego (pierwotny wynik), run 1, run 2, modelu po
   iteracji 3, `hybrid_v3` (odniesienie = pierwotny wynik produkcji; progi
   z kalibracji runu 1 — bez ponownej kalibracji na `gold`). Na `gold`
   osobno: rodziny widziane i niewidziane w treningu.
4. Jednorazowy odczyt holdoutów Reels i Treasure: na siatkach częściowych
   mierzone tylko plansze z etykietą (odzysk, NME, poprawność planszy);
   bez miar „zdjęcie kompletne” i „fałszywe plansze” (etykiety niepełne) —
   raport mówi to wprost. Mumie: 4 zdjęcia holdoutu.
5. Taksonomia błędów na `gold` (obejrzane, nie zgadywane): ręka, odblask,
   skrajna kolumna, przeskok okresu, plansza częściowa, błąd etykiety —
   z obrazkami porównawczymi dla co najmniej 20 przypadków.
6. Koszt czasu: ONNX CPU na zdjęcie dla każdego modelu.
7. Rekomendacja z uzasadnieniem i listą braków.

## Out of scope

- Trening, kalibracja progów na `gold` lub holdoutach, zmiany w aplikacji
  produkcyjnej (TASK-0805), symbole.

## Acceptance criteria

- [x] Każdy z holdoutów (`gold`, Reels, Treasure) odczytany dokładnie raz
      przez zamrożone modele i progi; zapis w raporcie, który model i które
      progi; brak ponownej kalibracji po odczycie.
- [x] Tabele per silnik: metryka nadrzędna D-483, image-macro, odzysk
      plansz, NME mediana/p95, fałszywe plansze — z przedziałami ufności
      tam, gdzie próba jest mała.
- [x] Silnik produkcyjny zmierzony na pierwotnym wyniku (nie na
      korekcie); zdjęcia bez pierwotnego wyniku wypisane z powodem.
- [x] Taksonomia błędów z obrazami.
- [x] Rekomendacja i lista braków.
- [x] Żadnego zapisu do bazy; eksporter tylko do odczytu.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

Zdjęcia `gold` mają też plansze U (bez etykiety oceny) — mierz tylko
plansze G; miara „zdjęcie kompletne” na `gold` liczona na zdjęciach, w
których wszystkie plansze są G (22 zdjęcia), osobno i wyraźnie opisana.
Holdouty labu czytaj przez istniejący katalog i magazyn anotacji labu
tylko do odczytu (magazyn jest używany przez stronę 8105 — kopia albo
krótka blokada z ponowieniem).

## Expected files

- Istniejące: `scripts/vision_lab_geometry_export.py`, moduły
  `vision_lab/neural_grid_*`, `hybrid_v3_*`.
- Nowe (proponowane): skrypt oceny porównawczej, raport
  `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "neural_grid or hybrid_v3 or production_geometry or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

## Outcome

### Changed

- Run 2 (zakres 1): `neural_grid_runs evaluate` (development, GPU: 553/600 =
  92,17%, `evaluations\d623eebfc876c7f3-best-development.json`) i `export`
  (`exports\d623eebfc876c7f3-round9`, parity PASS: 16 zdjęć / 144 plansze,
  0,0016 px).
- Eksporter `scripts/vision_lab_geometry_export.py`: tryb
  `--production-originals-for` / `--originals-roles` (`run_originals_export`,
  tylko `READ ONLY`); czyste reguły w `vision_lab/production_geometry.py`
  (`select_production_original`, `original_board_nodes`). Wynik
  `production-geometry\production-originals-777-20261004` (702 zdjęcia, 700 z
  pierwotnym wynikiem, 2 bez — `PRODUCTION_ORIGINAL_NO_AUTOMATIC_REVISION`;
  2 763 kontrole z manifestem renderu: 0,0 px).
- Nowe `vision_lab/grid_v3_comparison.py` (ocena celów D-483 z planszami
  znanymi, ale nieocenianymi, i z etykietami częściowymi; CI Wilsona i
  bootstrap; produkcja, run 1, run 2, iteracja 3, `hybrid_v3`; komendy
  `development`, `report`, `timing`) i `vision_lab/grid_v3_sealed.py`
  (jednorazowy odczyt holdoutów: rejestr `ledger.json` zapisywany przed
  odczytem, odmowa powtórzenia, `--confirm-single-read`, `--force-reason`,
  token `SealedRead` dla loaderów `gold`/Reels/Treasure/Mumie, `rehearse` na
  danych nieodłożonych, `inspect-gold` — rysunki z zapisanych wyników bez
  inferencji). Strażnik `require_roles` bez zmian.
- Odczyty: `gold-001`, `final_test-002`, `unseen_game-003`,
  `mumie_holdout-004` (każdy raz, bez wymuszenia) + inspekcja
  `gold-001-inspection-005`; wyniki w
  `game_predictor_vision_data\grid-v3-comparison\`.
- Raport `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`: development
  (produkcja 50,2%, run 1 92,3%, run 2 92,2%, iteracja 3 91,0%; S: produkcja
  0/298, sieci 82–85%), `gold` (plansze G: produkcja 41,4%, sieci
  96,5–97,2%; 22 zdjęcia all-G: produkcja 14/22, sieci 21–22/22),
  `hybrid_v3` (0 błędnych plansz `confident`; pokrycie = podzbiór akceptacji
  produkcji, S 0%), Reels 29/30, Treasure 30/30, Mumie 36/36, taksonomia (76
  braków produkcji na 32 zdjęciach, 17 błędów sieci „tuż za tolerancją”,
  7 przesuniętych etykiet U), czas ONNX CPU 0,173–0,177 s/zdjęcie,
  rekomendacja: shadow z runem 1 w ograniczonym zakresie i lista 8 braków.
- Testy: `services/worker/tests/test_vision_lab_grid_v3_comparison.py` (23),
  nowe przypadki w `test_production_geometry.py` (9) i test PostgreSQL
  `test_production_originals_read_the_engine_revision_before_the_first_manual`.

### Verification results

- `pytest services/worker/tests -k "neural_grid or hybrid_v3 or production_geometry or no_production_storage_imports or grid_v3"`:
  123 passed.
- `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 pytest services/api/tests/integration/test_vision_lab_geometry_export_postgres.py`:
  5 passed (baza `game_predictor_task0800_*` tworzona i usuwana).
- `ruff check services scripts`: tylko wcześniejsze E501 w
  `test_page_geometry_preflight.py`; `ruff format --check` zmienionych
  plików: OK; `mypy --strict` nowych i zmienionych modułów oraz skryptu: brak
  błędów w tych plikach.
- Baza deweloperska: wyłącznie transakcje `READ ONLY` eksportera i zapytania
  kontrolne z `default_transaction_read_only = on`; brak zapisu.

### Not completed

- Commit, wpis w `CURRENT_STATE.md` i przeniesienie pliku do `completed/` —
  zostawione orkiestratorowi.
- Zgodność symboli po cięciu (plan V3-C) — poza zakresem taska (symbole).
- Czas silnika produkcyjnego — `processing_time_ms` pusty, nie zmierzony.
- Produkcja i `hybrid_v3` na grach labu — brak wyniku produkcji, nie mierzone.

### Documentation updates

- `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md` (nowy).
- `ai_docs/guides/VISION_LAB_EXPORT.md` — sekcja o pierwotnym wyniku produkcji.

### Recommended next task

- Decyzja operatora po STOP V3-C: TASK-0805 (shadow z runem 1, zakres z
  sekcji „Rekomendacja” raportu) i zadania danych z listy braków (bramka
  plansz tylko z sieci, losowa próbka G zdjęć zaakceptowanych przez
  produkcję, komplet siatek Reels/Treasure, Gang).
