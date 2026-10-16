---
title: TASK-1009 — Losowa kontrola Mumii i 777a2
status: done
last_updated: 2026-10-16
---

# TASK-1009 — Losowa kontrola Mumii i 777a2

## Status

`done`

## Goal

Zmierzyć rodzaje błędów zamiast opierać decyzję o treningu na liczniku.

## Context

Task jest częścią zaakceptowanej rewizji 6. Dobór próby i interpretacja wyników. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1010, TASK-0993, TASK-1002 i korekta kompatybilności TASK-1018; kontrola operatora jest warunkiem raportu rzeczywistej jakości.

- Zgoda na implementację nie zastępuje zgód operacyjnych. D-549–D-555 są accepted w swoich zakresach; D-548 dla doszkalania z korekt pozostaje proposed do0995, bez blokowania opisowego pomiaru1009. Brak etykiet operatora blokuje rzeczywistą ocenę jakości, nie implementację mechanizmu.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. poprawna populacja, próba i interpretacja.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../../architecture/VISION_LAB.md).
- [VISION_LAB](../../requirements/VISION_LAB.md).
- [ADMIN_APP](../../requirements/ADMIN_APP.md).
- [D-555](../../process/DECISION_LOG.md) i D-554/D-551/D-550; [DATA_MODEL](../../architecture/DATA_MODEL.md), [API_CONTRACT](../../architecture/API_CONTRACT.md), [własność geometrii](../../architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md), [mapa](../../architecture/CODE_MAP.md).
- Materiały readonly preflight w artifacts/audits/TASK-1009_{CAPTURE_CONTRACT_DRAFT,APPROVAL_ALLOCATION_DRAFT,MEMBERSHIP_SEAM_PREFLIGHT,UNCHANGED_APPROVAL_PREFLIGHT}.md są dowodami wejściowymi; niniejszy kontrakt je zastępuje.

## Scope

- Zamrożona losowa próba do 100 zdjęć per gra, pełna kontrola oczekiwanych pozycji, osobny zbiór trudnych przypadków.
- Wyniki zapisane z wersją i pochodzeniem.

## Out of scope

- Nie deklarować niezależności filmów bez dowodów ani jakości całej gry na podstawie celowo trudnych przykładów.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Ten sam seed i populacja odtwarzają próbę.
- [x] Trudne przykłady nie zmieniają częstości z próby losowej.
- [x] Brak pełnej kontroli zdjęcia jest widoczny.
- [x] Raport rozdziela detekcję, geometrię, symbole i sekwencję.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

### Kontrakt wykonawczy przed kodem — 2026-10-16, D-555

To techniczne rozwinięcie zaakceptowanego całego planu i odpowiedzi operatora,
nie nowa zgoda na operacje jego danych. Baza wykonawcza: v1.7.383 /
`ea9a27b29be948c9328da2670dc2b4159675ac4e`. TASK1018 zakończony Claude R1 PASS.
Wykonawca gpt-6.1-sol/high, niezależny Claude high/do1200s: task zmienia schemat
i dane dowodowe, dlatego zastępujemy wcześniejsze medium w tasku i tabeli planu.

#### Populacja i zamrożenie

- Pomiar opisowy jest odrębny od kwalifikacji niezależnego zbioru uczącego.
  Brak rejestracji nagrania, aliasu lub lineage nie usuwa zdjęcia z pomiaru;
  daje unresolved przy kwalifikacji TRAIN/VALIDATION/REGRESSION w0995.
- Populacja całej wybranej gry V3 to bieżące własne wystąpienia źródeł według
  istniejącej semantyki ingestii/kompletności. Kod7 odrzucony. Brak rewizji,
  predykcji, pliku, zakresu, pełnej geometrii, akceptacji lub pewności nie jest
  filtrem usuwającym trudne przypadki. Wyłączamy wyłącznie źródła w całości
  zastąpione według istniejących reguł same-game live sequence/checksum takeover;
  podajemy ich liczbę i politykę. Częściowo zastąpione zdjęcie zachowuje wszystkie
  dziewięć fizycznych pozycji i stan ownership, bez przesuwania środkowej luki.
- Losowa próba1–100 zdjęć ma wersjonowany seed, pełny digest uporządkowanej
  populacji oraz dziewięć pozycji row-major. Osobna jawna próba hard przyjmuje
  do100 własnych źródeł i nigdy nie zmienia random mianownika/częstości.
