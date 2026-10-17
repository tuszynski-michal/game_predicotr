---
title: TASK-0995 — Kwalifikacja korekt i niezmienny snapshot
status: done
last_updated: 2026-10-16
---

# TASK-0995 — Kwalifikacja korekt i niezmienny snapshot

## Status

`done`

## Goal

Dostarczyć trenerowi odtwarzalny zbiór z czytelną listą braków.

## Context

Task jest częścią zaakceptowanej rewizji 6. Kwalifikacja i niezmienne dane dowodowe. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1002 i TASK-1009 są ukończone. D-548/D-556 przyjęto przed zależnym kodem. Operator2026-10-16 wybrał zachowanie historii z blokadą nowego użycia usuniętego źródła. Niezależny rdzeń jest zamrożony; zależna kwalifikacja wymaga spójnej implementacji i testów przed końcowym audytem/commitem. Usunięcie zdjęcia samo nie oznacza cofnięcia zatwierdzenia człowieka.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. D-548 przyjęto2026-10-16 z jawnej zgody na całą rewizję6; D-549–D-555 obowiązują w swoich accepted zakresach. Nie zastępuje to etykiet, niezależnych nagrań ani zgód operacyjnych.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. aktualność etykiet i dane dowodowe.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB_EXPORT](../../guides/VISION_LAB_EXPORT.md).
- [VISION_LAB](../../architecture/VISION_LAB.md).
- [VISION_LAB](../../requirements/VISION_LAB.md).
- [DATA_MODEL](../../architecture/DATA_MODEL.md).
- Zakres odczytu uzupełniający z planu: VISION_LAB_EXPORT, VISION_LAB, DATA_MODEL.

## Scope

- Preview required/eligible/missing per gra i rola.
- Osobne targety board/screen.
- Freeze źródeł, rewizji, preprocessing, base, ról i hashy.
- Cofnięte dowody unieważniają kwalifikację kandydata.

## Out of scope

- Stary eksporter zachowuje dotychczasową domyślną semantykę; bez treningu.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Pełna plansza z niekompletnego zdjęcia działa w grid-only.
- [x] Niepełne zdjęcie nie jest screen targetem.
- [x] Auto-accept nie tworzy etykiety.
- [x] Drift między preview/freeze blokuje zapis.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

D-556 przyjęto przed kodem w niezależnym zakresie technicznym. Operator następnie rozstrzygnął retencję: zachować historię i zablokować nowe użycie usuniętego źródła; zależny kontrakt zapisano niżej.

### Źródło prawdy i granice pionu

Ten kontrakt doprecyzowuje zaakceptowaną rewizję 6, D-548, D-554 i D-555 przed kodowaniem. Baza wykonawcza: v1.7.384 / `d2b692dbc59f1de339ad1acd2a961d402fced8c8`. Zadanie dostarcza mechanizm przygotowania danych, nie rzeczywistą kohortę operatora, trening, ocenę modelu ani zgodę operacyjną. Historyczny eksporter, protokoły labu, dane symboli i gra kod `7` zachowują swoje kontrakty.

Jedna kohorta należy do jednej gry, wskazuje niezmienną bazę/rodzinę, tryb `grid-only` albo `screen+grid`, wersję polityki, preprocessing oraz role całych nagrań. Wspólna kohorta obu gier w TASK-1006 składa się z referencji do oddzielnie zamrożonych zbiorów; nie przełącza zakresu gry w jednej transakcji. Folder, brak trafienia SHA, ręczna ocena pomiaru lub automatyczna akceptacja nie są dowodem niezależności ani etykietą.

Polityka `application-grid-cohort-v1` wymaga per gra: TRAIN grid-only co najmniej 30 plansz z 10 zdjęć; VALIDATION i REGRESSION po co najmniej 15 plansz oraz 5 całkowicie opisanych zdjęć, każde z osobnego nagrania; TRAIN screen+grid co najmniej 10 całkowicie opisanych zdjęć. Przy dziewięciu planszach kontrolne części wymagają po 45 etykiet, więc minimalny grid-only to co najmniej 120 plansz z 20 zdjęć. To próg techniczny, nie gwarancja jakości. Wagi poprawionych i sprawdzonych bez zmian targetów wynoszą 4:1, są przypiętym parametrem i nie zwiększają liczby unikalnych przykładów.

### Etykiety, geometria i pochodzenie

Kwalifikujemy wyłącznie aktualną geometrię zatwierdzoną przez człowieka, ze zgodnymi bieżącymi rewizją, aktorem, czasem, właścicielem sekwencji, źródłem, statusem, dokładnymi 24 węzłami i kontekstem renderowania. Dowodem jest rzeczywisty guarded zapis `geometry_saved` albo canonical `approved` z pasującą projekcją i receiptami. Sama ocena pomiaru, `accepted`, `automatic`, timestamp lub numer rewizji nie wystarcza. Późniejsze approval-only zachowuje pochodzenie wcześniejszej rzeczywistej korekty.

Brak historycznego modelu predykcji nie blokuje prawdziwej bieżącej etykiety ludzkiej. Nieznane pochodzenie zatwierdzenia pozostaje jednak `unresolved`; nie odtwarzamy go z podobieństwa węzłów, dat, aktywnego assignment albo samego revision0. Dokładny łańcuch approval receipt → manifest pomiaru pozwala odzyskać dawny fence. Wyjątek niezmienionego sąsiada wymaga dodatniego dowodu rzeczywistego manual writera innego targetu oraz zgodnych starych/nowych source identity, slotu, sekwencji, właściciela, 24 węzłów, renderu i decyzji. Nie ignorujemy globalnie checksum ani pointerów.

Zapisujemy wszystkie 24 węzły, również nieregularne wewnętrzne punkty. Nie odtwarzamy targetu z czterech rogów. Pełna zatwierdzona plansza z niekompletnego zdjęcia kwalifikuje się do grid-only. Nie wymaga `geometry_complete` zdjęcia, 15 materializowanych komórek, cropów ani zatwierdzeń symboli. Gdy istnieje manifest renderu, musi pasować; bez niego wymagamy deterministycznego dowodu renderowania z dokładnych węzłów i kompletnego kontekstu, bez zapisu nowych cropów. Brak kontekstu daje `RENDER_PROVENANCE_UNRESOLVED`. Nie zmieniamy engine na `manual_v1` ani wyjątku D-522. Częściowe i wyłącznie ekstrapolowane etykiety są wykluczone. Screen target wymaga całkowitej anotacji wszystkich oczekiwanych pozycji, bez zamiany nieopisanej planszy na negatyw.

Całe zadeklarowane nagrania, aliasy byte/pixel pomiędzy grami, zaufane descriptor mapping i wyłączenia przodków przechodzą przez istniejący prywatny rejestr. TRAIN przodka nie staje się niezależnym VALIDATION/REGRESSION potomka. `final_test`, `unseen_game`, Reels, Treasure i zachowane holdouty nie trafiają do TRAIN. Wybór podzbioru zdjęć nie pomija ochrony całego nagrania. Brak providera, mapowania albo domknięcia daje jawne braki; przekroczenie dotychczasowego limitu domknięcia 4096 daje unresolved, bez skanowania obcych partycji.

Późniejsza prawidłowa materializacja komórek/cropów nie unieważnia zatwierdzonej geometrii, skoro ich wcześniejszy brak nie blokuje etykiety. Własny wrapper0995 może porównać geometry-only projekcję cell/render membership dopiero po niezależnym sprawdzeniu aktualnych pending grid issues oraz dokładnej parity wyprowadzonych cellQuads i render configuration z frozen label. Nie pomija nieznanej konfiguracji lub różnic renderu. Istniejący positive publication/repoint verifier1009 pozostaje bez zmian i nadal sprawdza rzeczywiste old/new source revisions, ręczny sibling writer, actor/time/current approval, owner i revert guards. Samo podobieństwo nodes nie daje wyjątku. Symbol label/confidence oraz dodanie zgodnych cells nie są withdrawal; node/revision/config/grid-issue drift nadal blokuje. Regresje obejmują brak15cells → prawidłowa materializacja oraz odrębne negatywne config/node/issue/revert przypadki.

### Kanoniczna tożsamość źródeł

Poprawki po audycie R1 zachowują istniejący kontrakt. Completion po dotychczasowym exclusive game ownership fence i source FOR UPDATE wymaga co najmniej jednego rzeczywistego bieżącego własnego, nieodrzuconego targetu z board.source_geometry_revision_id równym expectedSourceGeometryRevisionId. Używa istniejących current_targets/own_target/target_fence na tej samej connection/TX, przed UPDATE i receipt; brak zgodnego targetu daje SOURCE_GEOMETRY_IDENTITY_UNRESOLVED. Nie dodajemy zbędnej blokady game projection ani nowego resolvera. Publisher ma produkować rzeczywistą nazwę tymczasową rozpoznawaną przez istniejący GC (.tmp-<hex>.part); regresja odtwarza twardą awarię realnego publishera oraz bounded scan/24h, z zachowaniem ochrony referencji. Bieżąca0163 i detach emitują zgodny nowy reason, a mapper prywatnych błędów obejmuje również GRID_COHORT_ z typed409 i recovery. To jedna runda korekty R1, wymagająca R2 dla zmiany P1.

