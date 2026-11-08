---
title: Trwałe niezależne etykiety zawartości komórek
status: todo
last_updated: 2026-11-08
---

# TASK-1165 — Trwałe niezależne etykiety zawartości komórek

## Status

`todo`

## Goal

Wersjonowane, zatwierdzane przez człowieka obwiednie i stany zawartości,
niezależne od predykcji i rewizji siatki, używane przez istniejący ledger.

## Context

Siatka nie opisuje obrysu symbolu. Ślepa referencja i powtarzalność
muszą poprzedzać wybór modelu; AI-propozycja nie jest etykietą człowieka.

## Dependencies / entry conditions

T1 kontrakt wejść; plan T2 zatwierdzony. Brak danych nie blokuje kodu
adnotacji, ale blokuje zależną rzeczywistą kwalifikację/trening.

## Recommended execution

gpt-6-astra/high; Claude Code claude-opus-5-5/high przed zamknięciem.

## Relevant docs

- AGENTS.md
- ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md (T2)
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/architecture/DATA_MODEL.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/decisions/DECISION_LOG_2026.md (D-577/578/582/587/588)
- ai_docs/architecture/CODE_MAP.md

## Scope

Pełne T2: append-only rewizje/stany/4punkty źródła/aktor/pochodzenie;
geometria niezależna; blind measurement bez AI; u/δ i zamrożenie;
oracle produkcyjnego renderer/padding; istniejący ledger i świeży test.
Zmiany schematu wyłącznie Alembic. Kontrakt backend/OpenAPI/SDK/wrapper/test
żądań, read/write API adnotacji rozszerza istniejący obszar geometrii.

## Out of scope

Samodzielne oznaczenia operatora, uznanie AI za człowieka, migracja operatora.

## Acceptance criteria

- [ ] Niezależne rewizje zawartości z jawnie zatwierdzonym aktorem i sourceSHA.
- [ ] Blind A/powtarzalność bez propozycji; ≥30plansz/10zdjęć, caps u/.02 iδ/.002.
- [ ] Oracle blokuje kwalifikację przy przycinaniu przez sam renderer.
- [ ] Ochrona ról/kopii/sesji/buforów/rodowodu/ekspozycji; seed20261108.
- [ ] Unknown>10%→not_evaluable; REG≥5pełnych zdjęć per wymagana gra.
- [ ] Niedobory są policzone, nie udają ukończonej oceny lub operator-label.
- [ ] Trwałość po restarcie, konflikty rewizji/replay, PostgreSQL, kontrakt i audyt.

## Expected files

Scoped inspekcja T2 (2026-11-08); poniżej zakres przewidywany, nie deklaracja
implementacji. Ścieżki API są względne do
`services/api/src/game_predictor_api/`, workera do
`services/worker/src/game_predictor_worker/`.

- Nowe proponowane: API `domain/grid_cell_content.py`,
  `application/grid_cell_content.py`, `storage/grid_cell_content_models.py`,
  `storage/grid_cell_content.py`, `schemas/grid_cell_content.py` — niezależne
  rewizje 15 komórek, ślepe sesje, receipt, readiness i zamrożona referencja.
- Istniejące wejście API: `api/grid_quality_measurements.py`
  (`create_grid_quality_measurements_router`), `main.py` (wstrzyknięcie serwisu),
  `application/image_reviews.py` (opcjonalny serwis zgodnie z istniejącym wzorcem).
  Rozszerzyć istniejący obszar pomiarów geometrii, bez drugiego systemu ról.
- Migracja proponowana: `services/api/alembic/versions/0182_cell_content_references.py`
  po sprawdzonym head `0181_validation_purposes`; przed implementacją ponownie
  sprawdzić numer. Nowy `storage/game_data_v2_manifest_v22.py`; konsumenci:
  `catalog_repository.py`, `game_partition_lifecycle.py`, `game_storage_routing.py`,
  `grid_cohort_asset_retention.py`. Nie przepisywać manifestu v21.
- Istniejące adaptery: `storage/grid_training_cohort_evidence.py`
  (`GridCohortEvidenceReader.capture/render`),
  `storage/grid_training_cohort_artifacts.py` (`GridCohortArtifactStore`),
  `domain/full_board_assessment_reference.py` (`FrozenAssessmentReferences`),
  `storage/full_board_calibration_evidence.py` (`snapshot_assessment_references`).
  Nowe referencje przypinać wersjonowanym manifestem/sidecarem, nie zmieniać
  historycznych SHA ani semantyki snapshot-v4.
- Istniejąca ochrona: `storage/grid_correction_split.py` (`population/contexts`),
  `domain/grid_validation_purpose.py`, `storage/source_recording_groups.py`
  (`attest/lineage`), SQL-v8 `recording_photo_context_v3` i
  `recording_cohort_command_v5`. Ewentualne nowe funkcje SQL muszą być addytywne,
  z uprawnieniami capability; nie zapisywać prywatnego ledgeru zwykłym ORM.