- Capture otwiera osobne połączenie ograniczonego runtime, REPEATABLE READ
  READ WRITE i własną Session z jawnym game/RLS routing. Nie przełącza sesji
  żądania. Stabilny keyset po source UUID, strony metadanych do500, O(100)
  pamięci wyboru:100 najmniejszych SHA(policy,seed,occurrenceKey), pełny digest
  wszystkich członków. Dopiero wybrane zdjęcia rozwijamy w tym samym snapshotcie.
  Kontrakt: capture deadline60s, pojedynczy statement do30s/pozostałego czasu,
  lock5s. Przekroczenie daje jawny timeout i rollback; brak częściowo ważnej próby.
  Żadnego source sweep/hashowania obrazów lub inferencji. Wielkość danych nie
  pozwala zastąpić snapshotu bezgłośnym skanem stron z różnych chwil.
- Zamrażamy dostępne oryginalne obserwacje automatyczne, dokładne nodes,
  producing job/snapshot, raw/pixel identity i normalizację, binding/sequence,
  board/review/target revision oraz wszystkie9 braków/deferred/partial/unknown.
  Obecny assignment nie dowodzi historycznego producenta. Zapisana już korekta
  jest bieżącą ręczną obserwacją, a nie jakością modelu; brak dokładnie związanej
  historycznej predykcji pozostaje coverage gap. Brak zapisanej planszy może
  wynikać z ownership/odrzucenia/polityki zapisu: to nie dowód błędu detektora.
- Manifest jest plikiem kanonicznego JSON bez bitmap, o niezmiennym SHA i
  content-addressed nazwie. Istniejący wzorzec store: przygotowanie → atomowa
  publikacja pliku → commit wskazania i receiptu; aktywny rekord nie może wskazać
  częściowego pliku. Crash przed commit może zostawić nieszkodliwy staged/orphan
  plik, nie aktywną próbę. Retry sprawdza dokładny SHA i odtwarza wynik; brak lub
  zmiana pliku daje jawny blocker, bez ponownego losowania pod tym samym kluczem.

Uściślenie baseline przed jego implementacją: dla niezmienionego celu używamy
jego własnej exact producing auto obserwacji; po ręcznej korekcie najnowszego
udowodnionego automatycznego przodka tego celu sprzed następujących po nim
ręcznych korekt. Nie najwcześniejszej rewizji zdjęcia z definicji. Konieczny
board/slot/source/sequence/owner lineage; daty i podobne nodes nie wystarczą.
Review.snapshot jest dowodem tylko po exact source/auto checksum i producenta.
Brak łańcucha daje coverage gap. Nie podstawiamy starej importowej predykcji za
nowszą reinferencję. Raport ujawnia exact producer/coverage i nie nazywa mieszanej
próby skutecznością obecnie aktywnego modelu. Test obejmuje dwie auto wersje,
późniejszą korektę człowieka i zachowany starszy immutable snapshot.

#### Pomiar, korekty i symbole

- Oceny dotyczą niezmiennej pokazanej obserwacji. Wyświetlamy oryginalny overlay
  i osobno bieżącą korektę. Source byte/pixel drift lub inny cel daje konflikt;
  zmiana samej zbiorczej rewizji źródła wskutek korekty sąsiada nie unieważnia
  pozostałych pozycji. Nie podmieniamy obserwacji nową geometrią.
- Każda z9 pozycji ma jawne geometry correct/incorrect/not_assessable/unreviewed
  oraz odrębne oceny wykrycia i sekwencji z unknown/unreviewed. Nieznanej
  sekwencji nie zgadujemy, nie uruchamiamy targetu. Unexpected detections mają
  odrębną listę/ocenę i nie znikają z raportu. Użytkownik może jawnie potwierdzić
  wszystkie9 tylko gdy wszystkie są pokazane i możliwe do oceny; nigdy na mount,
  reload, przejściu dalej, ukrytym lub brakującym obrazie.
- Raport podaje frozenPopulation/sample/expectedPosition counts, reviewed,
  assessed, correct, incorrect, unavailable/unreviewed. FullyReviewed wymaga
  jawnego verdictu wszystkich9; fullyAssessable wyklucza not_assessable.
  Complete-correct wymaga wszystkich9 ocen poprawnych i odpowiednich rozstrzygnięć
  detekcji/sekwencji; przy braku danych jest unknown. Każda stopa pokazuje własny
  mianownik oraz pokrycie wobec całej próby. Bez pozornego zera za brak kontroli.
- Zapis oceny nie zmienia geometrii, approval, symboli ani kanonu. Rzeczywista
  korekta prowadzi do istniejącego Reviewera i VirtualGridGeometryService
  save_review_item/save_pending_slot. Oryginalny błędny wynik pozostaje błędny.
- Symbole wyłącznie według istniejących, aktualnych ręcznych decyzji i zgodnego
  crop revision z własnej gry. Pozostałe są nieocenione. To liczba aktualnych
  potwierdzeń, nie skuteczność klasyfikatora mierzona przez porównanie skopiowanej
  etykiety z nią samą. Brak symboli nie blokuje geometrii; nie tworzymy etykiet,
  nowych sugestii lub wspólnego modelu symboli.

#### Jawne zatwierdzenie niezmienionej geometrii

