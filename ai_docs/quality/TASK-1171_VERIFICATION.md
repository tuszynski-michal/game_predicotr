---
title: TASK-1171 — Weryfikacja porównania produkcyjnych cropów
status: active
last_updated: 2026-11-09
---

# TASK-1171 — Weryfikacja

Implementacja T2 w `worktrees/grid-symbol-crop-preview`. Wynik dotyczy narzędzia
diagnostycznego. Operatorowy wynik jakości pozostaje `not_evaluable`; nie jest to
kwalifikacja modelu ani zmiana defaultu. Po Opus R1 wykonano jedną rundę poprawek;
mapowanie ustaleń jest w `TASK-1171_FIXES_R1.md`. Focused R2, mapa kodu,
docs:check, task-close i commit pozostają po stronie root po freeze wykonawcy.

## Kryteria i dowody

| Kryterium T2 | Implementacja / dowód |
|---|---|
| Wykonywalny producent | CLI czyta istniejącą kohortę, current source/owner, role/copy closure, bieżące geometrie, obrysy, approval events i modele w jednej transakcji REPEATABLE READ READ ONLY. Nie wymaga ręcznego JSON. |
| Rzeczywisty renderer 0.08/0.0 | Istniejący VirtualCellRenderer przez ProductionContentObserver; stały rozmiar, preprocessing, wagi i źródło. PNG, renderSpec i SHA pochodzą z faktycznego renderu. Test nieregularnych internal nodes zachowuje różnicę exact-cell-quad / outer-board-homography-inset. |
| Human → model | Dokładne current human nodes, następnie jedna rzeczywista inferencja przypiętego grid modelu na zdjęcie, wspólna dla obu marginesów. Runtime `load_assessment_engine` zachowuje routing/rescue; brak modelu nie jest zastępowany punktami ręcznymi. |
| Stałe instancje i brak kompensacji | Existing matching, coverage_matrix, assess_content i summarize_content. Raport per game/role/geometry zachowuje również niedostępne źródła w selectedInstances. New cut/wrong-cell/tie/foreign/match ambiguity, class degradation i false accept blokują rekomendację mimo poprawy clipping. |
| Ręczne klasy tych samych komórek | Current approved crop/revision/owner i aktywna klasa; dokładny human approve/reassign event. SELECT wiąże także autorytatywny target.review i source_replacement_current_v1. Regresja odrzuca starszy review dla tego samego board/cell/geometry. Zatwierdzone RGB weryfikowane ponownym renderem. Status/confidence/assignment_source sam nie daje GT. |
| Prawdziwy klasyfikator | LocalSymbolOnnxAdapter, pinned SHA, klasy, temperature i preprocessing. Test wykonuje rzeczywiste ONNX CPU bez treningu. Policy wymaga zgodnego modelVersion/calibrationVersion i jawnego runtimeAutoAccept. Sam calibrated threshold bez runtime pin daje unavailable/null. Known disabled pozostaje osobnym stanem: zero decyzji wynika z konfiguracji, nie dowodzi jakości automatu. Legacy M6 policy nie nadaje zakresu LAB_RGB. |
| LAB_RGB osobno | Istniejący require_iteration_candidate i osobny snapshot/weights. Test wykonuje prawdziwy wariant ONNX LAB, pełne RGB96 i istniejące preprocessing do64; odrzuca niepoprawne RGB64. LAB reference nie podszywa się pod legacy08/00. |
| Blind i aliasy przed pikselami | Current recording_photo_context_v3 i alias/component IDs źródeł zapisanych sesji. TRAIN/helpery wykluczają wszystkie sesje, także frozen. Testy blokady kończą się przed geometry/frame; rzeczywisty pilot przeszedł tę kontrolę. |
| A bez wiecznej blokady | Latest content_pin wymaga humanApproved/manual_blind/pass2, frozen i zgodności progress.pass2. Wszystkie wybrane A refs wiążą jeden kwalifikowany raport u/δ. Test pokazuje, że inna stara pass1 nie blokuje właściwej frozen referencji. Blank/missing current refs blokują przed pikselami. A nie zapisuje PNG, visualExportAllowed=false. |
| Rzeczywiste wejście NN bez GT | Wrapper obserwuje SHA faktycznie wykonanego tensora. Produkcyjna transformacja wybranego BASE/rescue musi odtworzyć ten SHA. Testy BASE i WIDE, przywrócenie runnera, aktualny pilot: screen i wszystkie9board inputs dostępne mimo0contentGT. Bez przybliżonego bbox. |
| Trwałość | Niezmienne capture/report/PNG, granice ścieżek i zakaz junction/symlink. Atomowe publikowanie nie zastępuje istniejącego pliku; regresja dwóch równoległych writerów. Zmieniony PNG odrzuca replay, zgodny replay nie wywołuje inference. Nowy proces CLI zachował report bytes po ponownym odczycie ochrony/pinów i walidacji źródeł/modeli. |
| Brak danych | Brak contentGT, u/δ, modelu, klasy lub acceptance policy ma jawny powód. J/10/ramki/ciemne symbole w danych operatora nie mają w tym zadaniu dopisanych GT; jakości grafik nie zadeklarowano na podstawie samej wizualizacji. |

