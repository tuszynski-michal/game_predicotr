---
title: TASK-0249 board cell geometry, stable review queue and shared Reviewer
status: in_progress
release: '0.6'
last_updated: 2026-08-20
---

# TASK-0249 — Geometria komórek, stabilna kolejka i wspólny Reviewer

## Status

`in_progress`

TASK 1, czyli stabilizacja baseline'u i decyzji architektonicznych, TASK 2,
czyli kontrakt i rzeczywisty corpus geometrii komórek, TASK 3, czyli nieaktywny
automatyczny estymator v19, TASK 4, czyli checkpoint 100 stron, oraz TASK 5,
czyli nieaktywny source-direct cropper v19, są ukończone. Pipeline, edytor, API
i UI opisane poniżej nie zostały jeszcze rozpoczęte.

## Goal

Zbudować trzy rozdzielne, etapowo odbierane piony:

1. niezawodną geometrię siatki symboli 5 × 3 na każdej z dziewięciu plansz,
2. niezmienną kolejkę zatwierdzania odporną na duże importy i równoległe osoby,
3. współdzielony lifecycle lokalnego i zdalnego Reviewera dla kilku importów.

Pierwszy pion ma poprawić geometrię przed dalszym strojeniem rozpoznawania
symboli. Pozostałe piony mają umożliwić jednoczesne zatwierdzanie 2–3 różnych
importów bez błędów kursora, blokad plików i wielokrotnego uruchamiania tunelu.

## Context

- Strony `seq_*` mają poświadczone numery i kompletną geometrię 3 × 3, ale
  lokalizacja całej planszy nie gwarantuje, że 15 cropów obejmuje symbole.
- Zdjęcia są wykonywane pod różnymi kątami. Prostokątna płaszczyzna planszy
  może być trapezem lub rombem w obrazie źródłowym; wymuszanie tam
  prostopadłości zniekształciłoby prawidłową perspektywę.
- Bieżąca operacyjna kolejka może zależeć od statusu albo numeru sekwencji.
  Przy około 19 745 elementach zmiana stanu powoduje
  `IMAGE_REVIEW_CURSOR_STALE` po zatwierdzeniu poprawnie wyświetlonej pozycji.
