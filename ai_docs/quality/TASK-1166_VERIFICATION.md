---
title: TASK-1166 — weryfikacja produkcyjnych wycinków
status: active
last_updated: 2026-11-08
---

# TASK-1166 — Verification implementacji i jednej rundy poprawek R1

Baza: `450f9ef11bc08aae5b9e9e5fbba89d1408a020ed` (T2, v1.7.574).
Zakres: T3 planu FULL_SYMBOL_CROPS_PLAN_20261108 i zaakceptowana D-591.
R1 zakończył się REVISE (0P0/1P1/5P2). Po jednej rundzie poprawek rzeczywisty
Opus R2 dał PASS0P0/0P1. Raport i zgodny receipt są obok pod nazwą
TASK-1166_AUDIT_claude-opus-5-5. Ten dokument nie zastępuje audytu.

## Wynik funkcjonalny i granice dowodu

Nowy raport `grid-model-evaluation-read-v6` używa dokładnie bramki
`production-cell-per-game-gate-v1` i reguły
`production-cell-content-evaluation-v1`. Zachowuje cały historyczny raport
jako `rawQuality`. Historyczne funkcje bramki, raporty i frozen cohorty nie są
reinterpretowane. Brak nowych backend-owned pinów oznacza brak kwalifikacji,
bez uzupełniania historii. Nowy capture jest opt-in; T4 przejmuje opt-in rodzica
workflow uczenia, T5 prezentację.

Produkcja i ocena używają tego samego VirtualCellRenderer i pełnego przypiętego
snapshotu klasyfikatora. Pomiar wykonuje float64 na rzeczywistym footprint
float32, przeciętym z realnym source support. Zachowuje offset i valid_box
zarządzanych cropów. Input NN i końcowy raster klasyfikatora mają osobne stany.
Niezależny czytnik ponownie oblicza raster wejścia A z przypiętego bundle/presetu,
źródła i transformacji; sam bool albo self-hash nie daje verified_content.

Freshness publikacji/defaultu/operacji odtwarza zapisane predykcje, matching,
renderowanie i podsumowania na frozen źródłach. Zmiana aktualnego paddingu,
rozmiaru lub wersji renderowania blokuje dowód; sama zmiana wag klasyfikatora
przy identycznych crop settings go nie unieważnia. Odczyty poszczególnych gier
mają osobne transakcje READ ONLY i nie przepinają transakcji katalogowej.

Testy nie kwalifikują rzeczywistego modelu ani danych operatora. Worker fixture
używa syntetycznych pikseli, etykiet i jawnego raportu powtarzalności; rzeczywiste
API/math/renderer/reader/replay działają, lecz fixture nie jest nowym pomiarem
ludzkiego u/δ. Replay nie uruchamia ponownie NN inference: weryfikuje zapisane
predykcje względem immutable źródeł i przypiętego preprocessingu. Pełne ludzkie
blind2pass/prepare/freeze było osobnym dowodem T2, nie powtórzono go w T3.

## Testy

CWD: `D:\game_predicotr\worktrees\full-symbol-crops`. Interpreter:
`D:\game_predicotr\.venv\Scripts\python.exe`; PYTHONPATH obejmuje api/src oraz
worker/src tego worktree. Każde uruchomienie kontrolował subprocess z timeoutem
≤120 s. Własne ścieżki pytest basetemp są w `.tmp/t1166-*`. Zestawy zachodzą
na siebie; poniższych liczb nie należy sumować jako unikalnych testów.

