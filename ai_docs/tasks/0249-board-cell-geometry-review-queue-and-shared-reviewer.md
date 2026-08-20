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
czyli nieaktywny source-direct cropper v19, oraz TASK 6, czyli ręczny edytor i
read-only podgląd 15 finalnych cropów v19, są ukończone. TASK 7, czyli
append-only zapis ręcznej geometrii v19, oraz TASK 8, czyli jawny pending-only
recrop na zaakceptowanym v19, również są ukończone. TASK 9 dodał trwałą
projekcję topologii kolejki, liczniki i `queueVersion`, TASK 10 przepiął na nią
listowanie, TASK 11 dodał transakcyjne first-save-wins oraz audyt `superseded`,
a TASK 12 rozdzielił konflikt rewizji itemu od zmian liczników. TASK 13 dodał
bounded bufor `previous/current/next two`. Pełny produkcyjny pipeline importu
pozostaje na historycznym v18. TASK 14–17 zbudowały trwałe assignments, osobne
scoped sesje, bezpieczny lifecycle procesu Windows, limit trzech prac online i
`stop-if-unused`. TASK 18 wystawił kontrakt HTTP i przebudował sekcję Admina.

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
5. [ukończone w TASK 6] Zbudować edytor ręczny, w którym cztery główne uchwyty oznaczają granice
   siatki 5 × 3. Cztery dodatkowe uchwyty krawędziowe są pochodne i nie zmieniają
   semantyki zapisu. Podgląd musi pokazywać wszystkie 15 finalnych cropów.
6. [ukończone w TASK 7] Zapisywać ręczną korektę append-only z checksumą
   źródła, pozycji, wersji i aktora. Ten sam walidator ma obsługiwać automat,
   preview i zapis.
7. [ukończone w TASK 8] Po zaliczeniu bramki udostępnić pending-only recrop.
   Nie otwierać ani nie modyfikować elementów rozwiązanych i nie uruchamiać
   ponownie OCR/discovery.

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

### Outcome TASK 6 — ręczny edytor i podgląd v19

- Istniejący modal Reviewera używa semantyki D-204: cztery numerowane uchwyty
  oznaczają `latticeBoundsQuad`, czyli zewnętrzne granice siatki symboli 5 × 3,
  a nie czerwoną ramkę planszy.
- Cztery szare uchwyty krawędziowe są wyprowadzane projektowo z tych samych
  narożników. Nie uczestniczą w hit-testingu i nie trafiają do komendy API.
- Overlay 5 × 3 jest liczony przez transform projektowy tego samego quadu,
  zamiast liniowej interpolacji, więc odpowiada granicom używanym przez
  source-direct cropper.
- Read-only endpoint preview używa
  `manual-board-cell-geometry-v19-preview-v1` i nieaktywnego croppera v19.
  Zwracany PNG jest contact sheetem `5 × 3` złożonym z dokładnie 15 finalnych
  cropów `64 × 64`, a nie rasterem pośredniej planszy `500 × 300`.
- Preview ponownie sprawdza checksumę źródła, rewizje, jednoznaczny numer,
  evidence, komplet pochodnych cell quadów i pełny source support. Nie zapisuje
  plików, rewizji ani BLOB-ów.
- Przycisk historycznego zapisu v1 został odłączony od edytora v19, aby nowe
  narożniki nie zostały zinterpretowane jako narożniki czerwonej ramki. Jego
  zastąpienie append-only zapisem v19 należy wyłącznie do TASK 7.

### Verification TASK 6

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_manual_board_cell_geometry_preview.py services/worker/tests/test_board_cell_geometry_crops.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_operational_image_reviews.py -q
npm.cmd test --workspace @game-predictor/reviewer
npm.cmd run openapi:check
```

### Acceptance criteria TASK 6

- [x] Cztery główne uchwyty mają semantykę granic siatki symboli 5 × 3.
- [x] Cztery dodatkowe uchwyty są pochodne i nie zmieniają payloadu.
- [x] Overlay zachowuje perspektywę i korzysta z tego samego quadu co cropper.
- [x] Podgląd pokazuje dokładnie 15 finalnych source-direct cropów row-major.
- [x] Preview używa walidacji v19 i nie tworzy plików ani rewizji.
- [x] Historyczny zapis nie może zapisać narożników o nowej semantyce.
- [x] Cropper v18, pipeline, modele symboli, baza i decyzje review pozostają bez
      zmian.

### Outcome TASK 7 — append-only zapis ręcznej geometrii v19

- Endpoint zapisu nie używa już aktywnie historycznego
  `manual-review-geometry-v1`. Preview i zapis przechodzą przez wspólny adapter
  `manual-board-cell-geometry-v19-append-only-v1`, ten sam kontrakt
  `BoardCellGeometryEntry` oraz source-direct cropper v19.
- Decyzja ręczna ma kanoniczną checksumę wiążącą checksumę i tożsamość źródła,
  `source_order_index`, `position_index`, numer planszy, cztery granice
  `latticeBoundsQuad`, wersję geometrii, wersję i fingerprint croppera,
  oczekiwane rewizje, checksumę komendy oraz aktora.
- Zapis materializuje dokładnie 15 finalnych PNG `64 × 64` w niezmiennym,
  rewizjonowanym namespace. Nie tworzy planszy `500 × 300`, nie wykonuje
  dodatkowego resamplingu i nie nadpisuje plików wcześniejszej rewizji.
- `image_board_geometry_revisions` pozostaje append-only. JSON geometrii
  zachowuje pełną proweniencję, 15 source/padded quadów oraz checksumy cropów;
  odpowiedź API ujawnia `decisionChecksumSha256`, z `null` wyłącznie dla
  historycznych rewizji v1.
- Reviewer pozwala zapisać tylko podgląd odpowiadający bieżącym narożnikom,
  blokuje podwójny submit, aktualizuje item odpowiedzią backendu i pozostaje na
  tej samej planszy ponownie otwartej do weryfikacji symboli.
- Historyczny adapter v1 i cropper v18 pozostają odtwarzalne. TASK 7 nie
  aktywuje automatycznego estymatora v19, nie uruchamia pending-only recropu i
  nie zmienia modeli symboli.

### Verification TASK 7

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_manual_board_cell_geometry_preview.py services/worker/tests/test_board_cell_geometry_crops.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_operational_image_reviews.py services/api/tests/test_openapi_contract.py services/api/tests/test_local_admin_security.py -q
npm.cmd test --workspace @game-predictor/reviewer
npm.cmd test --workspace @game-predictor/admin-api-client
npm.cmd run lint --workspace @game-predictor/reviewer
npm.cmd run typecheck --workspace @game-predictor/reviewer
npm.cmd run openapi:check
```