- Przyjęty plan dopuszcza sprawdzone bez zmiany geometrie do późniejszej kohorty.
  Obecny writer geometrii także dla tych samych nodes tworzy rewizję i recrop,
  więc nie jest approval-only. Dodajemy osobną jawną akcję w istniejącym pionie
  geometrii: POST image-reviews/{reviewItemId}/geometry-approvals, z istniejącym
  gameId/importJobId scope, nowym command UUID/bodySHA i target-local fences.
  Nie jest skutkiem ubocznym oceny pomiaru ani automatycznym zapisem całego zdjęcia.
- Canonical source of truth pozostaje RecognizedBoardModel approval projection
  i rzeczywisty ImageBoardGeometryReviewEventModel(action=approved). Nowy trwały
  receipt łączy dokładne polecenie i event; nie fabrykujemy source/board revision.
  Trusted actor pochodzi z istniejącego sprawdzonego lokalnego Admin lub scoped
  ReviewerAccessSession; nie z body. Rozszerzenie allowlisty Reviewera wyłącznie
  o tę scoped ścieżkę, bez otwarcia pozostałych originów lub cudzych zakresów.
- Autoryzacja przed replay, replay przed CAS; inna treść pod kluczem to409.
  Lock owning source/owner w istniejącej kolejności, ponowna kontrola source
  identity, current board revision i producing reference, pozycji/binding,
  kanonicznego właściciela, issues i exact nodes. Source revision zmieniona tylko
  przez sąsiada nie jest samodzielnym konfliktem. Baseline tej jawnej akcji to dokładna FROZEN CURRENT geometria pokazana
  przy capture, odrębna od historycznej original model observation. Wymagamy
  exact equality live target z tym frozen current (nodes/source/revision/binding/
  owner/issues/checksum). Gdy historyczny producent jest nieznany, operator nadal
  może jawnie zatwierdzić tę pełną current-only geometrię po jej obejrzeniu;
  original assessment pozostaje coverage gap/not_assessable. Nowsza inna live
  geometria po capture jest konfliktem, bez ukrytego zatwierdzenia. Rzeczywistą
  nową korektę operator zapisuje istniejącym writerem i ogląda świadomie.
- Jedna transakcja zapisuje projection, approval event, receipt i istniejącą
  projekcję wyszukiwania/kompletność z materialize=False. Błąd cofa całość.
  Geometria, payload/provenance, hash, cropy, symbole i właściciel pozostają
  bez zmian. Replay jest historycznym receiptem, nie gwarancją wciąż aktualnego
  approval po korekcie/revert/cleanup. Nie zmieniamy engine_kind na manual_v1.
- Nie dodajemy standalone revoke w1009.0995 sprawdza aktualne approval/event,
  geometrię i issues oraz późniejsze correction/revert/wycofane dowody przy
  preview/freeze i kwalifikacji. Nie fabrykujemy przyszłych cohort/report binding.
  D-522 manual_v1 wyjątek materializacji w niekompletnym źródle pozostaje bez
  zmian. Approval-only nie materializuje nowych komórek ani nie obchodzi bramki.

Uściślenie przed poprawką approval-only (2026-10-16): brak historycznego modelu
nie pozbawia operatora możliwości stworzenia prawdziwej etykiety geometrii.
Osobny przycisk zatwierdza dokładnie frozen current pokazany przy capture;
nie original, który może być niedostępny lub błędny. UI wyraźnie nazywa widok
current-only, a backend sprawdza live/frozen exact target i pozostałe guards.
Znajomość historycznego producer nie jest warunkiem canonical human approval.
Nadal jest warunkiem przypisania wyniku jakości do original modelu. Żaden
pomiarowy checkbox nie wykonuje approval i brak lineage nie staje się correct.
Regresja: producer gap + pełna identyczna frozen current daje jawny approval
bez zmiany geometrii/cropów/symboli; original pozostaje not_assessable. Zmieniony
target/owner/issue, niepełna geometria lub brak source identity nadal blokuje.

#### Schemat, recording seam i zgodność

- Proponowane pięć game-owned tabel w game_data_v2: grid_quality_measurements
  (header/policy/population/manifest SHA), grid_quality_measurement_members
  (immutable occurrence/original observations i oddzielna current projection),
  grid_quality_measurement_judgments (append-only oceny), grid_quality_measurement_commands
  (idempotent exact receipts), grid_geometry_approval_commands (canonical approval
  receipts). Game scope, composite relacje/unikalność i RLS według istniejącego
  lifecycle. Rewizja oceny/CAS nie zmienia immutable baseline.