| Kontrola | Wynik | Dowód |
| --- | --- | --- |
| Czysta geometria, erozja/dylatacja, ε, macierz, remisy, invalid/missing | 27 PASS / 0.32 s | `artifacts/TASK-1166_GEOMETRY_HELPER.md` |
| Domena gate/reader, per-instance/per-game, δ, REG5/+1, fixed denominator, unknown10%, legacy dispatch | 63 PASS / 0.62 s | `artifacts/TASK-1166_DOMAIN_GATE_TESTS.md` |
| Worker frozen pipeline/obserwacje + istniejące calibration/metrics/evaluation | 36 PASS / 18.98 s | transcript wykonawcy; pliki wymienione niżej |
| Worker frozen pipeline/obserwacje + reinference/operation/v3 acceptance/scoped publication | 57 PASS / 11.95 s | transcript wykonawcy; pliki wymienione niżej |
| Ostatnia zmiana routing stale + projekcja statusu | 12 PASS / 4.95 s | `artifacts/TASK-1166-final-routing-tests.log` |
| Istniejący renderer i legacy evaluation/calibration | 48 PASS / 6.64 s | `artifacts/TASK-1166-legacy-final.log` |
| DTO/reader/publication/root propagation | 9 PASS / 2.60 s | raport helpera consumers |
| HTTP GET/list raportów | 3 PASS / 2.37 s | `artifacts/TASK-1166-consumer-http.log` |
| Raw v5 REVISE → v6 PASS, dokładnie zachowany raw, δ i usable gain | 1 PASS / 2.04 s | `artifacts/TASK-1166-raw-revise-consumer.log` |
| Legacy consumers helpera | 17 PASS | raport helpera consumers |
| Brak explicit URL/name w cold subprocess, fail przed połączeniem | 1 PASS / 2.24 s | raport helpera consumers |
| Disposable PG nullable provenance/alias/currentness/cold replay | 1 PASS / 33.56 s | `artifacts/TASK-1166_DETACHED_ALIAS_HELPER.md` |
| Disposable PG migracja0183/grants/bind/pairguards/upgrade-downgrade/cold receipt | 1 PASS / 26.42 s | `artifacts/TASK-1166-bind-postgres.log` |
| Disposable PG dwa niezależne READ ONLY scope, parent Connection, SQLSTATE25006 | 1 PASS / 25.97 s | `artifacts/TASK-1166-reader-postgres.log` |

Zestaw 36: `test_production_cell_frozen_pipeline.py`,
`test_production_cell_observations.py`, `test_full_board_calibration_integration.py`,
`test_grid_correction_metrics.py`, `test_grid_model_evaluation.py` w worker/tests.
Zestaw 57: pierwsze dwa oraz worker `test_grid_reinference_handler.py`, API
`test_neural_grid_operation_qualification.py`, `test_v3_engine_acceptance.py`,
`test_grid_model_publication_scoped.py`. Zestaw 48: worker
`test_virtual_cell_extraction.py`, `test_grid_correction_evaluation_pipeline.py`,
API `test_grid_correction_evaluation.py`, `test_full_board_calibration_report.py`.

Nowy frozen pipeline przechodzi `_measure_unit` → realny renderer → A verified
plan → B po seal → REG → ponowny odczyt w nowym procesie. Sprawdza także
self-hashed input lie, checksum rastra, model input variant, brak artifact_root,
zmieniony padding oraz podmienione podsumowanie. Fixture DB dla freshness jest
jawnym boundary double; oddzielne PG testy sprawdzają authority, routing i bind.
Cold replay tego testu jest plikowy i nie łączy się z bazą.

## Kontrole jakości i kontraktu

Ruff check/format: 40 plików PASS (`TASK-1166-final-quality.log`). Mypy primary: 11 modułów
PASS; po ostatniej zmianie `production_cell_reference.py` i
`grid_recognition_status.py`: 2 PASS (`TASK-1166-final-types.log`). Helpery:
geometry 1, content pins/currentness 2, API/SQL/schema 8 modułów PASS oraz nowy
test domeny PASS. Użyto `mypy --follow-imports=silent`, bez pomijania wskazanych
modułów. Do raportu końcowego dołączony jest finalny log lint i docs/map.