- Lifecycle ingressu używa jednego globalnego stanu i wspólnych logów, lecz
  zatrzymanie jest związane z pojedynczą sesją. Równoległe uruchomienia mogą
  blokować `remote-reviewer-cloudflared.log` albo próbować uruchamiać ponownie
  ten sam proces.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/tasks/0149-pending-only-reinference-and-import-pinning.md`
- `ai_docs/tasks/0150-iterative-supervised-loop-acceptance.md`

## Baseline i izolacja zmian — TASK 1

Punktem bazowym jest commit `3595a32` (`v0.6.59`). Migracja
`0048_image_page_geometry_overrides` jest jedyną głową łańcucha i następuje po
`0047_pending_symbol_reinference_job`.

Przed rozpoczęciem TASK-0249 drzewo robocze zawierało niezacommitowane zmiany,
które nie należą do tego zadania i nie mogą wejść do jego przyszłych commitów:

- korektę fallbackowego ładowania anchorów importu w
  `production_workflow.py`, jej test oraz dopiski w `CURRENT_STATE.md` i
  TASK-0149,
- poprawki kontrolera procesów Windows w `manage_worker_lanes.ps1`,
  `windows_process_environment.ps1` oraz TASK-0211,
- niezwiązaną zmianę `apps/admin/next-env.d.ts`.

Zmiany są zachowane w miejscu i nie zostały cofnięte, dokończone ani
przypisane do TASK-0249. Numer kolejnego commita `v0.6.*` nie zostanie
przydzielony temu zadaniu, dopóki właściciel nie rozstrzygnie i nie odizoluje
tego wcześniejszego stanu.

Zaakceptowane decyzje baseline'u:

- D-204 — geometria komórek v19 i semantyka ręcznych narożników,
- D-205 — niezmienna kolejność źródłowa oraz first-save-wins,
- D-206 — jedno przypisanie na import i współdzielony Reviewer/Quick Tunnel.

## Invarianty wspólne

- `sequence_number` pozostaje elementem domeny i nie może być wyliczany po
  niejednoznacznym przypisaniu pozycji.
- Nazwa `seq_*` pozostaje poświadczonym źródłem numerów; OCR numerów nie wraca.
- Decyzje `accepted/corrected/rejected` i kanoniczny właściciel numeru są
  chronione przed ponownym pipeline'em i równoległym zapisem.
- Historyczne manifesty, `PageGeometryManifestV1` i cropper v18 pozostają
  odtwarzalne; nowa geometria otrzymuje nowe wersje i fingerprinty.
- Obrazy nie trafiają jako BLOB do głównych tabel domenowych.
- Zmiany schematu powstają wyłącznie przez Alembic, a typy Admina i Reviewera
  wynikają z backendowego OpenAPI.
- Nie dodajemy Redis/Celery, mikroserwisu, chmury ani osobnego tunelu dla każdej
  sesji.
- Wszystkie operacje procesowe muszą być trwałe po restarcie, ograniczone
  timeoutem i bezpieczne dla Windows.

## Pion A — geometria komórek v19

### Zakres przyszłej implementacji

1. [ukończone w TASK 2] Przygotować rzeczywisty corpus i kontrakt
   `BoardCellGeometryManifestV1`, oddzielony od geometrii dziewięciu plansz na
   stronie.
2. [ukończone w TASK 3] Zaimplementować
   `board-cell-geometry-v19-multi-point-source-direct-v1`:
   globalne kandydaty centrów symboli, wspólne przypisanie 5 × 3 i guarded
   RANSAC z co najmniej 10 wiarygodnymi punktami, 9 inlierami, pokryciem
   wszystkich wierszy i kolumn oraz wersjonowanym residualem.
3. [ukończone w TASK 3] Zachować perspektywę obrazu źródłowego. Prostokątność obowiązuje w
   płaszczyźnie kanonicznej, a nie jako prostopadłość boków w JPEG-u.
4. [ukończone w TASK 5] Wyprowadzać 15 komórek i padding bezpośrednio z
   oryginału w jednym resamplingu. Nie materializować pośrednio rozciągniętej
   planszy.
5. Zbudować edytor ręczny, w którym cztery główne uchwyty oznaczają granice
   siatki 5 × 3. Cztery dodatkowe uchwyty krawędziowe są pochodne i nie zmieniają
   semantyki zapisu. Podgląd musi pokazywać wszystkie 15 finalnych cropów.
6. Zapisywać ręczną korektę append-only z checksumą źródła, pozycji, wersji i
   aktora. Ten sam walidator ma obsługiwać automat, preview i zapis.
7. Po zaliczeniu bramki udostępnić pending-only recrop. Nie otwierać ani nie
   modyfikować elementów rozwiązanych i nie uruchamiać ponownie OCR/discovery.

### Outcome TASK 2 — kontrakt i corpus

- Dodano ścisły `BoardCellGeometryManifestV1` z kanonicznymi bajtami,
  content-addressed zapisem oraz walidacją kompletności, kolejności i
  proweniencji.
- `latticeBoundsQuad` ma semantykę D-204, a 15 quadów komórek jest
  deterministycznie wyprowadzanych w kolejności row-major. Trapez perspektywiczny
  jest poprawny; crossed, out-of-bounds albo niespójny quad jest odrzucany.
- Evidence automatyczne ma już fail-closed kontrakt dla 10 centrów, 9 inlierów
  i pełnego coverage 3 × 5. TASK 2 nie tworzy jeszcze tych obserwacji.
- Descriptor rzeczywistego corpusu przypina 27 zaakceptowanych geometrii
  `cell-grid-golden-v1`, po trzy na każdą pozycję, z dwóch grup źródłowych.
  Wszystkie źródłowe JPEG-i, manifest i golden przechodzą kontrolę checksumy.
- Źródłowe JPEG-i pozostają lokalnymi, ignorowanymi przez Git danymi. Test
  kontraktu zawsze sprawdza przypięte manifesty, a osobna bramka sprawdza bajty
  i wymiary wszystkich 27 JPEG-ów, gdy corpus jest dostępny w checkoutcie.
- Fingerprint wyprowadzonego corpusu to
  `45a82dbb0f86ca62646e1d680f2a0d9ea78a62f38b1d24b72be2ce50764aeb25`.
- `board-cell-crops-v18-source-direct-validated-v1` pozostaje aktywny i nie
  został zmieniony ani przepięty na nowy kontrakt.

### Verification TASK 2

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_board_cell_geometry_contract.py -q
.\.venv\Scripts\ruff.exe check services/worker/src/game_predictor_worker/images/board_cell_geometry_contract.py services/worker/tests/test_board_cell_geometry_contract.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/board_cell_geometry_contract.py
```