Wydzielamy wyłącznie czystą część istniejącego dekodera do `domain/canonical_source.py`: bytes, orientacja EXIF, pojedyncza klatka, normalizacja, checksum, błędy i stałe. Worker zachowuje loader ścieżek, cache, lease i orkiestrację oraz zgodne dotychczasowe eksporty. Nie dodajemy zależności ani importu API → worker. `domain/source_canonical_metadata.py` centralizuje istniejącą regułę: wszystkie pola NULL wolno jednorazowo uzupełnić; kompletny zestaw musi być identyczny. EXIF `None` jest legalną wartością kompletnego zestawu. Istniejący pipeline nadal wymaga własnego prawdziwego lease.

Jawna komenda uzupełnienia przyjmuje 1–5 własnych source IDs, oczekiwany byte SHA, geometry revision/checksum i trwały UUID/body. Limit to 64 MiB na źródło, istniejące 50 mln pikseli, jedna klatka i jeden budżet 60 s na komendę. Decode jest ograniczony rozmiarem, a deadline sprawdzamy między wywołaniami Pillow; nie obiecujemy przerwania Pillow co do milisekundy. GET i wejście na ekran nie czytają ani nie hashują obrazów.

Po autoryzacji i sprawdzeniu replay odczyt/decode odbywa się poza transakcją zapisu: managed root, containment, reparse/symlink, MIME, rozmiar, te same bajty dla raw SHA i normalizacji. Pod blokadami ownership/projection/source ponownie sprawdzamy generację, ścieżkę i tożsamość. Wymagamy rzeczywistej zachowanej rewizji źródła wskazanej przez aktualny własny target, zgodnej co do byte/pixel SHA, adaptera, wymiarów i układu współrzędnych. Nie tworzymy fikcyjnej rewizji, lease ani dowodu modelu. All-NULL completion i receipt są atomowe; identyczny komplet zwraca `already_complete` bez przepisywania; konflikt istniejących wartości nigdy nie jest nadpisywany. Nie zmieniamy istniejącego `attest_own_source_ids` v1.

### Magazyn i API

Proponowana addytywna migracja `0163_grid_training_cohorts` ma rodzica `0162` i nowy zamrożony manifest v16. Przed kodem ponownie sprawdzamy heads i wolny numer. Historyczne migracje, SQL/perms v1/v2 i manifesty v1–v15 pozostają bez zmian. Sześć tabel game-owned/partitioned/forced-RLS:

| Tabela | Zawartość i ochrona |
|---|---|
| `grid_training_cohorts` | Immutable selector, baza, polityka, preprocessing; rewizja, stan, okno capture, root SHA/path i podsumowanie. |
| `grid_training_cohort_members` | Gra/kohorta/source, stabilny ordinal, rola, zamrożone źródło i 9 targetów, approval/recording fences, powody; immutable source ID i nullable detach-only live link. |
| `grid_training_cohort_pages` | Immutable SHA/path/count/range oraz capture/materialization pins. |
| `grid_training_cohort_commands` | Gra/rodzaj/key, dokładna komenda i hash, zaufany aktor, immutable receipt. |
| `grid_training_cohort_events` | Dopisywane zdarzenia stanów, błędów i aktualności; indeksowane zależności kohorta/source/board. |
| `grid_source_identity_commands` | Idempotentne polecenia completion, oczekiwane pins i wynik; bez nowych blockerów live FK. |

Composite game FK i unikalności nie pozwalają nadać jednemu memberowi dwóch ról. Stan przechodzi `preparing` → `preview_ready` → `materializing` → `ready_to_freeze` → `frozen`, z jawnymi `failed`/`canceled`. Frozen payload jest niezmienny; aktualna kwalifikacja pozostaje osobnym wynikiem. Obrazy przechowujemy wyłącznie jako zarządzane pliki.

Rozszerzenie istniejącego Admin API pod `/api/v1/admin/games/{game_id}` obejmuje POST `grid-training-cohorts/prepare`, GET kolekcji/header/members/eligibility, POST `/{cohort}/prepare-page`, `materialize-page`, `freeze`, `cancel` i POST `grid-source-identities/complete`. Closed DTO nie przyjmuje zaufanych paths/pixel SHA/report proof. Prepare wskazuje własne importy/source selection, role recording groups, bazę/rodzinę/tryb oraz UUID; od0 do200 jawnie wybranych group IDs; pusty wybór daje wyłącznie preview braków. Członkostwo utrwala `INSERT SELECT`, bez timestamp/UUID high-water jako substytutu snapshotu. Odczyty i capture metadata mają strony do 200 źródeł; materialization do 5. Zapis sprawdza dokładny command hash, expected revision, cursor i właściwy preview/root SHA. Authorization poprzedza replay, a replay CAS. Zmieniona treść tego samego klucza daje 409 bez skutków. Pełny pion to backend → OpenAPI → generowany klient → wrapper → test żądania → UI.

### Publikacja plików i końcowy freeze

Capture metadanych i kopiowanie są jawne, stronicowane, wznawialne i mają receipt. Okno capture jest zapisane; nie udaje jednej globalnej migawki całej gry. Preview rozróżnia metadata eligible, jeszcze niesprawdzone bajty i rzeczywiście materialized eligible oraz required/eligible/missing osobno per gra/rola/board/screen. Nie wczytujemy całego zbioru do pamięci.

Materialization czyta wyłącznie wybrane oryginały poza blokadami DB. Content-addressed subtree własnej gry na D przechowuje sprawdzone kopie źródeł, JSONL targetów i małe strony. Manifest przypina wszystkie source/revision/byte/pixel/dimension/EXIF/adapter/decoder/Pillow/preprocessing/topology/24-node/approval-origin/recording-resolution/closure/provider/ancestor/base/checkpoint/export/role/weight referencje oraz SHA i rozmiary plików. Publikacja: temporary file na tym samym wolumenie, flush/fsync, atomowa publikacja bez nadpisywania odmiennej zawartości; directory fsync tylko gdzie wspierany. DB receipt zapisujemy po publikacji pliku. Crash przed commitem może zostawić nieaktywny plik, nigdy pozornie frozen zbiór. Retry weryfikuje te same bajty. Nie uruchamiamy cleanupu w ramach przygotowania.

Root manifest publikujemy przed końcowym commitem. Sam plik ani planowane ID użycia nie upoważnia do treningu. Końcowy freeze otwiera osobne ograniczone połączenie runtime w READ COMMITTED READ WRITE, bez dekodowania obrazów pod blokadami. Jeden deadline 60 s obejmuje całą transakcję, statement maksymalnie min(30 s, pozostały budżet), lock maksymalnie 5 s. Nie odnawiamy budżetu na stronę. Kolejność:

1. WRITE game/generation routing fence, authorization i command key/replay.
2. Katalog `9910994`, następnie registry `9921002`, przed ownership/source.
3. Ownership EXCLUSIVE, istniejący projection/game guard, wybrane sequence locks rosnąco. Nie pobieramy job lock po ownership.
4. Wszystkie wybrane source rows rosnąco UUID przed board/review/pending/canonical/counter/cell locks. Streaming JOIN members stronami do 200, bez globalnej tablicy IDs.
5. Świeży odczyt wszystkich wybranych source/current approval/receipt/owner/nodes/render/issues/revert fences i whole-recording proof pod już posiadanymi blokadami. Wywołanie capability nie może teraz czekać na nową globalną blokadę.
6. Sprawdzenie minimów, root i gotowości artefaktów; rzeczywiste recording uses, frozen header, event i receipt w jednym commicie.

Drift, timeout albo awaria cofa cały końcowy DB freeze/use/protection. Capture/copy można wznowić, ale freeze nie pomija aktualności dużego zbioru; po timeout operator może jawnie zawęzić wybór. Nie obiecujemy dowolnej liczby zdjęć w 60 s. Nie utrzymujemy starego snapshotu RR sprzed oczekiwania na ownership. Triggery notices nie pobierają globalnych blokad, a polecenia recording nie zapisują source partitions; zachowujemy istniejącą kolejność manual/import/cell writerów.

Ustawianie lokalnego statement timeout używa zwykłego DBAPI control cursor na tym samym fizycznym połączeniu/transakcji, także gdy właściwe zapytanie strumieniuje przez named ServerCursor. Nie wykonuje SET przez named cursor, nie tworzy nowej Session/connection i zamyka control cursor. Rzeczywisty ROLLBACK/ROLLBACK TO SAVEPOINT musi pozostać możliwy po błędzie albo wyczerpaniu deadline: hook nie poprzedza go SET ani ponownym sprawdzaniem budżetu, które zamaskowałoby pierwotny błąd. Zwykłe zapytania i commit nie dostają wyjątku. Istniejący recording error mapper może użyć SAVEPOINT w tej samej transakcji do odzyskania typowanego błędu; nie jest to nowa niezależna transakcja, commit ani implementacja asset guardu w savepoincie. Cały zapis oraz guard nadal należą do zewnętrznej transakcji i jej budżetu. Testy odtwarzają named-cursor SET, aborted savepoint i expired zwykłe zapytanie.

### Rzeczywiste użycie nagrań i granica oceny