- Nie dodawać FK blokującego istniejący source cleanup. Immutable source ID i
  nullable live_source_id jak0999, exact own detach w istniejących wejściach
  cleanupu, zachowanie snapshotu/receiptu po usunięciu. Brak live daje unavailable,
  nigdy resurrect. Approval receipt ma retained event/target IDs, bez nowego FK
  blokującego legalny board/review/event cleanup. Whole-game lifecycle usuwa
  game-owned tabele we właściwej kolejności; layout-data reset zachowuje dowody.
- Addytywna Alembic0162 po potwierdzeniu wolnego head, current manifestv15,
  EXPECTED_ALEMBIC_HEAD i wszystkie rzeczywiste current consumers. Frozenv1–14
  i historyczne migracje pozostają niezmienne. Downgrade tylko empty-history,
  odmowa zachowuje dane/rewizję; bez CASCADE/DROP OWNED/REASSIGN cudzych obiektów.
- Brak reverse source membership w1002: rozszerzyć istniejący GET
  source-recording-groups o sourceId oraz exact sześcioparametrowy overload
  public.resolve_own_groups(uuid,uuid[],uuid,integer,uuid,uuid). Own-game+MAIN+
  sourceId EXISTS i indeks(game_id,source_id), bez skanu manifestów grup lub
  owner SELECT do prywatnych tabel. Stary overload5argumentów nadal działa.
- Historical source_recording_sql_v1.py/source_recording_permissions.py i0161
  bez zmian. Nowy source_recording_sql_v2.py oraz permissions_v2 wrapper; aktualny
  database_roles korzysta z wrappera. Ten najpierw zachowuje pełne v1
  enforce/errors i osobno exact nowy overload: owner=capability, PUBLIC deny,
  DEFINER/search_path=pg_catalog, runtime wyłącznie EXECUTE. Gdy0162 zainstalowana,
  brak overloadu to deployment blocker. Przed0162 nie wymagamy nieistniejącego
  obiektu. Wersję wykrywamy z rzeczywistego kontraktu instalacji, także podczas
  upgrade przed aktualizacją alembic_version; nie z dowolnego prefixu funkcji.
  Reprovision/ALL/default grant/current permission audit obejmują union exact
  signatures; żadnego dostępu do prywatnych tabel/kolumn/sekwencji. Nie zmieniamy
  historycznego v1 grant helpera. Downgrade usuwa tylko nowe exact obiekty.

#### Repoint niezmienionego sąsiada — dowód rzeczywistego writera

Analiza kodu rzeczywistego writera wykazała przed finalizacją fence, że istniejący
apply_board_repoint może przestawić source_geometry_revision_id i aggregate
geometry_checksum u niezmienionych siblingów z board revision0. Nie ma dla nich
osobnego cell invalidation eventu. To nie jest rzeczywista zmiana ich cięcia.
Nie wolno ani traktować każdej takiej zmiany jako stale, ani pomijać pointerów
i checksumów globalnie. Dopuszczamy wyłącznie serwerowy dodatni equivalence proof:

- Istniejące stare frozen i nowe live source rows należą do tej samej gry
  i source identity; raw/pixel/normalization/dimensions pozostają identyczne.
- Ten sam board/review/geometryRevision/slot/sequence i proposal binding,
  exact nodes/quads, render/crop/cell identities oraz chronione decyzje człowieka;
  owner i bieżące issues bez zmian. Zmiana geometrii/cropa/etykiety nie jest repoint.
- Nowy source row jest powiązany z rzeczywistym canonical manual save innego
  targetu (geometry revision/event/source row/checksum), zgodnie z zapisem
  istniejącego writera; sam engine_kind manual lub późniejsza data nie dowodzą
  tej operacji. Nowa automatyczna wersja modelu nie otrzymuje tego wyjątku.
- Dopiero wtedy różnica aggregate pointer/checksum i odpowiadających im
  technicznych cell-source odwołań jest dozwolona dla niezmienionego targetu.
  Własny event approval zapisuje prawdziwy bieżący checksum, bez zmiany nodes,
  rewizji, cropów, symboli albo kanonu. Brak dowodu to konflikt, nie liberalny fallback.

Frozen original/producer pozostają niezmienne. Przy NOWYM capture, jeśli repoint
zgubił exact producing reference, domyślnie original coverage gap. Rev0, podobne
nodes i stary review.snapshot nie wystarczają do wybrania historycznego modelu;
wykorzystanie snapshotu wymaga jawnego exact lineage/producer proof odróżniającego
późniejszą automatic wersję. Current-only human approval nadal działa zgodnie
z poprzednią sekcją, więc nie trzeba zgadywać producenta, aby zebrać etykietę.

Regresja musi użyć prawdziwego save_review_item: capture auto → korekta jednego
targetu → original zachowany, niezmienieni sąsiedzi mogą być nadal oceniani
i jawnie zatwierdzani, zmieniony target nie przechodzi unchanged approval.
Nowy capture pokazuje original gap tam, gdzie exact producent został zgubiony.
Fałszywy manual repoint, nowa automatic wersja, inny owner/issue/crop lub brak
źródłowego dowodu nie otwierają wyjątku. Żadnego client opt-out ani rekonstrukcji
historii przez kolejność dat. To realizacja wcześniej przyjętej ochrony sąsiadów,
zapisana przed poprawką zależnego fence.