Wynik: `11` testów workera, `27` testów API, `26` testów Reviewera i `38`
testów generowanego klienta przeszło. Ruff, lint, typecheck i build Reviewera
oraz kontrola OpenAPI/generowanego klienta przeszły. Mypy dla nowego adaptera
workera przeszedł. Standardowy mypy API nadal raportuje dwa wcześniejsze błędy
w niezmienionym `symbol_model_iteration_repository.py` (typ mapy splitu i
nieużyty `type: ignore`); TASK 7 nie osłabia tej bramki ani nie zmienia pliku.

### Acceptance criteria TASK 7

- [x] Preview i zapis korzystają z tej samej walidacji v19 oraz dokładnie tych
      samych 15 finalnych cropów row-major.
- [x] Checksum decyzji wiąże źródło, pozycję, wersje i aktora.
- [x] Każdy zapis tworzy nową rewizję i nie zmienia poprzedniego rekordu ani
      jego plików; exact retry jest idempotentny.
- [x] Zapis odrzuca niejednoznaczny numer, drift źródła, nieaktualne rewizje,
      niepoprawny quad i niekompletny wynik przed zmianą projekcji.
- [x] Reviewer zapisuje wyłącznie aktualnie obejrzany podgląd i natychmiast
      przechodzi na zwróconą rewizję cropów bez przejścia do następnej planszy.
- [x] OpenAPI i generowany klient opisują checksumę decyzji i semantykę
      `latticeBoundsQuad`.
- [x] Pipeline, automatyczny estymator, cropper v18, modele symboli oraz
      rozwiązane decyzje innych plansz pozostają bez zmian.

### Outcome TASK 8 — pending-only recrop v19

- Jawna akcja `Przelicz oczekujące` tworzy teraz job schema v2 z niezmiennym
  snapshotem `pending-board-cell-recrop-v19-v1`. Snapshot przypina wersje
  estymatora, locatora, homografii, progów, geometrii, croppera, ich
  fingerprinty oraz checksumę zaakceptowanego audytu 100 stron.
- Worker zachowuje historyczne wykonanie schema v1, natomiast schema v2 nie
  uruchamia klasycznego detektora strony, OCR ani discovery. Dla planszy
  `pending` korzysta z istniejącego zweryfikowanego quadu strony, uruchamia
  fail-closed estymator v19 i zapisuje dokładnie 15 source-direct cropów v19.
- Brak kompletnego 3 × 5 pozostawia element w review jako
  `needsManualGeometry`; nie powstaje częściowa rewizja ani częściowe pliki.
  JPEG źródłowy jest weryfikowany checksumą i wymiarami oraz dekodowany tylko
  raz dla wszystkich plansz tej samej strony.
- Zapis blokuje ponownie item i planszę oraz porównuje status, rewizje,
  źródło, numer, pozycję, geometrię i checksumy. `accepted`, `corrected`,
  `rejected` albo równoległa korekta zawsze wygrywają z workerem. Automatyczny
  recrop dopisuje rewizję geometrii, nie zmienia statusu review ani nie otwiera
  rozstrzygniętej pozycji.
- Istniejąca geometria v19, również ręczna, nie jest nadpisywana. Finalne PNG
  mają immutable, rewizjonowany namespace; retry jest bezpieczny i raportuje
  osobno przeliczone, już aktualne, pominięte konkurencyjnie, wymagające ręcznej
  geometrii i błędy techniczne.
- Preview API i Admin rozróżniają wszystkie `pending`, kwalifikujące do
  przeliczenia, już zapisane w v19 oraz chronione. Przycisk jest aktywny tylko
  dla faktycznej liczby `recalculableBoardCount` i pokazuje przypięte wersje.
- Aktywny import oraz cropper v18, model i katalog symboli, staging i
  rozstrzygnięte decyzje pozostają niezmienione. TASK 8 nie uruchamia joba na
  danych właściciela.