### Acceptance criteria TASK 2

- [x] Kontrakt komórek jest niezależny od `PageGeometryManifestV1`.
- [x] Semantyka czterech narożników i współrzędnych źródłowych jest jawna.
- [x] Manifest zawiera dokładnie 15 pochodnych komórek w row-major.
- [x] Automatyczne evidence nie przechodzi bez 10 centrów, 9 inlierów i pełnego
      coverage; ręczne evidence wymaga checksumy decyzji.
- [x] Corpus ma 27 zaakceptowanych plansz, 9 pozycji × 3, z dwóch grup
      źródłowych.
- [x] Checksumy manifestów, JPEG-ów i wynikowego corpusu są weryfikowane.
- [x] Perspektywa jest dozwolona bez wymuszania prostopadłości w źródle.
- [x] Cropper v18 i pipeline produkcyjny pozostają bez zmian.

### Outcome TASK 3 — automatyczny estymator v19

- Dodano deterministyczny locator ograniczonych hipotez, który korzysta z
  globalnego zbioru jasnych komponentów, ale nie wykonuje kosztownego skanu
  wszystkich półpikselowych startów i odstępów historycznego v13.
- Kandydaci są wspólnie przypisywani do 5 × 3, jeden komponent na slot. Dopiero
  wynik z co najmniej 10 przypisaniami jest refinowany i przekazywany do
  guarded RANSAC.
- Estymator zachowuje progi 10 wiarygodnych centrów, 9 inlierów, pełne pokrycie
  wierszy i kolumn oraz P95 residualu do 10 px. Wersje locatora, homografii i
  progów trafiają do automatycznego evidence.
- Homografia ideal-to-analysis jest składana z odwrotnością transformu
  source-to-analysis. `latticeBoundsQuad` i 15 komórek powstają bezpośrednio w
  pikselach oryginalnego JPEG-a i przechodzą ten sam walidator kontraktu TASK 2.
- Rzeczywista regresja przepuszcza 25 z 27 zaakceptowanych plansz. Maksymalny
  średni błąd narożników wynosi 6,25 px; dwa przypadki z okluzją pozostają
  fail-closed przy odpowiednio 8 inlierach i 9 globalnych przypisaniach.
- Estymator nie jest podłączony do produkcyjnego pipeline'u. Nie tworzy cropów,
  nie zmienia v18, modeli symboli, bazy, API, Admina ani Reviewera.