Nowe forward SQL/perms v3 dodają wyłącznie exact public entry points `recording_cohort_page_v3(uuid,uuid,uuid,integer)` i `recording_cohort_command_v3(uuid,jsonb,text)`. Pierwsze obsługuje własną kohortę i stronę 1–200; drugie ma zamknięte rodzaje `register_cohort_use`, `validate_cohort_use`, `bind_existing_report`. Role, grupy, resolutions, baza i rodzina pochodzą ze stored pins, nie HTTP proof. Zapis actual `recording_evidence(kind=use)` wskazuje rzeczywistą kohortę/root SHA/rolę/resolution/dependency groups. VALIDATION/REGRESSION otrzymuje trwałą ochronę już przy freeze. TRAIN zachowuje lineage. Nie tworzymy report IDs na zapas.

Preproof i postproof po zapisie use muszą być identyczne: używane seed groups mają już zgodną role head, a dependency groups obejmują całe closure. Naruszenie daje `RECORDING_PROOF_CHANGED_BY_USE` i rollback całości, bez nowej resolution ani przepisywania root SHA. Niezwiązana zmiana global ordinal nie unieważnia kohorty. Wymagany rzeczywisty test invariantu, aliasów i wielu rodzin.

Runtime otrzymuje tylko EXECUTE dwóch exact nowych signatures i zachowuje dotychczasowe v1/v2. Ta sama zweryfikowana per-DB nonlogin/NOBYPASSRLS/NOINHERIT capability ma minimalne SELECT wymaganych własnych cohort columns pod forced RLS. Brak direct private tables/columns/sequences/helpers dla runtime, brak PUBLIC execute i owner fallback; kwalifikowane obiekty i `search_path=pg_catalog`. Aktualne `database_roles` sprawdza sumę v1/v2/v3 po broad/default grants i reprovision, nie zmienia historycznych importerów migracji.

Do walidacji rzeczywistego raportu rozszerzamy capability SELECT wyłącznie do `GridModelEvaluationReport(id, version_id, producer, report_json, report_sha256)`. Funkcja nie zwraca report JSON; sprawdza exact checksum/producer/schema/version/base/family/cohort references. Zmyślony, nieistniejący lub obcy raport jest odrzucany. Zwykły freeze tworzy zero report bindings. TASK-0997 zapisze prawdziwy raport i trwały protokół własnych game bindings, z atomową transakcją każdej kohorty oraz globalną barierą kompletności i aktualności przed publikacją; wymagany test producer → binding → withdrawal → blokada publikacji. Nie przepinamy game scope kilku gier w jednej transakcji. Istniejący invalidator obsługuje rzeczywiste use/report edges; brak takich dowodów nie jest PASS.

### Aktualność i retencja

Lokalne append-only notices wskazują indeksowane zależne members po istotnej zmianie source identity/link, board geometry/approval/status, owner, revert, review evidence lub `grid_issue`. Obserwujemy zarówno zdarzenia, jak i bieżące projekcje; sam event listener przegapi `apply_board_repoint`, a sama projekcja nie zastępuje dowodu canonical approval. Konkretne istniejące punkty:

| Writer / magazyn | Istotna zmiana |
|---|---|
| `grid_geometry_approvals.SqlAlchemyGridGeometryApprovalRepository.approve` | `recognized_boards.approved_geometry_revision`, `geometry_approved_at/by`, rzeczywisty board geometry review event i approval command/receipt. |
| `virtual_grid_geometry_repository.save_virtual_geometry_revision`, `save_virtual_source_geometry_revision`, `save_automatic_reinference_source`, `convert_legacy_source` | Board geometry/revision/source pointer/checksum/engine/approval oraz source/board revision i `geometry_saved`; konwersja nie jest nową oceną człowieka. |
| `geometry_correction_revert_repository._revert_board_revision`, `geometry_rejection_revert.revert` | Nowa current rewizja, status/rejection/resolution, przywrócona projekcja i rzeczywisty event revert. Równe dawne nodes nie pomijają przejścia. |
| `image_review_repository._apply_review_outcome`, `_claim_canonical_sequence`, `reopen_for_symbol_cell_issue` | Review status/resolved_value/resolution_revision, board status, canonical sequence owner i resolution events. Nie ma istniejącej osobnej komendy withdraw approval. |
| `image_symbol_review_repository.apply_board_mutations`, `_apply_symbol_cell_command` i obecne clear/restore przy save/revert | Przejście `image_symbol_review_cells.quality_issue` do/z `grid_issue`, związane zdarzenie i reopen rodzica. Sama etykieta/confidence symbolu nie odbiera geometrii. |
| `image_geometry_completeness_state_repository.apply_board_repoint` | Source revision pointer/checksum, render manifest i cell current/approved source pointer bez nowego approval event. Wymaga dokładnej weryfikacji niezmienionego targetu. |
| `source_images`, source/board geometry revisions i istniejący cleanup source graph | Byte/pixel/adapter/wymiary/tożsamość, usunięcie lub odłączenie źródła i utrata live dowodu. Jawny notice musi powstać przed usunięciem graph, które kasuje także eventy. |

Indeks zależności obejmuje `(game, source, board, review, cell)` wynikające z zapisanych members; tablice dziewięciu targetów mają odpowiedni indeks lub znormalizowany indeks zależności w ramach sześciu przyjętych tabel. Nie skanujemy całej gry. Triggery mają jawne OLD/NEW predykaty dla powyższych pól na rzeczywistych source/board/review/canonical/cell/event tables; immutability rewizji pozostaje zachowana. Fanout dotyczy tylko zależnych członków, bez cichego limitu pomijającego notices. Zdarzenia tej samej transakcji można złączyć bez utraty przyczyny. Trigger nie bierze catalog/registry/ownership locks, nie czyta obcej gry i nie zmienia frozen payload, publication ani default. Brak dowodu dla starego chain pozostaje unresolved, bez chronologicznych domysłów.

Notice oznacza konieczność dokładnej weryfikacji, nie automatycznie cofnięcie zatwierdzenia. Udowodniony unchanged sibling repoint zachowuje etykietę i pochodzenie. Rzeczywiste cofnięcie, zmiana nodes, revert, owner drift lub issue blokuje nowe admission/kwalifikację zależnego raportu. GET raportuje wynik bez mutacji; trusted admission/report command utrwala rzeczywiste invalidation. Upływ czasu nie usuwa notices.

Osobno raportujemy `humanLabelWithdrawn`, `liveSourceLinked` i `snapshotBytesAvailable`. Brak pliku nie dowodzi cofnięcia oceny. Missing/corrupt snapshot daje `DATASET_ASSET_UNAVAILABLE`/`CHECKSUM_MISMATCH`, blokuje dataset/run, bez automatycznego odtwarzania z innej ścieżki. Operator wybrał zachowanie historii i blokadę nowego użycia po source cleanup; wdrażamy jawną odmowę, zamiast poprzedniego tymczasowego unresolved. Usunięcie całej gry zachowuje istniejący lifecycle: usuwa game-owned partycje i katalog, bez obietnicy pełnego archiwum. Fizyczny asset GC pozostaje oddzielnym, zatwierdzanym i reference-aware krokiem; samo usunięcie partycji nie kasuje JPEG. Po game deletion może pozostać wyłącznie minimalna prywatna ochrona recording identity/use i lifecycle receipt, bez paths/labels/images. Nie projektujemy nowego wiecznego pełnego archiwum.

Zarządzane snapshot JPEG muszą wejść do istniejących source/game cleanup preview, quarantine, shared-reference checks i StorageRetentionPolicy. Staging używa istniejącej polityki 24 h od ostatniej rzeczywistej zależności/receipt, bez wykonania cleanupu w tym tasku. Ready/frozen copies chronią rzeczywiste retained cohort/run references. Nie dodajemy live FK blockerów ani resurrection źródeł. Source cleanup oraz istniejący reset operacyjnych plansz usuwają swój graph, ale zachowują konkretny immutable cohort snapshot/receipt i IDs z odłączonym live linkiem; nie obiecujemy zachowania wszystkich usuwanych operational events/revisions. Game cleanup zachowuje swoją istniejącą granicę. Downgrade jest dozwolony tylko przy braku wszelkiej nowej historii/use/protection/receipts, bez usuwania dowodów.

### Blokada nowego użycia po usunięciu źródła

Decyzja operatora2026-10-16: zachować historię i blokować nowe treningi oraz oceny używające usuniętego źródła. Nie jest to cofnięcie ludzkiej oceny ani polecenie usunięcia snapshotu. Wdrażamy stabilny reason `SOURCE_REMOVED_NEW_USE_BLOCKED`, zamiast tymczasowego `SOURCE_REMOVED_POLICY_UNRESOLVED`.

`grid_training_cohort_currentness.inspect_member` dla used=true i live_source_image_id=NULL zwraca typed409, liveSourceLinked=false i humanLabelWithdrawn=null. Used=false nie blokuje; missing bytes i infrastruktura zachowują własne powody. `eligibility` nadal zwraca200, lecz qualification=blocked przy dodatnim source-removed reason, także obok unresolved reasons. Zachowuje wszystkie reasons i jeden metadata-only przebieg60s; snapshotBytesAvailable=null. Nie wywodzimy withdrawal ze starego notice.