Sześć wcześniejszych błędów mypy w dwóch dużych, istniejących modułach pozostaje
poza zakresem: pięć Optional game_id w `pipeline_store.py` oraz Row/tuple w
`virtual_grid_geometry_repository.py`. Odtworzono dokładnie te same błędy na
git HEAD450f9ef w odizolowanym overlay bez zmiany worktree. Dowody:
`artifacts/TASK-1166-baseline-types.log`, `.json` i
`TASK-1166-check-baseline-types.py`. Nie jest to pełny globalny mypy PASS.

Backend/OpenAPI/SDK/wrapper/request test stanowią jeden pion. Helper wykonał
OpenAPI export/check, generated-client check, SDK typecheck/build i 3 testy
wrappera: PASS. Dokładne komendy, 17 ścieżek i SHA:
`artifacts/TASK-1166_REPORT_CONSUMERS_HELPER.md` oraz
`TASK-1166_REPORT_CONSUMERS_SOURCES.json`. Nowy SQL wymaga sparowanych wersji,
nie odczytuje nested rawQuality verdict; Python sprawdza semantykę.

Wymagania VISION_LAB, architektura, API_CONTRACT, task i mapy kodu zaktualizowane.
D-591 i indeksy prowadzi koordynator. `npm.cmd run docs:check` PASS653/589,
startup44123 B, code-map check PASS oraz `git diff --check` PASS
(`TASK-1166-final-docs.log`). Nie uruchamiano pełnego
globalnego test suite ani Admin UI build, ponieważ zmiana nie obejmuje UI.

## Nieudane próby i poprawki

- Test domeny wykrył rzeczywistą lukę `usableBoards > boards_correct`.
  Bramka odrzuca obecnie nierzetelne liczniki bazowe/kandydata; dodatkowo waliduje
  górne granice nowych błędów. Finalne 63 testy przechodzą bez osłabienia wymagań.
- Worker: pierwsze fixture miało brak canonical coordinateSpace/parametru
  threads, a managed-crop fixture pozostawiało oryginał. Poprawiono fixture,
  nie produkcyjne zasady admission/GT. Stary SimpleNamespace board preset ujawnił
  regresję kompatybilności; adapter używa BoardPreset.model_validate z
  from_attributes, finalny legacy test przechodzi.
- Ograniczenia Windows temp/hardlink i socketpair uniemożliwiły wybrane lokalne
  próby. Powtórzono wyłącznie właściwe testy z jawnym basetemp/uprawnieniem;
  nie uruchamiano usług. Dwa mypy przebiegi bez postępu przerwano/ograniczono
  czasowo, potwierdzono brak pozostawionych procesów, potem zawężono jawny scope.
- Alias PG: bezpośrednie usunięcie origin poprawnie zatrzymał FK RESTRICT.
  Uzgodniony dowód obejmuje legalne odłączenie nullable live_source_image_id,
  aktywną zweryfikowaną kopię oraz odrzucenie niedostępnego rzeczywistego targetu.
  Nie twierdzimy, że usunięto chroniony origin lub odtworzono supersesję.
  Drugi FAIL był błędem testowej ścieżki bez `data/`; finalny PASS i cleanup0/0.
- Nowy reader PG: pierwsza próba FAIL25.76 s przez nieistniejące pole receipt
  owner_role; poprawiono na role. Przed retry osobny proces potwierdził cleanup
  0/0 (`TASK-1166-reader-run1-cleanup.json`). Finalny PASS25.97 s również ma
  niezależny cleanup0/0 (`TASK-1166-reader-cleanup.json`).

### Incydent izolacji bazy w helperze SQL

Trzeci cold subprocess helpera bind użył domyślnego URL z ApiSettings zamiast
URL własnego fixture. Wykonał session-local set_config i SELECT nieistniejącej
funkcji v6 zakończony UndefinedFunction. Nie wykonał DDL, DML ani zapisu danych
domenowych. Koordynator został powiadomiony. Nie oznaczamy tej próby jako PASS
ani bezincydentalnej pracy wyłącznie na disposable DB.