### Verification TASK 3

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_board_cell_geometry_estimator.py services/worker/tests/test_board_cell_geometry_contract.py services/worker/tests/test_global_symbol_lattice.py services/worker/tests/test_symbol_lattice_homography.py -q
.\.venv\Scripts\ruff.exe check services/worker/src/game_predictor_worker/images/board_cell_geometry_estimator.py services/worker/src/game_predictor_worker/images/board_cell_geometry_contract.py services/worker/src/game_predictor_worker/images/global_symbol_lattice.py services/worker/tests/test_board_cell_geometry_estimator.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/board_cell_geometry_estimator.py services/worker/src/game_predictor_worker/images/board_cell_geometry_contract.py services/worker/src/game_predictor_worker/images/global_symbol_lattice.py
```

### Acceptance criteria TASK 3

- [x] Locator rozpoczyna od globalnego zbioru kandydatów i wspólnego
      przypisania 5 × 3.
- [x] Niepełne przypisanie, mniej niż 10 centrów, mniej niż 9 inlierów albo brak
      pełnego coverage kończy się bez geometrii i evidence produkcyjnego.
- [x] Progi i wersje są jawne oraz wchodzą do evidence.
- [x] Perspektywa źródła jest zachowana; test obejmuje dwa różne trapezy bez
      zmiany row-major.
- [x] Wynik ma dokładnie 15 komórek i przechodzi ścisły kontrakt manifestu.
- [x] Rzeczywisty corpus przechodzi 25/27, a dwa okludowane wyjątki są
      przypiętymi wynikami fail-closed.
- [x] Pipeline, cropper v18, baza, API i UI pozostają bez zmian.

### Outcome TASK 4 — checkpoint 100 stron

- Dodano read-only audyt `board-cell-geometry-v19-real-page-audit-v1`, który
  wybiera zarejestrowane strony deterministycznym rankingiem SHA-256 niezależnym
  od kolejności pól manifestu.
- Każdy JPEG i jego bezpieczna ścieżka względna są sprawdzane względem manifestu.
  Zakres `seq_*` musi poświadczać dokładnie dziewięć plansz, a każda strona musi
  mieć dziewięć quadów.
- Content-addressed raport zapisuje próbkę, progi, wyniki wszystkich plansz i
  powody fallbacków. Renderer tworzy 100 pełnych nakładek oraz 25 arkuszy po
  cztery strony.
- Na próbce 100 stron/900 plansz estymator utworzył 888 geometrii i 12 razy
  zakończył fail-closed. Ręczny audyt zaakceptował wszystkie wyemitowane
  geometrie: zero przesunięć o wiersz/kolumnę, zero symboli poza komórką i zero
  fałszywych sukcesów.
- Raport ma checksumę
  `320c9b1089b1481e8e4eea71c955eaf796c61554391783d2ac34020aa2421691`, a
  protokół znajduje się w
  `ai_docs/quality/board-cell-geometry-v19-100-page-audit.md`.
- TASK 4 nie generuje cropów, nie aktywuje estymatora i nie zmienia pipeline'u,
  v18, bazy, API, Admina ani Reviewera.

### Verification TASK 4

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_board_cell_geometry_audit.py services/worker/tests/test_board_cell_geometry_estimator.py services/worker/tests/test_board_cell_geometry_contract.py -q
.\.venv\Scripts\ruff.exe check services/worker/src/game_predictor_worker/images/board_cell_geometry_audit.py services/worker/tests/test_board_cell_geometry_audit.py scripts/audit_board_cell_geometry_v19.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/board_cell_geometry_audit.py scripts/audit_board_cell_geometry_v19.py
```

### Acceptance criteria TASK 4

- [x] Próbka 100 stron jest deterministyczna i niezależna od kolejności wpisów.
- [x] Audyt obejmuje wszystkie 900 plansz i przypina manifest, estymator i progi.
- [x] Źródła z dryfem checksumy, niebezpieczną ścieżką, złym `seq_*` albo
      niepełną geometrią strony są odrzucane.
- [x] Każda wyemitowana geometria ma 15 source-space komórek albo kończy się
      kontrolowanym fallbackiem bez komórek.