`source_recording_sql_v3.recording_cohort_command_v3` zmienia wyłącznie istniejący exception wspólnego used-member loop na ten sam kod, SQLSTATE22023. Register/validate/bind odmawiają nowego użycia; validate pozostaje READ ONLY bez writes/receiptów/locków. Istniejący mapper prefixu SOURCE_REMOVED_ zachowuje409 i rollback savepoint. Historyczny replay receipt pozostaje odczytem historii, nie nowym admission. `grid_reinference_retention.detach_grid_source_links` zapisuje nowy reason tylko dla nowych notices. Nie przepisujemy frozen payloadów, dawnych notices/receiptów i recording protections; nie odtwarzamy live source i nie zmieniamy GC/grants/migracji/DTO/worker adaptera.

Testy: NULL live link przy used=true, użyty usunięty+inny unresolved daje blocked i pełne reasons, used=false nie blokuje, nullable facts i GET bez file I/O, typed409 prywatnego seam i savepoint recovery oraz jeden existing HTTP case. SQL ma sprawdzony wspólny guard bez zmiany przepływu/grants. Jeśli istniejący mały negative fixture pozwala wywołać tę gałąź bez pełnej kohorty, osobny restricted/READ ONLY PG test potwierdza nowy kod i brak nowych use/receiptów po odłączeniu. Bez ponownego120target seedu, minimum bypass albo nowego pozytywnego fikcyjnego freeze; trudność istniejącego fixture należy zgłosić, bez szerokiej przebudowy. Scoped Ruff/mypy i nowy końcowy manifest zachowują poprzedni niezależny77source/520evidence archive.

### Jawne fakty kwalifikacji w istniejącym GET

Istniejący nowy DTO `GridCohortEligibility` otrzymuje trzy addytywne wymagane pola `boolean | null`: `humanLabelWithdrawn`, `liveSourceLinked`, `snapshotBytesAvailable`. Zachowujemy qualification/reasons/manifestSha256, istniejący endpoint oraz GET bez mutacji i odczytu/hashowania plików. Generated OpenAPI/client, wrapper, request tests i UI zmieniają się razem. Zamrożony poprzedni partial manifest pozostaje historią; zmieniony slice otrzyma nowy manifest i scoped weryfikację.

Fakty dotyczą tylko `used=true` members. `humanLabelWithdrawn=true` wymaga dodatniego dowodu utraty aktualnego ludzkiego zatwierdzenia co najmniej jednej użytej etykiety: rzeczywiste cofnięcie/revert albo udowodniona zmiana targetu unieważniająca tę etykietę. Wartość false wymaga potwierdzenia aktualnych approvals wszystkich użytych etykiet. Missing source/lineage/proof, sam notice, owner/alias/grid issue albo błąd infrastruktury nie stają się automatycznie true; gdy nie pozwalają ustalić faktycznego zatwierdzenia, wynik jest null. Pozostałe ochrony nadal niezależnie blokują qualification i podają własne reasons. Nie wnioskujemy cofnięcia człowieka z ogólnego LABEL_STALE.

`liveSourceLinked=true` oznacza potwierdzone aktualne powiązanie wszystkich użytych źródeł; false wymaga co najmniej jednego udowodnionego odłączenia/usunięcia. Nierozstrzygnięty stan daje null. Pusty wybór/zero used members daje null w obu polach, nie vacuous true/false. Odczyt nie udaje kompletnego pomiaru po błędzie zapytania. Istniejący ograniczony metadata verifier wylicza fakty przy tym samym przejściu; nie dodajemy trzech skanów korpusu ani obrazów. Obowiązuje jeden60 s budżet, bounded metadata pages, statement30 s/remaining i lock5 s tam, gdzie blokada jest konieczna.

`snapshotBytesAvailable=null` w metadata-only GET zawsze oznacza, że aktualnych bajtów nie sprawdzono. Poprzednia materializacja lub freeze nie dowodzi obecności pliku teraz. Bieżące missing/corrupt bytes ujawnia jawna operacja materialize/freeze albo file-backed adapter z istniejącym typed błędem; nie dodajemy w tym tasku nowej komendy weryfikacji. Qualification tego GET jest kwalifikacją metadanych, nie pozwoleniem na uruchomienie trenera. UI wyraźnie pokazuje „Aktualna dostępność kopii: nie sprawdzono”; null zatwierdzenia/powiązania również pokazuje „nie ustalono”. Prawdziwe run admission nadal wymaga aktualnych dowodów i bajtów.

Testy: actual withdrawal kontra missing-source/null, potwierdzone niezmienione used labels, zero used, owner/alias/issue reason bez fikcyjnego withdrawal, GET bez file reads/mutacji oraz trzy required nullable pola przez HTTP/generated wrapper/UI. Source-cleanup new-use policy blokuje nowe użycie przy zachowaniu historii; samo usunięcie nie dowodzi human withdrawal.

### Ochrona publikacji przed reference-aware GC

Istniejący GC odczytuje stan partii przed quarantine. Dla nowych plików kohort taki wcześniejszy odczyt nie wystarcza: wznowiona publikacja może ponownie użyć content-addressed JPEG ze starym mtime, zanim zapisze receipt. Rozszerzamy wyłącznie istniejący preview/retention/quarantine o adapter kohort; nie budujemy drugiego GC ani nie uruchamiamy cleanupu operatora.

Publikacja capture/materialize bierze transaction-scoped shared advisory guard w tej samej request Session po command key, przed publikacją plików i game write fence. Guard trwa przez IO, CAS, zapis page/receipt i istniejący commit albo rollback fabryki żądania. Bez drugiej sesji, nested TX lub odnawiania 60 s budżetu. Dwa argumenty PG: namespace `0x47504348` oraz signed32 z pierwszych czterech bajtów SHA256 tekstu `grid-cohort-assets-v1:<gameUUID>:<cohortUUID>`, z kanonicznymi lowercase UUID oraz big-endian signed32 (int.from_bytes(first4, "big", signed=True)). Ten namespace różni się od istniejącego reviewer two-int namespace; bigint advisory locks stanowią osobną przestrzeń. Kolizja skrótu powoduje wyłącznie dodatkową serializację, ponieważ wszystkie zapytania nadal sprawdzają pełne game/cohort IDs.

GC obejmuje pojedynczy cel exclusive guardem tego samego klucza w jednym restricted Session/TX. Pod guardem ponownie odczytuje rzeczywiste własne RLS references, stat/tożsamość pliku i reguły retencji, a następnie wykonuje istniejące quarantine/marker/delete przed zakończeniem transakcji. Wznowienie i obsługa istniejącego quarantine używają tej samej granicy. Nie bierze owner/source locks; porządek asset guard przed game fence/catalog/registry/owner nie jest odwracany. Lock timeout5 s i statement do min(30 s, remaining60 s); brak blokady lub dowodu chroni cel albo daje jawny typed unresolved, nigdy zgodę na usunięcie.

Page document zapisuje ograniczone deskryptory rzeczywiście opublikowanych assets, maksymalnie5 JPEG, page i odpowiednie root/indexes, w tym samym CAS/receipt. Zapytania nie otwierają obrazów ani dużych historycznych JSON. Rzeczywiste retained page/root/run references chronią pliki we wszystkich statusach; samo cancel/failed nie usuwa istniejących referencji. Niepodpięty plik po awarii podlega istniejącym24 h od max(mtime, ostatnia rzeczywista zależność/event/receipt). Source cleanup/layout reset zachowują konkretne frozen refs. Usunięcie game-owned partycji usuwa te referencje; minimalny prywatny recording use nie zatrzymuje JPEG.

Brak dokładnego ref może oznaczać orphan tylko po udanym scoped zapytaniu. Brak routingu nie oznacza pustych referencji: wymaga rzeczywistego zgodnego public lifecycle deletion receipt `done` oraz potwierdzonego braku katalogu, routingu i własnych partycji kohort, zgodnie z istniejącą walidacją zakończenia usunięcia gry. Wtedy anchor uwzględnia także deletion updated_at. Stan przejściowy, niespójny receipt, brak schematu/capability/uprawnień lub błąd zapytania daje protected/unresolved bez quarantine. GC nie omija przyjętej blokady nowego użycia usuniętego źródła i nie odbiera historycznej retencji rzeczywistych referencji.

Testy: retained ref kontra stary unreferenced crashfile; cancel z rzeczywistym ref; source reset kontra zakończone game deletion; missing/transitional/queryerror fail-closed; rzeczywiste dwa połączenia publication shared kontra GC exclusive, wraz ze wznowieniem przed receiptem i po quarantine. Bez cleanupu danych operatora.

### Worker i interfejs

Application-specific reader znajduje się w images/grid_cohort_dataset.py. Istniejący guard test_vision_lab_training_core.py zabrania game_predictor imports w neutralnym training_core; pozostaje bez zmian. Reader korzysta ze wspólnego canonical decoder i katalogowego descriptor_sha256 poza tym rdzeniem. Przyszły trener0996 otrzyma adapter przez kompozycję; nie obchodzimy guardu dynamicznym/relatywnym importem. Kohortowy canonical UTF-8 JSON i katalogowy canonical_json/descriptor_sha256 mają odmienne wersjonowane reguły ensure_ascii; do manifestu modelu używamy istniejącej funkcji katalogu i faktycznych preprocessingVersion/inferenceManifest pins. Manifesty utrzymują względne bezpieczne ścieżki; Windows native extended paths służą tylko I/O po containment/reparse checks, z kontrolą zgodności po restarcie. Nie skracamy fixture dla ominięcia realnego MAX_PATH.

