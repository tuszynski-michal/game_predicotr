---
title: Trwałe niezależne etykiety zawartości komórek
status: done
last_updated: 2026-11-08
---

# TASK-1165 — Trwałe niezależne etykiety zawartości komórek

## Status

`done`

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

- [x] Niezależne rewizje zawartości z jawnie zatwierdzonym aktorem i sourceSHA.
- [x] Blind A/powtarzalność bez propozycji; ≥30plansz/10zdjęć, caps u/.02 iδ/.002.
- [x] Oracle blokuje kwalifikację przy przycinaniu przez sam renderer.
- [x] Ochrona ról/kopii/sesji/buforów/rodowodu/ekspozycji; seed20261108.
- [x] Unknown>10%→not_evaluable; REG≥5pełnych zdjęć per wymagana gra.
- [x] Niedobory są policzone, nie udają ukończonej oceny lub operator-label.
- [x] Trwałość po restarcie, konflikty rewizji/replay, PostgreSQL, kontrakt i audyt.

## Expected files

Zakres T2 (2026-11-08); stan weryfikacji jest w raporcie jakości, a pełny
wykaz finalnych plików będzie w scoped manifest audytu. Ścieżki API są względne do
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
  Pełny rzeczywisty przepływ bada dodatkowo
  `services/api/tests/integration/test_grid_content_cohort_reference_pipeline.py`.
  Poprawkę aliasów/RLS/typed preflight sprawdza osobny rzeczywisty test
  `services/api/tests/integration/test_grid_content_alias_pipeline.py`.
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
- Wersjonowany pomiar `cell-content-repeatability-v1` używa wyłącznie TRAIN/A,
  nigdy REG. Dla niepustej próby nearest-rank P95 to
  `sorted(values)[ceil(0.95 * len(values)) - 1]`, bez interpolacji. Puste,
  niekompletne albo niezdatne pary pomiarów dają jawny niedobór, nie zero.
- u: dla odpowiadających source/board/cell dwóch ślepych przebiegów obliczyć
  symetryczną odległość Hausdorffa zamkniętych WYPEŁNIONYCH wypukłych quadów
  zawartości: maksimum odległości każdego wierzchołka pierwszego quadu do
  drugiego wypełnionego quadu oraz odwrotnie. Wierzchołek wewnątrz drugiego
  quadu ma odległość zero; poza nim mierzy się minimum do jego odcinków.
  Nie wymagać korespondencji narożników. Dla wypukłych quadów jest to
  Hausdorff całych zbiorów; nie zastępować go odległością wyłącznie między
  odpowiadającymi wierzchołkami ani odległością do samego brzegu dla punktów
  wewnętrznych. Dzielnikiem jest `min(d_cell_pass1, d_cell_pass2)` dla tej
  samej komórki w dwóch niezależnie narysowanych geometriach, nigdy
  przekątna obwiedni symbolu. Dokładnie
  `d_cell = norm(ptp(czterech węzłów komórki, axis=0))`, czyli przekątna
  osiowej obwiedni komórki, a nie jedna z przekątnych perspektywicznego quadu.
  Oba przebiegi odnoszą się do tego samego sourceNormalizedFrame, po EXIF,
  w kanonicznych źródłowych pikselach; content quad pozostaje niezależny
  od geometryRevision. u to P95 tych znormalizowanych rozbieżności.
  Obliczenia float64; zerowa, niefinitywna lub niepoprawna geometria daje
  unknown/invalid z licznikiem i blokuje pomiar, nigdy wynik zero.
- δ: zachować bazową definicję z
  `training_core/grid_correction_metrics.py::evaluate_photo`:
  `NME(prediction, GT) = min(1, mean(norm(prediction_i - GT_i)) /
  norm(ptp(GT, axis=0)))` dla wszystkich 24 węzłów. Dla każdej planszy
  przyjąć `max(NME(pass1, pass2), NME(pass2, pass1))`, następnie średnią
  po planszach każdego zdjęcia i nearest-rank P95 tych średnich. Nie
  dzielić δ przekątną komórki i nie używać tylko korzystniejszego kierunku.
  Parowanie jest po zachowanej tożsamości źródła i pozycji planszy,
  nie po predykcji kandydata. Wyniki i liczniki są osobno per gra.