- Worker: nowy proponowany `images/grid_cell_content_reference.py` (powtarzalność,
  adapter referencji i oracle), istniejące `images/grid_cohort_dataset.py` oraz
  `images/grid_training_data.py`. Produkcyjny renderer pozostaje
  `images/virtual_cell_extraction.py::VirtualCellRenderer.render`.
- Kontrakt: `packages/admin-api-client/openapi/openapi.json`, wygenerowane
  `packages/admin-api-client/src/generated/`, wrapper
  `packages/admin-api-client/src/index.ts` oraz nowy proponowany
  `packages/admin-api-client/test/grid-cell-content-request.test.mjs`.
- Nowe proponowane testy: `services/api/tests/test_grid_cell_content.py`,
  `services/api/tests/test_grid_cell_content_requests.py`,
  `services/api/tests/integration/test_grid_cell_content_postgres.py`,
  `services/worker/tests/test_grid_cell_content_reference.py`.
  Dokumentacja zachowania/modelu/API w istniejących Relevant docs, raport jakości
  oraz regeneracja `CODE_MAP.md`/`CODE_MAP_SYMBOLS.md` po implementacji.

## Technical notes

- Tożsamość etykiety: gra, source UUID z zachowaną tożsamością bytes/pixels SHA,
  kanoniczny układ współrzędnych i wymiary, `positionIndex` planszy oraz
  `cellIndex` 0–14 (row-major). Nie używać render ID ani geometryRevision jako
  klucza. `sequenceNumber` pozostaje osobnym atestowanym faktem domenowym.
  Przesunięcie siatki nie przesuwa obwiedni; zmiana SHA wymaga nowej referencji.
- Proponowane trzy game-owned relacje: append-only rewizje całej planszy
  (dokładnie 15 slotów, własny revision, SHA dokumentu), sesje pomiarowe z CAS
  i zamrożonym inwentarzem oraz immutable command receipts. Małe JSON metadane
  są dopuszczalne, bitmapy wyłącznie w plikach. Partycje/RLS/composite game FK,
  ochronę UPDATE/DELETE i downgrade z historią zapewnia migracja. Nullable live
  source FK może zostać odłączony, lecz source identity i etykiety pozostają.
- Visible wymaga skończonego, nieosobliwego uporządkowanego quadu w kanonicznych
  pikselach źródła. Unknown ani brak widocznej treści nie dostają wymyślonego
  obrysu. Osobno zachować `origin` propozycji i faktyczne human approval.
  Actor pochodzi z uwierzytelnionego request scope, nigdy z dowolnego body.
  AI-origin bez jawnej akceptacji nie zasila GT; ślepa sesja akceptuje tylko
  ręczny pomiar bez pokazania AI/etykiet wcześniejszego przebiegu.
- Kolejność zapisu: autoryzacja człowieka i gry → blokada klucza polecenia →
  exact replay → blokada sesji/tożsamości planszy → CAS → ponowna walidacja
  SHA i ochrony ledgeru → rewizja + receipt + postęp sesji w jednej transakcji.
  Zmienione body tego samego klucza i stale CAS dają rozłączne stabilne 409.
  Replay po utracie odpowiedzi nie tworzy rewizji; nowy proces czyta stan z DB.
- Źródło musi być rzeczywistym, własnym źródłem. Istniejący
  `application/grid_source_identities.py::complete` uzupełnia tylko całkowicie
  NULL canonical metadata i sprawdza geometrię oraz aktualną własność;
  `SqlAlchemySourceRecordingRepository.attest` tylko odczytuje atest własnych
  źródeł (SQL STABLE), nie tworzy occurrence ani dowodu niezależności.
  Rejestracja i użycia muszą przejść przez istniejące jawne komendy authority.
  Nie tworzyć fikcyjnego source ani nagrania z nazwy stagingu.
  Staging 691 najpierw daje preflight metadanych/niedoborów; brak legalnej
  tożsamości blokuje późniejsze użycie, nie wywołuje automatycznego importu.
- Ślepa sesja przypina exact TRAIN/A membership i dwa niezależne przebiegi.
  Odczyt roboczy zwraca źródło i puste sloty, bez wcześniejszych etykiet,
  siatki/propozycji AI. Każdy przebieg utrwala również 24 ręczne punkty do δ;
  samo ponowne użycie starej geometrii nie jest pomiarem powtarzalności.
  Zamrożony raport podaje operatora, ≥30 plansz/≥10 zdjęć per gra oraz
  ograniczenie do powtarzalności wewnątrzoperatorskiej przy tym samym aktorze.
- δ musi używać definicji `training_core/grid_correction_metrics.py::evaluate_photo`:
  średnia 24 odległości / przekątna obwiedni 24 punktów GT, potem średnia
  plansz zdjęcia i P95 zdjęć. Nie dzielić δ przekątną komórki. u stosuje
  symetryczną rozbieżność brzegów / przekątną komórki. Wersjonować kwantyl
  i procedurę dopasowania; wartości ponad 0.02/0.002 blokują zamrożenie,
  nie zwiększają tolerancji. Referencje i tolerancje zamrażać przed B/REG.
