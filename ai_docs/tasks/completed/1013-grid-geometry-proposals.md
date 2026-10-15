---
title: TASK-1013 — Trwałe propozycje dla „Złej siatki”
status: done
last_updated: 2026-10-15
---

# TASK-1013 — Trwałe propozycje dla „Złej siatki”

## Status

`done`

## Goal

Model przygotowuje korektę, a operator decyduje o jej zastosowaniu.

## Context

Task jest częścią zaakceptowanej rewizji 6. Decyzje człowieka i rewizje propozycji. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0993, TASK-0999.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. ochrona zgłoszenia i atomowy zapis decyzji.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [API_CONTRACT](../../architecture/API_CONTRACT.md).
- [D-551](../../process/decisions/DECISION_LOG_2026.md#d-551--propozycje-dla-błędnej-siatki-v3) — accepted przed TASK-0999; trwały wynik modelu i świadome przyjęcie propozycji.
- Zakres odczytu uzupełniający z planu: D-462/D-543, API_CONTRACT, schemat propozycji z sekcji 4.

- [D-462](../../process/decisions/DECISION_LOG_2026.md#d-462--weryfikacja-per-komórka-bez-zatwierdzania-planszy-i-siatki) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-543](../../process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Wdrożyć tabele propozycji i zdarzeń.
- Reviewer pokazuje porównanie, przyjęcie, edycję i odrzucenie.
- Przyjęcie korzysta z `VirtualGridGeometryService.save_review_item`, a nie z usługi samych liczników.

## Out of scope

- Automatyczny wynik nie może zostać oznaczony jako ręczny przed decyzją operatora.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Utworzenie nie zmienia cropów ani zgłoszenia.
- [x] Przyjęcie działa raz, zapisuje autora i zamyka właściwy problem.
- [x] Zmieniona rewizja daje konflikt.
- [x] Odrzucenie pozostawia zgłoszenie otwarte.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

### Contract recorded before implementation — 2026-10-15

TASK-0999 ukończono w v1.7.379 / `62e9f71986a74d67776eabad6e99154f4d18c0b2`, po jawnym dodatkowym
zleceniu operatora i Claude high R3 PASS. Poniższe doprecyzowania D-551
zatwierdził lead przed kodem na podstawie read-only preflight. Źródła:
`artifacts/audits/TASK-1013_PREFLIGHT_R2_NOTES.json` i rzeczywiste symbole
wskazane niżej. Zakres pozostaje zgodny z rewizją6; brak nowych uprawnień
do danych operatora, usług lub integracji.

### Source of truth and immutable candidate

- Źródłem jest istniejący terminalny `GridReinferenceTargetModel`, wyszukany
  bezpośrednio po `(game_id,target_result_id)`, nie przez skan wszystkich
  operacji. `target.outcome` i `result.outcome` muszą być `proposal_ready`;
  snapshot wskazuje `grid_issue`. Walidujemy rzeczywisty schemaVersion,
  operation/target/source/position IDs, hash wyniku i frozen fence oraz
  kompletne corners/lattice i kwalifikację. Nie wykonujemy inferencji.
- Kandydat przechowuje niezmienny oryginał wyniku0999, model/pin, źródłowe
  tożsamości i hashe, target fence i źródłowe dowody. Rzeczywiście przyjęta
  geometria i ręczne pochodzenie są osobnym zapisem; edycja nie podmienia
  oryginalnego wyniku modelu. Bieżący assignment nie wybiera ponownie modelu.
- Create i accept wymagają zgodnego retained `live_source_image_id` oraz
  aktualnego źródła/review w zakresie gry/importu. Create po detach/cleanup
  daje kontrolowany409, bez nowej propozycji i odtworzenia danych. Istniejące
  historyczne propozycje i receipts nadal można odczytać z applicable=false.

### Proposed schema, states and command receipts

- Proponowana Alembic0160 po rzeczywistej0159 oraz frozen manifest v13.
  `grid_geometry_proposals`: composite PK(game_id,id), unique
  (game_id,target_result_id), unique operation/target occurrence; niezmienny
  dokument `grid-geometry-proposal-v1`, stan pending|accepted|rejected|stale,
  revision>=1, oddzielna accepted geometry/provenance. Composite FK do
  retained target0999; frozen source/board/review IDs NIE są FK do żywych
  tabel. Nie dodajemy drugiego live linku.
- `grid_geometry_proposal_events`: append-only composite PK game/id,
  proposal reference, ordinal/revision, kind created|accepted|rejected|stale|
  command_completed|command_rejected, commandKind, UUID key, canonical
  command SHA, zaufany aktor/czas i typed HTTP outcome/receipt. Jeden event
  per nowa komenda; replay nie dopisuje eventu. Dla kontrolowanego błędu
  create przed utworzeniem obiektu proposal_id może być NULL wyłącznie
  dla command_rejected/create, z jawnym CHECK. Bez fikcyjnego proposal ani
  trzeciej tabeli ledgeru. Partial unique create(game,key) i odrębny
  namespace (game,proposal,kind,key) accept/reject; ten sam key/inny hash409
  zachowuje oryginalny receipt.
- pending/r1 przechodzi do accepted/r2, rejected/r2 albo stale/r2. Stany
  terminalne nie uruchamiają writera ponownie; nowy run ma nowy target ID.
  Druga create dla tego samego targetu odtwarza tożsamość istniejącego
  proposal, z command_completed receipt, bez drugiego created eventu.
  Nowy create UUID wymaga nadal autoryzowanego scope, zgodnego retained
  live ID oraz istniejącego źródła/review w tym scope. Istniejącą tożsamość
  zwraca również po accepted/rejected/stale, bez ponownego wymagania
  frozen fences lub otwartego issue i bez nowego zastosowania geometrii.
  Pełne fences dotyczą nowego obiektu i accept. Po detach nowy UUID daje409;
  replay starego UUID zachowuje historyczny receipt i osobny current view.
- Replay sprawdzamy przed CAS i aktualnością. Immutable receipt opisuje
  historyczny wynik tej komendy. Osobny current view/applicability pokazuje
  dzisiejszy stan; replay accepted po revert/cleanup nie jest dowodem,
  że dawna geometria nadal jest aktywna, i nie zapisuje jej ponownie.
- Stara expectedProposalRevision to command_rejected409 bez zmiany
  aktualnej propozycji na stale. Rzeczywisty drift pending zapisuje stale
  i powód. Oczekiwany domenowy konflikt jest typed wynikiem serwisu,
  nie wyjątkiem przez yield-session: router zwraca standard ErrorResponse
  z HTTP409, dependency normalnie commit event/receipt. Walidacja422,
  autoryzacja i infrastruktura nadal rzucają wyjątek/rollback; nie maskujemy
  błędów storage. Brak ręcznego commit w routerze. Testuje się nową session,
  utraconą odpowiedź oraz replay zarówno200 jak409.

### Current fences and the manual-save seam

- Wymagamy aktualnego grid_issue pending na właściwej bieżącej geometrii,
  board/review/import/game/sequence/slot, nie tylko CAS geometry/resolution.
  Sprawdzamy aktualne source/file/normalized-pixel identity, wymiary,
  orientację/normalization i topologię oraz target geometry ID/revision/SHA,
  qualification/approval/status, resolution/provenance, wszystkie właściwe
  cells ID/revision/current+approved pixel hashes/quality issue/decision/
  assignment/symbol/sourceAvailable, owner i foreign live owner. Ewentualny
  asset_mode/current-cell provenance dodajemy do proposal-specific fence,
  bez poluzowania starego0999. Zmienione piksele przy tej samej ścieżce też
  muszą dać konflikt; reuse istniejącej walidacji/renderu, bez zaufania
  samemu stringowi ścieżki lub checksumowi z żądania.
- Cały historyczny source geometryContext NIE jest fence aktualności:
  0999 mógł zapisać poprawne rodzeństwo w tej samej transakcji, pozostawiając
  target na R0. Zachowujemy oryginalny frozen dowód, porównujemy jawny
  niezmienny source/pixel subset i target-specific fence, a nowsze live sloty
  zachowujemy przez bezpieczny merge.
- Faktyczna luka istniejącego writera: `_current_row`/`_context_from_row`
  czytają historyczną source revision planszy, a `_settle_source_geometry`
  może przepiąć rodzeństwo. Dodajemy jawny opcjonalny
  `source_snapshot_policy=board_revision|current_live_slots` do repo manual
  geometry (lub równoważną typowaną politykę). Domyślny board_revision
  pozostaje bez zmian dla istniejących konsumentów. Dedicated proposal
  VirtualGridGeometryService używa current_live_slots w TEJ SAMEJ session.
- Opt-in helper waliduje target provenance, buduje snapshot z bieżących
  zgodnych live slotów/pending/binding i niecofniętej source revision.
  Jest użyty także przy locked reload; render/save context mismatch lub
  niemożliwy merge daje409. Nie zmienia rodzeństwa przed save. Repoint może
  powtórzyć wyłącznie zgodne bieżące sibling nodes/decisions. Publiczny
  `VirtualGridGeometryService.save_review_item` pozostaje ścieżką zapisu
  człowieka; nie używamy automatic writera ani samych liczników.
- Porządek: własny command advisory mutex, ownership EXCLUSIVE,
  projection/game guard, rosnące sequence locks, source/current
  board/review/canonical/cells zgodnie z manual writerem, dopiero proposal
  row i receipts. Ponawiamy CAS/fences pod lockiem. Bez proposal-first
  inwersji, operation/job locków i późniejszego job lock po ownership.
  Manual save, accepted event i receipt mają jedną session/transakcję;
  błąd writera/projekcji/eventu cofa wszystko. Reject nie wywołuje writera
  i nie zamyka problemu.

### Trusted actor and transport

- Istniejące authorize(None) zwraca None, a stara geometry route może
  używać body.corrected_by. Nowe human mutations NIE kopiują tego fallbacku.
  Online: rzeczywista ReviewerAccessSession i authorize_scope zwracają
  reviewer-session:<id>. Obecność samego Bearer nie uwierzytelnia.
- Lokalny workflow ma już zweryfikowany principal ADMIN_ACTOR=local-owner
  w LocalAdminSecurityMiddleware: peer loopback, dozwolony Origin,
  X-Admin-Intent:local-owner i wymagane confirmation checks. Middleware
  ustawia request.state.local_admin_actor wyłącznie PO tych kontrolach,
  przed call_next. Nowy mutation helper używa zweryfikowanej sesji albo
  tego markera; bez nich403. Brak autora w body i brak bezwarunkowego
  local-admin. Bez nowego logowania i bez zmiany starych konsumentów.
- GET zachowuje dotychczasowy lokalny odczyt i scope realnej sesji online;
  nie wymaga unsafe markera, którego safe request nie ma. Autoryzacja
  historii po cleanup używa frozen game/import/review scope, nie fikcyjnego
  żywego review. ID obcej gry/importu nie ujawnia ani nie modyfikuje danych.
- Rozszerzamy istniejące image-review-items: create/list/detail propozycji,
  accept/reject. Create: targetResultId+UUID key; accept: UUID key,
  expectedProposal/Geometry/ResolutionRevision i mode=model|edited.
  Model mode bierze geometrię z immutable candidate; edited ma kompletne
  corners/lattice/qualification i originalCandidateSha256. SHA liczy serwer.
  Reject ma CAS i opcjonalną notatkę. GET jest read-only i zwraca
  applicability/reasons. Dokładne nazwy pól zgodne z backendem/OpenAPI.
  Jeden pion schema/router→OpenAPI→generated client→wrapper→proxy policy→
  test żądania; żadnych ręcznie rozbieżnych typów.

### Reviewer, cleanup and verification

- W needs_grid_fix pokazujemy „Propozycja modelu”, przypiętą wersję i
  porównanie aktualna/proponowana; Przyjmij, Edytuj, Odrzuć. Edycja otwiera
  istniejący edytor4/24 z kandydatem, Save akceptuje edited geometry; original
  pozostaje niezmienny. Trwały draft i UUID polecenia wiążą proposal/revision,
  sourceSHA, target geometry/resolution i originalSHA. Retry/reload zachowuje
  dokładne polecenie;409 zachowuje szkic i wymaga odświeżenia. Accepted
  odświeża kolejkę, reject zostawia problem i ręczną korektę.
- Cztery istniejące cleanupy nadal odłączają retained0999 live link,
  zachowując propozycje/eventy; bez FK do live source/review i bez odtworzenia
  danych. Layout-data reset zachowuje joby/historię, whole-game lifecycle
  usuwa events→proposals→targets→sources→operations. Stary niezwiązany reset
  FAIL nie jest naprawiany ani zmieniany na xfail w tym tasku.
- Wymagane realne regresje: target na R0, automatyczne rodzeństwo na R1,
  human accept tworzy R2 z identycznymi sibling nodes/crops/decisions/owner;
  drift rodzeństwa pomiędzy prepare/save daje409/zero efektów; domyślny
  manual editor zachowuje kontrakt. Dodatkowo create bez cropów/issue write,
  accept raz/replay po restarcie, reject issue open, stale/command-CAS409,
  rollback event+geometry, dwie gry/RLS, cleanup/live guard oraz rzeczywisty
  principal bez body spoof/Bearer bypass. Bez benchmarków i operatorDB.

### R1 correction contract recorded before changes — 2026-10-15

- Claude high R1 wskazał P0-1 i P1-1. Lead zlecił jedną rundę poprawek,
  następnie statyczny R2 ograniczony do delty; bez audytu i commita wykonawcy.
- P0-1: wyłącznie proposal-specific save uzupełni brakującą kwalifikację
  kwalifikacją immutable kandydata. Wyliczone partial/exclude mają pierwszeństwo.
  Serwer nadal wymaga jawnej kwalifikacji i24nodes; domyślny manual consumer
  zachowuje zachowanie. Test sprawdzi rzeczywiste ciało UI dla item null
  również walidatorem ProposalAcceptCommand oraz odmowę null.
- P1-1: zamknięty zbiór lifecycle RLS zostanie rozszerzony o obie nowe
  tabele. Realna jednorazowa fixture sprawdzi enabled/forced RLS oraz jedną
  policy na dzieciach obu nowych gier i izolację bezpośredniego child access.
- P2-1: discovery pominie wyłącznie invalid_candidate; poprawne wpisy nadal
  będą dostępne, create jawnie odmówi wadliwego wyniku, infrastruktura rzuci błąd.
- P2-2: opt-in current_live_slots otrzyma istniejący filtr statusu rejected,
  po odtworzeniu przypadku w ograniczonej realnej regresji. Odrzucony wiersz
  nie może blokować ani odradzać się przy human accept; zachowamy jego status.
- P2-3: panel montujemy wyłącznie w istniejącym widoku needs_grid_fix.
  OperationalImageReviewItemResponse nie udostępnia osobnego open-issue
  predykatu; nie rozszerzamy DTO. Pozostałe widoki nie wykonują GET panelu.
  Sam unmount nie czyści trwałego polecenia ani szkicu.
- P2-4: coupling prywatnych fixture helpers i receipty w artifacts przyjęto
  jako dług utrzymania. Bez refaktoru frameworka; dowody bezpiecznego cleanup
  własnej bazy i roli pozostają wymagane i zachowane.

## Expected files

- Istniejące: [virtual_grid_geometry.py](../../../services/api/src/game_predictor_api/application/virtual_grid_geometry.py) — `VirtualGridGeometryService.save_review_item`, `save_pending_slot`.
- Istniejące: [virtual_grid_geometry_repository.py](../../../services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py) — `save_virtual_geometry_revision`.
- Istniejące: [image_review_repository.py](../../../services/api/src/game_predictor_api/storage/image_review_repository.py) — ochrona decyzji człowieka, licznik korekt.
- Istniejące: [models.py](../../../services/api/src/game_predictor_api/storage/models.py) — encje i relacje magazynu.
- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `services/api/src/game_predictor_api/application/grid_geometry_proposals.py`, `services/api/src/game_predictor_api/storage/grid_geometry_proposals.py`, schema/router, migracja oraz komponent propozycji w Reviewerze.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_geometry_proposals.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Utworzenie nie zmienia cropów ani zgłoszenia.
- Przyjęcie działa raz, zapisuje autora i zamyka właściwy problem.
- Zmieniona rewizja daje konflikt.
- Odrzucenie pozostawia zgłoszenie otwarte.

## Verification

Zakres: API, MIG, REVIEWER, OpenAPI; integracja rzeczywistej ścieżki zapisu geometrii.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test:geometry --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py services/api/tests/test_virtual_grid_geometry_repository.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Automatyczny wynik nie może zostać oznaczony jako ręczny przed decyzją operatora.

## Outcome

### Execution phase

- Claude high R1: REVISE, P0-1/P1-1 oraz P2-1–P2-4. Lead zlecił jedną rundę poprawek. Implementacja poprawek i skoncentrowana weryfikacja są przekazywane do ograniczonego R2; status pozostaje in_progress do audytu i commita leada.
- Baza v1.7.379 / `62e9f71986a74d67776eabad6e99154f4d18c0b2`; branch `codex/v3-grid-fine-tuning`; worktree `D:/game_predicotr/worktrees/v3-grid-fine-tuning`. Oryginalna baza planu v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2` i zatwierdzony upstream v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` pozostają historyczne.
- Wykonawca nie uruchamiał audytu ani nie tworzył commita. Następny patch ustala lead z rzeczywistej historii.

### Changed

- Alembic0160/frozenv13 dodają dwie game-owned tabele z composite FK/RLS, central ORM, indeksem discovery i właściwym lifecycle. Ordinal zdarzeń jest monotoniczny per propozycja. Nullable proposal FK występuje tylko w odrzuconej create przed powstaniem obiektu.
- Immutable kandydat z retained targetResultId0999, pin/fences i osobne faktycznie zapisane human geometry/qualification/SHA/provenance. Bez nowej inferencji i bez zmiany cropów lub issue przy create. Reject pozostawia zgłoszenie otwarte.
- Manual save_review_item/event/receipt mają jedną sesję/transakcję. Opt-in current_live_slots zachowuje nowsze rodzeństwo; domyślny manual workflow bez zmiany. Target/source/pixel/cell/issue/owner fences i CAS rozróżniają stare polecenie od rzeczywistego stale. Typed409 utrwala outcome bez wyjątków cofających receipt; infrastructure rollback obejmuje całość.
- Canonical command wiąże scope/path IDs/payload/principal. Replay200/409 jest historyczny; osobny current/applicability nie przedstawia dawnego accepted jako aktywnej geometrii po revert/cleanup.
- Trusted actor: scoped ReviewerAccessSession albo marker local-owner po pełnych kontrolach middleware. Brak autora w body. GET zachowuje lokalny odczyt i frozen scope sesji online po cleanup.
- Pełny pion OpenAPI/generated client/wrapper/proxy/Reviewer: read-only discovery, porównanie, przyjęcie, odrzucenie i edycja4/24. Trwały szkic i UUID chronią restart oraz utraconą odpowiedź. Create/accept po detach nie odtwarzają danych.

### Verification results

- PASS:11 unikalnych scenariuszy PostgreSQL na rzeczywistej roli bez bypassRLS. Są to accept/reject/edited, nowa sesja/replay, stale/CAS, rollback, cleanup guard, prawdziwy automatic siblingR1 przy targetR0, sibling drift pomiędzy render/save, zmiana bajtów pod tą samą ścieżką/path isolation, rzeczywisty selected-source cleanup i dwie gry/composite FK/whole-game lifecycle. Po dodaniu ordinal/CHECK powtórzono tylko3 właściwe regresje, PASS.
- Końcowa regresja3PASS potwierdza create B po accepted: ten sam proposalId, nowy command_completed i brak kolejnej rewizji geometrii; nowy UUID po rzeczywistym cleanup409 oraz mixed-sibling nadal PASS. Weryfikację typów i lint powtórzono wyłącznie dla zmienionej delty.
- PASS:77 schema/lifecycle/routing/readiness/default manual repo;9 nowych i frozen0999 kontraktów wcześniej zaliczonych przed poprawą wyłącznie oczekiwanej listy manifestu. Końcowy test nowego schematu obejmuje także wymaganie24 węzłów i kwalifikacji w edited.
- PASS:ASGI security/request1, nowe UI3, shared editor5, wrapper request1; mypy15 modułów, Reviewer types/lint i client build. Jedyny lint warning dotyczy wcześniejszego `_operationId` w share datasource.
- Admin OpenAPI artifact/generated PASS. Łączne openapi:check zatrzymał sandboxEPERM w tymczasowym rename VisionLab; oddzielny brakujący VisionLab checker po escalation PASS, bez zmian artefaktów labu. Końcowe Ruff/format/map/docs/diff i SHA/logi są w `artifacts/audits/TASK-1013_IMPLEMENTATION_EVIDENCE.json`; scope w `TASK-1013_PATHS.txt`.
- Wcześniejsze failurelogs zachowane. Jedna nowa fixture RLS miała brakujący import i teardown odmówił drop przy własnym PID. Po zakończeniu procesu zweryfikowano dokładną bazę/właściciela/zeroPID i sprzątnięto bazę/rolę. Recovery potwierdza brak wszystkich baz/ról TASK1013. Poprawiony test PASS i końcowy receipt per token mają0remaining.

### R1 correction round

- R1 correction: kwalifikacja immutable kandydata uzupełnia tylko brak w proposal-specific edited save; wyliczone partial/exclude zachowują pierwszeństwo. Domyślny manual consumer i rygor schematu bez zmian. Provisioning obu nowych tabel włącza/force RLS i child policy. Discovery pomija wyłącznie GRID_PROPOSAL_RESULT_INVALID, current_live_slots pomija rejected, panel montuje się wyłącznie w needs_grid_fix. R1 P2-4 przyjęto jako dług utrzymania fixture helpers/receipts, bez refaktoru wsparcia; bezpieczny cleanup nadal wymagany.
- Red/green poprawek: UI odtworzył null oraz GET poza widokiem; PG odtworzył child flags false/false/0, wadliwy kandydat404 i rejected sibling409. Następnie UI5PASS obejmuje realny ProposalAcceptCommand validator, complete i partial/exclude, odmowę null, zero GET poza widokiem oraz wcześniejsze lost-response/remount. PG4PASS obejmuje oba mixed-sibling, discovery i dwie gry z enabled/forced/1policy oraz bezpośrednim child cross-game0/own1. Dodatkowa regresja wąskiego catch sprawdza propagację infrastruktury i innego not-found. Szczegóły, wyniki końcowych kontroli i aktualne SHA: `TASK-1013_R2_IMPLEMENTATION_EVIDENCE.json`; rozliczenie uwag: [TASK-1013_CORRECTION_CODEX](../../quality/TASK-1013_CORRECTION_CODEX.md). R1 raport, źródła, manifest i dowody pozostają historyczne.
- Dodatkowy pg_discovery_final ma FAIL przy teardown: asercje przeszły, lecz guard zobaczył własny PID i odmówił drop. Po zakończeniu procesu sprawdzono exact DB/owner/zeroPID i sprzątnięto bazę/rolę; recovery potwierdza zero wszystkich zasobów TASK1013. Oba receipts i log zachowane. Mockowane wyjątki przeniesiono do czystego unit testu; unit5PASS. Mypy3, Reviewer types i scoped lint PASS. Nie osłabiono cleanup guard ani nie przedstawiono tego uruchomienia jako PASS.

### Not completed

- Audyt Claude, commit, finalna akceptacja/integracja/push i rollout0160 należą do leada/operatora. Brak fizycznego odbioru przeglądarki/Androida; UI sprawdzono w jsdom. Bez operatorDB, usług, rzeczywistej inferencji/treningu/GPU, aktywacji modeli, nowych gier operatora i nowego backupu.
- Nie naprawiano wcześniejszego layout-data reset FAIL i nie zmieniano go na xfail. Cztery cleanupy nie mają nowych live FK; pion ma realną regresję selected-range cleanup oraz odmowy po detach. Rzeczywisty reset operatora pozostaje niewykonany.
- Kolekcja jest ograniczona do100 kandydatów i100 zapisanych propozycji per review/import; nie jest masowym raportem ani paginowaną historią gry.

### Documentation updates

- Kontrakt D-551/task zapisał lead przed implementacją. Wykonawca zaktualizował API_CONTRACT, DATA_MODEL, ADMIN_APP, mapy, Outcome i wyłącznie sekcję TASK-1013 w CURRENT_STATE.
- Przy pierwszym zapisie Outcome bez jawnego encoding doszło do obcięcia taska. Lead przywrócił dokładny kontrakt z generatora release. Outcome zapisano osobno w UTF-8 i zastosowano dopiero po potwierdzeniu odtworzenia. Dowody błędu i naprawy pozostają jawne.

### Recommended next task

- Lead: audyt Claude high/do1200s, wymagane rozliczenie uwag, osobny commit i zamknięcie. Następnie TASK-1003 zgodnie z planem; bez integracji przed końcową akceptacją całego zakresu.


### Lead closure — Claude high R2 PASS, 2026-10-15

- Execution phase: gotowe do osobnego commita **v1.7.380**; oczekiwanie na integrację całego planu. Pełny hash zostanie zapisany po utworzeniu bez amend. Wszystkie kryteria taska rozliczone, brak P0/P1.
- [R1 REVISE](../../quality/TASK-1013_AUDIT_claude-fable-5-1_R1.md) zachowano; jedna runda poprawek, [R2 PASS](../../quality/TASK-1013_AUDIT_claude-fable-5-1_R2.md),329.600s/do1200s. Claude wykonał przegląd statyczny, bez testów. Lead zweryfikował52 źródła i119 dowodów SHA po audycie; brak driftu w audytowanej fazie. [Odpowiedź wykonawcy](../../quality/TASK-1013_CORRECTION_CODEX.md) rozlicza wszystkie uwagi.
- Zamknięte R1 P0-1/P1-1 oraz P2-1/2/3: jawna kwalifikacja edycji, wymuszona RLS nowych partycji, odporne discovery, pomijanie rejected history i montaż tylko needs_grid_fix. Regresje odtwarzały błędy przed poprawką; po poprawce UI5 z realnym walidatorem, PG4 i unit5 PASS; delta mypy3/typy/lint/format/map/docs/diff PASS. Wcześniejsze niezmienione dowody R1 pozostają ważne we własnych zakresach, bez sumowania nakładających się zestawów.
- Przyjęty R1-P2-4/R2-P2-1: coupling fixture i asynchroniczny teardown pozostają długiem testowym. Guard właściciela/zeroPID nie został osłabiony po PASS. Dodatkowy teardown run nadal FAIL, exact recovery potwierdza0DB/role/PID. R2-P2-2/P2-3 zamknięto jedynie komentarzem wymaganego Python/Pydantic venv i zdaniem kontraktu API; trzy post-PASS zmiany dokumentacyjne z osobnymi SHA/Prettier/docs/diff, bez zachowania i nowej pętli audytu.
- Źródła R1, raporty i dowody R1/R2 zachowane. Dwa live RUNS dostały po jednym późniejszym wpisie odczytowym; dokładne historyczne prefiksy zgodne z SHA zachowano w archiwach bez zmiany live historii. Błąd UTF-8 dokumentu odtworzono wcześniej dokładnie według pre-code SHA. Ograniczenia nie są oznaczane jako fikcyjny PASS.
- Bez operatorDB, nowego backupu/snapshotu, usług, rzeczywistej inferencji/GPU/treningu, aktywacji, nowych gier operatora, push i integracji. Fizyczny browser/Android oraz wcześniejszy pełny layout-reset FAIL pozostają poza wynikiem. Kod w branchu codex/v3-grid-fine-tuning, nie wdrożony.
- Następny TASK-1003 po tym commicie, zapisaniu jego kontraktu API/statystyk i uruchomieniu przypisanego wykonawcy medium. Cały plan pozostaje zlecony; bez pytania o scalenie między taskami.
