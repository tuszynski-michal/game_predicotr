---
title: Ocena produkcyjnych wycinków i monotoniczna bramka
status: done
last_updated: 2026-11-08
---

# TASK-1166 — Ocena produkcyjnych wycinków i monotoniczna bramka

## Status

`done`

## Goal

Porównywać zawartość tych samych komórek na rzeczywistych wycinkach,
bez ukrycia braków, pomylenia pól i kompensowania nowych błędów.

## Dependencies / entry conditions

T1–T2 implementacja gotowa, dopuszczalne przesunięcie audytu wyłącznie
przy limicie Opus; brak rzeczywistych etykiet daje not_evaluable.

## Recommended execution

gpt-6-astra/high; dodatkowy review Claude Code claude-opus-5-5/high.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T3)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-578/587/588/590/591)
- ai_docs/architecture/CODE_MAP.md

## Scope

T3 w całości: VirtualCellRenderer/classifier/padding snapshot, float64,
u z powtarzalności etykiet, ε wyłącznie numeryczny, trzy stany zawartości/missing, macierz przypisania,
per-instance pogorszenie, nowe ruleVersion i readery/publikacja/default.
Stara bramka i raporty zachowują interpretację. Wymagana baza3ed60010,
kandydat9992a316 jedynie komparator informacyjny.

## Acceptance criteria

- [x] Ten sam sourceSHA/board/cell i stały mianownik dla bazy/kandydata.
- [x] preserved/borderline/clipped/missing i wrong-cell/remis/obcy pełny symbol.
- [x] Brak kompensacji nowych błędów przez poprawę innych instancji.
- [x] NME_k≤NME_b+δ i brak regresji metryk per gra A/REG, FP na pełnych zdjęciach.
- [x] Bieżąca gra świeżyREG ≥1 dodatkowa użyteczna plansza; odrzuć-all nie daje sukcesu.
- [x] Brak danych/etykiet/pełnych zdjęć blokuje odpowiedni dowód i zastosowanie.
- [x] Historyczne reguły, raporty i ludzkie korekty pozostają bez zmian.
- [x] Testy/kontrakt/scoped lint/types/docs/map i audyt.

## Technical notes

Ustalenia wdrożenia 2026-11-08 po zamkniętych T1–T2.

Operator po dwóch timeoutach480s jawnie polecił zwiększenie limitu audytu do
30min. W ramach odblokowania odbioru T3 zmieniamy domyślny/maksymalny limit
runnera i PowerShell na1800s, host1860s; idle60s, blokada duplikatów i walidacja
raportu pozostają. Dodatkowy zakres: `scripts/run_claude_audit.py`,
`scripts/audit_task.ps1`, ich testy i wspólna procedura/instrukcje. Zmiana
parametru otrzyma test nowego procesu i wejdzie do tego samego audytu T3.
To jawne ponowienie transportu R1, nie nowa runda po poprawkach; nie wymaga
podziału audytu ani zmiany modelu. Poprzednie timeouty zachowują swój zapis.

Rozdzielenie dwóch faktów potwierdzone przez koordynatora:

- `finalContentState` opisuje wyłącznie końcowy raster produkcyjnego klasyfikatora:
  rzeczywisty footprint cropu przecięty z realnym wsparciem źródła. `inputContentState`
  opisuje osobno wejście sieci geometrii. Brak pikseli na wejściu NN może blokować
  automat, lecz nie zmienia pełnego rastra klasyfikatora w `clipped`.
- Użyć `VirtualCellRenderer` i przypiętego snapshotu klasyfikatora z dokładnym
  `renderConfiguration`/SHA. Produkcyjne `source_direct_warp_rgb` kwantyzuje source
  quad do float32; obliczenia metryki wykonywać w float64 na tym rzeczywistym
  footprint float32→float64, nie na idealizowanym quadzie. Padding=0 zachowuje
  niezależne interior nodes; padding>0 używa projekcji outerquad. Nie zmieniać
  renderera ani marginesów pod wynik pomiaru.
- `CanonicalSourceFrame` zarządzanego cropu ma rozmiar i współrzędne oryginału:
  `compose_canvas` wkleja crop w `(left,top)`. Nie odejmować tego offsetu ponownie.
  Dla kompaktowego rastra `p_source=p_local+(left,top)` i
  `H_local_to_out=H_source_to_out*T_offset`. Wypełnienie canvasu nie jest dowodem
  pikseli; respektować `valid_box` i produkcyjny clearance `EDGE_RING_PX+1`
  przy wewnętrznych brzegach. Odczyt ewaluacji musi zachować frame/support oraz
  checksum rastra, nie tylko tablicę `.rgb`.