#### API, UI i kontrole

- Zgodny pion backend/schema → OpenAPI → generated client → wrapper/request test.
  Nowe per-game grid-quality-measurements list/detail/commands są częścią tego
  samego obszaru; capture i assess jako typowane polecenia, nie równoległy rejestr
  anotacji. New family/game setting nie zmienia pomiaru historycznego.
- UI w sekcji gry: frozen random/hard i oryginalne9 overlay, stan unresolved
  nagrań, postęp, explicit assess/approve-unchanged, przejście do istniejącej
  korekty. Każde exact UUID/body utrwalone przed POST, reload GET-only, jawne
  retry, archive-before-discard, game/measurement fencing spóźnionych odpowiedzi.
  Brak obrazu/oryginalnej predykcji opisany, bez obiecywania jakości modelu.
- Przed właściwym kodem wykonawca ponownie czyta task/plan i wskazuje listę plików.
  Nowy konflikt źródeł prawdy lub istotnie inny kontrakt wymaga raportu przed
  zależną implementacją. Drobne nazwy/rozbicie małych modułów według konwencji.
- Testy: deterministic seed+digest/page order, missing/partial/superseded,
  source drift vs sibling correction, hard/random denominators, original model
  unavailable,9 obligatory verdicts, canonical approve exact/replay/rollback
  i brak recropu/symbol changes. Real-role/RLS dwie gry/private denial, v1/v2
  grant/reprovision/history0161, frozen manifests,0162 empty downgrade/reupgrade,
  cleanup retain/detach/no-resurrection, utracona odpowiedź i świeży proces UI.
  Małe własne UUID fixture, proof OID/marker/createdHere/cleanup, bounded120s
  partie przez wersjonowany scoped runner. Bez broad614/473, operatorDB, źródeł
  operatora, usług, benchmarku, inferencji, GPU, treningu lub aktywacji.

## Expected files

- Istniejące dodatkowo: storage/models.py (centralny rejestr), game_partition_lifecycle.py i bieżące consumers manifestu, schema_readiness.py; api/router.py/dependencies i api/image_grid_reviews.py, application/virtual_grid_geometry.py, obecne security/Reviewer allowlist oraz source cleanupy wskazane w0999.
- Istniejące recording seam: api/application/storage/source_recording_groups.py, storage/database_roles.py. Historical0161 i source_recording_*v1/permissions bez zmian.
- Proponowane: domain/grid_quality_measurements.py, application/storage/schemas/api/grid_quality_measurements.py, storage/grid_quality_measurement_models.py i manifest store; application/storage/grid_geometry_approvals.py, storage/source_recording_sql_v2.py, source_recording_permissions_v2.py, game_data_v2_manifest_v15.py, alembic/versions/0162_grid_quality_measurements.py.
- Proponowane UI: apps/admin/src/features/model-quality/grid-quality-measurement-{panel,state,command,client}.tsx/ts oraz scoped Reviewer link/approval control w istniejącym pionie. Nazwy i rozszerzenia doprecyzuje wykonawca bez równoległego writer'a.
- Właścicielskie docs ADMIN_APP/VISION_LAB/DATA_MODEL/API_CONTRACT i wygenerowany klient, skoncentrowane request/unit/PG/interactions tests. Root utrzymuje globalne README/plan/State/Decision Log oraz posthash1018; wykonawca nie nadpisuje tych plików.

- Istniejące: [virtual_grid_geometry.py](../../../services/api/src/game_predictor_api/application/virtual_grid_geometry.py) — `VirtualGridGeometryService.save_review_item`, `save_pending_slot`.
- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `services/api/src/game_predictor_api/application/grid_quality_measurements.py`, repozytorium i manifest pomiaru, schema/router oraz panel kontroli; dla zapisanych korekt.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_quality_measurement.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Ten sam seed i populacja odtwarzają próbę.
- Trudne przykłady nie zmieniają częstości z próby losowej.
- Brak pełnej kontroli zdjęcia jest widoczny.
- Raport rozdziela detekcję, geometrię, symbole i sekwencję.

## Verification

Zakres: API, ADMIN/REVIEWER, test deterministycznego próbkowania, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_operational_image_reviews.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Nie deklarować niezależności filmów bez dowodów ani jakości całej gry na podstawie celowo trudnych przykładów.

## Outcome

### Execution phase