- Oracle przypina rzeczywisty `DirectCellRenderConfiguration` z
  `GridCohortEvidenceReader.render`, classifier/padding snapshot i ręczne
  24 punkty; uruchamia rzeczywisty renderer. Samo dopasowanie zewnętrznego
  quadu nie wystarcza. Ucięcie pełnej visible zawartości lub brak dowodu
  wsparcia daje `render_contract_blocked`, bez zmiany cropu klasyfikatora.
- REG losować raz, seed 20261108, po całym closure kopii/sesji/ancestry/
  historycznego użycia/buforów/diagnostic exposure i przed treningiem.
  Trwałym autorytetem ról pozostaje istniejący ledger; wynik losowania jest
  przypiętym wyborem do jego komendy, nie drugą tabelą ról. Źródło 462205
  wyklucza dowód exposure, nie hardkodowany numer sekwencji. Brak dowodu
  pochodzenia/niezależności oznacza niedobór, nie automatyczne dopuszczenie.
- Readiness liczy wszystkie 15 slotów każdego opisanego targetu roli,
  zatwierdzone/niezatwierdzone/unknown i pełne zdjęcia. Unknown >10% daje
  `not_evaluable`; brak ≥5 pełnych opisanych zdjęć REG per wymagana gra
  blokuje rzeczywistą kwalifikację. Partial nie udaje pełnego zdjęcia;
  konflikt aktualnych etykiet kopii nie pozwala wybierać korzystniejszej.
- Adapter T1 otrzymuje metadane stanów/quadów źródła, nie bitmapy w DB.
  Cele visible=1, occluded/out_of_frame=0, unknown maskowane; konkretne
  nazwy opcjonalnych pól ustalić z wykonawcą T1 przed zmianą konsumenta.

## Test cases

Niezależność od przesunięcia siatki, błędny sourceSHA, niespójny actor,
utrata odpowiedzi/replay/nowy proces, blind UI-read model, kolejność testu,
ochrona źródeł, partial/oracle/unknown i limity niepewności.

## Verification

Scoped testy+PostgreSQL/kontrakt, lint/types, OpenAPI/SDK i docs/map;
wszystkie komendy kontrolowane ≤120s. Wyniki w quality/TASK-1165_VERIFICATION.md.

Komendy planowane, nie wykonane podczas analizy. Uruchamiać z worktree;
wrapper ogranicza każdy proces do 120 s i propaguje niezerowy wynik:

```powershell
$env:PYTHONPATH = "$PWD/services/api/src;$PWD/services/worker/src"
function Invoke-T2Bounded {
    & .venv/Scripts/python.exe -c 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[1:], timeout=120).returncode)' @args
    if ($LASTEXITCODE -ne 0) { throw "T2 verification failed: $LASTEXITCODE" }
}
Invoke-T2Bounded .venv/Scripts/python.exe -m pytest services/api/tests/test_grid_cell_content.py services/api/tests/test_grid_cell_content_requests.py -q
Invoke-T2Bounded .venv-vision-lab/Scripts/python.exe -m pytest services/worker/tests/test_grid_cell_content_reference.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
Invoke-T2Bounded .venv/Scripts/python.exe -m pytest services/api/tests/integration/test_grid_cell_content_postgres.py -q -s
Invoke-T2Bounded .venv/Scripts/python.exe scripts/export_admin_openapi.py
Invoke-T2Bounded npm.cmd run generate --workspace @game-predictor/admin-api-client
Invoke-T2Bounded npm.cmd run build --workspace @game-predictor/admin-api-client
Invoke-T2Bounded node.exe --import tsx --test packages/admin-api-client/test/grid-cell-content-request.test.mjs
Invoke-T2Bounded npm.cmd run typecheck --workspace @game-predictor/admin-api-client
Invoke-T2Bounded .venv/Scripts/python.exe scripts/generate_code_map.py
Invoke-T2Bounded npm.cmd run docs:check
```

Test PG ma używać sprawdzonego
`services/api/tests/integration/_application_role_database.py::application_role_database`
z prefiksem `t1165`: tworzy/migruje wyłącznie własną bazę
`game_predictor_t1165_<hex>_test`, działa jako rzeczywista rola aplikacyjna,
czyta po restarcie przez `subprocess_environment`, a cleanup dotyczy tylko
tej bazy/roli. Nie uruchamiać `verify_postgres_baseline.ps1`, bo podnosi usługę.
Brak dostępnego PostgreSQL jest blokerem testu; nie restartować ani nie
migrować bazy operatora. Lint/format/mypy uruchomić wrapperem tylko na
ostatecznie zmienionych modułach po ustaleniu listy. Brak node_modules
w worktree wymaga zapewnienia zależności przed generacją SDK, bez ręcznej edycji.

## Risks / open questions

691źródeł nie jest dowodem niezależności; kod ma policzyć niedobór,
nie importować ani przypisać ich testowo bez operacyjnej zgody.

## Outcome

Nie rozpoczęto.