- Niezależny, frozen reader T2 wiąże `contentReferenceSha256`, własną rewizję,
  source byte/pixel SHA, game, slot i sequence; A ma dowód blind pass2.
  `visible` wymaga pełnej czteropunktowej obwiedni. `unknown`, `occluded` i
  `out_of_frame` nie dowodzą preserved ani pełnej niewidocznej zawartości.
  Mianownik pochodzi z etykiet i jest taki sam dla bazy/kandydata; brak detekcji
  lub prawidłowego rastra to `missing`, nigdy zmiana etykiety na unknown.
- T1 `verified_content` wymaga trusted frozen A tuple:
  `contentReferenceSha256`, `contentReferenceRevision` oraz
  `contentReferenceInputCropped` jako strict bool. T2 przypina etykietę, ale
  nie zna wejścia/wariantu. Adapter T3 wylicza ten osobny fakt z rzeczywistego
  NNinput i pełnych visible source-quadów, wiąże go z wariantem/transformacją,
  wsparciem źródła i checksumami, następnie zamraża wersjonowany dowód przed
  planem progów. Niezależny czytnik weryfikuje obserwację, nie ufa samej fladze.
  Brak dowodu nie jest `False`. Nie dopisywać flagi do historycznego frozen
  cohort ani używać `gt_cropped` jako zastępstwa.
- T2 `cell-content-repeatability-v1`: `u_pixels=u*bbox_diagonal(GT_cell)`;
  wspólny promień dla bazy/kandydata. ε=1e-6 piksela źródła służy wyłącznie
  numeryce; nie używać go jako bezwymiarowej tolerancji utraty pola. Dylatacja
  mieści się w support → preserved; nawet erozja nie mieści się → clipped;
  pozostałe przypadki → borderline. Pusta erozja nie jest sukcesem: borderline
  z jawnym powodem. Niepoprawny polygon/transform nie daje dowodu zachowania.
- Zachować istniejący Hungarian IoU i poprawność plansz, dodatkowo wymagać
  jednoznacznego pred-target matching i zgodnego slotu. Macierz pokrycia
  rzeczywistych etykiet przez cropy wykrywa obce pole, remis i pełne przejęcie
  obcego symbolu, również poza właściwą planszą tego samego zdjęcia.
  Nie kompensować żadnego nowego pogorszenia inną poprawą.
- Nowa funkcja/ruleVersion/reader wylicza decyzję z przypiętych dowodów, bez
  zmiany historycznego `decide_game`. NME z
  `training_core/grid_correction_metrics.py::evaluate_photo`: mean24 przez
  przekątną bbox GT, clamp1/missing1, potem photo-average. `board_errors` używa
  innej przekątnej i nie zastępuje tej normalizacji. Każda gra A/REG zachowuje
  recall/correct/full-photo correctness/FP/duplicates, NME≤base+δ oraz instancje;
  REG wymaga ≥5 pełnych opisanych zdjęć per gra, bieżąca gra +1 użyteczna plansza
  (`board_correct`, 15 visible/preserved, bez wrong-cell/ambiguity).
- Istniejący `gt_cropped`/`geometry_proxy` zachowuje historyczną semantykę i nie
  staje się dowodem clippingu pełnego symbolu. Nowy raport nadal korzysta ze
  sprawdzania currentness, scope i istniejącego default CAS/replay.

## Expected files

Ścieżki poniżej względne do repozytorium. Istniejące punkty integracji:

Zaimplementowane nowe moduły: API `domain/production_cell_geometry.py`,
`domain/production_cell_evaluation.py`, `storage/production_cell_reference.py`,
`storage/source_recording_sql_v9.py`, `storage/source_recording_permissions_v9.py`
oraz migracja `0183_production_cell_evaluation.py`; worker
`images/production_cell_evaluation.py`, `production_cell_input.py`,
`production_cell_run.py`. Hook capture znajduje się w
`storage/grid_training_cohort_evidence.py`; tuple A przechodzi przez
`full_board_assessment_reference.py` i `storage/full_board_calibration_evidence.py`.
Publication reader odtwarza detail/render/matching w odrębnych game READ ONLY
sessions i porównuje bieżące crop settings, bez wiązania aktualności z wagami.
Callerzy operation pin przekazują artifact_root również przy finalnym zapisie
importu, reinferencji i odczycie `storage/grid_recognition_status.py`.
Nowy PG test `test_production_cell_reader_postgres.py` sprawdza dwie niezależne
READ ONLY sesje i zachowanie parent Connection. Dokładny finalny scope/SHA jest
w pakiecie audytu.