File-backed `GridCohortSnapshot`, `GridBoardDataset`, `GridScreenDataset` używają indeksu stron i cache najwyżej jednej strony/fotografii. Przed odczytem pikseli kontrolują rolę TRAIN; następnie exact SHA/size, politykę, preprocessing/decoder/base i współrzędne. Adapter używa pure canonical decoder i neutralnego geometry preprocessing, bez torch/GPU/ORM/AnnotationStore. Board target zachowuje 24 węzły, wagę i pochodzenie; screen target wymaga pełnego zdjęcia. Późniejszy TASK-0996 wymaga świeżego admission proof; same pliki nie upoważniają do treningu.

Panel pokazuje bazę, tryb, role/nagrania, wymagania i konkretne braki, rozróżnia targety oraz etykiety/kopiowanie. Completion dotyczy wyłącznie zaznaczonych źródeł. Przed POST zapisuje trwały UUID i dokładny body/cursor; reload wykonuje wyłącznie GET. Utrata odpowiedzi pozwala na jawny identyczny retry; 409 nie tworzy automatycznie nowego klucza ani targetu. Odpowiedzi poprzedniej gry/kohorty nie zmieniają aktualnego ekranu. Frozen nie oznacza trained ani jakości PASS. TASK-1000 później scala ten panel z całością procesu.

### Błędy i granice

| Przypadek | Zachowanie |
|---|---|
| Brak human proof / legacy lineage | Member missing/unresolved; preview kontynuuje, bez targetu lub negatywu. |
| Brak canonical metadata / bajtów / checksum mismatch | Odrębne powody; tylko jawne completion/copy, bez overwrite. |
| Brak providera/mapowania, role/ancestor/holdout conflict | Unresolved albo blocked; brak zaliczenia minimów i ochrony nie usuwamy. |
| Pełna plansza / incomplete photo | Grid-only eligible; screen `PHOTO_NOT_FULLY_ANNOTATED`. |
| Key/body/revision/cursor mismatch lub preview drift | 409, zero skutków; replay przed CAS, jawny nowy preview. |
| Lock/deadline/infra | Typowany błąd, rollback bieżącej transakcji; nieaktywny plik nie jest frozen. |
| Crash publikacja/commit/HTTP | Weryfikacja tych samych bajtów i exact receipt replay, bez duplikatu use. |
| Sibling repoint / rzeczywista zmiana | Dodatni exact verifier zachowuje niezmieniony cel; zmiana blokuje kwalifikację. |
| Usunięcie źródła / cofnięcie oceny / brak JPEG | Trzy odrębne osie, bez resurrection i ukrytej utraty historii. |

### Ustalona granica rzeczywistego raportu (D-556, przed zależnym SQL)

Istniejący publication reader w domain/grid_model_publication.py pozostaje bez zmiany w0995: producer kolumny i JSON to server:grid-model-evaluator-v1, schema grid-model-evaluation-read-v1, policy grid-model-per-game-gate-v1 i zamknięty dotychczasowy zestaw pól. Nowy application-grid-evaluation-v1 nie jest zgodnym producentem i nie jest przyjmowany.

Nowy binding rozpoznaje wyłącznie przyszły grid-model-evaluation-read-v2 z tym samym zaufanym producer/policy. Jest to wersjonowane rozszerzenie istniejącego read modelu, nie równoległy model oceny. Wymagana część identyfikacyjna obejmuje schemaVersion, producer, policyVersion, versionId, baseVersionId, familyId i cohorts. Cohorts jest niepustą listą do100 różnych gier i kohort; każdy wpis ma dokładnie gameId, cohortId, manifestSha256. UUID mają kanoniczną postać, SHA to64 małe znaki hex. Wersja kolumny report.version_id musi równać się versionId JSON, a wybrany własny wpis, baza i rodzina muszą dokładnie odpowiadać stored header/manifest rzeczywistej kohorty. JSON ma limit1MiB i exact SHA całych UTF-8 report_json, z canonical_json/descriptor_sha256 obowiązującymi po stronie rzeczywistego writera. Walidator bindingu sprawdza pełny checksum, producer i wymagane tożsamości; nie nadaje PASS ani nie zastępuje walidacji pełnych metryk przez0997. Pozostała część raportu zachowuje dotychczasowe przypięte manifest/base/cohort/requiredGameIds/games i szczegóły oceny zgodnie z kompletnym v2 kontraktem, który0997 utrwali przed swoim kodem. Nie zamrażamy dziś fikcyjnego formatu metryk. Zgodność requiredGameIds, rzeczywistych cohort refs i całej oceny musi być sprawdzona przez0997.

0995 nie zmienia obecnego require_evaluation_evidence i nie tworzy przyszłych raportów/bindingów. Stary v1 raport nie jest dowodem nowego v2 cohort binding i otrzymuje typed unsupported-provenance, bez naruszania jego dotychczasowego odczytu. Bind może chronić również rzeczywisty raport negatywny; jakość/PASS nie jest warunkiem zachowania zależności. Nieistniejący, zmieniony lub niepowiązany raport jest odrzucany. Test pełnego rzeczywistego0997 producer → binding → withdrawal → blokada publication jest obowiązkowy później, bez fikcyjnej oceny teraz.

Transakcja bindingu dotyczy jednej własnej kohorty i aktualnego zakresu jednej gry, z atomowym use/event/receipt. Wspólny raport kilku gier nie może przepinać GameStorageRouter do innej gry w jednej transakcji.0997 ma dostarczyć trwały, idempotentny protokół przygotowania raportu i oddzielnych własnych game bindings; brak choć jednego wymaganego bindingu lub aktualnego dowodu blokuje publikację/aktywację/default nowego v2 kandydata. Globalna bariera aktualności raportu musi uwzględnić notices wszystkich objętych gier bez owner fallback/obcych source partition reads i bez odwrócenia catalog→registry→ownership kolejności. Potrzebny most minimalnych notices/validation proofs i jego exact uprawnienia wymagają osobnego pełnego kontraktu przed kodem0997;0995 nie przedstawia tego mostu ani wspólnej publikacji jako wykonanych. Nie zakładamy fikcyjnej pojedynczej transakcji wszystkich gier. Dotychczasowe v1 historyczne dowody i już przypięte modele zachowują własne kontrakty.

### Nierozstrzygnięta rola nagrania

Member.role i DTO role mogą mieć null wyłącznie dla nierozstrzygniętego przypisania. RECORDING_MEMBERSHIP_REQUIRED/AMBIGUOUS pozostaje widoczny w preview, nie zalicza minimów i actual use, nie dostaje default TRAIN ani nowego enum. Initial INSERT SELECT zapisuje własne source IDs/ordinal w preparing members z role null. Następny prepare-page pod CAS/receipt korzysta z tego samego capability page dla już zapisanych members, a rolę przypisuje tylko przy jednoznacznym rzeczywistym mapping, deklaracji i proof. Nie tworzymy drugiego resolvera lub discovery API przed member insert. Przygotowywane wiersze są robocze; frozen są immutable. Freeze wymaga udowodnionej roli każdego rzeczywiście użytego targetu, a preview jawnie wykazuje każdy wykluczony/unknown member bez cichego znikania.

### Wybrane i rzeczywiście użyte źródła

Selector i immutable metadata pages zachowują wszystkie wybrane members. Serwer zapisuje member.frozen.used jako boolean; w preview jest to planowane użycie, a nie zgoda na trening. true wymaga jednoznacznej rzeczywistej roli, whole-recording proof i kwalifikującej się current human/source label. TRAIN grid-only może użyć co najmniej jednej pełnej zatwierdzonej planszy z incomplete photo; TRAIN screen+grid i zdjęcia kontrolne używają pełnej anotacji dziewięciu oczekiwanych pozycji. Pozostałe members mają used=false i jawne reasons, pozostają w preview/manifestach jako excluded, nie tworzą JPEG kopii/negatywnych targetów/actual use i nie zaliczają minimów.

Prepare-page może utrwalić wynik podczas preparing. Po preview_ready użyte flagi, targety i reasons są częścią przypiętego preview; materialization/freeze nie przestawia ich po cichu po wykryciu driftu lub brakujących bajtów. W takim przypadku jest typed fail/stale i jawne nowe preview/rebuild, bez samoczynnego zmniejszania zbioru. Actual registrar ponownie sprawdza rzeczywiście used=true, minima i wszystkie relevant whole-recording protection. used=true z role null jest błędem; excluded metadata nie staje się treningiem.