- [x] Ręczny audyt 100 stron wykazał zero przesunięć i symboli poza komórką.
- [x] Raport jest content-addressed i odtwarzalny; bezwzględna ścieżka źródła
      nie trafia do dokumentu.
- [x] Pipeline, cropper v18, baza, API i UI pozostają bez zmian.

### Outcome TASK 5 — source-direct cropper v19

- Dodano nieaktywny
  `board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1`, który
  przyjmuje pojedynczy zwalidowany `BoardCellGeometryEntry` i źródłowy obraz
  RGB o wymiarach przypiętych w manifeście.
- Stały padding ma osobną wersję i oznacza inset `10 px` w kanonicznym slocie
  `100 × 100`. Płaszczyzna kanoniczna służy wyłącznie do projekcji granic;
  cropper nie materializuje planszy `500 × 300`.
- Przed pierwszą operacją rastrową walidowany jest komplet 15 komórek,
  row-major, zgodność z `latticeBoundsQuad`, evidence oraz pełne położenie
  padded quadów w źródle. Błąd dowolnej komórki daje jeden kontrolowany
  `needs_review` bez częściowego wyniku.
- Każdy finalny crop powstaje przez dokładnie jedno `warpPerspective`
  bezpośrednio z oryginalnego RGB do przypiętego rozmiaru wejścia modelu. Nie ma
  pośredniego `resize`, border replication ani syntetycznego uzupełniania.
- Wersja, geometria, padding, interpolacja, polityka brzegu i rozmiar wejścia
  wchodzą do fingerprintu. Dla aktywnego rozmiaru modelu `64 × 64` fingerprint
  wynosi
  `49146bca0f232a8d8e5e744811577b9f9d01a3cf791d31894775dfb5a677195d`.
- Rzeczywisty corpus TASK 2 przechodzi `27/27` plansz i tworzy `405/405`
  kompletnych cropów. Cropper v18 i produkcyjny pipeline pozostają bez zmian.