### Verification TASK 8

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_pending_grid_reinference.py services/worker/tests/test_board_cell_geometry_crops.py services/worker/tests/test_board_cell_geometry_estimator.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_jobs_api.py services/api/tests/test_operational_image_reviews.py services/api/tests/test_openapi_contract.py -q
npm.cmd test --workspace @game-predictor/admin
npm.cmd test --workspace @game-predictor/admin-api-client
npm.cmd run typecheck --workspace @game-predictor/admin
npm.cmd run lint --workspace @game-predictor/admin
npm.cmd run openapi:check
```

Wynik: `22` testy workera, `39` testów API, `212` testów Admina i `38` testów
generowanego klienta przeszły. Ruff i Prettier dla zmienionych plików,
typecheck oraz build Admina, build/typecheck klienta, lint zmienionego
komponentu i kontrola OpenAPI/generowanego klienta przeszły. Ograniczony mypy
dla obu zmienionych modułów workera przeszedł. Pełny mypy repozytorium nie
zwrócił wyniku przez 90 sekund i został przerwany zgodnie z limitem
`AGENTS.md`; TASK 8 nie osłabia tej bramki ani nie ukrywa jej jako zaliczonej.

### Acceptance criteria TASK 8

- [x] Pending-only recrop używa wyłącznie zaakceptowanego, checksum-bound
      snapshotu v19 i nie zmienia odtwarzalności schema v1 ani croppera v18.
- [x] Przetwarzane są wyłącznie itemy nadal `pending`; każdy zapis ponownie
      sprawdza status i wszystkie zależne rewizje pod blokadą.
- [x] Pełne 3 × 5 daje dokładnie 15 source-direct cropów; niepełna geometria
      pozostaje fail-closed bez częściowego zapisu.
- [x] Istniejąca ręczna lub automatyczna rewizja v19 nie jest nadpisywana.
- [x] OCR, discovery, numery `seq_*`, status review, model symboli, staging i
      decyzje rozstrzygnięte nie są zmieniane.
- [x] API/OpenAPI/Admin pokazują kwalifikujące, już aktualne i chronione
      pozycje oraz blokują pusty start.
- [x] TASK 8 nie uruchamia rzeczywistego joba i nie rozpoczyna pionu B ani C.

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

1. [ukończone w TASK 9] Dodać trwałą projekcję kolejki importu i stan liczników z niezmiennym kluczem
   `(source_order_index, position_index, review_item_id)` oraz `queueVersion`.
2. [ukończone w TASK 10] Zmienić listowanie, keyset cursor, wybór pierwszej pending, poprzedni/następny
   i resume tak, aby używały dokładnie tego samego klucza.
3. [ukończone w TASK 11] Zaimplementować transakcyjne first-save-wins dla
   `game_id + sequence_number`. Przegrane oczekujące wystąpienia oznaczać jako
   `superseded`, zachowując źródło i audyt.
4. [ukończone w TASK 12] Odróżnić rzeczywiście nieaktualną komendę elementu od
   prawidłowej decyzji, po której zmieniły się liczniki. Sama zmiana sąsiedniego
   elementu nie może unieważniać kursora bieżącej pozycji.
5. [ukończone w TASK 13] Dostosować Reviewer do małego, ograniczonego bufora
   `previous/current/next two`, bez ładowania całych 19 745 pozycji do pamięci.

### Outcome TASK 9 — trwała projekcja kolejki

- Migracja `0049_image_review_queue_projection` dodaje per import
  `image_review_queue_items` i `image_review_queue_states`.
- Niezmienny klucz pozycji jest przechwytywany z source-order i pozycji planszy
  przy tworzeniu review itemu. Guard bazy blokuje późniejszą zmianę topologii.
- Stan przechowuje dokładne liczniki wszystkich czterech istniejących statusów.
  `queueVersion` rośnie tylko przy zmianie topologii, więc decyzja albo korekta
  geometrii aktualizuje liczniki bez przesuwania kolejki.
- Projekcja jest utrzymywana transakcyjnie w PostgreSQL dla wszystkich ścieżek
  API i workera. Brak source-order lub brak projekcji kończy zapis fail-closed.
- Migracja backfilluje istniejące elementy i kontroluje kompletność przed
  włączeniem triggerów. Usunięcie elementu czyści pochodną projekcję i stan
  pustej kolejki, bez pozostawienia niezgodnych liczników.
- TASK 9 nie zmienia listowania, kursorów, resume, endpointów, OpenAPI, Admina
  ani Reviewera. Ich przełączenie na nową projekcję należy wyłącznie do TASK 10.

### Verification TASK 9

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_migration_baseline.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_batch_store.py -k 'queue_projection or reuses_execution' -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_postgres_baseline.py -q
.\.venv\Scripts\ruff.exe check services/api/alembic/versions/0049_image_review_queue_projection.py services/api/src/game_predictor_api/storage/models.py services/api/tests/test_migration_baseline.py services/api/tests/integration/test_image_batch_store.py services/api/tests/integration/test_postgres_baseline.py
```

Wynik: pełny zestaw API dał `356 passed, 27 skipped`; ponadto `2` rzeczywiste
testy projekcji i ścieżek statusu oraz pełny cykl
upgrade/downgrade/upgrade PostgreSQL przeszły. Ruff i Prettier dla zmienionych
modułów przeszły. Pełny mypy `services/api/src` i
`services/worker/src` nie zwrócił wyniku przez 60 sekund i został przerwany
zgodnie z limitem `AGENTS.md`; wcześniejsza węższa próba uruchomiona bez obu
source rootów pokazała wyłącznie znane problemy rozpoznania importów między
pakietami oraz wcześniejszy `unused-ignore`, a nie błąd nowych modeli.

### Acceptance criteria TASK 9

- [x] Każdy istniejący i nowy review item ma dokładnie jedną trwałą pozycję
      `(source_order_index, position_index, review_item_id)` w swoim imporcie.
- [x] Zmiana statusu albo `sequence_number` nie zmienia klucza ani
      `queueVersion`.
- [x] Dodanie lub usunięcie pozycji zmienia `queueVersion`, a liczniki pozostają
      zgodne z lustrzanymi statusami.
- [x] Backfill, zapis API, zapis workera i restart procesu zachowują tę samą
      projekcję oraz liczniki.
- [x] Niepełne powiązanie source-order i próba zmiany topologii kończą się
      fail-closed.
- [x] TASK 9 nie rozpoczyna przepięcia endpointów ani konkurencyjnego
      first-save-wins.

### Outcome TASK 10 — wspólny klucz listowania i nawigacji

- Job-local endpoint operacyjny czyta pozycje i statusy z trwałej projekcji
  `image_review_queue_items`; sortowanie, keyset cursor, poprzedni/następny oraz
  resume używają wyłącznie `(source_order_index, position_index, review_item_id)`.
- `sequence_number` pozostał filtrem i wartością domenową. Zmiana numeru ani
  statusu nie zmienia położenia elementu i nie unieważnia kursora.
- Opaque cursor schema v2 wiąże klucz z `gameId`, `importJobId`, widokiem i
  trwałym `queueVersion`. Tylko zmiana topologii powoduje
  `IMAGE_REVIEW_CURSOR_STALE`; zmiana liczników nie podnosi wersji.
- Odpowiedź API zwraca `queueVersion`, a liczniki operacyjne i game-wide są
  odczytywane z `image_review_queue_states`. OpenAPI i generowany klient zostały
  zaktualizowane.
- Pierwsze wejście/reload w `all` wybiera pierwszą `pending` według kolejności
  źródłowej, a przy jej braku pierwszy element importu. Nawigacja w lewo nadal
  obejmuje elementy już rozstrzygnięte.
- TASK 10 nie implementuje first-save-wins, statusu `superseded`, semantyki
  konkurencyjnego zapisu ani bufora Reviewera z kolejnych zadań.

### Acceptance criteria TASK 10

