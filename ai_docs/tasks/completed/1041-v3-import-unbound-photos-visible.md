# TASK-1041 — Pominięte zdjęcia V3 bez przypisania plansz są jawne

## Status

`done`

## Goal

Import V3 nie pomija już po cichu zdjęć `slot_binding_required`: Admin pokazuje
ich liczbę przed startem, API odmawia startu bez jawnego potwierdzenia, a job
importu zapisuje liczbę i pełną listę pominiętych zdjęć.

## Context

Operator wgrał do gry `777a2` staging `60a7bc4d` (2200 zdjęć 1080×1920 całej
maszyny, plansze 1–19810). Preflight `fac295e2` i import `c2b7d87a`: 1962
zdjęcia miały status `slot_binding_required`, zaimportowano 238. Nigdzie poza
manifestem preflightu (`artifacts/data/page-geometry-manifests/`) nie ma śladu
pominięcia, więc w „Brakach plansz” widać dużą lukę bez przyczyny.

Ścieżka kodu (odczyt `main` 2026-10-16):

- `neural_grid_proposal.py` `associate_expected_slots` wiąże tylko dokładny,
  jednoznaczny przestrzennie inwentarz (liczba wykryć = liczba plansz zakresu
  `seq_X-Y.jpg`);
- `neural_page_geometry_preflight.py` `_evaluate` oznacza resztę
  `slot_binding_required` / `NEURAL_GRID_SLOT_BINDING_REQUIRED` (albo
  `NEURAL_GRID_SOURCE_TIME_LIMIT`);
- `neural_pending_geometry.py` `bound_neural_originals` pomija je (`continue`),
  wywołanie w `production_workflow.py` `ProductionImageImportWorkflow.__call__`;
- `api/image_imports.py` `start_ready_browser_import`: bramka „najpierw popraw
  geometrię” działa tylko dla manifestów nie-neuronowych.

## Dependencies / entry conditions

- Fakt: `main` 756a10e5 (v1.7.387). Gałąź `codex/v3-grid-fine-tuning` nie
  zmienia reguły wiązania (ta sama reguła, ten sam model v1 dla 777a2).
- Zlecenie: sesja nadrzędna operatora (2026-10-16), pojedynczy task bez planu.
- Brak migracji bazy: zapis idzie do `checkpoint_payload` joba i artefaktu.

## Recommended execution

