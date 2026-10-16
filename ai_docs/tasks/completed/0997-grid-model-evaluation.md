---
title: TASK-0997 — Ocena per gra i bramka kandydata
status: done
last_updated: 2026-10-16
---

# TASK-0997 — Ocena per gra i bramka kandydata

## Status

`done`

## Goal

Zapobiec publikacji poprawy jednej gry kosztem drugiej.

## Context

Task jest częścią zaakceptowanej rewizji 6. Metryki i bramka osobno dla gier. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- D-556 report seam z0995: przed kodem0997 trzeba rozstrzygnąć pełny v2 reader/writer i globalną barierę aktualności wspólnego raportu. Zmiana danych dowodowych wymaga audytu high zgodnie z AGENTS i tabelą planu.
- TASK-0996 i niezależne, kompletne dane kontrolne.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-opus-5-5`, reasoning `xhigh` (zamiennik `claude-fable-5-1`/`high`; wybór wykonawcy po sugestii operatora 2026-10-16, uzasadnienie w sekcji 8 planu). metryki i kwalifikacja publikacji.
- Dodatkowy review: `gpt-6-astra` (przy braku dostępności `gpt-6.1-sol`), reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../../architecture/VISION_LAB.md).
- [VISION_LAB](../../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: D-483, VISION_LAB, reguły oceny tego planu.

- [D-483](../../process/decisions/DECISION_LOG_2026.md#d-483--metryka-nadrzędna-silnika-siatek-odsetek-zdjęć-kompletnych-i-poprawnych) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Identyczne źródła dla bazy i kandydata, pełny inference od zdjęcia, wyniki per gra/nagranie.
- Wersjonowane definicje metryk.
- REGRESSION tylko do końcowej kontroli.

## Out of scope

- Nie zastępować nieznanej jakości zerowym błędem.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Regresja dowolnej gry blokuje wspólny PASS.
- [x] Brak detekcji ma koszt.
- [x] Brak danych, parity lub aktualnych dowodów blokuje publikację.
- [x] Dobór checkpointu nie używa REGRESSION.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Identyczne źródła dla bazy i kandydata, pełny inference od zdjęcia, wyniki per gra/nagranie. Wersjonowane definicje metryk. REGRESSION tylko do końcowej kontroli.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

### Ustalona granica rzeczywistego raportu (D-556, przed zależnym SQL)

Istniejący publication reader w domain/grid_model_publication.py pozostaje bez zmiany w0995: producer kolumny i JSON to server:grid-model-evaluator-v1, schema grid-model-evaluation-read-v1, policy grid-model-per-game-gate-v1 i zamknięty dotychczasowy zestaw pól. Nowy application-grid-evaluation-v1 nie jest zgodnym producentem i nie jest przyjmowany.

Nowy binding rozpoznaje wyłącznie przyszły grid-model-evaluation-read-v2 z tym samym zaufanym producer/policy. Jest to wersjonowane rozszerzenie istniejącego read modelu, nie równoległy model oceny. Wymagana część identyfikacyjna obejmuje schemaVersion, producer, policyVersion, versionId, baseVersionId, familyId i cohorts. Cohorts jest niepustą listą do100 różnych gier i kohort; każdy wpis ma dokładnie gameId, cohortId, manifestSha256. UUID mają kanoniczną postać, SHA to64 małe znaki hex. Wersja kolumny report.version_id musi równać się versionId JSON, a wybrany własny wpis, baza i rodzina muszą dokładnie odpowiadać stored header/manifest rzeczywistej kohorty. JSON ma limit1MiB i exact SHA całych UTF-8 report_json, z canonical_json/descriptor_sha256 obowiązującymi po stronie rzeczywistego writera. Walidator bindingu sprawdza pełny checksum, producer i wymagane tożsamości; nie nadaje PASS ani nie zastępuje walidacji pełnych metryk przez0997. Pozostała część raportu zachowuje dotychczasowe przypięte manifest/base/cohort/requiredGameIds/games i szczegóły oceny zgodnie z kompletnym v2 kontraktem, który0997 utrwali przed swoim kodem. Nie zamrażamy dziś fikcyjnego formatu metryk. Zgodność requiredGameIds, rzeczywistych cohort refs i całej oceny musi być sprawdzona przez0997.

0995 nie zmienia obecnego require_evaluation_evidence i nie tworzy przyszłych raportów/bindingów. Stary v1 raport nie jest dowodem nowego v2 cohort binding i otrzymuje typed unsupported-provenance, bez naruszania jego dotychczasowego odczytu. Bind może chronić również rzeczywisty raport negatywny; jakość/PASS nie jest warunkiem zachowania zależności. Nieistniejący, zmieniony lub niepowiązany raport jest odrzucany. Test pełnego rzeczywistego0997 producer → binding → withdrawal → blokada publication jest obowiązkowy później, bez fikcyjnej oceny teraz.

Transakcja bindingu dotyczy jednej własnej kohorty i aktualnego zakresu jednej gry, z atomowym use/event/receipt. Wspólny raport kilku gier nie może przepinać GameStorageRouter do innej gry w jednej transakcji.0997 ma dostarczyć trwały, idempotentny protokół przygotowania raportu i oddzielnych własnych game bindings; brak choć jednego wymaganego bindingu lub aktualnego dowodu blokuje publikację/aktywację/default nowego v2 kandydata. Globalna bariera aktualności raportu musi uwzględnić notices wszystkich objętych gier bez owner fallback/obcych source partition reads i bez odwrócenia catalog→registry→ownership kolejności. Potrzebny most minimalnych notices/validation proofs i jego exact uprawnienia wymagają osobnego pełnego kontraktu przed kodem0997;0995 nie przedstawia tego mostu ani wspólnej publikacji jako wykonanych. Nie zakładamy fikcyjnej pojedynczej transakcji wszystkich gier. Dotychczasowe v1 historyczne dowody i już przypięte modele zachowują własne kontrakty.

### Kontrakt przed kodem (2026-10-16, Claude Code, D-559)

Stan zastany (HEAD v1.7.388): `domain/grid_model_publication.py::require_evaluation_evidence` czyta wyłącznie raport `grid-model-evaluation-read-v1` z zamkniętym zestawem pól i werdyktami tekstowymi, bez metryk. Nie ma żadnego writera `public.grid_model_evaluation_reports` ani trasy HTTP raportów. `recording_cohort_command_v3('bind_existing_report')` (0163) wiąże raport v2 z jedną kohortą jednej gry, sprawdzając tylko tożsamość. Notices `currentness_notice` (0163) są zapisywane w partycjach gier, ale nikt ich nie czyta poza grą. Neutralne metryki `geometry_core/metrics.py` (`neural-grid-metrics-v1`, `evaluate_photo`, `summarize`) i pełne wnioskowanie CPU `geometry_core/inference.py::onnx_engine` istnieją i są wspólne z laboratorium.

**Raport v2** (`domain/grid_model_evaluation.py`, czysty): kanoniczny JSON `canonical_json`, `report_sha256 = descriptor_sha256` (identyczny z dokładnym UTF-8 SHA, którego wymaga SQL bind), ≤ 1 MiB, zamknięte klucze:
`schemaVersion` = `grid-model-evaluation-read-v2`, `producer` = `server:grid-model-evaluator-v1`, `policyVersion` = `grid-model-per-game-gate-v1`, `policy` (pełne progi, `metricsVersion` = `neural-grid-metrics-v1`), `versionId`, `manifestSha256`, `baseVersionId`, `baseManifestSha256`, `familyId`, `trainingGameId`, `cohorts` (1–100 `{gameId, cohortId, manifestSha256}` posortowane po `gameId`, jedna kohorta na grę), `requiredGameIds` (posortowane, równe grom `cohorts`), `games`, `verdict` (`PASS` | `REVISE` | `NOT_EVALUABLE`), `parity` (`passed` i `bundleSha256` kandydata). Bez znaczników czasu: ponowienie tej samej oceny odtwarza bajtowo ten sam raport.
Element `games`: `{gameId, cohortId, mode, targetMetric, validation, regression, coverage, reasons, roles}`; `roles.VALIDATION|REGRESSION` = `{photos, inputSha256, base, candidate, recordings, detail}` (`detail` = względna ścieżka i SHA pliku wyników per zdjęcie), gdzie `base`/`candidate` to podzbiór `summarize` (`photo_complete_correct`, `photo_complete_correct_rate`, `boards_expected`, `boards_correct`, `board_correct_rate`, `boards_matched`, `detection_recall`, `false_boards`, `image_macro`, `nme_p95`, `max_node_error_p95`), a `recordings` to te same miary per grupa nagrania.

**Polityka `grid-model-per-game-gate-v1`** (jedna czysta funkcja `decide_game` używana przez writer i reader): baza = `baseVersionId` kandydata; oba modele dostają identyczne zdjęcia (te same źródła, ten sam zdekodowany kanoniczny frame, `inputSha256` per rola). Pełne wnioskowanie od oryginalnego zdjęcia, bez rogów z etykiet. Brak planszy kosztuje (koszt 1 w `image_macro`, spadek `detection_recall` i `board_correct_rate`); nadmiarowa detekcja zwiększa `false_boards` albo, gdy pokrywa już dopasowaną planszę, `duplicate_predictions`. Miary wymagane bez pogorszenia (tolerancja 0, porównanie liczników, `image_macro` z epsilonem 1e-9): `photo_complete_correct`, `boards_correct`, `boards_matched`, `false_boards` (niewięcej), `duplicate_predictions` (niewięcej; dodane po audycie R1), `image_macro` (niewięcej). Miara celu: grid-only `boards_correct`, screen+grid `photo_complete_correct`; w grze treningowej (gra kohorty z `manifest.cohortId`) VALIDATION wymaga ścisłej poprawy miary celu, w pozostałych grach tylko braku pogorszenia. REGRESSION służy wyłącznie końcowej kontroli braku pogorszenia we wszystkich grach; nie wpływa na nic poza werdyktem. Pokrycie `complete` wymaga ≥ 5 pełnych zdjęć na rolę, oceny każdego użytego zdjęcia przez oba modele i zdanego parity eksportu kandydata (`bundle.json.parity.passed`). Werdykt: `PASS` tylko gdy każda gra ma `validation=pass`, `regression=pass`, `coverage=complete`; `NOT_EVALUABLE` gdy którakolwiek gra ma niepełne pokrycie; inaczej `REVISE`. Reader v2 przelicza `decide_game` z zapisanych miar i odrzuca raport z niespójnym werdyktem.

**Wymagane gry:** zbiór `cohorts` musi zawierać kohortę treningową kandydata (`manifest.cohortId`) oraz kohortę każdej gry, której bieżące przypisanie należy do rodziny kandydata; dowolne inne gry są dozwolone. Każda kohorta musi być `frozen` z tymi samymi `familyId` i `baseVersionId` co kandydat (warunek SQL bind D-556). Ten sam warunek przypisanych gier jest ponownie sprawdzany przy publikacji (brak gry → `GRID_MODEL_EVALUATION_REQUIRED`).

**Ocena jako job** `JobType.GRID_MODEL_EVALUATION` (`evaluation_kind = grid-model-evaluation-v1`, schema 1) w lane `general` (CPU ONNX, bez GPU; slot 1 obejmuje go bez zmiany CHECK). Handler `images/grid_model_evaluation_handler.py`: dla każdej gry w jej własnym zakresie (`game_storage_scope`) ponowna dokładna kwalifikacja (`eligibility == eligible`), odczyt snapshotu i mapowania źródło → grupa nagrania, wnioskowanie bazy i kandydata zdjęcie po zdjęciu (`ManagedGridEngineModelStore.require` + `onnx_engine` z oczekiwanym SHA `bundle.json`), wyniki per zdjęcie jako plik `<artifact_root>/grid-model-evaluations/<jobId>/<gameId>-<role>.json` (atomowo, SHA w stanie). Postęp per (gra, rola) w `checkpoint_payload`; restart pomija ukończone jednostki i odtwarza ten sam raport. Cancel sprawdzany między zdjęciami. Następnie zapis raportu (id = uuid5(jobId)), idempotentny: istniejący wiersz o tym samym SHA jest reużywany, inny SHA → `GRID_EVALUATION_REPORT_CONFLICT`.

**Most aktualności (D-559):** dwie nowe współdzielone tabele `public` (manifest v17, migracja `0166_grid_model_evaluation`):
- `grid_model_cohort_notice_marks(id bigint identity, game_id, cohort_id, created_at)` — append-only; zapisuje ją wyłącznie wyzwalacz `AFTER INSERT ... WHEN (NEW.kind = 'currentness_notice')` na `game_data_v2.grid_training_cohort_events` przez funkcję `public.grid_cohort_notice_mark_v1()` (`SECURITY DEFINER`, `search_path = pg_catalog`, `REVOKE ALL FROM PUBLIC`). Rola aplikacji ma wyłącznie `SELECT` (tabela w `_READ_ONLY_TABLES` provisioningu). Licznik zapisów dla (gra, kohorta) jest odpornym na kolejność commitów znakiem wodnym; nie zawiera danych gry poza identyfikatorami.
- `grid_model_evaluation_cohort_proofs(id, report_id FK, game_id, cohort_id, manifest_sha256, notice_count, bind_receipt_sha256, eligibility_sha256, actor, created_at)` — append-only (istniejący `grid_model_immutable_v1`), zapisywana wyłącznie przez kod serwera po skutecznym `bind_existing_report` w transakcji danej gry. Kolejność dla każdej gry: (1) odczyt `notice_count`, (2) dokładna kwalifikacja i `validate_cohort_use`, (3) `bind_existing_report` z kluczem uuid5(reportId, gameId) (ponowienie = replay), (4) zapis proof z licznikiem z kroku 1 i generacją aktywnej lokalizacji magazynu gry (`storage_generation`, po audycie R1). Notice po kroku 1 zawsze unieważnia proof; notice przed krokiem 1 jest widoczny dla weryfikacji. Bez backfillu historii notices: proof porównuje licznik z wartością, którą sam odczytał.
**Bariera publikacji v2** (w `GridModelPublicationService._evidence`, więc także activate, rollback, default i widoki eligibility): poprawny raport v2 z werdyktem `PASS`, brak unieważnienia (istniejący mechanizm D-554), dla każdej kohorty raportu najnowszy proof z `notice_count` równym bieżącemu licznikowi i aktywna lokalizacja magazynu gry o generacji z proof (gra usuwana/usunięta → stan `unavailable` i `GRID_MODEL_EVALUATION_STALE`) ; pokrycie wszystkich gier przypisanych do rodziny sprawdza tylko publikacja (gra dodana do rodziny później nie unieważnia opublikowanego modelu ani tworzenia gier z modelu domyślnego). Brak proof → `GRID_MODEL_EVALUATION_REQUIRED`; nieaktualny proof → `GRID_MODEL_EVALUATION_STALE` ze wskazaniem gry. Odczyt tylko tabel `public` w transakcji katalogu po blokadzie 9910994; bez odczytu partycji gier, bez owner fallback i bez jednej transakcji wielu gier. Notice nie jest cofnięciem etykiety: polecenie „Sprawdź aktualność” ponownie wykonuje kroki 1–4 per gra i przy wciąż kwalifikującej się kohorcie zapisuje nowy proof. Dowód raportu (`evidence_json` publikacji) pozostaje dotychczasowy (`evaluationId`, `evaluationSha256`, `manifestSha256`), więc nowy proof nie zmienia tożsamości publikacji. Raport v1 i jego odczyt pozostają bez zmian.

**API** (`application/grid_model_evaluation.py`, router `/admin/grid-model-evaluations`): `POST` utworzenia oceny (klucz idempotencji z blokadą advisory jak w TASK-0996, kandydat, lista `{gameId, cohortId}`) z walidacją wymaganych gier i kohort; `GET` listy po wersji kandydata, `GET` szczegółu (job, raport, aktualność każdej kohorty); `POST /reports/{reportId}/currentness` (kroki 1–4 per gra). Publikacja używa istniejącego `publishGridModelVersion` z `evaluationId`. Pełny pion OpenAPI/klient/wrapper/test żądania. Admin: `grid-model-comparison.tsx` pokazuje bazę i kandydata per gra/rola/nagranie, werdykty, powody i aktualność oraz akcję sprawdzenia aktualności.

**Błędy:** brak kohorty wymaganej gry `GRID_EVALUATION_GAME_COHORT_REQUIRED`; kohorta innej rodziny/bazy `GRID_EVALUATION_COHORT_BASE_MISMATCH`; kohorta nie frozen lub nie kwalifikuje się — kod z `eligibility`; kandydat bez parity lub niedostępny `GRID_EVALUATION_CANDIDATE_UNAVAILABLE`; za mało zdjęć kontrolnych — pokrycie `incomplete` i werdykt `NOT_EVALUABLE` (raport zapisany, publikacja zablokowana); błąd bind jednej gry kończy job `FAILED` z kodem po zapisaniu raportu, a retry ponawia brakujące bindingi.

## Expected files

- Istniejące: [neural_grid_training.py](../../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_training.py) — `compute_losses`, `train_run`, `evaluate_network`.
- Istniejące: [gate.py](../../../services/worker/src/game_predictor_worker/geometry_core/gate.py) — `GateThresholds`, `compare`, `decide`, `gate_photo`.
- Pozostały zakres wskazany w zaakceptowanym planie: i istniejące metryki; nowe proponowane `services/worker/src/game_predictor_worker/training_core/grid_evaluation.py`, `services/api/src/game_predictor_api/application/grid_model_evaluation.py`, `grid-model-comparison.tsx`.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/worker/tests/test_grid_model_evaluation.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Rzeczywisty v2 report writer jest akceptowany przez publication reader; v1 kontrakt bez regresji. Brak jednego multi-game bindingu, stale proof, crash/restart i withdrawal blokują nową kwalifikację; bez rebind/fallback/obcych source partition reads. Nowy most aktualności/proofs wymaga pełnego kontraktu przed kodem0997.
- Regresja dowolnej gry blokuje wspólny PASS.
- Brak detekcji ma koszt.
- Brak danych, parity lub aktualnych dowodów blokuje publikację.
- Dobór checkpointu nie używa REGRESSION.

## Verification

Zakres: WORKER, API, ADMIN, OpenAPI.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_datasets.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_neural_grid.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Nie zastępować nieznanej jakości zerowym błędem.

## Outcome

### Execution phase

- Wykonano 2026-10-16: Claude Code `claude-opus-5-5`/`xhigh` (sesja przełączona przez operatora), baza HEAD v1.7.388 `6397bc517e787271b76fa7d49425fef40fd6b785`, branch `codex/v3-grid-fine-tuning`, worktree `D:\game_predicotr\worktrees\v3-grid-fine-tuning`. `main` v1.7.376 pozostaje zawarty w gałęzi.
- Kontrakt przed kodem zapisano w Technical notes („Kontrakt przed kodem”) i jako D-559; podczas implementacji doprecyzowano: `parity` jako pole raportu, pin pliku wyników per rola (`detail`), kontrola gier rodziny tylko przy publikacji, trasa `POST /reports/{reportId}/currentness`, brak backfillu notices.
- Commit: v1.7.389 (poprzedni wersjonowany commit gałęzi v1.7.388); pełny hash w następnym commicie zgodnie z AGENTS.
- Audyt R1: [REVISE](../../quality/TASK-0997_AUDIT_gpt-6-astra_R1.md) (Codex `gpt-6-astra`/`high`): P0-1, P0-2, P2-1..P2-4; jedna runda poprawek wykonana. Audyt R2: [PASS](../../quality/TASK-0997_AUDIT_gpt-6-astra_R2.md), P0-1, P0-2, P2-1, P2-3 i P2-4 zamknięte, bez P0/P1; częściowo otwarte P2-2 domknięto po R2 (strażnik żądania także w `start`, selektor zablokowany w trakcie polecenia, test źródła), bez osobnego R3.
- Poprawki R1: proof przypina generację aktywnego magazynu gry, a bariera wymaga aktywnej lokalizacji tej generacji — usunięcie gry (odłączenie partycji bez wyzwalaczy, usunięcie `game_storage_locations`) daje stan `unavailable` i `GRID_MODEL_EVALUATION_STALE` (P0-1); `duplicate_predictions` w raporcie i bramce bez pogorszenia (P0-2); przed zbudowaniem raportu handler sprawdza ścieżkę i SHA każdego pliku `detail`, brak lub zmiana → `GRID_EVALUATION_DETAIL_CHANGED` (P2-1); panel odrzuca odpowiedzi dla wcześniejszego kandydata lub żądania (P2-2), klucz idempotencji jest związany z dokładną treścią polecenia (P2-3), etykieta PASS: „Poprawa gry treningowej bez regresji w pozostałych grach” (P2-4).

### Changed

- Domena: `domain/grid_model_evaluation.py` (zamknięty raport v2, polityka `grid-model-per-game-gate-v1` w jednej funkcji `decide_game`, `build_report`, czytnik przeliczający decyzje, `proof_state`); `domain/grid_model_publication.py` rozpoznaje v2 i przyjmuje wyłącznie zmierzony `PASS`, v1 bez zmian.
- Bariera: `application/grid_model_publication.py` sprawdza najnowszy proof każdej kohorty wobec bieżącego licznika notices (`GRID_MODEL_EVALUATION_REQUIRED`/`_STALE` ze wskazaniem gry) we wszystkich ścieżkach dowodu; publikacja wymaga też każdej gry rodziny. Repozytorium katalogu czyta tylko tabele `public`.
- Most i migracja: `0166_grid_model_evaluation` (etykieta joba, `grid_model_cohort_notice_marks` z wyzwalaczem `SECURITY DEFINER` na notices, append-only `grid_model_evaluation_cohort_proofs`, odebranie zapisu znaków wszystkim rolom poza właścicielem, manifest v17, strażnik downgrade); `storage/grid_model_evaluation_repository.py`, modele, `game_data_v2_manifest_v17.py`, rola aplikacji tylko czyta znaki (`_READ_ONLY_TABLES`), oczekiwany head `0166`, konsumenci runtime na v17.
- Ocena: `JobType.GRID_MODEL_EVALUATION` (lane `general`), `application/grid_model_evaluation.py` (utworzenie z walidacją kohort, gier rodziny i parity, idempotentny replay po kluczu, lista, szczegół, `prove_cohort` kroki 1–4 per gra, ponowne sprawdzenie aktualności), worker `training_core/grid_evaluation.py`, `images/grid_model_evaluation_handler.py`, `images/grid_model_evaluation_store.py`, rejestracja w CLI.
- API `/admin/grid-model-evaluations`, OpenAPI, wygenerowany klient, wrapper i test żądania; admin `grid-model-comparison.tsx` z `grid-model-evaluation-state.ts`, etykieta joba i podpięcie w sekcji „Geometria V3”.
- Testy: `services/api/tests/test_grid_model_evaluation_report.py`, `services/worker/tests/test_grid_model_evaluation.py`, PG `test_grid_model_evaluation_bridge_postgres.py` i `test_grid_model_evaluation_e2e_postgres.py`, admin `grid-model-evaluation-state.test.mjs`, klient `grid-model-evaluation-request.test.mjs`; aktualizacje testów manifestu/head do v17/0166.
- Naprawa fixture TASK-0995: `test_grid_training_cohort_e2e_postgres.py` uzupełniał tożsamość źródła przed zapisem geometrii; od poprawki R1 TASK-0995 kod produkcyjny wymaga bieżącego własnego targetu wskazującego dokładną rewizję, a E2E po R1 nie był ponownie uruchomiony (padał też na commicie v1.7.385). Fixture uzupełnia teraz tożsamość po zapisie człowieka i wskazuje tę rewizję; kod produkcyjny i strażnicy bez zmian.

### Verification results

- Po poprawkach R1: API raport/bramka/bariera 24 PASS (w tym duplikat i gra usuwana/usunięta/innej generacji), worker ocena 9 PASS (duplikat w REGRESSION innej gry, brak/zmiana pliku detail po restarcie), admin stan panelu 5 PASS, most PG z rzeczywistym usunięciem gry przez lifecycle PASS 33,7 s, E2E 0997 i trzy testy lane PASS łącznie 145 s (dowód `artifacts/audits/TASK-0997_E2E_6d4e7bd6820b409085cfddc3ca19cc2b`).
- Przed R1: API raport/bramka/bariera 20 PASS; worker ocena 7 PASS (identyczne wejścia, brak planszy z kosztem, regresja innej gry daje `REVISE`, restart bez ponownego pomiaru i z tym samym raportem, cancel między zdjęciami, zmienione piny, strażnik braku REGRESSION w wyborze checkpointu); admin 767/767; klient 2 PASS.
- PostgreSQL (izolowane bazy `*_test`): most 0166 PASS 19,7 s (wyzwalacz liczy tylko notices, rola aplikacji bez zapisu znaków i z odmową UPDATE/DELETE proof, czysty downgrade/upgrade, strażnik historii). E2E 0997 PASS 94,46 s na rzeczywiście zamrożonej kohorcie: prawdziwy serwis, handler, store i SQL bind (fałszywe tylko silniki ONNX, bazowe artefakty historyczne zaakceptowane bez fabrykowania wag), raport `PASS`, proof `current`, publikacja i eligibility, potem rzeczywisty revert korekty → `GRID_MODEL_EVALUATION_STALE`, ponowne sprawdzenie odmawia (`GRID_COHORT_LABEL_STALE`) i blokada trwa; restart bez pomiaru. Dowód: `artifacts/audits/TASK-0997_E2E_696da44c27e7471abb87e6df76557f4c`. E2E TASK-0995 po naprawie fixture PASS 100,62 s.
- Regresje dotknięte zmianą: publikacja/rejestr/readiness/manifest/routing/retencja/proposals/reinference/cohort storage/training runs PASS; `openapi:check`, `docs:check`, `code-map:check` PASS; Ruff PASS; mypy projektu: jedyne 2 błędy w nietkniętym `schemas/source_lattice_geometry.py` (od v1.7.224).
- Pełne zestawy: API 3239 PASS, 482 skip, 4 FAIL przed poprawką oczekiwań: lista typów jobów w `test_jobs_api.py` (z 0997) oraz trzy przestarzałe oczekiwania potwierdzone na czystym HEAD — przestrzeń `grid-training-cohorts` z TASK-0995 w `test_image_storage_api.py` i lane `grid_training` z TASK-0996 w `test_worker_lanes.py`; po aktualizacji oczekiwań te trzy pliki 40 PASS, 1 skip. Formatowanie wrapperów klienta z TASK-0996 wyrównano prettierem. Worker 2963 PASS, 43 skip, 17 FAIL wyłącznie środowiskowych: `.venv` worktree jest dowiązaniem do venv głównego checkoutu, którego instalacja editable wskazuje kod `main` v1.7.376 (bez `domain/canonical_source` z tej gałęzi), więc 16 testów laboratorium uruchamiających podproces bez `PYTHONPATH` nie importuje API, a jeden odrzuca `sys.executable` jako reparse point; na czystym HEAD w katalogu bez dowiązania ten ostatni przechodzi. Admin 768/768, klient 128/128.

### Not completed

- Rzeczywista ocena na danych operatora, publikacja, aktywacja i migracja bazy operatora — poza zakresem (koniec planu, osobne zgody).
- Panel admina sprawdzony testami i typami, bez uruchomienia w przeglądarce (usługi nie były startowane). Czas oceny CPU na prawdziwych zdjęciach nie był mierzony.

### Documentation updates

- D-559 (pełny wpis i indeks; D-530 przeniesiony do archiwum indeksu), sekcje D-559 w architekturze i wymaganiach VISION_LAB, kontrakt w tym pliku, CURRENT_STATE, CODE_MAP.

### Recommended next task

- TASK-1006