### Verification TASK 5

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_board_cell_geometry_crops.py services/worker/tests/test_board_cell_geometry_contract.py services/worker/tests/test_board_cell_geometry_estimator.py -q
.\.venv\Scripts\ruff.exe check services/worker/src/game_predictor_worker/images/__init__.py services/worker/src/game_predictor_worker/images/board_cell_geometry_crops.py services/worker/tests/test_board_cell_geometry_crops.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/__init__.py services/worker/src/game_predictor_worker/images/board_cell_geometry_crops.py services/worker/tests/test_board_cell_geometry_crops.py
```

### Acceptance criteria TASK 5

- [x] Każda zaakceptowana plansza daje dokładnie 15 cropów w row-major.
- [x] Każdy crop jest projektowany z obrazu źródłowego w jednym resamplingu.
- [x] Nie powstaje pośredni raster planszy ani drugi resize finalnej komórki.
- [x] Padding `10/100` i rozmiar wyjścia są jawne oraz objęte fingerprintem.
- [x] Niezgodna geometria, evidence, wymiary albo support kończą się bez
      częściowych cropów.
- [x] Rzeczywisty corpus `27/27` tworzy komplet `405` cropów.
- [x] Pipeline, cropper v18, modele symboli, baza, API i UI pozostają bez zmian.

### Kryteria odbioru pionu

- corpus obejmuje różne kąty, częściowe zasłonięcia i znane błędy v18,
- wynik nie przechodzi bez kompletu 3 × 5 i zweryfikowanego pochodzenia,
- 100 losowych stron rzeczywistego importu przechodzi ręczny audyt bez cropu
  przesuniętego o wiersz/kolumnę i bez symbolu wypadającego poza komórkę,
- automat i ręczna korekta dają tę samą kolejność row-major,
- zmiana kąta źródła zmienia quady, ale nie numery ani kolejność,
- pending-only recrop zachowuje checksumy wszystkich rozstrzygniętych decyzji,
- model i katalog symboli nie są zmieniane przed osobnym odbiorem geometrii.

## Pion B — stabilna kolejka Reviewera

### Zakres przyszłej implementacji

1. Dodać trwałą projekcję kolejki importu i stan liczników z niezmiennym kluczem
   `(source_order_index, position_index, review_item_id)` oraz `queueVersion`.
2. Zmienić listowanie, keyset cursor, wybór pierwszej pending, poprzedni/następny
   i resume tak, aby używały dokładnie tego samego klucza.
3. Zaimplementować transakcyjne first-save-wins dla
   `game_id + sequence_number`. Przegrane oczekujące wystąpienia oznaczać jako
   `superseded`, zachowując źródło i audyt.
4. Odróżnić rzeczywiście nieaktualną komendę elementu od prawidłowej decyzji,
   po której zmieniły się liczniki. Sama zmiana sąsiedniego elementu nie może
   unieważniać kursora bieżącej pozycji.
5. Dostosować Reviewer do małego, ograniczonego bufora
   `previous/current/next two`, bez ładowania całych 19 745 pozycji do pamięci.

### Kryteria odbioru pionu

- kolejność pozycji jest identyczna przed i po ich zatwierdzeniu,
- reload i wznowienie wybierają pierwszą nierozwiązaną pozycję w kolejności
  źródłowej, a lewa strzałka może wrócić do zapisanej pozycji,
- zatwierdzanie importu około 19 745 plansz nie daje
  `IMAGE_REVIEW_CURSOR_STALE` wyłącznie wskutek zmiany liczników,
- dwie równoległe decyzje tego samego numeru tworzą jednego kanonicznego
  właściciela; przegrany element jest kontrolowanie `superseded`,
- liczniki wszystkich/pending/zakończonych są zgodne po restarcie i konkurencji.

## Pion C — wiele przypisań i współdzielony Reviewer

### Zakres przyszłej implementacji

1. Dodać `reviewer_work_assignments`: najwyżej jedno aktywne przypisanie na
   import, typ local/online, lease/heartbeat, scope i historia zamknięcia.
2. Rozdzielić lifecycle przypisania/sesji od lifecycle'u procesu Reviewera i
   Quick Tunnel. Jeden proces i URL obsługują wszystkie aktywne scope'y.
3. Serializować `ensure-running/status/stop-if-unused` między procesami Windows
   przez mutex/lock oraz atomowy stan zawierający PID, start time, executable i
   instance id. Każda próba startu ma unikalne logi, a publikacja stanu następuje
   dopiero po health checku.
4. Ograniczyć online do trzech różnych importów. Zatrzymanie jednego
   udostępnienia unieważnia tylko jego sesję; tunel jest zatrzymywany dopiero,
   gdy nie istnieje inne aktywne online assignment.
5. Przebudować sekcję Admina: select gotowego importu, statystyki zakresu,
   `Otwórz lokalnie` albo `Utwórz link online`, status i niezależne zatrzymanie.
   Lista nie pokazuje kodu, tokenu ani sekretu po utworzeniu sesji.
6. Zachować jeden build produkcyjny Reviewera, same-origin allowlist proxy,
   loopback-only lokalny dostęp i istniejące ograniczenia Quick Tunnel.

### Kryteria odbioru pionu

- dwa lub trzy różne importy mogą być zatwierdzane online równolegle, a kolejny
  import lokalnie, bez dodatkowego procesu Reviewera albo tunelu,
- równoległe kliknięcia startu są idempotentne i nie blokują wspólnego pliku
  logu,
- zatrzymanie jednego linku nie przerywa pozostałych; ostatni stop zamyka tunel,
- restart API lub Admina odzyskuje przypisania i zdrowy proces bez duplikatu,
- publiczny URL nie udostępnia Admina, niescoped API, stagingów ani sekretów,
- zimny start ma ograniczony czas, a istniejący zdrowy ingress zwraca link bez
  ponownego uruchamiania Cloudflare.

## Konflikty z bieżącą implementacją

- `PageGeometryManifestV1` opisuje dziewięć quadów plansz, ale nie zastępuje
  osobnej geometrii 15 komórek; v18 nadal jest aktywnym cropperem.
- Canonical review listuje i stronicuje po `sequence_number`, podczas gdy nowy
  invariant wymaga kolejności źródłowej. Zmiana wymaga migracji i kontraktu, nie
  samego sortowania w UI.
- Obecny stop ingressu jest globalny, a skrypt startowy korzysta ze wspólnych
  ścieżek stanu i logów. Nie wolno rozszerzać równoległości przez uruchamianie
  kolejnych kopii tych samych skryptów.
- TASK-0149 wyklucza recrop i geometrię. Prace v19 muszą pozostać w TASK-0249;
  TASK-0149 może konsumować nową rewizję dopiero po jej niezależnym odbiorze.

Konflikty są jedynie odnotowane w TASK 1. Ich implementacyjne rozwiązanie
należy do późniejszych etapów i nie zostało rozpoczęte.

## Out of scope bieżącego TASK 1

- zmiany pipeline'u, croppera, workera, modeli i progów geometrii,
- migracje nowych manifestów, kolejki i assignments,
- zmiany endpointów, OpenAPI, Admina, Reviewera i skryptów ingressu,
- ponowny import, pending-only recrop i trening symboli,
- refaktory niezwiązane z baseline'em oraz porządkowanie wcześniejszego dirty
  worktree.

## Verification TASK 1

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_migration_baseline.py -q
.\.venv\Scripts\ruff.exe check services/api/tests/test_migration_baseline.py
git diff --check
git status --short
```

