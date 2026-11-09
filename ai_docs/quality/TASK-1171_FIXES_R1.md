---
title: TASK-1171 — Jedna runda poprawek po Opus R1
status: active
last_updated: 2026-11-09
---

# TASK-1171 — Poprawki R1

Podstawa: rzeczywisty raport `TASK-1171_AUDIT_claude-opus-5-5_R1.md`.
To raport wykonawcy, nie niezależny werdykt audytora. Po tej rundzie kod jest
zamrożony do focused R2 prowadzonego przez root; bez stage/commita.

| ID | Zmiana | Dowód |
|---|---|---|
| P0-1 | `_policy` produkuje current-diagnostic-runtime: zwalidowany canonical pipeline envelope/fingerprint, reviewBoundary.autoAcceptEnabled, snapshot modelu oraz input/preprocessing scope, z checksum. Nie udaje historycznej polityki importu. Known manual daje disabled i pozwala na rekomendację diagnostyczną, brak runtime pozostaje unavailable. | `test_real_candidate_author_policy_producer_reaches_candidate`: rzeczywisty build_symbol_candidate → `_policy` → acceptance_policy → realny renderer/CPU → candidate. Brak runtime odrzucony. |
| P1-1 | Konsument rozpoznaje autentyczne M6 calibrationVersion v1/v2-safe-floor oraz candidate_gate version. Weryfikuje model, ONNX, klasy, temperature i zakres input z przypiętego manifestu/configuration. Nie tworzy nowego progu. | Powyższy test używa plików rzeczywistego autora candidate_gate v2; `test_real_legacy_calibration_producer_and_current_runtime` czyta repozytoryjny przypięty M6 v1 przez prawdziwy `_policy`, odrzuca błędny model i brak runtime. |
| P1-2 | board_synchronized jest human GT wyłącznie dla current cell board_decision, dokładnej rewizji/cropu i aktualnej human resolution planszy z tym samym aktorem. System/reopened/stary event nadal niedostępne. Current owner zachowany. | Parametryzowana regresja oraz PostgreSQL `test_real_human_board_decision_and_current_frozen_a_pin`: produkcyjne validate_image_review_resolution/save_resolution → zapis zdarzeń → readonly `_classes`, 15 dostępnych klas. Ten test wykrył i usunął błędne oczekiwanie assignment_source w tabeli eventów, która tego pola nie ma. |
| P1-3 | Każdy licznik szkody blokuje rekomendację mimo mniejszego clipping. | Parametryzacja degradedInstances/newWrongCells/newTies/newForeignSymbols/newMatchAmbiguities; rzeczywisty ProductionContentObserver/renderer: margin0 przejmuje pełny sąsiedni symbol przy fewerClipped i daje regression. |
| P2-1 | Poprawa wymaga spadku clipped+missing. Każda nowa missing instance blokuje gate; odzysk innej missing jej nie kompensuje. | Regresja clipped→missing oraz `test_missing_recovery_cannot_compensate_new_missing_instance`; także producer→consumer candidate test z dodanym missing. |
| P2-2 | Screen witness uczestniczy w stanie: brak zgodności wykonanego BASE/rescue tensora daje partial i CROP_ACTUAL_SCREEN_INPUT_NOT_BOUND. | BASE/WIDE × screen drift, dokładny observed tensor i przywrócenie runnerów; rzeczywisty pilot ma available screen +9 board inputs. |
| P2-3 | Uczciwa granica: sealed internal A JSON zachowuje geometrię/klasy do replay/metryk, z zaakceptowanym lokalnym ryzykiem metadanych. Brak wizualnego eksportu A. Raport ma accessScope i visualExportRule; T4 wymaga TRAIN oraz visualExportAllowed=true. | Wymagania/architektura/task zaktualizowane; regresja A bez PNG. PG: current frozen A działa mimo starej pustej pass1, źródło nadal chronione przed TRAIN hints; odczyt tylko READ ONLY. |
| P2-4 | LAB ma absolute-reference bez fikcyjnego gate no_improvement i osobne labGames per game/role/geometry, z zachowaniem selected/evaluated instances. | Rzeczywisty test LAB RGB96→64 i sum; pilot bez LAB iteration jawnie not_evaluable, nie zero-quality-success. |

Wyniki końcowe: **47 passed (18.58 s)**, jeden zastany FutureWarning torch;
**1 PostgreSQL passed (25.34 s)**, własna jednorazowa baza i cleanup kontekstu;
Ruff format/check **PASS**, scoped mypy siedmiu modułów/CLI **PASS**.
Logi: `artifacts/t1171-r1-unit-final.log`, `t1171-r1-postgres.log`,
`t1171-r1-checks.log`. Baza testowa zawiera małe syntetyczne adnotacje i rekordy
realnego repozytorium; nie stanowią one kwalifikacji danych operatora.

Nowy pilot: `D:/game_predicotr/artifacts/t1171-r1-final`, READ ONLY/CPU na jednym
ponownie sprawdzonym TRAIN, bez A/B/REG. 135 instancji, 540 cropów i10 wejść NN.
Cold replay w nowym procesie exit0, identyczne bajty report.json. Body SHA
`c450b5e9196ecec377e8599cfbe8d756264ee74dd4f1c1fdb6913ffc1acb686f`, file SHA
`2e2c33044f5111a8289a0ed0c3a36e67e3caf03b149becd49595c633248e6a8d`.
Logi: `artifacts/t1171-r1-pilot.log`, `t1171-r1-cold-replay.log`.
Stare raporty pozostają nietknięte. Operatorowy wynik nadal **not_evaluable**:
brak contentGT/uδ, current class GT i modelowego classifier snapshotu, brak LAB.

Jedynymi dodatkowymi plikami kodu/dokumentacji względem zakresu R1 są
`services/api/tests/integration/test_production_crop_capture_postgres.py` oraz
ten raport. Pozostałe zmiany mieszczą się w dotychczasowych plikach TASK-1171.