## Wykonane kontrole

Po R1 gate wymaga spadku clipped+missing i zakazuje każdej nowej missing instance.
Testy obejmują wszystkie damage counters oraz prawdziwe przejęcie sąsiada przez
renderer0 mimo fewerClipped. Human GT obejmuje także zweryfikowane aktualne
board_synchronized. Runtime pin jest osobnym zwalidowanym current diagnostic
envelope, bez przypisywania go historycznemu importowi. Rzeczywisty autor
candidate_gate v2 i repozytoryjny artefakt M6 v1 przechodzą producenta i konsumenta;
candidate jest osiągalny przy manual/disabled, brak runtime pozostaje unavailable.
LAB ma absolute-reference i `labGames`, a screen/rescue mismatch daje partial.
Sealed internal A JSON zawiera metadane do replay/metryk, z zaakceptowanym lokalnym
ryzykiem. Nie jest publicznym wejściem HTML: wizualizować wolno tylko TRAIN oraz
visualExportAllowed=true. Szczegółowa mapa dowodów znajduje się w FIXES_R1.

Każdy proces miał limit120s, logi UTF-8; PYTHONPATH wskazywał własne
`services/api/src;services/worker/src;services/test_support` w worktree.
Interpreter: `D:/game_predicotr/.venv/Scripts/python.exe`.

- `pytest services/worker/tests/test_production_crop_comparison.py services/worker/tests/test_production_cell_observations.py --basetemp=D:/game_predicotr/artifacts/t1171-r1-unit-final -q`:
  **47 passed, 18.58 s**, jeden FutureWarning torch, log `artifacts/t1171-r1-unit-final.log`.
- `pytest services/api/tests/integration/test_production_crop_capture_postgres.py --basetemp=D:/game_predicotr/artifacts/t1171-r1-pg5 -q -s`:
  **1 passed, 25.34 s**, log `artifacts/t1171-r1-postgres.log`. Własna jednorazowa
  baza PostgreSQL, migracje do bieżącego schematu i cleanup kontekstu. Prawdziwe
  save_resolution tworzy board_synchronized, readonly _classes zwraca15klas.
  SQL content_pin wybiera current frozen A mimo starej pass1, protected_source
  nadal chroni całe źródło przed helperami TRAIN. Małe syntetyczne adnotacje
  służą testowi readera, nie kwalifikacji danych operatora.
- `ruff format` i `ruff check` wszystkich9 zmienionych/nowych plików Python:
  **PASS**, log `artifacts/t1171-r1-checks.log`.
- `mypy --follow-imports=silent` siedmiu modułów/CLI, bez test fixtures:
  **PASS**, `artifacts/t1171-r1-checks.log` (scoped types).
- Rzeczywisty CLI READ ONLY / CPU na1TRAIN: **exit0**, log
  `artifacts/t1171-r1-pilot.log`.
- Cold replay w drugim procesie: **exit0**, identyczne report bytes,
  log `artifacts/t1171-r1-cold-replay.log`. SHA pliku report.json:
  `2e2c33044f5111a8289a0ed0c3a36e67e3caf03b149becd49595c633248e6a8d`.

Nie było zmian UI/API/OpenAPI, schematu ani zależności; nie uruchamiano Admin
build, usług ani ponownie jego testów z T1. Nie tworzono bazy operatorskiej,
nie zmieniano etykiet/defaultów, nie trenowano i nie używano GPU. Testy ochrony
odwołują się do ograniczonych fixtures; pilot SQL używa rzeczywistych istniejących
metadanych tylko do odczytu, bez fikcyjnej frozen sesji A.

## Rzeczywisty artefakt operatora i przekazanie T4

