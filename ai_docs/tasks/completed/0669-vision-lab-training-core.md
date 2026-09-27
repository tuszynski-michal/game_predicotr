---
title: TASK-0669 — T04 — izolowany rdzeń treningu
status: done
last_updated: 2026-09-27
---

# TASK-0669 — T04 — izolowany rdzeń treningu

## Status

`done`

## Goal

Dostarczyć neutralny rdzeń, trwały backend runów i izolowane środowisko GPU z checkpointem v2.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

D-456: dla zatwierdzonego pilota wystarczy T03k done, zamrożony manifest
i aktualny split całymi grami. Pełny pomiar i verified rodzin T03 są odroczone,
nie uznane za wykonane. Przed kodowaniem ponownie sprawdź bieżący kod,
dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz
w planie i tasku. T04 nie może trenować na final_test/unseen.

## Recommended execution

`gpt-6-sol`, reasoning `high`; osobny audyt `gpt-6-astra`, reasoning `medium`. Granice importów, protokół runów i checkpointy wpływają na odtwarzalność treningu. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T04 — izolowany rdzeń treningu)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Wydzielić czyste funkcje bez przepinania training_job.py; adapter plikowy, constraints CUDA, kontrola GPU, checkpoint optimizer/scheduler/RNG/config/data SHA i odczyt v1. Zaimplementować backend `RunManager` oraz endpointy start/list/detail/cancel/retry dla późniejszego panelu T08. Stany: `queued`, `running`, `succeeded`, `failed`, `cancelled`; bez pauzy.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [x] Test importów lab/produkcja/rdzeń; GPU wykonuje krótkie obliczenie lub jawny brak; v2 wznawia, v1 odczytuje bez obietnicy identyczności.
- [x] `queued` jest trwałe przed startem; identyczny `requestId`+payload zwraca ten sam run, inny payload konflikt. Restart nie tworzy duplikatu. Cancel zachowuje checkpoint, jawne retry ma nowy lease i odgradza starego writera; sukces ma checksumowany raport.
- [x] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

### Doprecyzowany kontrakt pilota D-456 (przed implementacją)

- Izolowany runtime `.venv-vision-lab` poza główną `.venv`; CUDA13.0 torch
  2.12.1/torchvision0.27.1 instalowane pierwsze. Własne przypięte requirements
  i constraints, projekt editable --no-deps; bez zbędnych DB/Paddle. Główne
  środowisko i produkcyjny training_job.py pozostają nietknięte. Skrypt
  PowerShell sprawdza wersje/GPU i krótkie obliczenie w nowym procesie.
  Nie uruchamia nieograniczonego install; kroki mają jawne timeouty.
- Manifest T03k: checksummed {payload,sha256}, format
  vision-lab-whole-game-pilot-manifest-v1, status frozen; manifest_id jest
  digestem payloadu, plik w LAB/manifests/<manifest_id>.json. Rozdzielić
  snapshot_manifest_id od katalogowego snapshot_id. Walidować split/policy,
  kompletną kohortę, mapę gier, unikalność i komplet kluczy targetów względem
  geometry_target_fingerprints oraz pełne nodes/revision/SHA/ścieżki i zgody.
  Proposal lub null fingerprint odrzucić RUN_MANIFEST_NOT_FROZEN. Rozwiązywać
  ścieżki tylko przez Catalog, nigdy według dowolnej ścieżki z JSON/HTTP.
  Integralność holdoutów kontroluje metadane; TrainingInputs zwraca wyłącznie
  development/validation i nigdy nie ładuje obrazów final_test/unseen.
  Odczyt bajtów przez istniejący verifier snapshotu wyłącznie dla SHA jest
  dozwolony; zakaz dotyczy dekodowania i dostarczenia holdoutów do modelu,
  augmentacji, metryk lub strojenia. Test kontroluje wywołania loadera obrazów,
  nie blokuje niezależnej kontroli checksum całego katalogu.
- POST /runs przyjmuje request_id, manifest_id, model_version,
  preprocessing_version, topology, seed, purpose (smoke/train), configuration.
  GET /runs ma offset/limit, GET /runs/{id} szczegóły; POST
  /runs/{id}/cancel i /retry przyjmują request_id i expected_attempt. Klient
  nie podaje ścieżek, interpreterów ani poleceń. Rejestr wykonawców jest
  zamknięty; model hybrydy dostarcza T05, nie atrapowy sukces T04.
- Najwyżej jeden aktywny run; nowy start przy aktywnym zwraca RUN_BUSY.
  To nie kolejka wielu zleceń. Trwały queued zapisuje attempt=1, lease,
  rosnący fencing token i launch_deadline przed spawnem pod blokadą procesu.
  Tylko newly_created uruchamia ukryty proces. Worker sam claimuje queued,
  zapisuje PID i czas utworzenia procesu po kontroli tokenu. Restart/replay
  nigdy nie uruchamia automatycznie drugiej kopii; wygasły queued bez claim
  staje się recoverable failed. Start/cancel/retry mają trwałe receipts.