- [x] Wszystkie widoki job-local używają jednego niezmiennego klucza kolejki.
- [x] Status i numer sekwencji nie są częścią keyset cursora ani sortowania.
- [x] Kursor zachowuje ważność po rozwiązaniu elementu granicznego.
- [x] Zmiana topologii i `queueVersion` odrzuca stary kursor fail-closed.
- [x] Resume i poprzedni/następny używają tej samej kolejności źródłowej.
- [x] Liczniki oraz `queueVersion` pochodzą z trwałej projekcji.
- [x] Kontrakt OpenAPI zawiera `queueVersion`; klient pozostaje generowany.
- [x] TASK 10 nie rozpoczyna first-save-wins ani zmian bufora Reviewera.

### Verification TASK 10

```powershell
npm run db:migrate
npm run db:current
\.venv\Scripts\python.exe -m pytest services/api/tests -v --tb=short
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_batch_store.py::test_image_review_queue_projection_backfills_and_tracks_durable_state -q
npm test --workspace @game-predictor/admin-api-client
npm test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/admin-api-client
npm run typecheck --workspace @game-predictor/reviewer
npm run openapi:check
```

Wynik: baza działa na `0049 (head)` i zawiera 33 174 pozycje w czterech
trwałych kolejkach. Pełny zestaw API dał `357 passed, 27 skipped`, a osobny
test PostgreSQL projekcji, resume, nawigacji i stale po zmianie topologii
przeszedł. Klient API dał `38 passed`, Reviewer `26 passed`; oba typechecki,
OpenAPI i Ruff dla zmienionych modułów przeszły. Mypy doszedł do dwóch
wcześniejszych, niezwiązanych błędów w `symbol_model_iteration_repository.py`
(`arg-type` i `unused-ignore`); nie wykazał błędu w kodzie TASK 10.
Read-only smoke największej rzeczywistej kolejki (`19 746` wszystkich,
`19 745 pending`) zwrócił pierwszą pending wraz z oboma kierunkami nawigacji i
`queueVersion = 1` w `72,43 ms`.

### Outcome TASK 11 — first-save-wins i audyt przegranych źródeł

- Migracja `0050_image_review_first_save_wins` dodaje terminalny status i event
  `superseded` oraz osobny, trwały licznik per import.
- Zapis accepted/corrected serializuje wyłącznie wspólny klucz
  `game_id + sequence_number` przez transakcyjny advisory lock i atomowy insert
  kanonicznego właściciela. Różne numery nie są globalnie blokowane.
- Zwycięzca zachowuje staging i kanoniczną projekcję. Wszystkie znane pending
  tego samego numeru są w tej samej transakcji oznaczane `superseded`; staging
  przegranych jest usuwany, natomiast review item, źródło, alternatywa i event
  pozostają audytowalne.
- Równoległa komenda, której pozycja została już systemowo zastąpiona, zapisuje
  idempotentny event przegranej komendy i zwraca kontrolowany wynik
  `superseded`. Nie nadpisuje właściciela.
- `queueVersion` nie zmienia się przy tej zmianie statusu. Triggery aktualizują
  dokładne liczniki, a ponowne otwarcie `superseded` korektą geometrii jest
  blokowane fail-closed.
- Worker przy ponownym źródle już kanonicznego numeru używa tej samej semantyki
  statusu, eventu i alternatywnego źródła. `superseded` nie jest materializowany
  do layout staging ani do kohorty treningowej.
- TASK 11 nie zmienia semantyki konfliktu zwykłej nieaktualnej komendy (TASK 12)
  ani strategii bufora Reviewera.

### Acceptance criteria TASK 11

- [x] Dwie równoległe decyzje jednego numeru utrwalają dokładnie jednego
      kanonicznego właściciela.
- [x] Przegrana pozycja kończy się kontrolowanym `superseded`, nie błędem SQL ani
      drugim staging row.
- [x] Pozostałe pending tego numeru są zastępowane bez zmiany topologii i
      `queueVersion`.
- [x] Źródło, kanoniczny właściciel, alternatywa i append-only event pozostają
      audytowalne po restarcie.
- [x] `accepted/corrected/rejected` nie są automatycznie zastępowane, a
      `superseded` nie może zostać ponownie otwarty korektą geometrii.
- [x] Liczniki trwałej projekcji i kontraktu API obejmują osobny
      `superseded`, zaś `completed` pozostaje `accepted + corrected`.
- [x] TASK 11 nie rozpoczyna TASK 12 ani bounded bufora Reviewera.

### Verification TASK 11

```powershell
npm run db:migrate
npm run db:current
.\.venv\Scripts\python.exe -m pytest services/api/tests -q --tb=short
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_batch_store.py::test_parallel_review_decisions_persist_one_canonical_owner_and_supersede_loser -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_postgres_baseline.py -q
npm test --workspace @game-predictor/admin-api-client
npm test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/admin-api-client
npm run typecheck --workspace @game-predictor/reviewer
npm run reviewer:build
npm run openapi:check
```

Wynik: lokalna baza działa na `0050 (head)`, a suma pięciu trwałych liczników
w czterech kolejkach jest równa wszystkim `33 174` pozycjom. API dało
`358 passed, 28 skipped`. Rzeczywisty równoległy test PostgreSQL oraz pełny
cykl baseline przeszły. Klient API dał `38 passed`, Reviewer `26 passed`; oba
typechecki TypeScript, build Reviewera, OpenAPI, Ruff i Prettier przeszły.
Pełny worker dał `841 passed`; trzy niezwiązane testy datasetu treningowego
kończą się istniejącym `WinError 3` w atomowym `os.replace` pod zbyt długą
ścieżką `%TEMP%`. Ich osobne ponowienie dało ten sam błąd. Mypy dotarł do dwóch
wcześniejszych, niezwiązanych błędów w
`symbol_model_iteration_repository.py` (`arg-type`, `unused-ignore`) i nie
zgłosił problemu w kodzie TASK 11.

### Outcome TASK 12 — konflikt itemu i autorytatywny wynik komendy

- Pomyślna odpowiedź resolution zawiera `queueVersion` oraz pełne `counts`
  odczytane z trwałej projekcji po wykonaniu zapisu i triggerów. Reviewer używa
  tego snapshotu zamiast lokalnie odejmować i dodawać status bieżącego itemu.