- `services/worker/src/game_predictor_worker/images/production_workflow.py::_virtual_renders`
  oraz `virtual_cell_extraction.py::VirtualCellRenderer/source_direct_warp_rgb`
  — źródło prawdy produkcji, domyślnie bez zmiany zachowania.
- W tym samym katalogu: `grid_model_evaluation_handler.py::_photos/_measure_unit/_run`,
  `grid_cohort_dataset.py::GridCohortSnapshot.frame`,
  `full_board_calibration_observations.py::CalibrationObserver`,
  `full_board_calibration_run.py::FullBoardCalibrationRun`,
  `full_board_completeness.py::input_support`; użyć observera istniejących wyników.
- `services/worker/src/game_predictor_worker/training_core/grid_correction_metrics.py::measure_role`
  i `geometry_core/metrics.py::evaluate_photo` — istniejący pomiar/matching,
  historyczne reguły chronione.
- Nowe w T2: `images/grid_cell_content_reference.py::frozen_content_reference/content_oracle`
  oraz API `domain/grid_content_repeatability.py` — współdzielone zaufane odczyty
  i helpers, bez alternatywnego magazynu etykiet.
- `services/api/src/game_predictor_api/domain/grid_correction_evaluation.py`,
  `full_board_calibration_report.py`, `grid_model_publication.py`;
  `application/grid_model_evaluation.py::_report`,
  `application/grid_model_publication.py`,
  `storage/neural_grid_operation_qualification.py`,
  `schemas/grid_model_evaluations.py` — dispatch/readers/publikacja/kwalifikacja.
- `services/api/src/game_predictor_api/storage/source_recording_sql_v8.py::WRAPPER_SQL/BIND_SQL`
  wskazuje obecne ograniczenia wersji. Proponowane: nowy moduł SQL i kolejna
  migracja Alembic rozszerzająca funkcje bind/dispatch, bez przepisywania
  historycznych migracji, raportów lub danych. Numer ustala koordynator.
- Proponowane nowe moduły: API `domain/production_cell_evaluation.py` (czyste
  typy, geometria i bramka), worker `images/production_cell_evaluation.py`
  (adapter renderera/observer), z testami tych samych nazw. Ostateczny podział
  dopasować do gotowego kontraktu T2; bez nowego frameworka i usług.
- Przy zmianie publicznego raportu: istniejący OpenAPI, wygenerowany klient,
  jego wrapper i test żądania w jednym pionie. Dokumentację globalną/rejestrację
  decyzji koordynuje root; mapa kodu po implementacji, nie podczas analizy.

### Handoff po T2

P2-6 przekazane z Opus T2/R2: capture może użyć etykiety z odłączonego
oryginalnego źródła na potwierdzonej kopii, ale require_current_content_pin
odrzuca live_source_image_id=None. W T3 ujednolicić regułę capture/currentness
z dowodem rzeczywistych pikseli docelowego źródła i zachowanym provenance;
dodać regresję po odłączeniu źródła. Nie zmieniać ochrony usuniętego faktycznego
targetu ani legacy raportów. Raport T2 ma PASS z jawnym residualem.

## Test cases

Przesunięta granica rzędu bez zmiany outerquad; wrong-row/column, brakdetekcji,
foreignsymbol, remisy, borderline→clipped, odrzucenie wszystkiego, nierówne
źródła, częściowe zdjęcia, epsilon i δ jednostki, stare wersje.

Dodatkowo: pełny końcowy crop przy obciętym wejściu NN (oddzielne wyniki),
managed crop/canvas i niezerowy offset, sztuczny fill oraz clearance,
float32 footprint blisko granicy ε, pusta erozja, niepoprawny quad/transform,
obcy symbol z sąsiedniej planszy, alternatywne optimum matching,
brak frozen content/revision/SHA, unknown bez auto-PASS,
stale report/default i dokładny replay po restarcie/utracie odpowiedzi.

## Verification

Weryfikacja wykonania i dokładne wyniki są w
`ai_docs/quality/TASK-1166_VERIFICATION.md`; poniżej zachowane polecenia zakresu.
CWD: worktree `D:\game_predicotr\worktrees\full-symbol-crops`; Python root
`D:\game_predicotr\.venv\Scripts\python.exe` (ma pytest, Torch i ONNX).
Każda skończona komenda przez kontrolowany runner z timeoutem ≤120 s;
dzielić zestaw testów, jeśli nie mieści się w limicie.

```powershell
& D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_virtual_cell_extraction.py services/worker/tests/test_grid_correction_metrics.py -q
& D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_correction_evaluation_pipeline.py services/worker/tests/test_full_board_calibration_integration.py -q
& D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_evaluation.py services/api/tests/test_full_board_calibration_report.py services/api/tests/test_grid_model_publication_scoped.py -q
# Osobno nowe testy T3 oraz ruff check / mypy na faktycznie zmienionych plikach.
npm run openapi:check
npm run docs:check
npm run code-map:check
```