Katalog po R1: `D:/game_predicotr/artifacts/t1171-r1-final`.
Poprzedni `t1171-final` zachowano bez zmian.
Game `246a1f54-eee8-49d5-b11a-0fde70e5eecd`, cohort
`dae22c06-33cf-5f6a-accc-ce3166d13cf3`, manifest SHA
`1b97e3a11ee37906367d930a5955ce4299eb2a9e8c9135792c5a0626b54b0c93`.
Wybrany źródłowy TRAIN `42f8dc65-153d-4806-b4f8-2f42d160d3d7` przeszedł
aktualne role/copy/blind checks. Dziewięć plansz,135stałych instancji,
270cropów human +270model. Bez przetwarzania A/B/REG.

- `capture.json` / `production-crop-capture-v1`, body SHA
  `f47b0b3d17fe8eaa5aa1ee4595a4a405ccdebf61f961c523e5d5d14b298547d5`.
- `report.json` / `production-crop-comparison-v1`, body SHA
  `c450b5e9196ecec377e8599cfbe8d756264ee74dd4f1c1fdb6913ffc1acb686f`.
- Grid version `3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e`; bundle SHA
  `21ecfc69e670be6f99dc279491f23d469d04e67c4a2e0efb85fb0dbe1467e3e7`;
  screen.onnx `2135192aa2f6a0b1345a7bd767ff42b20a8a8b79a8e5d3afa9e01e4e990343ea`;
  board.onnx `295dbbd122b12d09ff874470742d00adc0a2addcf405a2ffba67f49b1e859a7c`.
- `photos[].neuralInput`: actual BASE, screen768×608 i9board320×192,
  wszystkieavailable. Każdy wpis ma transformację, preset/routing/variant,
  SHA RGB/tensora oraz ścieżkę PNG w `neural-inputs/`.
- `photos[].modelPredictions` zachowuje faktyczne raw/fitted nodes i screenQuad.
  `geometry.human/model.observation.boards` daje matching i per-instance ocenę;
  `rasters` ma RGB PNG, file/pixel/renderSpec SHA; `classification` i `labRgb`
  mają jawny stan. T4 może korzystać tylko z `visualExportAllowed=true`.

**Wynik not_evaluable**: contentGT0, brak pomiaru u/δ;78klas bez current approval
i57bez reference. Historyczny classifier snapshot źródła to
`cold-start-unclassified-v1`, inferenceMode=unclassified, a nie zastępcze wagi.
Nie wskazano LAB iteration. FalseAccept=null. Nie ma podstaw do rekomendacji
marginesu ani poprawy modelu; kandydat diagnostyczny nigdy nie pozwala na
qualification/publication (`diagnosticOnly=true`, `qualificationAllowed=false`).

## Uruchomienie i format

Z katalogu worktree:

```powershell
& D:/game_predicotr/.venv/Scripts/python.exe scripts/compare_production_symbol_crops.py `
  --game-id 246a1f54-eee8-49d5-b11a-0fde70e5eecd `
  --cohort-id dae22c06-33cf-5f6a-accc-ce3166d13cf3 `
  --manifest-sha256 1b97e3a11ee37906367d930a5955ce4299eb2a9e8c9135792c5a0626b54b0c93 `
  --source-id 42f8dc65-153d-4806-b4f8-2f42d160d3d7 `
  --grid-version 3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e `
  --artifact-root D:/game_predicotr/artifacts --repository-root D:/game_predicotr `
  --output D:/game_predicotr/artifacts/t1171-r1-final
```

Powtórzenie identycznego polecenia weryfikuje istniejący raport. Nowe GT/piny
wymagają nowego katalogu capture; stary raport i frozen snapshot pozostają
niezmienne. `--source-id` powtarzalny, maksymalnie50; `--lab-iteration` opcjonalny,
wyłącznie rzeczywista zarejestrowana iteracja lab_import. Brak modelu jest
raportowany, nie uruchamia się treningu. Rozdzielenie raportów per gra wymaga
osobnego capture, bez sumowania poprawy ponad grami.

## Pozostałe kroki

Root: focused Opus R2/receipt po jednej wykonanej rundzie poprawek, regeneracja
mapy i sprawdzenie docs, formalne zamknięcie i commit. T3 wiąże ten kontrakt
z istniejącym uczeniem; T4 buduje HTML z rzeczywistych dozwolonych rastrów.
Żaden z tych kroków nie może traktować obecnego not_evaluable jako sukcesu jakości.

Root po freeze zaliczył regenerację mapy, docs:check i code-map:check. Raport jakości operatora nadal not_evaluable; te kontrole potwierdzają kod/dokumentację.

Root: focused Opus R2 PASS (0P0/0P1), canonical report/receipt SHA verified.
Otwarte P2-5–P2-9 i granice zapisano w Outcome; map/docs/mapcheck po R1 PASS.