- u > 0.02 lub δ > 0.002 blokuje zamrożenie i wymaga poprawy etykiet,
  nie zwiększenia tolerancji. Zamrożony raport przypina wersję miary,
  oba przebiegi i operatorów, liczniki, źródła i SHA referencji przed B/REG.
  Jeśli oba przebiegi wykonała jedna osoba, jawnie nazywa wynik
  powtarzalnością wewnątrzoperatorską; nie dowodzi zgodności wielu osób.
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
- Zapisany kontrakt T1: API `domain/grid_visibility_contract.py`
  `BoardContentReference(gameId, sourceRepresentativeSha256, positionIndex,
  revision, humanApproved, cells)`; `cells` ma dokładnie 15 row-major
  `CellContentReference(state, quad)`. SHA oznacza
  `sourceIdentity.normalized_pixel_checksum_sha256`, nie SHA pliku ani cropu.
  Źródłowy klucz komórki T2 to
  `(gameId, sourceRepresentativeSha256, positionIndex, cellIndex)`, gdzie
  cellIndex 0–14 jest pozycją w tablicy. Source UUID i byte SHA pozostają
  provenance. GeometryRevision/render ID nie wchodzą do klucza etykiety.
- Worker `images/grid_training_data.py::content_references(photos, index)`
  wywołuje opcjonalny `photos.content_references(index)`: lista referencji
  albo None, równoległa do `photos.targets(index)`. Adapter weryfikuje
  TRAIN, gameId, pixel SHA oraz pozycje posortowanych source.targets;
  obsługuje JointPhotos. T2 podpina reader metadanych, nie przepisuje lossu.
- `visibility_supervision(refs, game_ids=...)` deduplikuje kopie i odrzuca
  konflikt. Mapa `games` zawiera KAŻDĄ wymaganą grę: osobno co najmniej
  30 visible i 30 occluded/out_of_frame komórek oraz 5 zdjęć każdej klasy,
  przed augmentacją, wyłącznie zatwierdzone TRAIN. Negatywy innej gry
  nie uzupełniają niedoboru; brak gry/referencji maskuje nadzór.
  Batch T1: `node_weights` float32 [N,24], `visibility_targets` i
  `visibility_mask` float32 [N,15]; visible=1, occluded/out_of_frame=0,
  unknown maskowane. Eksport oznacza trainedVisibility dopiero na podstawie
  rzeczywistej ekspozycji wybranego checkpointu, nie deklaracji T2.

## Test cases

### Operator workflow and T5 adapter

T2 udostępnia rzeczywisty pion zapisu (router, serwis, repo i Alembic),
nie seed etykiet. Trasy są pod
`/api/v1/admin/games/{gameId}/grid-quality-measurements`:

- `POST /content-sessions`: zamknięty `ContentSessionCreate` przypina
  `cohortId`, `expectedManifestSha256`, jawne `sourceIds` oraz `idempotencyKey`.
  Opcjonalne `targetSelection[{sourceId, positionIndices}]` wybiera dokładne
  sloty tych samych zdjęć (np. 3×10=30); brak pola wybiera wszystkie dostępne
  plansze. Nie ma ukrytego dosamplowania ani zmiany rosteru między przebiegami.
  Serwer wybiera wyłącznie rzeczywiste członkostwo TRAIN/A z istniejącej kohorty.
- `GET /content-sessions` i `GET /content-sessions/{sessionId}`: wznowienie
  po nowym procesie bez zależności od pamięci przeglądarki. Stan `pass1`,
  `pass2` albo `frozen`, CAS `revision`, lista źródeł/slotów/numerów i licznik
  ukończonych. Brak quadów, punktów, wcześniejszych etykiet i propozycji.
- `GET /content-sessions/{sessionId}/sources/{sourceId}/asset`: zwykłe źródło
  z zamrożonej kohorty, sprawdzone SHA, bez overlay. UI stosuje EXIF i
  sprawdza wymiary względem `ContentSource`, a kliknięcia zapisuje w
  kanonicznych pikselach oryginału; nie we współrzędnych powiększonego viewportu.