- Implementacja zamrożona do niezależnego audytu; mechanizm gotowy do przeglądu, nie jest raportem rzeczywistej jakości bez anotacji operatora.
- Baza wykonawcza: v1.7.383 / `ea9a27b29be948c9328da2670dc2b4159675ac4e`. Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`; zaakceptowany wcześniejszy upstream v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` pozostaje historycznym odniesieniem.
- Worktree: `D:/game_predicotr/worktrees/v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`. Bez stage, commita, merge, push i uruchamiania usług.
- Wykonawca gpt-6.1-sol/high; wąscy wykonawcy recording seam i Admin UI gpt-6.1-sol/high. Audyt `claude-fable-5-1/high` do1200s uruchamia lead po freeze. Nie wykonano audytu; nie deklarujemy R1/PASS ani zamknięcia uwag.

### Changed

- Dodano deterministyczny frozen random/hard pomiar, full ordered population digest i bounded RR runtime/RLS capture z60s deadline. Rank zależy od policy/seed/sourceId, metadane zmieniają digest populacji bez ukrytej zmiany klucza losowania.
- Manifest JSON i pięć game-owned tabel0162/currentv15 zachowują oryginalne obserwacje, dziewięć pozycji, exact producer albo coverage gap, wersjonowane oceny i trwałe receipty. Aktualni konsumenci head/manifest używają0162/v15; frozen migracje i manifesty v1–14 pozostają niezmienione.
- Serwer odrzuca pozorne sukcesy przy brakującym oryginale/producentach/źródle, wymaga wszystkich9 jawnych ocen i pełnej listy unexpected detections. Raport rozdziela osie, mianowniki, pokrycie, random/hard i producentów. Symbole liczą wyłącznie bieżące ręczne potwierdzenia własnej gry, bez deklaracji classifier accuracy.
- Odrębne explicit approval-only zatwierdza exact FROZEN CURRENT. Wykorzystuje istniejącą kwalifikację writera i ownership/sequence/source locks, zapisuje prawdziwy projection/event/receipt w jednej transakcji, bez recropu, zmiany nodes, rewizji, symboli lub kanonu. Current-only przy producer gap nadal można świadomie zatwierdzić; nie tworzy to oceny modelu. Processing pending import ma jawny server approvalBlocker.
- Dodatni verifier chroni frozen niezmienionego sąsiada po canonical manual publication innego targetu. Full cell/render/decision/owner/issues oraz old/new source/slot identity muszą pozostać zgodne. Nowy automatic model, brak publication proof lub inny crop/target daje konflikt. Nowy capture po utracie producing reference pozostawia original gap.
- Own-source membership filtruje przed keyset/limit przez nowy exact sixarg resolver, forward-only SQL/permissions_v2. V1 i0161 bez zmian. Draft membership pozostaje unresolved do rzeczywistej deklaracji.
- Trwała historia przeżywa legalne odłączenie/usunięcie źródła i istniejące wejścia cleanupu. Backend/OpenAPI/generated client/wrapper/request/UI stanowią jeden typowany pion. UI zachowuje UUID/body przed POST, explicit retry i archive-before-discard, readonly reload oraz fences spóźnionych odpowiedzi.

### Verification results

Wyniki są grupami kontroli; nakładających się przypadków i ponowień nie sumujemy jako unikalnego pokrycia. Dokładne polecenia, jawne timeouty do120s, node IDs, SHA i cleanup są w `artifacts/audits/TASK-1009_IMPLEMENTATION_EVIDENCE.json`.