- `expectedRevision` chroni wyłącznie wskazany review item. Zmiana sąsiedniej
  pozycji albo liczników nie blokuje poprawnej komendy i nie zmienia
  `queueVersion`.
- Rzeczywiście stara komenda zwraca `IMAGE_REVIEW_REVISION_CONFLICT` ze scope
  `item`, identyfikatorem, oczekiwaną i aktualną rewizją oraz aktualnym statusem.
  Konflikt geometrii i konflikt topologii kursora pozostają odrębnymi kodami.
- Reviewer zachowuje ten sam UUID idempotencji dla ponowienia niezmienionej
  komendy po błędzie transportu. Zmiana numeru albo symbolu zeruje próbę; exact
  retry odzyskuje wcześniejszy sukces jako `created = false` wraz z aktualnymi
  licznikami.
- TASK 12 nie implementuje bufora `previous/current/next two`, prefetchu ani
  lifecycle'u wspólnego Reviewera.

### Acceptance criteria TASK 12

- [x] Decyzja bieżącego itemu przechodzi po równoległej zmianie sąsiedniej
      pozycji, jeżeli jego własna rewizja nadal odpowiada komendzie.
- [x] Pomyślna odpowiedź i exact retry zawierają dokładne trwałe liczniki oraz
      `queueVersion` po transakcji.
- [x] Tylko zmiana rewizji bieżącego itemu daje item-scoped konflikt z danymi
      umożliwiającymi jednoznaczne przeładowanie.
- [x] Reviewer nie wyprowadza liczników resolution z lokalnego snapshotu i
      ponawia niezmienioną komendę z tym samym UUID.
- [x] OpenAPI oraz generowany klient obejmują nowy snapshot odpowiedzi.
- [x] TASK 12 nie rozpoczyna bounded bufora ani pionu C.

### Verification TASK 12

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -q --tb=short
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_batch_store.py::test_parallel_review_decisions_persist_one_canonical_owner_and_supersede_loser -q
npm test --workspace @game-predictor/admin-api-client
npm test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/admin-api-client
npm run typecheck --workspace @game-predictor/reviewer
npm run reviewer:build
npm run openapi:check
```

Wynik: pełny zestaw API dał `359 passed, 28 skipped`, a rzeczywisty równoległy
test PostgreSQL potwierdził first-save-wins oraz snapshot liczników po zapisie.
Klient API dał `38 passed`, Reviewer `28 passed`; oba typechecki TypeScript,
build Reviewera, OpenAPI, Ruff, Prettier i celowany ESLint przeszły. Pełny ESLint
workspace Reviewera oraz mypy obu source rootów nie zwróciły wyniku przez 60
sekund i zostały przerwane zgodnie z limitem `AGENTS.md`. Wąski mypy uruchomiony
bez workerowego source rootu pokazał wyłącznie znany problem `import-untyped`
między pakietami oraz wcześniejszy `unused-ignore`, a nie błąd w kodzie TASK 12.

### Outcome TASK 13 — bounded bufor Reviewera

- Reviewer utrzymuje najwyżej cztery jednopozycyjne odpowiedzi API: jednego
  poprzednika, bieżącą planszę i dwóch następników. Każde pobranie nadal używa
  `limit = 1`; pełna kolejka nie jest materializowana w React ani w jednym
  żądaniu.
- Poprzednik i pierwszy następnik są pobierani równolegle, a drugi następnik
  dopiero z kursora pierwszego. Przejście po gotowym sąsiedzie jest lokalnym
  przesunięciem okna, po którym brakujący brzeg jest uzupełniany w tle.
- Prefetch obejmuje również 15 cropów i pojedynczy widok planszy każdego
  sąsiada w ograniczonym oknie. Bieżące zasoby są ładowane przez widoczny ekran,
  a strony wypadające z okna są usuwane ze stanu React.
- Pomyślna resolution z TASK 12 aktualizuje bieżący item i propaguje jej
  autorytatywne liczniki oraz `queueVersion` do stron już znajdujących się w
  buforze przed natychmiastowym przejściem dalej.
- Nieaktualny kursor wykryty również podczas prefetchu pozostaje fail-closed i
  wymaga przeładowania. Zwykły błąd transportu prefetchu nie usuwa bieżącej
  planszy; nawigacja wykonuje wtedy dotychczasowy foreground fallback.
- TASK 13 nie zmienia API, OpenAPI, bazy, topologii kolejki, first-save-wins ani
  lifecycle'u wspólnego Reviewera z pionu C.

### Acceptance criteria TASK 13

- [x] Stan klienta zawiera najwyżej `previous + current + 2 next` strony.
- [x] Każda strona jest pobierana osobnym żądaniem z `limit = 1`.
- [x] Gotowy następnik i poprzednik są pokazywane bez pełnoekranowego ponownego
      ładowania, a brakujący brzeg jest uzupełniany bounded w tle.
- [x] Prefetch zasobów obejmuje wyłącznie poprzednika oraz dwóch następników.
- [x] Resolution nie przywraca starych liczników z wcześniej pobranego
      następnika.
- [x] Konflikt topologii pozostaje fail-closed, a błąd transportu prefetchu ma
      bezpieczny foreground fallback.
- [x] TASK 13 nie rozpoczyna pionu C ani nie zmienia kontraktu backendu.

### Verification TASK 13

```powershell
npm.cmd test --workspace @game-predictor/reviewer
npm.cmd run typecheck --workspace @game-predictor/reviewer
npm.cmd exec --workspace @game-predictor/reviewer -- eslint src/features/operational-reviews/operational-review-actions.ts src/features/operational-reviews/operational-review-state.ts src/features/operational-reviews/operational-review-workspace.tsx
npm.cmd run reviewer:build
```

Wynik: Reviewer dał `33 passed`; typecheck, celowany ESLint trzech zmienionych
modułów, Prettier i produkcyjny build Next.js przeszły. Test async prefetchu
potwierdził dokładnie trzy jednopozycyjne żądania dla pustego okna sąsiadów, a
test stanu potwierdził limit czterech stron, przesuwanie w obu kierunkach,
bounded prefetch 48 zasobów trzech sąsiadów oraz zachowanie autorytatywnego
snapshotu resolution. API, OpenAPI i baza nie zostały zmienione, dlatego ich
generowanie i migracje nie należą do bramki TASK 13.

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

1. [ukończone w TASK 14] Dodać `reviewer_work_assignments`: najwyżej jedno aktywne przypisanie na
   import, typ local/online, lease/heartbeat, scope i historia zamknięcia.
2. [ukończone w TASK 15] Rozdzielić lifecycle przypisania/sesji od lifecycle'u
   procesu Reviewera i Quick Tunnel. Jeden proces i URL obsługują wszystkie
   aktywne scope'y.
3. [ukończone w TASK 16] Serializować `ensure-running/status/stop-if-unused` między procesami Windows
   przez mutex/lock oraz atomowy stan zawierający PID, start time, executable i
   instance id. Każda próba startu ma unikalne logi, a publikacja stanu następuje
   dopiero po health checku.
4. [ukończone w TASK 17] Ograniczyć online do trzech różnych importów. Zatrzymanie jednego
   udostępnienia unieważnia tylko jego sesję; tunel jest zatrzymywany dopiero,
   gdy nie istnieje inne aktywne online assignment.
5. [ukończone w TASK 18] Przebudować sekcję Admina: select gotowego importu, statystyki zakresu,
   `Otwórz lokalnie` albo `Utwórz link online`, status i niezależne zatrzymanie.
   Lista nie pokazuje kodu, tokenu ani sekretu po utworzeniu sesji.
6. [zachowane w TASK 18] Zachować jeden build produkcyjny Reviewera, same-origin allowlist proxy,
   loopback-only lokalny dostęp i istniejące ograniczenia Quick Tunnel.

### Outcome TASK 14 — trwałe przypisania pracy

- Migracja `0051_reviewer_work_assignments` dodaje osobną od sesji dostępowej i
  procesu tabelę scope'owaną przez `game_id + import_job_id`.
- Typ `local/online`, właściciel, fencing token, heartbeat i wygaśnięcie lease
  mają wspólne constrainty czasu. Częściowy unikalny indeks po aktywnym
  `import_job_id` gwarantuje najwyżej jedno aktywne przypisanie na import.
- Lifecycle domenowy odrzuca pustego właściciela, naiwne timestampy, cofnięcie
  heartbeat, zły token i odnowienie wygasłego lease. Zapis SQL aktualizuje
  aktywny rekord wyłącznie przy zgodnym fencing tokenie.
- Zamknięcie zachowuje rekord, scope i lease oraz dopisuje `closed_at`, powód i
  aktora. Wygasły assignment jest zamykany jako `lease_expired` przed
  utworzeniem następcy; historia pozostaje deterministycznie listowalna.
- Scope jest walidowany pod blokadą import joba według tej samej gotowości co
  istniejąca sesja Reviewera: import obrazów tej gry, status
  `waiting_for_review/completed` i co najmniej jeden review item.
- TASK 14 nie uruchamia procesu Reviewera ani Quick Tunnel, nie łączy jeszcze
  assignmentu z sesją, nie wprowadza limitu trzech linków i nie zmienia API,
  OpenAPI, Admina ani Reviewera.

### Verification TASK 14

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_reviewer_work_assignments.py services/api/tests/test_migration_baseline.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_postgres_baseline.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests -q --tb=short
.\.venv\Scripts\ruff.exe check <zmienione pliki Python>
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip --ignore-missing-imports <nowe moduły>
npm run db:migrate
npm run db:current
```

