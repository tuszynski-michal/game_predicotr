---
title: TASK-1003 — Podgląd i raport ponownego rozpoznania
status: done
last_updated: 2026-10-15
---

# TASK-1003 — Podgląd i raport ponownego rozpoznania

## Status

`done`

## Goal

Operator rozumie zakres, koszt i wynik przebiegu.

## Context

Task jest częścią zaakceptowanej rewizji 6. Podgląd zakresu i raport operacji. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0999, TASK-1013.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `medium`. gotowy kontrakt backendu.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [ADMIN_APP](../../requirements/ADMIN_APP.md).
- [API_CONTRACT](../../architecture/API_CONTRACT.md) — istniejący pion reinferencji D-551.
- [IMAGE_INGESTION](../../requirements/IMAGE_INGESTION.md) — selected-only zapis/ochrona.
- [D-551](../../process/decisions/DECISION_LOG_2026.md#d-551--propozycje-dla-błędnej-siatki-v3) — addytywny kontrakt1003 przyjęty przed kodem.
- Zakres odczytu uzupełniający z planu: ADMIN_APP, D-541, zakresy z sekcji 2.

- [D-541](../../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Oddzielne liczby zdjęć, slotów, plansz i komórek; domyślny zakres, pilot do 100, jawny szeroki wybór, postęp i wznowienie.
- Raport rozróżnia propozycje, automatyczne zapisy, ochronę, brak zmiany i konflikty.

## Out of scope

- Frontend nie wylicza samodzielnie kwalifikacji ani zakresu na podstawie jednego licznika.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Stary preview daje konflikt; utrata odpowiedzi odtwarza tę samą operację; zmiana gry nie miesza stanu; wszystkie automatyczne nie są domyślnie zaznaczone.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

### Kontrakt przed implementacją — 2026-10-15

Baza v1.7.380 / `a688a40108f33ede3a894002a6fc8a8ed53d8141` po osobnym commicie1013 i Claude high R2 PASS.
Lead rozstrzygnął kontrakt na podstawie read-only preflight:
`TASK-1003_PREFLIGHT_NOTES.json`, `TASK-1003_STATS_HISTORY_PREFLIGHT.json`
i `TASK-1003_ROOT_CONTRACT_PENDING.md` w artifacts/audits. Poniższa pełna
treść i D-551 są trwałym źródłem, bez zależności od ignorowanych artefaktów.
Wykonawca gpt-6.1-sol/medium; audyt Claude medium/do1200s. Zatwierdzony
zakres całego planu obejmuje potrzebne zgodne rozszerzenie istniejącego API.

### Liczniki, źródło prawdy i historia

- Zachowujemy znaczenie sourceCount/targetCount/processedSources/outcomes/
  sourceStatusCounts. Dodajemy zamknięte, generowane DTO scopeStats/effectStats
  z wersjami. Stare operacje: null/nie zapisano, nigdy fikcyjne0. Podczas
  preparing liczby ukończonego zakresu pozostają niedostępne; po finalizacji
  opisują frozen manifest i okno przygotowania, bez obietnicy atomowego
  snapshotu całej żywej gry.
- scopeStats: sourceOccurrenceCount (wystąpienia w import/source/execution,
  nie globalny pixel dedup), selectedSlotCount, unique existingBoardCount,
  deferredSlotCount, actual frozen existingCellCount, availableCellCount,
  potentialCellCount według przypiętej topologii. Potencjalne komórki nie są
  obietnicą zapisu ani zmiany pikseli. proposalOnly/protected/automaticCandidate
  są rozłączne według istniejącej kolejności ochrony; nie sumujemy kategorii
  globalnych jako odrębnych braków. Liczby wynikają z istniejących snapshotów.
  Source/slot/klasy zbieramy inkrementalnie w prepare_page. Unikalne frozen
  board/cell IDs finalizuje operation-scoped SQL COUNT(DISTINCT) z JSONB,
  bez całej listy seenUUID w Python/JSON operacji i bez whole-game/GET scan.
  Source unique(game,operation,source_image_id), unique review.board i
  cells(item,index) dają normalną jedyność, lecz nie zakazują przeniesienia
  board do innego source między stronami przygotowania. Dlatego SQL domyka
  deduplikację także tego przypadku. Finalizacja ma statement_timeout30s;
  timeout/infra cofa jej całość, bez publikacji częściowego manifestu/stats0.
  Trwałe strony/cursor pozostają do jawnego resume. Legacy pin nie wykonuje
  nowej agregacji. Koszt pełnego szerokiego zakresu jest niezmierzony;
  preparing pokazuje finalizację, bez obietnicy czasu ani ukrytego benchmarku.
- effectStats: recordedTargetCount, automaticWrittenBoardCount,
  createdBoardCount, createdCellCount, changedExistingPixelCellCount,
  unchangedExistingPixelCellCount, newlyRequiresReviewCellCount,
  pixelComparisonUnavailableCellCount, notRecordedTargetCount. Ponowna ocena
  może przecinać zmienione piksele. Nowe deferred cells są created, nie changed
  existing. Brak starego checksumu to unknown comparison, nie udowodniona zmiana.
  proposal/protected/conflict/unchanged nie są automatycznymi zapisami ani
  potwierdzonymi naprawami. UI opisuje wykonane działanie, nie domniemaną jakość.
- Minimalny receipt rzeczywistych komórek before/after obejmuje wyłącznie
  wybrane cele w dotychczasowej transakcji źródła: przed materializacją deferred,
  po istniejącym D-462 synchronize. Bez renderowania starych pikseli dla samego
  licznika. Target receipt i operation aggregate/progress zapisują się atomowo
  raz; restart/replay nie dubluje agregatu. Zachowujemy domyślną sygnaturę i
  konsumentów automatic writera przez jawny opcjonalny collector albo typowany
  opt-in, bez zmiany geometrii/ochrony/ownership/D-462. Istniejące JSON wystarczą;
  brak migracji wyłącznie dla tych statystyk.
- Nowe prepare przypina server-owned statsPolicy w operation.document oraz
  identyczne stats_policy w immutable job.input_payload. Nie jest to pole
  klienta/modelSnapshot/target snapshot/manifest/scopeSignature. Oba absent:
  legacy; oba exact known: nowy kontrakt; brak jednego/nieznana wersja/mismatch:
  fail-closed przed pracą. Replay/resume nie podnosi starego pinu. Stara gałąź
  reportSHA pozostaje dokładnie zachowana; wyłącznie nowy pin hashuje policy
  i finalne stats. Historyczny zgodny pilot zachowuje SHA i unknown stats.

### Odczyty, pilot i paginacja

- Istniejący detail GET ujawnia executionScope, selector, pilotAcknowledgement,
  executionQuarantine i już zapisane membership/preparation timestamps.
- Addytywny GET kolekcji w istniejącym namespace grid-reinference: wyłącznie
  metadane operacji gry, keyset(game,id) DESC, limit1..50, opcjonalnie
  compatible_with_operation_id. Kolejność UUID jest stabilnym przejściem,
  nie chronologią. Timestampy pokazujemy bez obietnicy newest-first.
  Cursor wiąże grę, filtr/reference, reference scopeSignature i lastId;
  mismatch daje typed cursor409, obca reference scopedNOT_FOUND.
- Jawne READ/RLS/game predicate i istniejący statement bound; bez source/
  target/photo scan, OFFSET i totalCOUNT. Filtr zgodnych completed pilotów
  używa rzeczywistych warunków scopeSignature/pilot/count/report. Lista jest
  doradcza, ACK ponownie sprawdza istniejący autorytatywny transition. Brak
  manualnego przepisywania UUID pilota; brak pozornego PASS jakości.

### Jedna ścieżka Admina i trwałe polecenia

- Zastąpić montowany legacy pending-preview/start w GridQualityPanel jednym
  nowym workflow. Wejście/reload tylko GET history/detail/targets, bez prepare,
  joba, inferencji, POST i automatycznej próby pending komendy.
- Domyślnie grid_issue+deferred. unconfirmed/all_automatic jako osobne opt-in.
  Jawne prepare pilota do100 wystąpień, postęp preparing, prepared preview,
  jawne freeze i start. Broader ma nowy manifest, zgodny zakończony pilot,
  reportSHA/actor ACK i oddzielne broad confirmation. Nie obchodzimy startu
  genericretry. Failed/cancelled resume tylko gdy backend dopuszcza; kwarantanna
  wyjaśnia nową operację, bez przycisku resume. Operacja posiada liczniki;
  genericjob link daje kontekst. Komendowe HTTP409 różni się od późniejszego
  target outcome conflict.
- Przed POST trwale zapisać dokładne body+UUID w namespace API/game/operation/
  kind. Utrata odpowiedzi/5xx/reload zachowuje komendę, retry jest jawne.
  Nie kopiować lab-registry helpera kasującego każdy404/409/422. Potwierdzane
  Porzuć najpierw trwale archiwizuje rawbody/key/namespace/game/op/time,
  potem clear; failure archiwizacji zachowuje pending. Nie usuwa ani nie
  adoptuje operacji serwera. Zmiana widoku/unmount nie czyści pending/draft.
  Late responses odrzuca generation token game+operation.
- Linki propozycji/Reviewera wyłącznie z rzeczywiście ukończonego1013 i
  istniejących helperów nawigacji, bez zgadywania URL. Brak danych historycznych
  i przyczyn blokady jest widoczny. Nie wyliczamy kwalifikacji na froncie.

### Weryfikacja i granice

Jeden pion backend→OpenAPI→generated SDK/types→wrapper→request tests→Admin.
Testy: legacySHA/prepare replay/resume i mixed pins; scope counts i overlap;
realne before/after unchanged/changed/new/unknown cells; atomowy rollback i
brak podwójnego agregatu; keyset/two-game/pilot filter/cursor; GET-only mount,
defaulty, jawne bramki, lostresponse/reload/exactUUID, late result, discard
archive failure, resume/cancel/quarantine i nieobecny stary start. Najpierw
API/worker/transport/Admin focused, potem właściwe lint/types/build. Każda
skończona komenda timeout<=120s, bez usług/produkcyjnych przebiegów.

Bez operatorDB/migracji/backupu, rzeczywistej inferencji/GPU/treningu,
publikacji/aktywacji/defaultu, integracji i push. Stara777kod7 archiwalna,
symbole per gra. Root owns README/Dlogs/posthash1013 i resztę State;
wykonawca source/tests/owner docs/maps/ten task i ONLY1003 subsection State.


### Jedna runda poprawek po Claude R1 — kontrakt przed kodem

- R1 REVISE: P1-1 wykazał brak producenta notRecordedTargetCount. Pełny
  oryginalny raport jest zachowany w quality, bez zmiany werdyktu. Root
  zweryfikował35 źródeł i72 dowody SHA po audycie; brak driftu.
- Pole opisuje bieżący brak receiptów w znanym frozen zakresie:
  `targetCount - effectStats.recordedTargetCount`. Nie jest addytywnym efektem
  celu. Czysty helper kontroluje0<=recorded<=target; nie maskuje uszkodzonych
  sum przez max(0,...). Po finalizacji prepared gap wynosi targetCount,
  source transaction aktualizuje go razem z receipt/progress, terminalny
  sync uzupełnia przed nowym reportSHA. Replay/resume zachowuje tę samą
  arytmetykę i nie dubluje efektów. COMPLETED z pełnym rozliczeniem daje0.
- Zmiana dotyczy tylko znanego nowego pinu i finalnego manifestu. Oba absent
  pozostają legacy, bez nowych statystyk/zmiany SHA. FAILED/CANCELLED przy
  uszkodzonym lub mieszanym pinie nadal zwalnia lease zgodnie z istniejącym
  kontraktem; nie podnosimy polityki ani nie publikujemy nowych statystyk.
- Przed finalnym manifestem nie ma gotowego mianownika. Scope i effects UI
  pokazują nieukończony zakres także przy failed/cancelled prepare. Nie
  wyświetlają wtedy pozornego gap0; nie trzeba nowego pola API.
- P2-1: świadomie przyjęty limit statement_timeout30s obejmuje również
  późniejsze statementy tej samej krótkiej transakcji finalizacji. Nie
  obiecujemy, że dotyczy wyłącznie SELECT DISTINCT, ani wydajności szerokiego
  zakresu. Późniejszy timeout cofa całość; nie poluzowujemy limitu po audycie.
- P2-2: pin/capacity raz na prepare_page. P2-3: usunięcie tylko nieużywanych
  helperów legacy i ich wymagania Pick po rg; historyczne API/SDK pozostają.
  P2-4: dopisać rzeczywistą komendę test:geometry do Verification. P2-5:
  wyjaśniona etykieta braku finalizacji i odpowiedni test interakcji.
- Regresje: prepared gap3; częściowe rozliczenie3/1 daje2; FAILED i CANCELLED
  zachowują2; rollback źródła zachowuje dokładny poprzedni gap; replay/resume
  nie dubluje; COMPLETED daje0; legacy SHA/null i invalidpin cleanup bez
  regresji. Poprawić nowy PG invalid_partial test: komórkowe efekty0 i gap
  równy frozen targetCount, nie nieprawidłowa teza, że wszystkie pola są0.
  Zachować stare czerwone logi; brak kolejnych eksperymentów unknown-path.
- Jedna runda poprawek przez gpt-6.1-sol/medium. Ponieważ P1 zmienia
  zachowanie licznika, potem wymagany Claude medium R2/do1200s, ograniczony
  do delta wobec R1. Brak automatycznej pętli, commita ani operator operations.

## Expected files

- Istniejące: `schemas/grid_reinference.py::GridReinferenceResponse`, `storage/grid_reinference.py::view/prepare_page/finalize_preparation/synchronize_grid_job/worker_record`, application/router grid_reinference, `storage/virtual_grid_geometry_repository.py::save_automatic_reinference_source`, worker `images/grid_reinference_handler.py` — statystyki/pin/receipts, bez zmiany polityki zapisu.
- Istniejące: `packages/admin-api-client` OpenAPI/generated/wrapper; `grid-quality-panel.tsx`, `model-quality-actions.ts`; nowe proponowane moduły grid-reinference preview/report/state/command i ich testy. Konkretne symbole zweryfikowano w preflight; ścieżki backendu względem services/api/src/game_predictor_api.

- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `grid-reinference-preview.tsx`, `grid-reinference-report.tsx`, stan i akcje w Adminie; istniejące linki do jobów.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `apps/admin/src/features/model-quality/grid_reinference_preview_and_report.test.ts`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Stary preview daje konflikt; utrata odpowiedzi odtwarza tę samą operację; zmiana gry nie miesza stanu; wszystkie automatyczne nie są domyślnie zaznaczone.

## Verification

Zakres: API, WORKER, ADMIN, transport, OpenAPI, DOC i MAP odpowiednio do zmienionego pionu.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Frontend nie wylicza samodzielnie kwalifikacji ani zakresu na podstawie jednego licznika.

## Outcome

### Execution phase

- Pierwszy Claude R1/medium zakończył się REVISE z P1-1 i pięcioma P2; oryginalny raport i dowody zachowano bez zmian. Wykonano jedną zatwierdzoną rundę poprawek poniżej. Oczekuje niezależnego Claude R2/medium/do1200s; nie ogłoszono końcowego PASS taska.
- Baza wykonania: **v1.7.380 / `a688a40108f33ede3a894002a6fc8a8ed53d8141`**; worktree `D:/game_predicotr/worktrees/v3-grid-fine-tuning`, branch `codex/v3-grid-fine-tuning`. Pierwotna baza planu v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2` i zaakceptowany upstream v1.7.362 pozostają historycznymi punktami planu.
- Wykonawca gpt-6.1-sol/medium; wydzielony wykonawca Admina dziedziczył tę samą konfigurację. Bez stage, commita, audytu, integracji i push po stronie wykonawców.

### Changed

- Istniejący pion API rozszerzono o wersjonowane nullable scope/effect DTO, jawne pola wykonania/pilota/kwarantanny i keyset GET kolekcji operacji. Lista czyta wyłącznie game-scoped metadane, maksymalnie50 pozycji; UUID order nie oznacza chronologii. Odkrywanie pilota jest doradcze, dotychczasowy ACK ponownie waliduje raport.
- Nowe prepare zapisuje identyczny server-owned pin statystyk w operacji i jobie. Oba absent zachowują legacy, mieszane/nieznane odmawiają pracy. Resume/replay nie dodaje pinu. Stara gałąź reportSHA i wszystkie snapshoty/manifesty/scopeSignature pozostają identyczne. Failure/cancel mogą zakończyć job także z błędnym pinem, bez publikacji statystyk lub sukcesu; nie blokujemy sprzątania lease walidacją finalnego raportu.
- Przygotowanie zbiera zakres stronami, a finalny SQL COUNT DISTINCT frozen board/cell IDs oraz available IDs domyka deduplikację bez dużych zbiorów w Pythonie. Przygotowanie z niegotowym manifestem nie publikuje końcowych scopeStats. Statystyki nie są obietnicą jednego snapshotu żywej gry.
- Opcjonalny collector zachowuje dotychczasowy wynik i zachowanie automatycznego writera. Obserwuje wyłącznie wybrane persystowane komórki przed materializacją i po istniejącym write-through. Target receipt, sumy operacji, outcome i progress są atomowe. Nie zmieniono geometrii, ochrony, ownership ani D-462. Zmienione piksele, nowe komórki, brak porównania i ponowna ocena mają odrębne znaczenie.
- Jeden workflow Admina zastępuje montowany legacy pending-preview/start. GET-only wejście/reload; domyślnie grid_issue/deferred; jawne prepare/freeze/ACK/broad confirmation/start, resume/cancel i kwarantanna. Exact body/UUID powstaje trwale przed POST, retry jest jawne; potwierdzone porzucenie archiwizuje raw i metadane przed clear. Spóźnione odpowiedzi gry i operacji są odrzucane. Polskie etykiety i szczegóły techniczne są rozdzielone.
- OpenAPI, wygenerowany klient, wrapper i request tests tworzą jeden pion. Naprawa test-only: bound lifecycle fixture0999 pobiera CREATE_TABLES z bieżącego runtime, zachowując ADDED_GAME_TABLES frozenv12.

### Verification results

- `TASK-1003_final_units_r4.log`: **61 PASS, 2 HTTP deselected**. Obejmuje backend command/replay/resume, rzeczywisty repository history/cursor, scope/effects helper, mixed pins i terminalny failure oraz worker regressions. Dwa wyłączone z sandboxa HTTP uruchomiono osobno poza sandboxem: `api_http_r2` **1/1 PASS**, `http_history_r1` **1/1 PASS**. Znany sandboxowy Proactor/socketpair hang nie jest błędem produktu.
- `pg_stats_r3`: **6/6 PASS** na jednej własnej małej fixture: actual changed/unchanged, proposal-ready, konflikt celu, rollback/replay i JSONB DISTINCT duplikowanych frozen IDs wraz z legacy bez agregacji. `pg_new_unknown_r4`: nowy deferred board/cells **PASS**; dodatkowy niepoprawnie skonstruowany unknown-case **FAIL**, zachowany.
- `pg_invalid_partial_r8`: **1/1 PASS** odrzucenia niespójnej częściowej projekcji, z niezmienionymi board revisions, dokładnym przed/po source revision UUID, zerowym progress/effects/outcomes i brakiem target receipts. Baseline źródła pobieramy w prepared transakcji przed freeze/start: `_seed` tworzy source revision0, `project_recognition` już przed reinferencją tworzy revision1. R7 omyłkowo porównał source do stałej0; R8 porównuje dokładną tożsamość wcześniejszej rewizji, bez obniżania expected do1.
- Wszystkie użyte fixture receipts `TASK-1003_PG_R*_PG_RECEIPT.json` potwierdzają owner, pustą listę PID przed cleanup, databaseRemaining0 i roleRemaining0. Nie zmieniono bazy operatora. Krótkie basetemp pozostają ignorowanymi artefaktami testów.
- Admin: finalne mounted interakcje **10/10 PASS** (`ADMIN_LABEL_INTERACTIONS_1`), journal **4/4 PASS** (`ADMIN_REVIEW_UNIT_1`), pełny typecheck Admin PASS oraz focused ESLint/format PASS. Wcześniejszy zestaw interakcji z istniejącym loading regression **17/17 PASS** zachowano.
- Transport **2/2 PASS** (`request_r2`), client build PASS, OpenAPI export/generation/generated drift PASS. Mypy **7 modułów PASS** z `--follow-imports=silent` (`pytypes_final_r2`). Ruff, format, DOC/MAP i końcowy diff są w dzienniku weryfikacji `TASK-1003_RUNS.jsonl`; końcowe wyniki dołącza dowód freeze.
- Czerwone dowody zachowano: pierwszy sandbox HTTP timeout; worker tmp-path poza writable root, naprawiony własnym basetemp; PG R1 historyczny bound fixture, PG R2 MAX_PATH, PG R4/R5/R6 niespójne próby unknown fixture i autoflush, PG R7 błędna stała source revision. Nie maskowano ich xfail ani zmianą produkcyjnej walidacji. `rN` w nazwach oznacza lokalną iterację kontroli, nigdy rundę audytu Claude.

### Not completed

- **Jawne odstępstwo od planowanej macierzy:** persystowany legalny unknown-comparison path nie został wykazany. Logikę braku porównania dowodzi wyłącznie czysty `cell_effects` helper, nie PG unknown PASS. Nowy niespójny fixture został, za zgodą lead, regresją odmowy i rollback zamiast pozornego sukcesu. Wymogi: `models.py`, `ImageSymbolReviewCellModel`, CHECK `ck_image_symbol_review_cells_source_asset` (około2793–2803) i `ck_image_symbol_review_cells_asset_provenance` (2816–2824) wymagają checksumów dostępnego virtual assetu. `image_review_repository.py::_virtual_manifest_cells` (2585,2611–2615) wymaga zgodnego kompletnego row-major manifestu. Nie osłabiono tych warunków dla statystyki.
- Brak pomiaru szerokiego zakresu 341k+ plansz / 5m komórek, benchmarków, pełnego builda Admina i pełnych transitive test suites. Skoncentrowane kontrole, typecheck i małe fixture nie są takim dowodem. Brak fizycznego odbioru na urządzeniu.
- Niezależny audyt Claude, rozliczenie jego uwag, końcowe zamknięcie taska, commit i integracja należą do lead. Nie wykonano operatorDB/migracji/backupu, usług, rzeczywistej inferencji/GPU/treningu, publikacji/aktywacji/defaultu ani push. Historyczny layout reset pozostaje poza zakresem.

### Documentation updates

- Zaktualizowano owner `ADMIN_APP.md`, `API_CONTRACT.md`, wygenerowane mapy kodu, ten task i wyłącznie jego sekcję CURRENT_STATE. D-551/plan/README i pozostała metadata pozostają własnością lead.
- Porównanie DoD/plan: funkcjonalny zakres i przypadki restartu/utraconej odpowiedzi/stale gry/operacji są sprawdzone; kontrakt wygenerowany; dokumentacja uzupełniona. Pending są audyt/commit/closure, powyższa niewykazana legalna ścieżka unknown i odbiór fizyczny. Nie utożsamiamy statystyk z poprawą jakości.

### Recommended next task

- Po audycie i osobnym commicie1003 lead kontynuuje TASK-1002 w ramach zleconego planu. Integracja wymaga końcowej akceptacji całego zleconego zakresu.


### Jedna runda poprawek po R1 — wynik wykonawcy

- R1: `TASK-1003_AUDIT_claude-fable-5-1_R1.md`, REVISE, SHA `3a5cec7020d5d3fd85c68cfead05a6d276d1d8934b78becdbde568a397419f07`. Kontrakt korekty zapisano przed kodem; wykonawca gpt-6.1-sol/medium, Admin dziedziczył medium. Wykonawca nie zmieniał historycznych RUNS, raportów, archiwum R1 ani wcześniejszych evidence SHA.
- P1-1 poprawiono: `refresh_effect_gap` ustawia bieżący frozen gap `targetCount-recordedTargetCount`, wyłącznie znany nowy pin i gotowy manifest. Jest producent po finalizacji, w atomowej transakcji źródła oraz terminalnym sync przed nowym SHA. Walidacja odmawia ujemnych/nadmiarowych counts zamiast clamp. Gap usunięto z addytywnych EFFECT_FIELDS; empty_effect, DTO i per-target receipt nadal zawierają pole0. Replay/resume nie dubluje efektów. Legacy i invalidpair failure/cancel cleanup pozostają bez zmian.
- Red reproducer `R2_gap_red`: FAILED/CANCELLED pokazały0 zamiast2 (**2 FAIL**). Po poprawce `gap_green` **2 PASS**; `backend_green_1` **37 PASS, 1 HTTP deselected**; `gap_cleanup_hash_green_02` **11 PASS**, w tym gap3→2→0, brak clamp, oba legacy pins absent, stary hash i mieszany/nieznany pin z failure/cancel cleanup.
- R2 PG `pg_gap_01`: **3 PASS**. Prepared ma gap=frozen targetCount. Prawdziwy runtime/workflow zapisuje dwa target receipts pierwszego źródła z zakresu trzech pozycji, potem cancel ma recorded2/gap1; resume kończy ostatnie źródło i gap0. Nie ustawiano ręcznie tych receiptów. Kontrolowany fail po rzeczywistym writerze cofa efekty i zachowuje całe prepared effectStats, po resume/replay jest0. Odrzucenie niespójnej partial projekcji ma komórkowe efekty0, ale gap równy frozen targetCount. Kontrolny przypadek3/1→2 pochodzi z czystego helpera/unit, nie jest przedstawiany jako PG receipt. Fixture receipt `TASK-1003_R2_PG_01_PG_RECEIPT.json`: owner zgodny, PID[], databaseRemaining0/roleRemaining0, bez operatorDB.
- P2-1 świadomie przyjęto: statement_timeout30s obejmuje kolejne statementy tej samej krótkiej transakcji finalizacji, nie tylko DISTINCT. Timeout nadal cofa całość; brak benchmarku szerokiej gry. P2-2 poprawiono: pin i capacity raz na prepare_page. P2-3 usunięto wyłącznie martwe Admin helpery, ich typy/import/Pick; backend i SDK legacy pozostały. Trapfixture z legacy fake metodami nadal sprawdza ich nieużywanie.
- P2-4: rzeczywista komenda test:geometry dopisana i uruchomiona. Pełny wynik **226 PASS / 10 FAIL** (236 testów): wyłącznie niezmieniony super-game-series-workspace fixture przekazuje undefined counts do `undefinedSeriesCountLabel`, state.ts:101. Source/state/workspace/test tego pionu nie mają diffu; pozostają poza zakresem1003. Nie maskowano ani nie naprawiano tych błędów. Focused Admin interakcje **19/19 PASS**, actions/contract **18/18 PASS**, pełny typecheck i focused lint/format PASS.
- Świadoma aktualizacja starego static contracttest: usunięto siedem asercji dawnego mounted UI (`recalculableBoardCount`, `currentV19BoardCount`, `unsupportedVirtualBoardCount`, komunikat wirtualnych v0.10, komunikat plikowego v19, `geometryVersion`, `cropperVersion`). Resztę asercji zachowano. Red17/18 i green18/18 zachowane; real mounted GET-only/default/exactcommand/reload/conflict/late-response testy nadal obowiązują. Nie usunięto backend/SDK historycznej ścieżki.
- P2-5 poprawiono: nowy pin bez finalnego manifestu pokazuje nieukończony zakres i niedostępne efekty także po failed/cancelled prepare, bez pozornego gap0. Legacy nadal pokazuje „nie zapisano”; nie dodano pola API.
- Mypy3 zmienionych modułów **PASS** (`--follow-imports=silent`); Ruff/format/DOC/MAP/diff oraz końcowy cleanup zawiera nowe R2 evidence. Nie powtarzano zielonych szerokich zestawów. Legalny persystowany unknown-path nadal niewykazany; poprzednie świadome ograniczenie i czerwone dowody pozostają ważne.
- Status wykonawcy: P1-1 i P2-2/3/4/5 poprawione, P2-1 zaakceptowane ryzyko; to nie zastępuje werdyktu wymaganego Claude R2. Nie wykonano audytu, stage/commita, integracji, push, usług ani operator operations. Raport odpowiedzi: `ai_docs/quality/TASK-1003_CORRECTION_CODEX.md`.


- Uzupełnienie baseline pełnego test:geometry: jedna ograniczona reprodukcja na dokładnym module stanu z HEAD380 (SHA `7e4190ab0ff322904723e805dea87767c2476f78b09ce02e84ae2d5718c2951a`, brak runtime imports) potwierdziła ten sam TypeError dla undefined counts. To **nie** jest pełna mounted reprodukcja dziesięciu testów na czystym HEAD ze wszystkimi zależnościami; tej nie wykonano. Pełny wynik236 pozostaje226 PASS/10 FAIL poza diffem, bez twierdzenia o udowodnionej niezależności całego suite. Dowód `R2_supergame_pure_baseline_01` i szczegóły w odpowiedzi jakościowej.


### Lead closure — Claude medium R2 PASS, 2026-10-15

- Execution phase: gotowe do osobnego commita **v1.7.381**, następnie oczekiwanie na integrację całego planu. Pełny hash zostanie zapisany po utworzeniu bez amend. Brak otwartych P0/P1.
- [R1 REVISE](../../quality/TASK-1003_AUDIT_claude-fable-5-1_R1.md) zachowano; jedna runda poprawek i [R2 PASS](../../quality/TASK-1003_AUDIT_claude-fable-5-1_R2.md), 258.600s/do1200s. Audyt statyczny, bez testów przez audytora. Lead po audycie potwierdził 38 źródeł i 107 dowodów SHA bez driftu. [Rozliczenie wykonawcy](../../quality/TASK-1003_CORRECTION_CODEX.md).
- P1-1: producent gap po finalizacji, source transaction i przed terminalnym SHA; gap nie jest sumą efektów celu. Red2 FAIL, green2 PASS, backend37 i focused11 PASS; rzeczywisty PG3 PASS dowodzi częściowych receiptów, cancel/resume, rollback/replay i completed0. P2-2/3/4/5 rozliczono: pin/capacity raz na stronie, usunięte martwe helpery UI bez usuwania SDK/backend, rzeczywista komenda geometry, jawny niesfinalizowany zakres. Historyczne SHA/piny i invalidpin cleanup pozostają zachowane.
- Focused Admin19/actions18, types/lint/format, mypy3, DOC/MAP/diff PASS. Stare niezmienione dowody R1 pozostają ważne we własnym zakresie, bez sumowania nakładających się zestawów. Full test:geometry pozostaje FAIL226/236, dziesięć błędów SuperGame poza diffem. ExactHEAD380 helper reproducer1 PASS nie jest pełnym mounted baseline i nie dowodzi wszystkich dziesięciu błędów na czystym HEAD. Nie wykonano nieautoryzowanej naprawy SuperGame ani xfail.
- Przyjęte ryzyka i ograniczenia po pełnym odczycie raportu:
- P2-1: Limit statement_timeout30s obowiązuje do końca krótkiej transakcji; bind już stosuje ten sam limit. Bez poluzowania granicy i bez obietnicy wydajności szerokiego przebiegu.
- P2-6: Zgodny pin i uszkodzony ujemny/nadmierny aggregate odmawia STATS_INVALID także terminalnego cleanup. Świadomy fail-closed wobec naruszenia serwerowej atomowej niezmienniczości; bez clampowania i ukrytego success. Nie zmieniano zachowania po PASS.
- P2-8: Fullgeometry FAIL226/236,10 SuperGame poza diffem. Helper-only baseline nie dowodzi wszystkich10. Przed integracją najpóźniej TASK1001 obowiązuje pełny czysty HEAD380 mounted baseline i porównanie, zapisane także w ograniczeniach CURRENT_STATE; brak zgody na obcą naprawę/xfail.
- Uzupełniająca kontrola po R2, bez zmiany kodu i bez nowej rundy audytu: P2-7 zamknięte: pełny test_grid_reinference_stats_postgres.py bez filtra9 PASS/67.84s, wrapper71.73s<120. Pierwsza próba sandbox01 TCP10013 przed CREATE i bez asercji zachowana jako FAIL; jedna środowiskowa próba02 z identycznym zakresem poza sandboxem PASS. Exact owner/DB0/role0/PID[] potwierdzone. Oddzielne TASK-1003_POST_AUDIT_PG_02 log/RUN/PG_RECEIPT/CLEANUP i SHA; frozen R2/RUNS/source bez zmian.
- Legalny persystowany unknown-comparison path nadal nie został wykazany; dowód helper-only i odmowa niespójnej projekcji są rozdzielone. Brak szerokiego benchmarku, fizycznego Android/browser odbioru i pełnego Admin builda. Każda własna fixture potwierdza owner/DB0/role0/PID cleanup. Quota attempt przed rzeczywistym R1 był bez werdyktu, zachowany oddzielnie; nie jest PASS ani rundą audytu. Harmonogram wznowienia jest wyłączony, audyty odebrano w tej sesji.
- Bez operatorDB/migracji/backfillu/resetu, nowego backupu, usług, rzeczywistej inferencji/GPU/treningu, publikacji/aktywacji/defaultu, integracji i push. Symbole per gra, stara777 archiwalna. Następny TASK-1002 po osobnym commicie1003 oraz zapisaniu jego kontraktu/nowej decyzji przed kodem; cały plan pozostaje zlecony.