- Backend final:49 PASS, `TASK-1009_backend_final.json` (limit110s). Recording seam:51 PASS, `TASK-1009_recording_seam_full.json` (limit60s), zachowany dowód wykonawcy. Current-consumers:48 PASS, `TASK-1009_current_consumers.json` (limit110s).
- Real-role PostgreSQL final:6 PASS, `TASK-1009_pg_attempt11.json` (~92s, limit115s). Własna UUID DB:0161 fresh→0162, empty downgrade/reupgrade, runtime forced RLS dwóch gier/private denial/sixarg/reprovision, exact replay z nowego procesu, projection failure rollback, actual browser source deletion/no resurrection, retained downgrade guard oraz real save_review_item i processing eligibility. SHA core/testów przed/po zgodne. PG10 zawiera także10 PASS kontrprzykładów verifiera; są uwzględnione w49 backendowych, bez podwójnego liczenia.
- Admin UI:17 PASS, typed blocker/current-only/mount/reload/retry/storage/late-response interactions; Admin tsc i scoped eslint0warning PASS. Safe receipt: `TASK-1009_UI_APPROVAL_BLOCKER_VERIFICATION_RECEIPT.json`. Wrapper requests:3 PASS. Reviewer proxy:7 PASS, Reviewer tsc i scoped lint PASS. Client typecheck PASS.
- Scoped Ruff wszystkich60 dotkniętych plików Python PASS; mypy14 nowych źródeł PASS. Format59/60 początkowo PASS, jedna dotknięta linia superseded cleanup wymagała formatowania; osobny retry tego pliku PASS. Prettier UI i wrapper/request/proxy PASS. Po wyłącznie formatowaniu nie powtarzano zaliczonych testów.
- Admin OpenAPI artifact/drift PASS. Pełne `npm run openapi:check` zakończyło się FAIL wyłącznie na Vision client sandbox TEMP EPERM rename; nie przedstawiamy tej komendy jako PASS. Ponowiony tylko nieudany Vision drift w dokładnie własnym krótkim TEMP:PASS, timeout110s, TEMP cleanup true. Doc i map generate/check PASS;552 decyzje/50 active/10 done.
- Historyczne próby pozostają niezaliczone: initial domain collection brak exportu RECORDING_TABLES; domain_r2 trzy niespójne oczekiwania schema/fixture PYTHONPATH; mypy_r1 obejmował niezaanotowane testy i błędy nowych typów, naprawione w kodzie. Recording seam dwa sandbox HTTP timeouty zostały sprzątnięte przed odrębnym końcowym PASS.
- PG1 FAIL: ORM legacy source_images nie mapuje game_id, zachowano fizyczny composite FK w migracji zgodnie z konwencją0999. PG2 FAIL: roboczy test/formatowanie nałożyły się, ten wynik nie dowodzi sformatowanej wersji. PG3 FAIL: own-source guard wymagał doprecyzowania pending own owner; PG4 FAIL: pomocniczy odczyt fixture nie związał routingu. PG5/6 PASS to wcześniejsze, częściowe grupy. PG7/8 FAIL: fixture writer context bez gotowej search projection/import state. PG9 FAIL: fixture nie miała aktywnych symboli wymaganych przez istniejący writer; dodano wyłącznie dwa własne symbole fixture. PG10/11 PASS po poprawkach; niczego nie oznaczono xfail ani nie osłabiono guardów. OdPG4 before/after SHA zapisane; dlaPG3 brak współczesnego before SHA.
- Finalny odczyt zasobów:11 own capability journals cleaned, dokładne DB/role/connections0;20 scoped test Windows Job receipts empty/closed, process/TEMP cleanup true. Read-only pomocnicza próba z opcjonalnym psutil FAIL (brak pakietu, bez mutacji) została zastąpiona sprawdzonymi Windows Job receipts. `TASK-1009_FINAL_RESOURCE_CHECK.json` zachowuje rozróżnienie.

### Not completed

- Rzeczywiste ręczne anotacje Mumii/777a2 i wynik jakości operatora pozostają oczekujące. Nie wykonywano anotacji prawdziwych zdjęć, source sweeps, inferencji, checkpointów, GPU, treningu, aktywacji/defaultów ani operacji na bazie operatora.
- Audyt Claude, zamknięcie wymaganych uwag, commit, przeniesienie taska do completed i aktualizacja globalnego statusu po commicie należą do kolejnego kroku leada. HEAD nadal v1.7.383. Bez merge/push/restart/deployment.
- Nie uruchamiano pełnych macierzy614/473, urządzenia Android ani ręcznego odbioru z działającymi usługami. Dawne niezwiązane reset/SuperGame UI FAIL pozostają poza zakresem; nie zmieniano ich oczekiwań ani guardów.

### Documentation updates

- ADMIN_APP, requirements/architecture VISION_LAB, DATA_MODEL, API_CONTRACT, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP, APP_V3_FUNCTIONAL_INVENTORY oraz wygenerowane CODE_MAP/CODE_MAP_SYMBOLS opisują nowe zachowanie.
- README, plan, CURRENT_STATE, obie kopie DecisionLog i posthash1018 są metadanymi leada, obecnymi przed implementacją i rozliczanymi osobno. Współdzielony task: lead owns kontrakt Technical notes; wykonawca owns ten Outcome.

### Definition of Done / next step

- Deterministyczna próba, rozdział hard/random, widoczne braki wszystkich9 oraz odrębne osie i manual-only symbole są zaimplementowane i sprawdzone. Kontrakt backend/OpenAPI/client/wrapper/UI, migracja, trwałość nowego procesu i dokumentacja są gotowe do niezależnego przeglądu.
- DoD całego taska pozostaje oczekujące na Claude high i decyzje po audycie; rzeczywista miara jakości dodatkowo wymaga anotacji operatora. Lead uruchamia audyt na zamrożonych plikach/evidence; wykonawca czeka bez zmian.
- Recommended next task po przyjęciu1009: TASK-0995.


### Rozliczenie audytu przez lead — korekta P1-1

- Claude Code `claude-fable-5-1/high`, runda1, limit1200s; rzeczywisty czas
 719.665858s. [Oryginalny raport R1](../../quality/TASK-1009_AUDIT_claude-fable-5-1_R1.md)
 pozostaje bez zmian, z werdyktem REVISE i jedyną uwagą blokującą P1-1.