Recording selection ma0–200 wpisów. Puste recordings=[] pozwala jedynie zobaczyć podgląd braków: role null, zero used/actual use/minimów/permission. Nie oznacza wyboru wszystkich nagrań ani domyślnego TRAIN. Brak wyboru jest RECORDING_SELECTION_REQUIRED; brak faktycznego membership jest RECORDING_MEMBERSHIP_REQUIRED, a niejednoznaczność AMBIGUOUS. Jeżeli przy pustym wyborze istnieje już membership, UI nie twierdzi, że go nie ma. Wybór ról i grup jest jawny; istniejących role heads nie nadpisujemy parametrem kohorty.

## Expected files

Nowe proponowane pliki API pod `services/api/src/game_predictor_api/`:

- `domain/canonical_source.py` — czysty istniejący decoder; `domain/source_canonical_metadata.py` — reguła all-NULL completion/equality; `domain/grid_training_cohorts.py` — kwalifikacja, polityka, minima i manifest.
- `application/grid_training_cohorts.py::GridTrainingCohortService`, `application/grid_source_identities.py::GridSourceIdentityService` — orkiestracja poleceń, aktualność i kontrolowane granice transakcji.
- `storage/grid_training_cohort_models.py` — sześć tabel; `grid_training_cohort_repository.py` — pages/CAS/receipts/locks; `grid_training_cohort_evidence.py` — rzeczywiste human chains i repoint; `grid_training_cohort_artifacts.py` — bounded atomic store; `grid_training_cohort_currentness.py` — notices, exact currentness i report seam.
- `storage/source_recording_sql_v3.py`, `storage/source_recording_permissions_v3.py`, `storage/game_data_v2_manifest_v16.py` — wyłącznie forward kontrakty, bez edycji poprzedników.
- `schemas/grid_training_cohorts.py`, `api/grid_training_cohorts.py::create_grid_training_cohorts_router` — zamknięte DTO i rozszerzenie istniejącego Admin API.

Pozostałe nowe proponowane pliki:

- `services/api/alembic/versions/0163_grid_training_cohorts.py` — head/numery ponownie sprawdzane przed utworzeniem.
- `services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py` — CPU/file-backed adapter bez trenera lub laboratorium.
- `apps/admin/src/features/model-quality/grid-cohort-preview.tsx`, `grid-cohort-actions.ts`, `grid-cohort-command-storage.ts` — interfejs i trwałe polecenia.

Istniejące punkty wejścia do ograniczonej edycji:

- Worker `images/normalization.py` / istniejące canonical decoder exports, `CanonicalSourceLoader` i `pipeline_store.project_source_metadata` — zachowanie algorytmu, cache, lease i dotychczasowego API pozostaje zgodne. Dokładną aktualną lokalizację potwierdzić z mapy przed edycją.
- API `storage/models.py`, `database_roles.py`, `catalog_repository.py`, `game_partition_lifecycle.py`, `game_storage_routing.py`, `schema_readiness.py` — rejestracja encji/current v16/head i exact capability enforcement.
- `storage/grid_reinference_retention.py::{retained_grid_source_link_count,detach_grid_source_links}`, `cleanup_repository.py`, `superseded_import_image_removal_repository.py`, `storage_gc_repository.py`, domenowy `StorageRetentionPolicy` — istniejące preview/detach/artifact/quarantine paths, bez wykonania cleanupu.
- `api/router.py` i rzeczywista istniejąca fabryka zależności po wskazaniu symbolu z mapy; `model-quality-workspace.tsx` jako ograniczone miejsce montowania panelu.
- `packages/admin-api-client/openapi/openapi.json`, generowany klient/eksporty oraz istniejący Admin wrapper — generacja wyłącznie właściwym toolchainem.
- Dokumenty właścicielskie VISION_LAB requirements/architecture, DATA_MODEL, VISION_LAB_EXPORT oraz generowane mapy. Task, plan, stan, Decision Logs, README i posthash1009 pozostają własnością leada.

Proponowane testy: `services/api/tests/test_grid_training_cohort_snapshot.py`, `test_grid_source_identities.py`, `test_grid_training_cohort_requests.py`, `test_grid_training_cohorts_postgres.py`; worker `test_grid_cohort_dataset.py`; klient `grid-training-cohorts-request.test.mjs`; Admin ograniczone `grid-cohort-*.test.mjs` i test interakcji. Drobniejszy podział modułów zgodny z warstwami jest dozwolony po zapisaniu ostatecznego zakresu; nowy niezależny refaktor wymaga odrębnego rozstrzygnięcia.

## Test cases

1. Zdeformowane 24 węzły zachowują dokładne wartości i render; te same cztery rogi z innymi wewnętrznymi węzłami nie dają tego samego targetu. Rzeczywiste approval-only dla pełnej planszy z incomplete source i bez 15 cells kwalifikuje grid-only; screen wymaga pełnej anotacji. Partial/extrapolated/auto-accept i sam judgment nie tworzą etykiety.
2. Guarded geometry_saved, późniejsze approval-only i aktualne provenance zachowują corrected origin. Brak historycznego modelu nie blokuje aktualnej etykiety. Exact receipt/manifest chain, legacy gap, actual manual sibling writer i wcześniejszy approval przechodzą; zmieniony target/source/owner/issues/revert nie przechodzi. Nie usuwamy checksum guards.
3. EXIF 1–8 i None, frame/checksum/cache i zgodne worker exports; all-NULL completion, complete EXIF None, non-NULL mismatch, actual geometry witness, path/reparse/foreign-source odmowa. Brak bajtów i pixel/byte mismatch mają oddzielne powody. Brak fake lease/revision i mutacji geometrii.
4. Minima board/photo/recording, role i wagi 4:1; niezależne nagrania, ancestor TRAIN, cross-game aliases/holds/provider/mapping, whole-recording ochrona mimo wyboru podzbioru. Braki pozostają w preview, nie zmniejszają mianownika i nie stają się PASS.
5. Stable pages/cursor/CAS/hash i bounded memory; zero odczytu niezaznaczonych assetów. Prepare/copy/completion/freeze po utracie odpowiedzi i restarcie, crash publish-before-commit i commit-before-HTTP, corrupt file. Jeden 60 s deadline, drift rollback, brak partial use/protection i brak duplikatów. Rzeczywisty preproof==postproof dla aliasów i wielu rodzin.
6. Mały rzeczywisty PostgreSQL z ograniczoną nonowner runtime rolą: foreign partition/direct private columns/sequences/helpers deny, exact owner/DEFINER/search_path/PUBLIC i brak owner fallback. Reprovision po ALL/default grants, nowy proces, actual 0162→0163 i fresh install/current v16; frozen 0161/v1/0162/v2 pozostają niezmienione. Empty downgrade działa, jakakolwiek historia odmawia; rollback nie otwiera grantów. Mock SQL nie zastępuje real-role testu.
7. Lokalne notices nie odwracają lock order. Unchanged repoint zachowuje kwalifikację; rzeczywiste cofnięcie/zmiana blokuje zależności. Cleanup źródła, cofnięcie oceny i missing snapshot JPEG są odrębne; detach/history/protection bez resurrection. Snapshot copies są widoczne w preview/GC/game lifecycle. Ordinary freeze ma zero report bindings; nonexistent/unrelated report odmawia. Prawdziwy report producer i pełny promotion E2E pozostają obowiązkiem0997, bez fake danych teraz.
8. CPU dataset sprawdza role przed pikselami kontrolnymi, exact SHA/base/preprocessing i 24 węzły; bez importów torch/ORM/AnnotationStore. Stary eksporter i kohorty symboli zachowują kontrakt. UI GET-only reload, durable UUID/body, identyczny retry, stale response game fence, jawne reasons i selected identity completion, bez fikcyjnego quality PASS.

## Verification

Wszystkie poniższe kontrole są planowane. Najpierw czyste reguły, identity/HTTP i worker CPU, następnie mały rzeczywisty runtime/RLS PostgreSQL oraz skoncentrowane testy regresji, Ruff/mypy, klient/UI/interakcje, OpenAPI, DOC/MAP/diff. Każdy skończony proces ma hard timeout do 120 s i własny kontrolowany TEMP/PID. Dłuższe zestawy dzielimy według modułów, nie zwiększamy bez uzasadnienia zakresu. Nie powtarzamy szerokich macierzy614/473 ani benchmarków.

Polecenia uruchamiamy z worktree. Python jest w `D:/game_predicotr/.venv/Scripts/python.exe`; PYTHONPATH jawnie wskazuje API/workera/test_support tego worktree, bez przypadkowego importu głównego checkoutu. Używamy `npm.cmd`, zgodnie z istniejącą polityką PowerShell. Przykłady sprawdzonych istniejących regresji:

```powershell
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_cohorts.py services/api/tests/test_verified_training_datasets.py
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_quality_repoint.py
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_recording_groups.py services/api/tests/test_source_recording_permissions.py services/api/tests/test_source_recording_membership_v2.py
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_image_normalization.py services/worker/tests/test_vision_lab_training_manifest.py services/worker/tests/test_verified_training_dataset.py
npm.cmd run openapi:check
npm.cmd run docs:check
npm.cmd run code-map:check
git diff --check
```

Przed uruchomieniem potwierdzamy aktualne ścieżki testów z mapy i dodajemy dokładne nowe testy z Expected files. Lint i typy obejmują zmienione moduły, a UI istniejące odpowiednie workspace scripts. Aktualne niepowodzenia resetu/SuperGame i poprzednie timeouty pozostają jawne; nie raportujemy pełnego suite PASS. OpenAPI full FAIL nie jest zastępowany sumą niezależnych eksportów PASS.