Wynik: testy domeny i migracji dały `42 passed`, rzeczywisty cykl PostgreSQL i
repozytorium `2 passed`, a pełny zestaw API `367 passed, 29 skipped`. Ruff i
ograniczony mypy nowych modułów przeszły. Lokalna baza działa na
`0051_reviewer_work_assignments (head)`.

### Acceptance criteria TASK 14

- [x] Dla jednego importu istnieje najwyżej jeden rekord z `closed_at IS NULL`.
- [x] Różne typy przypisania używają jednego modelu scope'u i lease.
- [x] Heartbeat oraz zapis są ogrodzone tokenem i nie odnawiają wygasłego lease.
- [x] Zamknięte i automatycznie odzyskane wpisy pozostają trwałą historią.
- [x] Scope jest związany z gotowym importem obrazów wskazanej gry.
- [x] Migracja ma poprawny downgrade, a model przechodzi rzeczywisty test
      PostgreSQL i pełne testy API.
- [x] TASK 14 nie rozpoczyna lifecycle'u procesu/tunelu, limitu online ani UI.

### Outcome TASK 15 — assignment/session niezależne od shared ingressu

- Migracja `0052_reviewer_assignment_sessions` wiąże assignment online z
  dokładnie jedną scoped `reviewer_access_session`. Złożony FK po
  `session_id + game_id + import_job_id` blokuje przypięcie obcej sesji, a
  constraint trybu zabrania sesji dla pracy lokalnej.
- `ReviewerWorkLifecycleService` zapewnia gotowość jednego współdzielonego
  procesu. Kolejne prace online ponownie używają zdrowego publicznego originu,
  a praca lokalna ponownie używa gotowego loopback Reviewera także wtedy, gdy
  istnieje tunel.
- Każdy assignment online zachowuje własną sesję i kod. Zamknięcie assignmentu
  unieważnia tylko tę sesję; warstwa TASK 15 celowo nie ma operacji globalnego
  `stop`.
- Nieudane utworzenie assignmentu po utworzeniu sesji kompensuje operację przez
  revoke. Odzyskanie wygasłego assignmentu również unieważnia jego dawną sesję
  przed utworzeniem następcy.
- TASK 15 nie dodaje endpointów ani UI, limitu trzech prac online,
  `stop-if-unused` ani synchronizacji procesów Windows. Są to późniejsze,
  niezależnie odbierane zadania pionu C.