- P1-1 naprawiony: odwrócono wyłącznie udowodnione jedno-/dwukrotne błędne
 dekodowanie UTF-8 jako cp1250. Każdą linię sprawdzono przez dokładną odwrotną
 transformację do zamrożonego tekstu R1; bez zmiany treści kontraktu i Outcome.
 Dwa checkboxy uzgodniono z istniejącymi testami i oceną audytora. Nie dopisano
 wyników rzeczywistej kontroli operatora ani fikcyjnego PASS audytu.
- P2-1…P2-5 są w jednej dozwolonej rundzie poprawek wykonawcy. Do ich zakończenia
 task pozostaje in_progress. Dokumentowy P1-1 nie zmienia zachowania domeny;
 samo przywrócenie kodowania nie uruchamia automatycznej rundy2.


### Zamknięcie przez lead — 2026-10-16

- Execution phase: gotowe do osobnego commita **v1.7.384**, potem oczekiwanie na integrację całego planu. Pełny hash po commicie, bez amend.
- [Claude high R1 REVISE](../../quality/TASK-1009_AUDIT_claude-fable-5-1_R1.md),719.665858s/do1200s; jedyny P1-1 procesowy zamknięty i wszystkie P2 rozliczone w jednej rundzie. [Odpowiedź Codex](../../quality/TASK-1009_RESPONSE_CODEX.md). Oryginalny werdykt pozostaje bez zmian; brak twierdzenia o PASS audytora.
- P1-1: Zamknięte: poprawny UTF-8 odzyskano odwracalnie dla każdej linii (207 dwie warstwy,26 jedna,157 bez zmiany), bez zmiany semantyki kontraktu/Outcome; cztery kryteria są zgodne z testami. Nowy proces potwierdził tytuł, polskie znaki i brak mojibake. Sekcja3.3 planu utrwala jawny UTF-8 przy odczycie/zapisie. Raport R1 i jego REVISE pozostają bez zmian.
- P2-1: Zamknięte: nieblokujący request-transaction key lock poprzedza niezależny RR snapshot. Drugi request dostaje typed409 GRID_QUALITY_CAPTURE_BUSY bez drugiego capture/manifestu; exact retry odtwarza200 receipt. Real HTTP/restricted PostgreSQL PASS1 (~27.984s):1 measurement/command/manifest,0 staged,1 snapshot call. Osobne request Sessions,5s bariery, brak wymuszonych statusów. Pierwszy brak pól ApiSettings w fixture zachowano jako FAIL, potem poprawiono wyłącznie fixture; własne zasoby obu prób sprzątnięto.
- P2-2: Zamknięte: link prowadzi do lokalnego origin Reviewera bez nieobsługiwanych query. Opis jawnie wymaga ręcznego wyboru gry/importu/zdjęcia; nie obiecuje automatycznego przejścia do celu. UI18 PASS wraz z testem linku; nowego routingu nie dodano.
- P2-3: Zamknięte: komentarz allowlisty opisuje scoped approval-only D-555; historyczny singular approval i whole-source save nadal nie są dostępne. Guardy bez zmian.
- P2-4: Zamknięte: MODEL-11 jest ciągłym wierszem tabeli inwentarza; sprawdzono strukturę i UTF-8.
- P2-5: Zamknięte: neutralna etykieta „Kolejne pomiary” odpowiada stabilnej paginacji UUID, bez obietnicy chronologicznej kolejności. Backendowego porządku nie zmieniono.
- Korekta SHA: `45b1c5ecaa6b5e64f4b599378136efb2877c91c9a6f5d96fd37c8b086b72b9c7`. Dowód P1: artifacts/audits/TASK-1009_P1_ENCODING_REPAIR.json. Bez automatycznego R2: P1 dotyczył tekstu, zmiana zachowania była P2. Nowy proces odczytał poprawne UTF-8 i cztery kryteria; instrukcja zapisu jest utrwalona w sekcji3.3 planu.
- Końcowe DOC/MAP/diff oraz staged lista/stat są sprawdzane przed commitem. Dotychczasowe zapisy „audyt niewykonany” i „poprawki w toku” opisują wcześniejsze przekazanie; niniejsza sekcja je zastępuje. Rzeczywista jakość nadal wymaga anotacji operatora.
- Recommended next task:0995. Bez integracji i operacji operatora.


### Post-commit — 2026-10-16

- Commit **v1.7.384** / `d2b692dbc59f1de339ad1acd2a961d402fced8c8`. git show --stat i pozostały status sprawdzone; worktree był czysty.
- Execution phase: oczekiwanie na integrację całego planu; bez merge/push. Pełny hash dopisany po commicie, zapis wejdzie do następnego commita bez amend. Następny TASK-0995, kontrakt przed kodem i D-548 do przyjęcia.