- Żywy zgodny PID+czas utworzenia jest tylko obserwowany, również przy starym
  heartbeat (diagnostyka unresponsive). Martwy lub ponownie użyty PID po
  lease timeout daje recoverable failed. Brak możliwości kontroli tożsamości
  procesu daje RUN_PROCESS_IDENTITY_UNAVAILABLE, bez retry/zabijania.
  Retry tylko failed/cancelled po potwierdzeniu braku poprzednika i CAS
  expected_attempt; nowy lease/fence/attempt, bez resetowania budżetu runu.
- Heartbeat, checkpoint, raport i terminalny zapis wymagają zgodnego lease,
  attempt i fence. Artefakty w osobnym katalogu próby, SHA i atomowa publikacja;
  stary writer nie może podmienić wskaźnika checkpointu lub zakończyć runu.
  Fresh walidacja manifestu/state przy start/retry/claim i przed publikacją;
  drift daje RUN_DATA_DRIFT i zachowuje ostatni checkpoint.
- Neutralny checkpoint v2: model/optimizer/scheduler, RNG Python/NumPy/torch
  CPU/CUDA i generator DataLoadera, config/dataSHA/manifest, model/topology/
  preprocessing/seed, epoch/global_step, history/best state. SHA przed
  deserializacją, weights_only=True i bezpieczne reprezentacje RNG.
  Exact resume gwarantowane tylko na completed_epoch boundary (cursor=0).
  Checkpoint epoki0 zapewnia punkt odtworzenia przed pierwszą partią.
  V1 odczytuje modelState/optimizerState/history/inputFingerprint z jawnym
  ograniczonym wznowieniem; brak RNG i spójności best-model/last-optimizer
  nie może być przedstawiany jako exact resume. Produkcyjnego v1 nie zmieniać.
- Cancel queued kończy bez spawnu; running zapisuje intencję i kończy po
  checkpointcie epoki. Twardy budżet sprawdzany przed/po każdej partii ma
  pierwszeństwo; przerwana epoka nie udaje ukończenia. Ostatni completed
  checkpoint pozostaje resume-safe, ewentualny partial jawnie approximate.
  Budżet runu obejmuje retries, RUN_BUDGET_EXHAUSTED bez pozostałego limitu.
  Naliczenie nie pochodzi z checkpointu: przed każdą partią atomowo i trwale
  rezerwuje się jeden krok w stanie runu; crash go nie zwraca. Czas ma trwały
  licznik użycia, started_at/last_accounted_at i deadline próby wynikający
  z pozostałego limitu. Heartbeat/finalizacja monotonicznie naliczają czas.
  Po crash martwego procesu niepotwierdzony odcinek do czasu wykrycia nalicza
  się konserwatywnie (do pozostałego limitu), także gdy obejmuje wyłączenie
  komputera; nie przedstawiać tego jako zmierzonego czasu GPU. Cofnięty lub
  niewiarygodny zegar oznacza wyczerpanie pozostałego budżetu, nie jego zwrot.
  Długi przestój może zatem wyczerpać limit pilota; kolejny eksperyment
  wymaga odrębnej zgody. Retry nie odtwarza liczników z checkpointu epoki.
  Smoke max50kroków i train max20epok/1800s to osobne zatwierdzone runy;
  T05 nie omija RunManager wywołaniem adaptera bokiem.
- Nowe pliki: training_core/checkpoint.py i runtime.py (stdlib/torch/numpy),
  vision_lab/training_manifest.py, training_adapter.py, run_contracts.py,
  runs.py, run_worker.py, process_identity.py. Dopuszczalne małe moduły
  pomocnicze zamiast monolitu. Istniejące api/proxy/OpenAPI/client/wrapper
  i test HTTP uzupełnić jednym pionem. Konfiguracja manifest/run root oraz
  izolowanego interpretera tylko po stronie operatora. Błędy domenowe 409,
  nieznany run 404, błędny schemat 422, brak konfiguracji/runtime 503.

Szczegółowy kontrakt powyżej jest wiążący dla implementacji. Żywy zgodny
PID i czas utworzenia nigdy nie stają się failed wyłącznie przez stary
heartbeat/lease. Dopiero potwierdzony brak tego procesu pozwala wykonać
odzyskiwanie i konserwatywne rozliczenie budżetu; restart nie spawnuje.
Wymagany kontrakt API i test żądania powstają w tym tasku. Zachowaj izolację
od produkcyjnego handlera.

## Expected files

- Istniejące `services/worker/src/game_predictor_worker/symbols/training_job.py::_train_epochs` (tylko analiza), `services/worker/src/game_predictor_worker/images/keypoint_geometry/model.py::KeypointGeometryHeatmapNetwork`.
- Nowe (proponowane) `services/worker/src/game_predictor_worker/training_core/checkpoint.py::load_checkpoint`, `.../vision_lab/training_adapter.py::train_from_manifest`, `.../vision_lab/runs.py::RunManager`, `RunState`, `create_or_get_run`, `cancel_run`, `retry_run`, `.../vision_lab/api.py::start_training_run`, `services/worker/tests/test_vision_lab_training_core.py`, `services/worker/tests/test_vision_lab_runs.py`, `requirements-vision-lab.txt`.