### Verification TASK 15

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_reviewer_work_assignments.py services/api/tests/test_reviewer_work_lifecycle.py services/api/tests/test_reviewer_access.py services/api/tests/test_reviewer_ingress.py services/api/tests/test_migration_baseline.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest services/api/tests -q --tb=short
.\.venv\Scripts\ruff.exe check <zmienione pliki Python>
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip --ignore-missing-imports <zmienione moduły aplikacyjne>
npm run db:migrate
npm run db:current
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_postgres_baseline.py -q --tb=short
```

Wynik celowany: `62 passed`, a pełny zestaw API dał `374 passed, 29 skipped`;
Ruff i mypy przeszły. Lokalna baza oraz rzeczywisty cykl PostgreSQL przeszły na
`0052_reviewer_assignment_sessions (head)`, a test integracyjny dał `2 passed`.

### Acceptance criteria TASK 15

- [x] Online assignment wskazuje jedną sesję o identycznym scope gry/importu.
- [x] Local assignment nie tworzy ani nie przechowuje sesji dostępowej.
- [x] Dwa różne importy ponownie używają jednego procesu i publicznego originu,
      zachowując oddzielne sesje i lease.
- [x] Zamknięcie jednego assignmentu unieważnia wyłącznie jego sesję i nie
      wywołuje globalnego zatrzymania ingressu.
- [x] Nieudane otwarcie nie pozostawia aktywnej, osieroconej sesji.
- [x] Migracja zachowuje scope w bazie i ma odwracalny downgrade.
- [x] TASK 15 nie rozpoczyna TASK 16 ani późniejszych zmian API/UI/limitu.

### Outcome TASK 16 — serializowany lifecycle procesu Windows

- Wspólny helper PowerShell wyprowadza nazwany mutex z pełnej ścieżki
  repozytorium i serializuje z ograniczonym timeoutem zdalny start, status,
  stop oraz lokalny start Reviewera także między niezależnymi procesami API.
- Stan lokalny i zdalny schema v2 jest publikowany atomowo dopiero po health
  checku. Tożsamość procesu wiąże `instanceId`, PID, czas uruchomienia, pełną
  ścieżkę executable i nazwę procesu; niezgodność lub ponowne użycie PID nie
  pozwala zatrzymać obcego procesu.
- Każda próba startu ma unikalne pliki stdout/stderr/log w
  `.runtime/reviewer-lifecycle-logs`. Każde wywołanie kontrolera API ma również
  unikalny plik wyniku, więc niezależne procesy nie współdzielą otwartego pliku.
- Start publikuje stan dopiero po gotowości publicznego originu oraz produkcyjnego
  Reviewera. Kontrolowany compare-and-stop wymaga oczekiwanego `instanceId` i
  nie zatrzymuje nowszej instancji.
- TASK 16 nie zmienia publicznego API/OpenAPI, bazy, Admina ani Reviewera. Nie
  dodaje limitu trzech prac online i nie decyduje jeszcze, kiedy ostatni
  assignment ma zatrzymać wspólny tunel; to pozostaje TASK 17.

### Verification TASK 16

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_reviewer_process_lifecycle_scripts.py services/api/tests/test_reviewer_ingress.py services/api/tests/test_reviewer_work_lifecycle.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest services/api/tests -q --tb=short
.\.venv\Scripts\ruff.exe check services/api/src/game_predictor_api/application/reviewer_ingress.py services/api/tests/test_reviewer_ingress.py services/api/tests/test_reviewer_process_lifecycle_scripts.py
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip --ignore-missing-imports services/api/src/game_predictor_api/application/reviewer_ingress.py
```

Testy procesowe uruchamiają niezależne procesy PowerShell i potwierdzają
mutual exclusion, atomowy stan, odrzucenie PID z innym czasem startu, unikalne
logi oraz compare-and-stop na rzeczywistym procesie testowym. Nie uruchamiają
rzeczywistego Quick Tunnel ani nie zmieniają aktywnego ingressu operatora.
Wynik celowany dał `18 passed`, a pełny zestaw API `380 passed, 29 skipped`;
Ruff, ograniczony mypy i parser wszystkich zmienionych skryptów PowerShell
przeszły.

### Acceptance criteria TASK 16

- [x] Równoległe kontrolery jednego repozytorium są serializowane nazwanym
      mutexem z ograniczonym oczekiwaniem i odzyskaniem porzuconej blokady.
- [x] Opublikowany stan zawiera pełną tożsamość procesu i powstaje atomowo
      dopiero po health checku.
- [x] Status i stop nie ufają samemu PID oraz nie zatrzymują procesu o
      niezgodnej tożsamości.
- [x] Spóźniony compare-and-stop nie zatrzymuje nowszego `instanceId`.
- [x] Równoległe próby nie współdzielą plików logu ani wyniku kontrolera API.
- [x] Publiczny kontrakt, baza, limit online oraz UI pozostają bez zmian.

### Outcome TASK 17 — limit online i stop ostatniego assignmentu

- `ReviewerWorkAssignmentService` serializuje online capacity jednym
  transakcyjnym advisory lockiem PostgreSQL; repozytorium in-memory zachowuje tę
  samą semantykę dla testów współbieżności. Maksymalnie trzy różne importy mogą
  mieć aktywny assignment online, a local assignment nie zajmuje limitu.
- Sprawdzenie zajętego importu i limitu następuje przed zapewnieniem ingressu i
  utworzeniem sesji. Czwarta praca kończy się stabilnym
  `REVIEWER_ASSIGNMENT_ONLINE_LIMIT_REACHED` z licznikami `3/3` i nie zostawia
  sesji ani drugiego tunelu.
- Capacity lock obejmuje również ensure-running, utworzenie scoped sesji i
  zapis assignmentu. Równoległy open nie może więc otrzymać linku do instancji,
  którą właśnie zatrzymuje close ostatniej pracy.
- Zamknięcie odwołuje tylko sesję wskazanego assignmentu. Ingress pozostaje,
  dopóki istnieje inny online assignment; ostatni close wykonuje
  compare-and-stop po aktualnym `instanceId` z TASK 16.
- Lazy recovery domyka wszystkie wygasłe online lease'y pod tą samą blokadą,
  unieważnia ich sesje i zwalnia capacity. Jawne `stop_if_unused` zatrzymuje
  osierocony ingress, gdy nie ma już aktywnej pracy online.
- TASK 17 nie zmienia bazy, publicznego API/OpenAPI, Admina ani Reviewera. Select
  importu, lista prac i przyciski per assignment pozostają TASK 18.