Po zmianie kontraktu wykonać również test żądania wygenerowanego klienta.
Istniejące testy PG: `services/api/tests/integration/test_grid_model_evaluation_bridge_postgres.py`,
`test_grid_model_evaluation_e2e_postgres.py`, `test_grid_model_publication_postgres.py`.
Uruchamiać wyłącznie z explicit disposable PostgreSQL configuration, nigdy na
bazie operatora; brak konfiguracji raportować jako niewykonane, nie PASS.
Kryterium: scenariusze T3 i chronione stare wersje przechodzą, brak otwartych
P0/P1, dokładne wyniki w `ai_docs/quality/TASK-1166_VERIFICATION.md`.

## Outcome

Commit: v1.7.575 / `ac724d297448785bdcb98b17dc6a3d5e3fc104e5`.

Pion implementacji obejmuje realny renderer, niezmieniony padding i pełny
backend-owned snapshot, czystą geometrię/niepewność, per-instance/source-wide
matching, v6 reader/gate/SQL/API/SDK oraz freshness publikacji/defaultu/aplikacji.
Actual NNinput ma osobny zapis i replay z przypiętym modelem; verified_content A
jest sprawdzany przed B. Historyczne raporty i cohorty nie są przepisywane.
Domknięto P2-6 przez legalną semantykę odłączonego nullable provenance z aktywną
zweryfikowaną kopią; usunięty target nadal nie kwalifikuje się.

Testy używają danych syntetycznych oraz własnych disposable baz. Nie wykonano
treningu, migracji operatora, aktywacji/defaultu, importu691, usług ani merge/push.
Incydent błędnego default-DB cold replay helpera oraz trwała poprawka jawnego URL
są opisane w Verification; nie stanowią bezincydentalnego PASS starej próby.
Końcowy audyt Opus R2 dał PASS,0P0/0P1; raport i receipt:
`ai_docs/quality/TASK-1166_AUDIT_claude-opus-5-5.md`. R1 i obie próby bez
werdyktu zachowano osobno. AC8 obejmuje statyczną zgodność DTO/OpenAPI/SDK/
wrappera i wcześniej wykonane kontrole; audytor nie uruchamiał testów.
Limit audytu1800s/host1860s działa w rzeczywistym terminalu.

Weryfikacja: geometry27, domain63, worker/legacy36, caller57, final routing12,
legacy48 oraz consumers13 PASS w opisanych, częściowo nakładających się grupach.
Trzy osobne scoped PG piony: retention33.56 s, bind26.42 s, reader25.97 s;
każdy ma własny cleanup. OpenAPI/SDK/wrapper PASS. Scoped lint/types PASS z
wyjątkiem sześciu odtworzonych na exact HEAD wcześniejszych błędów mypy w dwóch
dużych modułach; dokładny scope i ograniczenia zapisano w Verification.

Rzeczywisty Opus R1: REVISE,0P0/1P1/5P2. Jedna runda poprawek obejmuje
membership freshREG (kopie/unlabelled), canonical detail path i brak ponownego
niezahashowanego odczytu, trusted A wyłącznie bound/bezambiguity/inputEvidence,
minimum5/15 wyłącznie REG oraz stabilne sumowanie matching kosztów.
Primary final11PASS7.94s, helper gate65PASS0.73s i matching22PASS4.70s;
scoped Ruff/types PASS. R2 potwierdził zamknięcie P1-1/P2-2/3/4/5 i AC8 SDK.

P2-1 przyjęte jako jawne ryzyko: pełny replay pozostaje kosztowny przy odczycie
statusu i każdym właściwym źródle importu. Prosty cache report/detailSHA
pominąłby kontrolę bieżących fizycznych source/model assets/SHA/support;
bezpieczne wydzielenie/cache i profiling są poza tą rundą, bez osłabienia proof.

R2 P2-6 przyjęte jako residual przekazany do TASK-1167: worker nie sprawdza
limitu96MiB przed parsowaniem detali, a końcowa weryfikacja niepotrzebnie
przetrzymuje dokumenty. Zbyt duży detal może zakończyć job sukcesem, ale nie
przejdzie późniejszego freshness API; brak ścieżki fałszywego PASS. W T4,
który zmienia ten sam handler i zasady zasobów, dodać limit przed odczytem
i końcową kontrolę samych hashy, z testem bez wielkiego fixture. To otwarte
P2, nie wykonana w T3 poprawka ani powód zmiany werdyktu audytora.