## Test cases

- Manifest: zła koperta/proposal/stale, brak/duplikat targetu, błędne nodes,
  snapshot ID, ścieżka lub symlink poza katalogiem blokują; integralność
  holdoutów sprawdzona, zero odczytów ich obrazów przez TrainingInputs.
- V2 uninterrupted vs resume na granicy epoki: model, optimizer, scheduler
  i RNG zgodne; v1 jawny warning. Uszkodzona najnowsza publikacja nie usuwa
  poprzedniego checkpointu; checksum raportu sukcesu obowiązkowa.
- Równoległe starty, utrata odpowiedzi start/cancel/retry, crash przed/po
  spawnie, restart żywego procesu, ponownie użyty PID, martwy lease, wygasły
  queued oraz odgrodzony stary heartbeat/checkpoint/report. Budżet zachowany
  przez retry; wyczerpanie nie udaje ukończenia epok. Małe testy, bez benchmarku.
- Crash po rezerwacji kroku/przed checkpointem, powrót do starej epoki,
  długi przestój i cofnięty zegar: kroki/czas nie są odzyskiwane przez retry;
  niepotwierdzone naliczenie odróżnione w raporcie od czasu zmierzonego.
- Proxy rozszerzyć wyłącznie o runs, bez otwierania dowolnych ścieżek/query:
  apps/vision-lab/src/lib/boundary.ts, src/app/api/lab/[...path]/route.ts,
  test/boundary.test.mjs. offset/limit wyłącznie listy runs; identyfikatory
  i cancel/retry ściśle walidowane. Backend/OpenAPI/client/request spójne.

- Nowy checkpoint odtwarza RNG i optimizer; stary v1 daje jawnie ograniczone wznowienie; importy nie przeciekają. Utrata odpowiedzi i identyczne retry → jeden run; inny payload pod tym samym ID → konflikt. Crash przed/po spawnie, restart z żywym procesem, wygasły lease, cancel po checkpointcie i fenced retry → brak duplikatu lub starego zapisu.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_training_core.py','services/worker/tests/test_vision_lab_runs.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Po teście wykonaj lint/typecheck zmienionych modułów i wymagane kontrole kontraktu, każdą jako skończony proces z limitem maksymalnie 120 s. Testy tu są planowane, niezaliczone; zaliczenie wymaga kryteriów powyżej i braku regresji.

## Risks / open questions

- Zmiana schematu danych, zakresu zdjęć lub kosztu poza planem wymaga jawnej aktualizacji przed zależnym działaniem.

## Outcome

T03k odebrany: v1.7.28 / 84f523ea8a26a45ce419dfc65cd64d73fdaf0cba.
Manifest 1e7cc3a70a583320a1f051ef6598c35595aeefb3b94a60631d311c1da0b25bb0,
split 3ebcc3a401a17295c5509cbe5d1f59886fa7a87588427c6bed671665dbe63572,
stan rev268. Audyt kontraktu T04 Astra medium PASS po dwóch doprecyzowaniach
P2 (żywy proces i trwały budżet); nie są to wyniki testów implementacji.
Implementacja Sol high odebrana przez Astra medium po jednym cyklu poprawek,
bez pozostałych P0–P2. Definition of Done i zakres T04 spełnione; trening
nadal należy do T05. Osobny commit v1.7.29 przygotowany; pełny hash po zapisie.

### Changed

- Neutralne checkpointy v2 z kontrolowanym odczytem v1 i runtime epok.
- Adapter zamrożonego manifestu, trwałe runy/API/proxy/klient, fencing,
  procesowe odzyskiwanie, nieodwracalny licznik budżetu i watchdog.
- Oddzielne środowisko CUDA, przypięte zależności, skrypty kontroli i instrukcja.

### Verification results

- Wykonawca: backend46/46, UI35/35, client9/9 PASS; Ruff/mypy28/ESLint,
  oba TypeScript, OpenAPI/generated, PS parse i diff check PASS.
- GPU w nowym procesie PASS; główna .venv nadal CPU. Rzeczywisty manifest:
  90 development/30 validation, rev268 bez zmian, zero dekodowania/startów.
- [Raport i dowody](../../quality/VISION_LAB_TRAINING_CORE_20260927.md).
  Astra medium: końcowy PASS po poprawce fresh walidacji przed publikacją
  checkpointu i regresji zachowania poprzedniego zapisu. Niezależnie24backend,
  9client,35UI,3testy checkpointów i9wariantów ochrony katalogów PASS.

### Not completed

- T05/trening, pełne quality/build repo,
  restart systemu Windows, aktywacja modelu i push nie zostały wykonane.

### Documentation updates

- Wymagania, architektura i instrukcja VISION_LAB; task, Current State i raport jakości.

### Recommended next task

- Po osobnym commicie: T05 w zatwierdzonym zakresie pilota D-456.