### Verification TASK 17

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_reviewer_work_assignments.py services/api/tests/test_reviewer_work_lifecycle.py services/api/tests/test_reviewer_ingress.py services/api/tests/test_reviewer_process_lifecycle_scripts.py -q --tb=short
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_postgres_baseline.py -q --tb=short
.\.venv\Scripts\python.exe -m pytest services/api/tests -q --tb=short
.\.venv\Scripts\ruff.exe check <zmienione pliki Python>
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip --ignore-missing-imports <zmienione moduły aplikacyjne>
```

Test współbieżności PostgreSQL uruchamia cztery niezależne transakcje i wymaga
dokładnie trzech sukcesów oraz jednego kontrolowanego limitu. Test aplikacyjny
blokuje stop ostatniego assignmentu, równolegle rozpoczyna nową pracę i
potwierdza, że nowa sesja powstaje dopiero na następnej instancji ingressu.
Wynik celowany dał `33 passed`, rzeczywisty baseline PostgreSQL `3 passed`, a
pełny zestaw API `387 passed, 30 skipped`; Ruff i ograniczony mypy przeszły.

### Acceptance criteria TASK 17

- [x] Nigdy nie powstają więcej niż trzy aktywne online assignmenty, również
      przy czterech równoległych transakcjach PostgreSQL.
- [x] Local assignment działa równolegle i nie zużywa online capacity.
- [x] Odrzucona czwarta praca nie uruchamia ingressu i nie tworzy sesji.
- [x] Zamknięcie jednej z kilku prac odwołuje tylko jej scoped sesję i nie
      zatrzymuje tunelu.
- [x] Ostatni close lub recovery wygasłych prac wykonuje ogrodzony stop bieżącej
      instancji; równoległy open nie otrzymuje starego URL.
- [x] Historia zamknięć, fencing lease, jeden assignment na import i granice
      bezpieczeństwa Reviewera pozostają bez zmian.
- [x] TASK 17 nie rozpoczyna endpointów ani UI TASK 18.

### Outcome TASK 18 — assignment-scoped API i sekcja Admina

- Dodano lokalny kontrakt list/open local/open online/heartbeat/close. Wszystkie
  operacje używają istniejącego `ReviewerWorkLifecycleService`; frontend nie
  składa już pracy z globalnego startu tunelu i osobnego tworzenia/revoke sesji.
- Open tego samego importu i trybu jest idempotentny. Pierwsza odpowiedź online
  ujawnia kod, a ponowienie i lista nie zawierają kodu, bearer/fencing tokenu ani
  osobnego pola identyfikatora sesji. Publiczny URL może zawierać jego opaque
  identyfikator. Tryb przeciwny nadal kończy się konfliktem.
- Composition root wiąże repozytoria assignmentu i sesji jedną transakcją.
  Stabilne błędy assignments mają statusy 404/409/422, a high-impact guard
  wymaga dokładnego targetu dla local, online i close.
- Admin pokazuje select gotowego importu, liczniki plansz, capacity `N/3`, stan
  wybranego scope'u i listę aktywnych prac. Import bez pracy oferuje local/online;
  praca online zastępuje local własnym stopem. Każda pozycja listy ma niezależne
  zakończenie.
- Kod jest zachowywany wyłącznie w nietrwałym stanie React odpowiedzi create.
  Reload odtwarza assignments bez sekretu. Background heartbeat nie przesyła
  lease tokenu.
- Historyczne endpointy ingress/sessions pozostają kompatybilne, lecz zwykły
  przepływ Admina ich nie używa. Reviewer, proxy allowlist, baza, migracje,
  worker oraz pipeline importu pozostały bez zmian.

### Verification TASK 18

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -q --tb=short
.\.venv\Scripts\ruff.exe check <zmienione pliki Python>
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip --ignore-missing-imports <warstwa assignments/lifecycle/storage>
npm run openapi:check
npm test --workspace @game-predictor/admin-api-client
npm test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run admin:build
```

Wynik: API `393 passed, 30 skipped`, klient `39 passed`, Admin `211 passed`.
OpenAPI/generowany klient, Ruff, ograniczony mypy, typecheck i produkcyjny build
Admina przeszły. ESLint nie zgłosił błędów; zachował dwa wcześniejsze ostrzeżenia
`no-img-element` w niezwiązanych modułach geometrii i manualnej selekcji.

### Acceptance criteria TASK 18

- [x] Select gotowego importu zachowuje liczniki wszystkich/pending/zakończonych.
- [x] Local i online otwierają dokładnie jeden assignment wskazanego importu.
- [x] Idempotentny open nie tworzy drugiej sesji i nie ujawnia kodu ponownie.
- [x] Lista po reloadzie pokazuje aktywne prace i nie zawiera sekretów ani tokenów.
- [x] Stop wskazanej pracy nie wywołuje globalnego stopu z frontendu i nie
      przerywa innego assignmentu.
- [x] UI pokazuje limit online, stan wspólnego Reviewera oraz loading/empty/error.
- [x] OpenAPI, generowany klient i high-impact target odpowiadają backendowi.
- [x] TASK 18 nie zmienia Reviewera, proxy allowlist, bazy, migracji ani pipeline'u.

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
podgląd v19 powstały w TASK 6, a TASK 7 uruchomił ich append-only zapis z pełną
proweniencją. TASK 8 udostępnił osobno odbierany pending-only recrop v19 bez
zmiany pełnego pipeline'u importu. TASK 9 utrwalił topologię i liczniki kolejki,
TASK 10 przepiął operacyjne listowanie na jeden klucz, TASK 11 utrwalił
first-save-wins i audyt `superseded`, a TASK 12 rozdzielił konflikt komendy itemu
od zmian liczników. TASK 13 zamknął pion B ograniczonym buforem
`previous/current/next two` i prefetchowaniem zasobów sąsiadów. Pion wspólnego
Reviewera został rozpoczęty w TASK 14 od trwałych `reviewer_work_assignments` z
fencingiem i historią zamknięcia. TASK 15 powiązał assignment online ze scoped
sesją, TASK 16 zabezpieczył proces Windows i jego stan, a TASK 17 dodał globalny
limit trzech prac online oraz ogrodzony stop po ostatnim assignmentcie. TASK 18
wystawił typowane endpointy assignments i przepiął na nie sekcję Admina bez
zmiany publicznej granicy Reviewera.