Claude Opus 5.5, reasoning high: pion API + worker + Admin z kontraktem
OpenAPI, średnie ryzyko regresji startu importu. Audyt krzyżowy nie jest
wymagany (brak planu z kolumną `Dodatkowy review`; audyty zawieszone przez
operatora).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [D-544](../../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2)
- [D-523](../../process/decisions/DECISION_LOG_2026.md#d-523--operational-neural-crops-and-recoverable-symbol-verification)
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Preflight raportu (`previewReadyBrowserImageImport`) zwraca
  `neuralUnboundSourceCount`, `neuralUnboundAttestedBoardCount` i
  `neuralUnboundCountPreflightJobId` z ukończonego manifestu neuronowego (bez
  źródeł wykluczonych przez operatora).
- Start (`startReadyBrowserImageImport`) przyjmuje opcjonalne
  `confirmedNeuralUnboundSourceCount`. Gdy przypięty manifest neuronowy ma
  N > 0 niezwiązanych zdjęć, a potwierdzenie nie jest równe N (także przy
  replayu istniejącego runu), API zwraca 409
  `NEURAL_GRID_UNBOUND_SOURCES_CONFIRMATION_REQUIRED` z `details`.
- Worker importu V3 zapisuje niezmienny raport
  `data/image-import-unbound-sources/{jobId}.json` (pełna lista: checksum,
  ścieżka, zakres z nazwy pliku, kod powodu) i podsumowanie
  `neural_unbound_sources` w każdym checkpoincie (liczba, liczba plansz z
  zakresów, liczniki powodów, checksum i ścieżka raportu, próbka ≤ 20).
- `JobResponse.progress.neuralUnboundSources` (typowany) dla jobów importu.
- Admin: ostrzeżenie przed startem z liczbą, checkbox „Importuj bez nich”,
  przycisk otwierający podgląd propozycji sieci z `NeuralSourceBindingPanel`;
  w liście importów wiersz „Pominięte bez przypisania plansz: N”.
- OpenAPI, wygenerowany klient, wrapper i testy żądań.

## Out of scope

- Częściowe automatyczne wiązanie przy mniej niż 9 wykryciach (zmiana polityki
  wymaga decyzji operatora i nowego D-); opisane tylko jako opcja.
- Ponowne przetwarzanie `/{source_job_id}/reprocess` i re-inferencja: bez zmian.
- Zmiana `missing-boards` API.
- Dane operatora, staging, działające usługi, migracje.

## Acceptance criteria

- [x] Preflight z niezwiązanymi zdjęciami blokuje start bez potwierdzenia (409),
      a z potwierdzeniem równym liczbie tworzy job.
- [x] Wynik joba importu raportuje liczbę i listę pominiętych zdjęć (checkpoint
      + niezmienny raport), widoczne w `JobResponse.progress`.
- [x] Admin pokazuje ostrzeżenie, wymaga zaznaczenia i pokazuje licznik w liście
      importów.
- [x] Kontrakt: backend, OpenAPI, klient, wrapper, test żądania.

## Technical notes

- Niezwiązane źródło = wpis manifestu `status == "slot_binding_required"`
  (powód z `reasonCode`); `skipped_human_resolved` nie jest pominięciem.
- Potwierdzenie to liczba, nie flaga: nowy preflight po ręcznym wiązaniu zmienia
  liczbę, więc stare potwierdzenie przestaje pasować.
- Raport workera jest deterministyczny dla joba (bez znaczników czasu), więc
  wznowienie po restarcie zapisuje identyczne bajty; inna treść = błąd
  `NEURAL_GRID_UNBOUND_SOURCES_REPORT_COLLISION`.
- Pełna lista nie trafia do checkpointu (checkpoint jest nadpisywany przy każdym
  kroku i serializowany w listach jobów); checkpoint ma tylko próbkę.

## Expected files

- `services/worker/src/game_predictor_worker/images/neural_pending_geometry.py`
- `services/worker/src/game_predictor_worker/images/production_workflow.py`
- `services/api/src/game_predictor_api/api/image_imports.py`
- `services/api/src/game_predictor_api/schemas/image_imports.py`
- `services/api/src/game_predictor_api/schemas/jobs.py`
- `packages/admin-api-client/openapi/*`, `src/generated/*`, `src/index.ts`
- `apps/admin/src/features/imports/*` (panel, akcje, stan)
- testy API, workera, klienta i Admina; dokumentacja wymagań i kontraktu

## Test cases

- API: manifest z 1 niezwiązanym zdjęciem → preflight `neuralUnboundSourceCount=1`;
  start bez potwierdzenia → 409; z potwierdzeniem 1 → 201; replay bez → 409.
- API: manifest w pełni związany → start bez potwierdzenia przechodzi; zła
  liczba potwierdzenia → 409.
- Worker: import, w którym wszystkie źródła są niezwiązane → checkpoint z
  `neural_unbound_sources` i raport z pełną listą; ponowny przebieg zapisuje
  te same bajty.
- Worker: `_ProgressWindowContext` przenosi podsumowanie do każdego checkpointu.
- API: `JobResponse.progress.neuralUnboundSources` parsuje checkpoint.
- Admin: stan startu blokuje bez potwierdzenia; akcja wysyła liczbę.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_page_geometry_api.py services/worker/tests/test_neural_folder_correction_pipeline.py -q
npm run openapi:check
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Istniejący import `c2b7d87a` nie ma podsumowania (powstał przed zmianą);
  jego luka jest widoczna tylko w manifeście preflightu `fac295e2`.
- Opcja na później: częściowe wiązanie przy mniej niż 9 wykryciach (decyzja
  operatora, nowe D-).

## Outcome

Commit: v1.7.388 (hash dopisuje kolejny commit).

Wykonawca: Claude Opus 5.5 (sesja poboczna sesji operatora). Bez audytu
krzyżowego (task poza planem; audyty zawieszone przez operatora).

### Changed

- Worker: nowy moduł `images/neural_unbound_sources.py`
  (`unbound_neural_sources`, `record_neural_unbound_sources`): niezmienny raport
  `data/image-import-unbound-sources/{jobId}.json` z pełną listą i podsumowanie
  `neural_unbound_sources` (liczba, plansze zakresów, powody, checksum, ścieżka,
  próbka ≤ 20). `ProductionImageImportWorkflow.__call__` wpisuje podsumowanie do
  checkpointu `image_deferred_geometry_skip` i do `checkpoint_extras` każdego
  checkpointu pipeline'u. Reguła wiązania bez zmian.
- API: `_neural_unbound_source_counts`; preflight zwraca
  `neuralUnboundSourceCount`, `neuralUnboundAttestedBoardCount`,
  `neuralUnboundCountPreflightJobId`; start przyjmuje
  `confirmedNeuralUnboundSourceCount` i bez równej liczby kończy się 409
  `NEURAL_GRID_UNBOUND_SOURCES_CONFIRMATION_REQUIRED` (także replay);
  `JobProgressResponse.neuralUnboundSources` (`NeuralUnboundSourcesJobProgressResponse`).
- Kontrakt: OpenAPI, wygenerowany klient, eksport typów w wrapperze, test żądania.
- Admin: ostrzeżenie z liczbą zdjęć i plansz, przycisk „Przypisz plansze ręcznie”
  (otwiera podgląd propozycji sieci z `NeuralSourceBindingPanel`), checkbox
  „Importuj bez tych N zdjęć” wymagany przez `canStartReadyImport`; potwierdzenie
  wiązane z stagingiem, manifestem i liczbą; ponowny odczyt licznika po
  ukończeniu preflightu i po 409; w liście importów „Pominięte bez przypisania
  plansz: N zdjęć” z powodami, próbką i ścieżką pełnej listy.

### Verification results

- `pytest` (izolowane, bez bazy): `test_neural_page_geometry_api.py`,
  `test_jobs_api.py`, `test_managed_reprocess_evidence.py`,
  `test_image_imports_api.py`, `test_neural_unbound_sources.py` (nowy, 5),
  `test_neural_folder_correction_pipeline.py`, `test_production_image_workflow.py`,
  `test_neural_page_geometry_preflight.py`: 207 passed; wcześniej także
  `test_image_import_storage_resume.py`, `test_virtual_only_import_writers.py`,
  `test_lateral_partial_engine_contract.py`: PASS.
- Test bramki: preflight z 1 niezwiązanym zdjęciem → start bez potwierdzenia i z
  liczbą 2 → 409, z liczbą 1 → 201, replay bez potwierdzenia → 409, związany
  manifest ze starym potwierdzeniem → 409, bez potwierdzenia → nowy run.
- Test wyniku: import bez związanych źródeł zapisuje checkpoint z
  `neural_unbound_sources` i raport; częściowy import niesie podsumowanie w
  checkpointach pipeline'u; ponowny zapis daje te same bajty, inna lista → kolizja.
- `ruff check`, `ruff format`, `mypy --strict` (5 zmienionych modułów): PASS.
- Klient: `check-generated-client` aktualny, `tsc` wrappera PASS, 83 testy PASS.
- Admin: `typecheck` PASS, `lint` 0 błędów (5 starszych ostrzeżeń), 738 testów
  PASS, `neural-import-readiness` 16 PASS.
- Środowisko: worktree na D bez `.venv` (venv z `D:\game_predicotr` +
  `PYTHONPATH` worktree); pełne `npm install` odmówiło zależności git
  (`allow-git=none`), więc zainstalowano tylko workspace'y Admina i klienta.

### Not completed

- Istniejący import `c2b7d87a` (777a2) powstał przed zmianą i nie ma
  podsumowania; jego 1962 pominięte zdjęcia są tylko w manifeście preflightu
  `fac295e2`.
- Nie sprawdzono w uruchomionym Adminie (usługi należą do operatora; po scaleniu
  wymagany restart API, workera i Admina).
- `npm run quality` w całości nie był uruchamiany.

### Documentation updates

- `ai_docs/requirements/IMAGE_INGESTION.md`, `ai_docs/architecture/API_CONTRACT.md`,
  mapa kodu (`CODE_MAP.md`, `CODE_MAP_SYMBOLS.md`).

### Recommended next task

- Decyzja operatora: częściowe automatyczne wiązanie przy mniej niż 9 wykryciach
  (nowe D-) albo ręczne wiązanie próbki zdjęć 777a2 i nowy preflight.