Rzeczywiste fixture PG wymagają nowego własnego UUID DB/game/role, marker/OID/createdHere, małych danych, oddzielnego owner migratora i ograniczonego runtime, receiptów i potwierdzenia cleanup DB/role/connections/PID/TEMP. Bez operatorDB, globalnego cleanupu i przejmowania obcych zasobów. Istniejąca kopia `D:/game_predictor_backup` pozostaje wystarczającym punktem odniesienia; nie robimy nowego operator backupu.

Po zamrożeniu źródeł i bezpiecznych dowodów audytuje rzeczywisty Claude Code `claude-fable-5-1/high`, tylko do odczytu, brief task/fragment planu/exact diff, limit do 1200 s zgodnie ze zgodą operatora. Jedna runda i jedna korekta; R2 tylko według reguł P0/P1. Raport bez zmian wchodzi do commita. Brak anotacji, rzeczywistego pomiaru, GPU lub operator runu nie daje PASS jakości. Zamknięcie wymaga kryteriów technicznych, braku otwartych P0/P1, Outcome, map/owner docs i osobnego commita.

## Risks / open questions

- Decyzja operatora2026-10-16: zachować historię i zablokować nowe użycie usuniętego źródła. Zależna kwalifikacja i testy są w realizacji. Usunięcie gry zachowuje istniejące partycje/GC bez nowego pełnego archiwum.
- Stary eksporter zachowuje dotychczasową domyślną semantykę; bez treningu.

## Outcome

### Execution phase

- Oczekiwanie na integrację: implementacja, skoncentrowane kontrole, jedna korektaR1 i rzeczywisty R2 PASS zakończone; brak otwartychP0/P1. Commit został utworzony; pełna wersja i hash poniżej. P2-5 przyjęto jako jawne niskie ryzyko testu i przekazano1001. Operator polecił teraz zamianę ról; następne6tasków wykonuje Claude Code, audytuje Codex. TASK-1005 nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: **v1.7.385** / `f0cfa9bdf2deaf0e5abdf7970624bd5575f10dc7`; hash zapisany po utworzeniu, do następnego commita zgodnie z AGENTS; bez scalenia.
- Audit: Claude high R1 REVISE648.089326s, jedna korekta; R2 PASS288.719457s/do1200s, wszystkie uwagiR1 zamknięte, brakP0/P1. P2-5 zaakceptowane jako ryzyko pokrycia, wpisane do1001. Raporty/copieR1/R2 i quality/TASK-0995_RESPONSE_CODEX.md zachowane; brak dalszej pętli.
- Następny krok: przekazanie Claude Code według guides/V3_GRID_FINE_TUNING_ROLE_HANDOFF.md. Claude wykonuje1005, Codex audytuje; bieżąca sesja nie rozpoczyna1005. Dwie jawne zmiany posthash taska i stanu mogą wejść do następnego commita, bez amend.

### Changed

- Zaimplementowano niezależny pion: wspólny kanoniczny decoder, kontrolowane uzupełnianie tożsamości źródeł, jednogrowe kohorty z rolami nagrań, stronicowany preview, sekwencyjne kopie, niezmienny manifest i atomowy freeze rzeczywistego użycia. Backend/OpenAPI/generated klient/wrapper/trwałe polecenia UI i CPU dataset zachowują exact24nodes, sekwencje, pochodzenie i minima. Ochrona kopii korzysta z istniejącego reference-aware GC i wspólnego asset guard. Operator wybrał zachowanie historii z blokadą nowego użycia usuniętego źródła; wybraną regułę wdrożono i sprawdzono.

### Verification results