## Acceptance criteria TASK 1

- [x] Oryginalny plan jest reprezentowany przez trzy oddzielne piony oraz ich
      invarianty i bramki.
- [x] D-204–D-206 rozstrzygają semantykę v19, kolejność/konkurencję review i
      współdzielony lifecycle Reviewera.
- [x] `0048_image_page_geometry_overrides` jest jedyną oczekiwaną głową testu
      migracji, a test sprawdza jej rodzica `0047`.
- [x] Wcześniejsze niezacommitowane zmiany są jawnie wskazane i wykluczone.
- [x] TASK 1 nie zmienia runtime, API, schematu domenowego ani UI.
- [x] Numer następnego commita nie został przypisany przed rozstrzygnięciem
      wcześniejszych zmian.

## Kolejność i checkpointy dalszych prac

1. Kontrakt, corpus i automatyczny estymator v19 są ukończone.
2. **Checkpoint geometrii:** audyt 100 stron przed edytorem i recropem jest
   ukończony w TASK 4.
3. Następnie ręczna korekta, manifest i pending-only recrop.
4. Niezależnie po baseline można rozpocząć projekcję stabilnej kolejki albo
   trwałe assignments, lecz zmiany kontraktu każdej z nich mają osobny commit.
5. **Checkpoint konkurencji:** testy SQL/API first-save-wins przed integracją UI.
6. **Checkpoint bezpieczeństwa:** lifecycle jednego shared ingressu i model
   zagrożeń przed udostępnieniem wielu linków w Adminie.
7. Końcowy E2E łączy trzy piony dopiero po ich osobnym odbiorze.

## Outcome

TASK 1 ustabilizował baseline dokumentacyjny i test głowy migracji. TASK 2 dodał
ścisły kontrakt oraz zweryfikowany rzeczywisty corpus. TASK 3 dodał
deterministyczny, fail-closed estymator v19 bez aktywowania go w pipeline. TASK 4
zaliczył deterministyczny checkpoint 100 stron bez fałszywego sukcesu. Edytor i
pozostały runtime pozostają otwarte i wymagają osobnych poleceń dla kolejnych
numerów z zaakceptowanego breakdownu.