- `POST /content-sessions/{sessionId}/observations`: `ContentBlindWrite`
  zawiera `idempotencyKey`, `expectedSessionRevision`, `passNumber`, source/slot,
  dokładnie 24 ręczne `measuredNodes`, 15 `cells` row-major i jawne
  `humanApproval=true`. Actor pochodzi z rzeczywistego lokalnego Admina lub
  lokalnego Reviewera przez istniejący middleware, nie z body. Zdalny scoped
  Reviewer nie otrzymuje nowego uprawnienia przez sam kontrakt.
- `POST /content-sessions/{sessionId}/advance`: `ContentSessionAdvance`
  (`idempotencyKey`, CAS). Po wszystkich planszach przejście pass1→pass2
  zeruje wyłącznie roboczy odczyt dla nowego przebiegu; historia pozostaje.
  Końcowe zamrożenie wymaga minimów i u/δ. Oracle powstaje na pojedynczej
  planszy przy zapisie drugiego przebiegu, z rzeczywistego renderer i
  przypiętego classifier/padding, bez nieograniczonego finalnego batcha.
  Blokada render-contract nie usuwa etykiet ani nie podnosi tolerancji.
- Mutacje zwracają mały `ContentSessionCommandResponse` z licznikiem/CAS,
  bez ponownego rosteru i bez pokazania etykiet. Identyczne UUID/body po
  utracie odpowiedzi odtwarza receipt; zmienione body albo stale CAS daje 409.
- Zwykły odczyt/zapis poza ślepym pomiarem:
  `GET /content-references/{sourceId}/{positionIndex}` oraz
  `POST /content-references` (`ContentWriteCommand`). Sam zapis nie oznacza
  zatwierdzenia: `humanApproval` domyślnie false. AI-origin zachowuje
  `proposalSha256`; nie staje się ręcznym ślepym pomiarem.
- `GET /content-readiness?cohortId=...&manifestSha256=...` liczy rzeczywiste
  braki/unknown/pełne zdjęcia per rola. `annotationProgress` dotyczy żywych
  etykiet, `frozenPinCoverage` dokładnych pinów; główne state/games mają
  basis=frozen_content_pins. Legacy bez pinów nie udaje gotowego wejścia workera.
  Endpoint nie tworzy etykiet ani ról.

T5 musi włączyć osobny blind workspace z czystym canvasem i samym assetem
T2, zastępujący zwykły widok propozycji na czas sesji. Istniejący
`BoardGeometryCorrectionEditor` inicjalizuje suggestedCorners/lattice i
szkice, więc nie może być bezpośrednio użyty jako ślepy edytor. T5 może
ponownie użyć transformacji/pointerów, ale musi umożliwić samodzielne
24 punkty i 15 quadów/stany bez podpowiedzi. Dla visible pełen quad jest
wymagany; inne stany dopuszczają tylko faktycznie widoczny fragment.
Po reload pending UUID/body służy wyłącznie retry, nigdy odtworzeniu
poprzednich etykiet do canvasa. Nowy przebieg zaczyna od pustych pól.
Brak tego UI oznacza nieukończony odbiór użytkownika T5, nie rzekome
wykonanie pomiaru T2 na danych operatora. Brak operator-labels nadal
blokuje rzeczywistą kwalifikację/trening zależny od etykiet.

Niezależność od przesunięcia siatki, błędny sourceSHA, niespójny actor,
utrata odpowiedzi/replay/nowy proces, blind UI-read model, kolejność testu,
ochrona źródeł, partial/oracle/unknown i limity niepewności.

## Verification

Scoped testy+PostgreSQL/kontrakt, lint/types, OpenAPI/SDK i docs/map;
wszystkie komendy kontrolowane ≤120s. Wyniki w quality/TASK-1165_VERIFICATION.md.

Komendy operatorskie do odtworzenia kontroli; rzeczywiste wyniki są w raporcie
jakości. Uruchamiać z worktree, z unikalnym `--basetemp=.tmp/t1165-<run>`;
wrapper ogranicza każdy proces do 120 s i propaguje niezerowy wynik:

```powershell
$env:PYTHONPATH = "$PWD/services/api/src;$PWD/services/worker/src"
function Invoke-T2Bounded {
    & .venv/Scripts/python.exe -c 'import subprocess,sys; sys.exit(subprocess.run(sys.argv[1:], timeout=120).returncode)' @args
    if ($LASTEXITCODE -ne 0) { throw "T2 verification failed: $LASTEXITCODE" }
}
Invoke-T2Bounded .venv/Scripts/python.exe -m pytest services/api/tests/test_grid_cell_content.py services/api/tests/test_grid_cell_content_requests.py -q
Invoke-T2Bounded .venv/Scripts/python.exe -m pytest services/worker/tests/test_grid_cell_content_reference.py -q
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

Commit: v1.7.574 (hash dopisuje kolejny commit).

R1 audytu: REVISE, P0=0/P1=1/P2=4. Jedna runda poprawek jest gotowa do R2:
pixel/frame-bound contentTargetSource z zachowanym annotation provenance;
typowany błąd422, live-progress versus frozen-pin coverage, osobne stany oracle.
P2-2 pozostaje jawnie przyjętą granicą ekspozycji poza protokołem blind wedługD590.
Rzeczywisty test aliasówPG PASS38.02s, cleanup0/0; wykazał jednego own target
i poprawną ochronę drugiej kopii, nie dwa równoczesne ownership. Projection/reader
obu źródeł i konflikt sekwencji są sprawdzone bez obchodzenia bramek. Scoped
17+1+2 testy domeny/workera,2HTTP,1SDK oraz mypy8/Ruff12/docs przeszły;
chronologia późniejszych liczników i dokładne ograniczenia są w VERIFICATION.
Brak nowego audytu wykonawcy, stage/commit/close; koordynator uruchamia focusedR2.

Implementacja obejmuje trwałe adnotacje, sesje/źródłowy asset/readiness/preflight,
migrację0182/manifestv22, rzeczywisty oracle, nową opcjonalną politykę low-level
prepare oraz piny ślepej geometrii A, currentness, worker reader i klientSDK.
18 focused testów i13requestregresji przeszło; pełny rzeczywisty pipeline ma
PASS92.49s, końcowe gałęzie gotowości/HTTP15PASS, mypy31modułów iRuff41plikówPASS.
SDK/build/request test przeszedł. Szczegóły, cztery wcześniejsze przyczyny prób
pipeline i dziewięć odtworzonych wcześniejszych błędów fixture są w raporcie jakości.
Brak operator-labels nie jest pozornym PASS. T3 owns input-cropped proof,
T4 propagację opcji przez parent/child, T5 izolowany pusty edytor. Audyt i zamknięcie
wykonuje koordynator po zakończeniu weryfikacji, nie ten agent.

Audyt terminalowy Opus 5.5/high R2: PASS, bez otwartych P0/P1. Raport i zgodny
receipt: `ai_docs/quality/TASK-1165_AUDIT_claude-opus-5-5.md`. R1 zachowany
osobno; timeout pierwszej próby nie został uznany za werdykt. P1-1 i P2-1/3/4
zamknięte po jednej rundzie poprawek. Actual PG aliasów PASS38,02s, z jawną
granicą jednego właściciela i wykluczonej kopii; brak fikcyjnych dwóch own targets.

Przyjęte P2: P2-2 to jawny protokół ślepoty egzekwowany przez T5, bez obietnicy
technicznego zablokowania zewnętrznej ekspozycji. Nowe P2-5 i P2-6 są fail-closed:
nie przepuszczają błędnego modelu, ale ograniczają gotowość. W całym planie
przekazano je odpowiednio do T5 (żywy konflikt nie zasłania frozenPinCoverage)
i T3 (spójny capture/currentness po odłączeniu źródła adnotacji na legalnej kopii).
W T2 nie wykonywano trzeciej rundy zmian ani audytu. Te ograniczenia pozostają
jawne do odbioru zależnych tasków.

Odbiór AC/DoD: wszystkie właściwe kryteria T2 mają implementację i zapisane
testy, realną migrację/disposable PG, cold replay/RLS, produkcyjny renderer,
pion backend/OpenAPI/SDK/wrapper/request, scoped lint/types i docs/map.
Nie deklaruje się pełnego suite PASS (9 wcześniejszych fixture FAIL), realnych
etykiet operatora, niezależnego pomiaru jakości lub gotowości treningu operatora.
T4/T5 nadal muszą podłączyć istniejący low-level flow do parent/UI.