- Niezależny decoder slice: baseline27 PASS przed zmianą; po ekstrakcji62 PASS, w tym35 nowych przypadków. Ruff7 plików PASS; mypy4 modułów z --follow-imports=silent PASS,86.703s/limit120s; własny PID/TEMP cleanup potwierdzony. Lead zweryfikował SHA/rozmiary7 source/test i10 evidence oraz zarchiwizował dokładny slice. Manifest SHA256:6ec47fc5d900a90f4c0d2e960b7d3a8e7475ab6b26ccbe6958939c12e6da5543. To częściowa kontrola, bez audytu/commita całego0995.
- Częściowy HTTP/UI slice:8 HTTP PASS oraz9 UI/storage/wrapper PASS; scoped lint/typecheck, OpenAPI i generated drift PASS. Dataset CPU15 PASS i odczyt długiej ścieżki w nowym procesie PASS, scoped Ruff/mypy PASS. Lead sprawdził exact SHA/rozmiary i zarchiwizował DATASET2 source/42 evidence oraz HTTP_UI17 source/68 evidence; proof TASK-0995_{DATASET,HTTP_UI}_ROOT_VERIFICATION.json. Manifesty odpowiednio414ef0d37f8ce4ca7897476bdd8e83b41f64184c5c02180c5669280838bca15c i b8cb8e9373d1731976911c4e81c4e1d1b159c59f7be360026ec35ac7fd42da8e. To sprawdzone części, bez audytu/ukończenia całego taska.
- Storage PG06: exact nowy isolated-owned node test_exact_owned_v3_migration_privileges_use_and_read_only_validation PASS;27.344s/60s. Fresh migration, empty down/up, reprovision, actual recording use, read-only validation, RLS i odmowa nonempty downgrade sprawdzone. Własny PID/TEMP cleanup true. Wcześniejsze PG01–05 błędy/timeouty zachowane; sam ten node nie dowodzi pełnego application freeze/dataset.
- Nowszy HTTP/UI V2 po dodaniu nullable facts: exact8 HTTP PASS3.703s z cleanuptrue; UI7/wrapper1 oraz DTO/type/lint/OpenAPI/drift PASS według odrębnych wyników, bez sumowania nakładających się przypadków. Lead zarchiwizował17source/30evidence bez SHA mismatch: TASK-0995_HTTP_UI_V2_ROOT_VERIFICATION.json, manifest4c03693742ebad59c6ea06bf644edc24e3bbccf46cf749bb23ccecb47236efb8. V1 pozostaje historią.
- Core33 CPU PASS, w tym metadata-only facts i materialization/render parity. Stabilna końcowa mypy9 kontrola przerwana po60s bez wyniku, sourceUnchanged=true i cleanuptrue; wcześniejsze42.985/51.203s PASS nie zastępują tego przerwanego finalnego uruchomienia. Te same9 modułów podzielono do skoncentrowanej dalszej kontroli, bez rozszerzania zestawu.
- GC14 nowych CPU PASS; mieszany zestaw24PASS/1FAIL obejmuje również10 legacy PASS i jeden stary os.link WinError5, odtworzony na HEAD. Drugi actual two-connection PG node ma assertionPASS15.53s, lecz raw runner result cleanup_failed18.032s; osobny exact nonce/inode TEMP recovery PASS i DB/role/PID zero. Bez trzeciego PG tylko dla cleanup. Lead zweryfikował8source/40evidence i zarchiwizował manifest196e87d2abbe60ab834e87cc1963b9e7aa0ef4aa5b85d4e7bf3ee0af33d8371e w TASK-0995_GC_ROOT_VERIFICATION.json. Actual full game deletion/source reset E2E nie jest wynikiem tego małego guard testu; CPU receipt-shape ma odrębny zakres.
- Pełny E2E01 raw FAIL63.98s/node,68.06s/process: dojście do ready_to_freeze po20JPEG/120guardedtargets, potem named ServerCursor odrzucił SET. Naprawiono nowy timeout hook zwykłym control cursor na tej samej connection/TX; wyjątek recovery rollback zachowuje pierwotny typed reason. Core36 CPU PASS, zmienione3 moduły Ruff/format/mypy PASS43.297s ze stabilnymi SHA; pozostałe6 modułów miały wcześniej stabilny mypy PASS w rozdzielonych grupach. Przerwany wcześniejszy final9-run pozostaje timeout, bez zastępowania go fikcyjnym PASS.
- E2E02 raw cały node FAIL81.12s/process85.31s, własne DB/role/PID/TEMP zero. Udowodnione milestones:20JPEG,120unikalnych targets/121geometry_saved events, capture/copy4 stron, restricted-runtime freeze COMMIT (checkpoint elapsed62.469s; sama komenda około6.2s), nowa sesja replay/metadata eligible, NOWY PROCES dataset30TRAIN+45VALIDATION+45REGRESSION oraz120 pixel SHA renderów zdeformowanej komórki i exact24nodes. Następny actual mark_grid_issue odmówił SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE; stale-ready/revert nie osiągnięto. Pozytywne milestones nie zmieniają rawwholeFAIL. Dalsza kontrola prerequisite/ujemnego freeze pozostaje w toku, bez obniżania minimów lub fałszowania neural provenance.
- Odrębny mały prerequisite PG02 PASS1test22.69s/process26.688s, własne DB/role/PID/TEMP zero. Na current0163/v16 istniejące backfill/reconcile/counts umożliwiły rzeczywisty public mark_grid_issue. Legalny caseA revert zatwierdzono w transakcji (rewizja3,15 odtworzonych komórek, istniejący status geometry_complete), a nowa sesja potwierdziła exact24nodes. Pierwszy prerequisite PG01 pozostaje FAIL: asercja fixture oczekiwała błędnego literału complete; wykonanie revert w tamtej próbie nie było commitem. Produkcyjnych guardów nie osłabiono. Ostatni pełny E2E używa rzeczywistego revert jako przyczyny stale, bez powtarzania issue/backfill w dużym fixture.
- Ostatni pełny E2E03 PASS1node90.31s/process94.36s, bez timeoutu; własne DB/role/PID/TEMP zero.120targets/121geometry_saved events/20unikalnych JPEG, capture i4 materializacje, restricted freeze COMMIT (6.250s od poprzedniej materializacji), replay i nowy proces dataset30TRAIN+45VALIDATION+45REGRESSION z exact24nodes, sekwencjami oraz renderem zdeformowanej komórki. Druga gotowa kohorta B po rzeczywistym caseA revert COMMIT (rewizja3/15cells, bez backfill/issue) zwróciła humanLabelWithdrawn=true/liveSourceLinked=true i typed GRID_COHORT_LABEL_STALE409. Prywatne actual use/use receipts, freeze receipts i frozen events B pozostały zerowe; cały header i app receipts B były niezmienione. Nie obniżono minimów ani guardów. Poprzednie wholeFAIL pozostają zachowane; jest to PASS tego E2E, nie audytu/całego taska.
- DISTINCT sekwencje przed freeze są strumieniowane yield_per200 przy zachowaniu dotychczasowej kolejności. Zmieniony moduł freeze ma aktualny Ruff/format i scoped mypy PASS44.594s, sourceUnchanged/cleanup=true; wcześniejsze dowody pozostałych modułów zachowano.
- Real1009 canonical approval-only→0995 verified measurement manifest/receipt reader potwierdził human_checked_unchanged/weight1, obok actualmanual human_corrected/weight4; roleNULL/usedfalse nadal unresolved. Actual sourcecleanupA COMMIT zachował frozen payload/Page/JPEG i odłączył live link, runtimeGC nadal widział ref. Te milestones pochodzą z rawretentionPG1/2 FAIL; PG1 przerwał fixture revision0, PG2 istniejący reset RESTRICT pending→review. Wcześniejszy znany reset bug pozostaje poza0995, bez bypass/xfail i bez resetPASS.
- Osobny real full-gameDELETE node PASS26.60s (runner30.454s), DB/role/PID/TEMP zero. Existing lifecycle ukończył89tabel, v16done receipt, absence catalog/route/6cohortpartitions; fresh restrictedGC potwierdził noRefs/known deleted i actual deletion.updated_at anchor, ochronę24h oraz kwalifikację przy testowym+25h. DwaJPEG/page pozostały byte-identyczne, bez uruchamiania fizycznegoGC. Lead zweryfikował nowy1source/14evidence/2linkedmanifests: TASK-0995_GC_V3_ROOT_VERIFICATION.json, SHA d7c772f491b43d2745fb71ddba30043f31d4b2a54c30e33dcbed3179a76296cf. Historyczne V1/V2 oraz rawresetFAIL zachowane.
- Historyczne TestClient sandbox socketpair timeouty, Windows MAX_PATH i pierwsze PG failures pozostają FAIL z osobnymi dowodami naprawy/recovery. Brak whole-task PASS/audytu/commita; polityka nowego użycia po source cleanup została następnie rozstrzygnięta; jej zależna implementacja i testy są w toku.
- Finalny niezależny handoff:77 source/docs i520 evidence, manifest SHA2568ca83fefaf3fc5738cdf915d2a3612fc55ec2d1a5fd32871f175e6625d4d506e. Lead potwierdził SHA/rozmiary wszystkich597 plików i zarchiwizował ich dokładne kopie; proof artifacts/audits/TASK-0995_INDEPENDENT_CORE_ROOT_VERIFICATION.json. Pierwszy pomocniczy root archive copy przerwał Windows MAX_PATH; drugi zachował i zweryfikował już zapisane pliki oraz dokończył archiwum przy użyciu ścieżek rozszerzonych. Nie był to błąd testu aplikacji. Końcowe scoped map/diff checks PASS. Handoff nie jest audytem ani whole-task PASS.
- Po jawnej decyzji operatora: nowy reason SOURCE_REMOVED_NEW_USE_BLOCKED w3 produkcyjnych miejscach i3 testach;4 owner docs opisują wybraną politykę. Aktualne core40PASS/storage18PASS w8.156s, exact zmieniony HTTPcase1PASS3.703s, Ruff/format6 plików PASS, mypy3 produkcyjnych plików PASS57.031s; źródła stabilne i PID/TEMP cleanuptrue. GET daje blocked przy dodatnim source-removed proof również obok unresolved, facts false/null/null; used=false nie blokuje, mapper zachowuje409/savepoint recovery.
- Nie wykonano nowego PG dla wybranego literalnego reason: istniejące minima10TRAIN+5VALIDATION+5REGRESSION poprzedzają wspólny NULL-link guard, więc mały1–2source fixture kończy się MINIMUM_NOT_MET. Nie zmieniono kolejności, minimów, SQLSTATE22023, READ ONLY ani grants; nie fabrykowano pełnych labels i nie powtarzano120target seedu. Nowy literal/common branch i mapper mają focused CPU kontrakty; wcześniejsze real PG/sourcecleanup proofs pozostają dowodami tylko swoich ścieżek. To jawne ograniczenie, nie nowy runtime PG PASS.
- Końcowy manifestV2 artifacts/audits/TASK-0995_FINAL_MANIFEST_V2.json:77source/539evidence, SHA335975fe3961cefe500f3b770c3658864ccbab0035d657cb3f9a457335ef456c. Pierwotne520 deskryptorów dowodów pozostały niezmienione; root-owned14 dokumentów są poza manifestem wykonawcy. Bieżący audyt obejmie również ich właściwy diff i przekazanie ról.
- Korekta R1 zamrożona:7 zmienionych source/23 nowych evidence, pełne77 bieżących source SHA i niezmienione wcześniejsze539 dowodów. Manifest d55559b0781412e67da178b41938a65d633a31392db8ccdedd4bb78caac6b1dc; rzeczywisty delta vs root R1 archive d286330479cab695b76bf046b6543eca5f62370141a41e90b65fd0e3dc4d5edc. P1 ma real child crash73 po fsync i guarded scan/24h/ref/25h regression; P2 trigger/mapper/current-own target poprawiono. CPU01wholeFAIL75PASS7FAIL11.438s (nowy fixture bez expectedSHA), po wyłącznie fixture poprawce exact7CPU02PASS4.938s. Przechodzące części CPU01: GC API10/core41/storage19/worker5. Ruff/format8PASS, mypy3production57.454s i migration1~9sPASS, MAP/diffPASS, własne PID/TEMPzero. Bez ponownego PG/E2E/HTTP; formalne potwierdzenie zamknięcia uwag wymaga R2. Szczegóły w quality/TASK-0995_RESPONSE_CODEX.md.
- Docs:check po technicznym doprecyzowaniu GC PASS:553 wpisy/592 anchor links,49 aktywnych tasków,10 done; indeks90867B, stan97807B. Kontrole końcowe i audyt całego0995 nadal planowane; brak wyniku jakości modelu.

- R2 PASS288.719457s, reportSHAc17dfb4b1a4bcfd63a121fb6d051310fc1c266b5054ee8ab2cb2cfb2989e3ba4; root potwierdził93pinned files/562evidence bez zmian. BrakP0/P1; wszystkie5uwagR1 zamknięte. P2-5 jawnie zaakceptowane: stary success/replay testglob*.staged nie sprawdza nowych*.part; runtimefinally unchanged i actualhardcrash/guardedscan regresjaPASS. TASK-1001 ma uzupełnić asercję; bez kolejnej korekty/audytu. DOC i finalstagingchecks opisane w closure receipts.

### Not completed

- Integracja, migracje operatora, rzeczywiste kohorty/anotacje, trening i ocena modelu; nie były wykonaniem tego taska. Pełny panel po nazwach pozostaje w1000. Known layout-reset FK bug poza0995, bez resetPASS. Przyjęte P2-5 wymaga uzupełnienia asercji w1001. Bez nowych usług, backupu, fizycznegoGC, aktywacji lub push.

### Documentation updates

- Zaktualizowano task, plan, D-548/D-556, stan, dokumenty właścicielskie i mapy kodu. TASK-0997 doprecyzowuje zgodny kontrakt przyszłego raportu i podwyższony audyt dowodów; TASK-1000 wymaga wyboru po nazwach w finalnym interfejsie operatora. Te zmiany nie implementują przyszłych tasków. Raport niezależnego przekazania: artifacts/audits/TASK-0995_INDEPENDENT_CORE_HANDOFF.md.

### Recommended next task

- Ukończyć zależny kontrakt/kod/testy i audyt/commit TASK-0995. Przekazać TASK-1005 Claude Code jako wykonawcy, z Codex jako audytorem według nowego sterowania operatora. Bez automatycznego rzeczywistego treningu, GPU lub integracji.