Trwała poprawka w teście wymaga `TEST_DATABASE_URL` i niezależnego
`TEST_DATABASE_NAME` przed create_engine; po połączeniu sprawdza current_database
przed SET/funkcją. Brak zmiennych testuje osobny przypadek bez połączenia.
Czwarta próba przeszła. Świeży proces potwierdził brak wszystkich czterech
własnych DB i ośmiu ról (`artifacts/TASK-1166-bind-cleanup-all.json`). Pełny opis
w raporcie helpera. Nowy test reader także przekazuje explicit URL/name.

## Zwiększenie limitu audytu na polecenie operatora

Po dwóch transportach bez werdyktu (każdy timeout480s) operator polecił limit
30min. Runner i wejście PowerShell mają teraz domyślny/maksymalny limit1800s;
host1860s i idle60s opisano zgodnie w AGENTS, procedurze, skillach i planie.
Nie wyłączono blokady duplikatów, własności procesów ani walidacji raportu.
41 testów Python PASS59.70s, 19 kontroli PowerShell5.1 PASS; rzeczywiste nowe
procesy z fast fakeCLI sprawdzają default/explicit1800, odrzucenie wyższego
limitu i wartości niefinitywnych przed CLI. Ruff2/format2/mypy1/diffcheck PASS.
Raport, SHA i dokładne polecenia: `artifacts/TASK-1166_TIMEOUT_HELPER.md`.
To test runnera, nie niezależny audyt T3; pełny Opus R1 pozostaje wymagany.

## Odbiór punkt po punkcie

| Kryterium T3 / DoD | Dowód |
| --- | --- |
| Stały source/board/cell i mianownik, brak maskowania missing przez unknown | observer + frozen replay + gate tests |
| preserved/borderline/clipped/missing, u/ε, macierz, remisy i foreign | geometry 27 + real renderer observations |
| Brak kompensacji nowej gorszej instancji | observer counters, gate 63, niezależny detail replay |
| Per game A/REG, recall/correct/full-photo/FP/duplicates/NMEδ | gate tests, partial/full denominator |
| Bieżąca gra +1 usable, 15 visible/preserved, świeży REG5 | gate i observer, reject-all regression |
| Brak danych, niepełne zdjęcia, unknown>10%, input GT | not_evaluable i blokada automatu; brak proxy-to-GT |
| Historyczne reguły i nowe wersjonowanie | legacy48/17, consumer pairing, raw REVISE→v6 PASS |
| Trwałość, currentness, zmiana crop config, source retention | cold file replay, 3 różne PG piony, typed stale |
| Migracja i kontrakt |0183 upgrade/downgrade/bind/RLS + OpenAPI/SDK/wrapper |
| Dokumentacja i kontrola kodu | scoped Ruff/mypy z jawnymi baseline błędami, docs/map |
| Niezależny audyt | terminal Opus5.5/high requested, R2 PASS0P0/0P1, matching receipt/SHA |

Nie wykonano treningu, GPU, kwalifikacji realnego modelu, migracji operatora,
uruchomienia usług, zmiany defaultu/aktywacji, importu691, merge ani push.
Nie naprawiano znanych dziewięciu starych fixture T2 ani dwóch starych Mock T1.
Pakiet źródłowy audytu i manifest SHA są w `artifacts/audits/TASK-1166-R1-sources`;
aktualny jawny scope w `artifacts/TASK-1166_SOURCE_SCOPE.json`.

## Jedna runda poprawek po rzeczywistym R1

R1: payload SHA `d072fa83c3ac9ba694640988c129b4c399a84acbfd646523e3009d4792b844e4`,
request `4d6cb549dba633d88e3b6b0f6d9ae013af74996f52640060fad5a6464bcbc171`.
Receipt potwierdza completed/exit0/REVISE/model claude-opus-5-5; raport SHA
`5cedd45d1bf16711b1ae788358efd6dfdd14a4d5ecba13611b7770b0038525f7`.
Wcześniejsze dwa timeout480s nie miały werdyktu. Operator następnie jawnie
zlecił limit30min; nie uruchomiono planowanego podziału audytu na trzy części.

| ID | Zmiana / status po implementacji | Dowód |
| --- | --- | --- |
| P1-1 | Fresh REG porównuje źródła użyte z wybranymi pinami representative i eligibleBoards>0. Brak pinu, brak kwalifikowanego źródła albo pusty eligible set nadal blokuje. | 4 real frozen-roster przypadki w test_production_cell_audit_regressions.py |
| P2-2 | Canonical detail_path wymagany; API i worker przekazują do finish dokładnie dokumenty odczytane z bajtów sprawdzonych SHA, bez drugiego odczytu. | alternate path odrzucona; podmiana pliku po verify nie zmienia summary; następny odczyt zmienionych bytes odrzucony |
| P2-3 | verified_content tylko dla bound, bez matchAmbiguous i z inputEvidence obserwatora. Brak świadka nie uruchamia ponownego obejściowego observe_input. | actual duplicate tie i missing-input dają0 threshold targets; clean daje1 |
| P2-4 | Minimum5photos/15boards dotyczy wyłącznie REG, zgodnie D591; A nadal musi być ocenialne i bez regresji. | 65 API gate tests PASS0.73s, w tym A1/3 przy pełnym REG |
| P2-5 | Koszt dopasowania rozdziela liczbę sentinel1e9/forbidden1e12 i fsum kosztów skończonych. | 22 tests PASS4.70s; real quads/missing/permutations/genuine gap |
| P2-1 | Pozostaje zaakceptowanym ryzykiem P2; nie dodano cache pomijającego physical-source/modelasset/SHA/support currentness. | Decyzja koordynatora; pełny replay nadal działa przy statusie i każdym właściwym źródle importu |

Finalny primary scoped zestaw: **11 PASS / 7.94s**, log
`artifacts/TASK-1166-r1-primary-final.log`; Ruff5/format5 i mypy3 PASS
(`TASK-1166-r1-primary-quality.log`). Wcześniejszy powiązany zestaw miał
27PASS/1FAIL22.52s: nowy fixture nie przekazał available_source_box do obserwatora;
uzupełniono ten sam adapter co produkcyjny measure_role. Jeszcze wcześniejsze
5FAIL/6PASS6.11s obejmowało brak importu json w nowej gałęzi, błędną nazwę
loadera testowego i niedokładny regex nowego typed reason. Przyczyny usunięto,
nie zmieniano oczekiwanej semantyki. Nie powtarzano PG ani szerokich zestawów.

Test świeżego rosteru ma5 realnych użytych źródeł oraz exact-pixel copy i
nieopisane źródło wyłączone z użycia. Izoluje membership: nie udaje pełnych
zdjęć ani kwalifikacji modelu; empty measured docs nadal dają not_evaluable.
Minima świeżego fullREG5 i15visible/preserved pozostają chronione testami domeny.
Testy podmiany pliku używają rzeczywistych lokalnych bajtów, a wrapper testowy
zmienia plik dokładnie po wykonaniu realnego verify_photo_details. Nie omija
samej kontroli renderowania, SHA ani decyzji bramki.

AC8 pozostało nieweryfikowane w R1 w zakresie wygenerowanego SDK: audytor
przeczytał DTO/migrację, ale nie mechanical diff. Focused R2 ma otrzymać pełny
dotychczasowy mechanical diff, wrapper/request i dowody generatora; wcześniejsze
testy SDK pozostają aktualne (poprawki R1 nie zmieniają pól kontraktu).
Zamknięcie ID powyżej jest zgłoszeniem wykonawców do R2, nie zastępczym PASS.
