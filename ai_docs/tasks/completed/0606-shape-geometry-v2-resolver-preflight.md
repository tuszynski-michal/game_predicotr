---
title: Resolver i preflight wspólnej geometrii shape v2
status: done
task_id: TASK-0606
---

# TASK-0606 — resolver i preflight wspólnej geometrii shape v2

## Status

`done`

## Goal

Przypiąć do nowego preflightu wyłącznie zgodny aktywny profil
`framed_full_page_v2` i na każdym bieżącym obrazie zweryfikować go rdzeniem
G02, zapisując odtwarzalny wynik bez automatycznego importu.

## Context

G02 wykrywa pełną stronę z ramką przez kształt i kontrast, lecz sam zwraca tylko
propozycję. G06 przechowuje immutable wersje descriptorów poza data plane gry.
G03 łączy oba piony z istniejącym `page_geometry_preflight`: publiczny profil
może być użyty tylko po aktywacji, a każdy job zachowuje dokładny snapshot,
lokalne ustawienie neutralne kolorystycznie, dowód bieżących pikseli oraz
werdykt. Brak, niezgodność lub niepowodzenie nie może uruchomić legacy fallbacku
ani automatycznie oznaczyć źródła jako gotowego do importu.

## Dependencies / entry conditions

- G02 (`v0.10.345`) dostarcza deterministyczny wynik `proposal` lub
  `needs_manual_review` dla kompletnej siatki 3 × 3 / 3 × 5.
- G06 (`v0.10.346`) dostarcza kontrolny plane profili i invariant jednej
  aktywnej wersji dla rodziny/topologii; G06 nie wystawia operacji aktywacji,
  dlatego normalny brak profilu pozostaje stanem poprawnym.
- Istniejący `page_geometry_preflight` wersjonuje input, manifest i retry;
  snapshot G03 musi uczestniczyć w jego identyczności oraz kompatybilności
  reuse.
- Nie ma blokującego pytania produktowego. Przyjmujemy zapisane w planie
  rozstrzygnięcie: kolor różni się między grami, dlatego G03 używa stałej
  lokalnej polityki `structural_only`; przyszłe ustawienia gry są zakresem G04.

## Recommended execution

gpt-5.6-terra, xhigh — zadanie dotyka granicy API/worker, snapshotów i
istniejącego kontraktu preflightu, więc wymaga kontroli całego przepływu oraz
regresji retry. Niezależny audyt gpt-6-astra, medium jest obowiązkowy po
implementacji; P0/P1 zatrzymuje plan, P2/P3 należy naprawić i poddać
re-audytowi przed zamknięciem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md` (G03)
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md` (preflight geometrii)
- `services/api/src/game_predictor_api/application/jobs.py`
- `services/api/src/game_predictor_api/storage/global_geometry_library_repository.py`
- `services/worker/src/game_predictor_worker/images/page_geometry_preflight.py`
- `services/worker/src/game_predictor_worker/images/shape_geometry_v2/core.py`

## Scope

- Dodać zamknięty kontrakt `shape_geometry_v2_profile` dla wejścia preflightu:
  wersję snapshotu, identyfikator/numer/checksumę aktywnej biblioteki,
  topologię, znormalizowany szablon, descriptor ramki i lokalną politykę
  `structural_only`. Kontrakt ponownie waliduje descriptor G06, checksumę,
  status i topologię, bez obrazu, `game_id`, kotwicy, OCR, symboli, payoutu
  oraz sekwencji.
- Dodać resolver API odczytujący tylko `active` profil `framed_full_page_v2`
  3 × 3 / 3 × 5. Brak profilu daje zwykły historyczny preflight; profil
  uszkodzony albo więcej niż jeden aktywny profil kończy tworzenie joba
  kontrolowanym błędem, bez wyboru zastępczego.
- Wpiąć resolver do fabryk `JobService`; przy wybranym profilu utworzyć nową
  wersję polityki preflightu, przypiąć snapshot do inputu oraz uwzględnić go w
  idempotencji i w warunkach bezpiecznego reuse manifestu.
- Rozszerzyć worker o parser zamkniętego inputu v4 i lokalny verifier G02.
  Sprawdzi on pełny wynik rdzenia oraz aspect ratio względem przypiętego
  szablonu. Zapisze snapshot profilu, politykę, wynik G02 i werdykt per źródło
  do immutable manifestu. Sukces nadal ma `review_required` z konkretnym
  powodem ręcznego potwierdzenia; nie zamienia propozycji w `registered`.
- Brak dopasowania, niekompletny kadr, słaba siatka lub niezgodny aspect ratio
  pozostawia wyłącznie `review_required`, z kodem powodu i bez geometrii
  importowej. Uszkodzony snapshot jest błędem inputu joba fail-closed, ponieważ
  worker nie ma wiarygodnego profilu do oceny. Ręczna override zachowuje
  pierwszeństwo.
- Dodać testy resolvera, identity/reuse oraz workerowego snapshotu, sukcesu
  propozycji i każdego fail-closed przypadku; zachować regresję v2/v3 bez
  profilu.

## Out of scope

- Tworzenie gry, ustawienia operatora i widok gotowości (G04).
- Kwalifikacja, aktywacja, replay regresji, rollback i tworzenie kandydatów z
  korekt (G07).
- Użycie propozycji jako `registered`, import bez review albo pilot Mumie/Gang
  (G05).
- Obsługa Treasure bez ramki oraz zmiany historycznych silników v1/v1.1.
- Migracja bazy: snapshot należy do istniejącego immutable inputu joba.

## Acceptance criteria

- [x] Resolver wybiera tylko jeden poprawny profil `active` zgodnej rodziny i
  topologii; candidate/rejected/retired, brak lub konflikt nie może potajemnie
  wybrać innej wersji.
- [x] Job z profilem przypina kompletny snapshot do inputu i manifestu, a
  zmiana profilu nie identyfikuje się z historycznym jobem ani jego reuse.
- [x] Worker waliduje snapshot oraz aktualne piksele rdzeniem G02; wynik zawiera
  wersję biblioteki, lokalną politykę, dowody i jawny werdykt per źródło.
- [x] Sukces pozostaje propozycją do ręcznego potwierdzenia, a każda
  niezgodność daje `review_required` bez geometrii dopuszczonej do importu.
- [x] Historyczny preflight bez aktywnego profilu pozostaje kompatybilny;
  testy, lint, typecheck i audyt Astra Medium potwierdzają pełny zakres.

## Technical notes

`shape_geometry_v2_profile` jest obecne tylko wraz z nową polityką
`page-geometry-preflight-v4-shape-geometry-v2-profile`; w przeciwnym razie
worker odrzuca payload. Snapshot ma dokładnie określone pola i jest kopiowany
do manifestu, przez co restart i odczyt późniejszej aktywnej wersji nie mogą
zmienić wyniku joba.

Resolver pobiera wszystkie aktywne wersje bez limitu historii kandydatów oraz
przed serializacją odtwarza ich pełną checksumę z descriptorowych dowodów.
Snapshot ma dodatkową checksumę własnych descriptorów, którą worker ponownie
sprawdza. Następnie `JobService` dodaje snapshot przed
wyszukaniem base manifestu i identycznego requestu. Porównanie kompatybilności
wymaga bajtowej równości przypiętego snapshotu; historyczny manifest nie może
zostać reuse dla innej wersji biblioteki.

Verifier ma dwa niezależne warunki: `detect_shape_geometry_v2` musi zwrócić
kompletną `proposal` z dziewięcioma planszami, a relacja boków wykrytej ramki
musi mieścić się w `aspectRatioRange` profilu. `frameAppearance` jest
przypiętym dowodem konfiguracyjnym, lecz lokalna polityka `structural_only` nie
porównuje koloru ramek między grami. Zatem Mumie i Gang mogą mieć różne kolory,
ale dzielą format pełnej strony. Werdykt sukcesu nie ma pola `quads` ani statusu
`registered`; istniejący importer widzi `review_required` i pozostaje
zablokowany do późniejszego, jawnego etapu.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/domain/global_geometry_library.py`
  — walidacja i serializacja snapshotu istniejącego profilu.
- Nowe: `services/api/src/game_predictor_api/storage/global_geometry_profile_snapshot_resolver.py`
  — resolver aktywnego profilu bez routingu gry.
- Istniejące: `services/api/src/game_predictor_api/application/jobs.py` —
  protocol resolvera, przypięcie inputu, identity i compatibility.
- Istniejące: `services/api/src/game_predictor_api/main.py` — dependency
  injection resolvera.
- Nowe: `services/worker/src/game_predictor_worker/images/shape_geometry_v2/preflight.py`
  — parser i lokalny verifier G02.
- Istniejące: `services/worker/src/game_predictor_worker/images/page_geometry_preflight.py`
  — wersja polityki, walidacja inputu, wynik per źródło i manifest.
- Nowe: testy resolvera API i workerowego verifiera; istniejące testy jobów i
  preflightu — regresje idempotencji oraz pełnego przepływu.
- Istniejące: `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`,
  `ai_docs/process/DECISION_LOG.md` i `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Jeden ważny aktywny profil → nowy job v4 i manifest zawierają ten sam
  immutable snapshot; ta sama prośba jest idempotentna.
- Brak aktywnego profilu → istniejąca ścieżka v2/v3 bez nowego pola; candidate,
  rejected, retired, niepoprawny checksum albo dwa profile active → brak wyboru
  i kontrolowany wynik/błąd zgodny z kontraktem.
- Zmiana numeru, checksumy lub descriptorów profilu → inny identity i zakaz
  reuse poprzedniego manifestu.
- Pełna strona o innej barwie ramki, ale zgodnej strukturze → lokalny sukces
  `review_required` z dokazem rdzenia i bez `quads` importowych.
- Brak ramki/siatki, niepełny kadr lub aspect poza zakresem →
  `review_required` z dokładnym kodem, bez `registered`; uszkodzony snapshot
  → kontrolowany błąd inputu joba przed odczytem źródeł.
- Ręczny override zachowuje istniejące pierwszeństwo; stary job v2/v3 przechodzi
  dotychczasowy parser i manifest bez pola G03.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
# timeout: maks. 120 s na komendę
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services\api\tests\test_global_geometry_profile_snapshot_resolver.py services\api\tests\test_jobs_domain.py services\worker\tests\test_shape_geometry_v2_preflight.py services\worker\tests\test_page_geometry_preflight.py -q --basetemp .runtime\pytest-shape-v2-g03
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check services\api\src\game_predictor_api\domain\global_geometry_library.py services\api\src\game_predictor_api\storage\global_geometry_profile_snapshot_resolver.py services\api\src\game_predictor_api\application\jobs.py services\worker\src\game_predictor_worker\images\shape_geometry_v2\preflight.py services\worker\src\game_predictor_worker\images\page_geometry_preflight.py services\api\tests\test_global_geometry_profile_snapshot_resolver.py services\worker\tests\test_shape_geometry_v2_preflight.py
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m mypy --no-incremental --follow-imports=skip services\api\src\game_predictor_api\domain\global_geometry_library.py services\api\src\game_predictor_api\storage\global_geometry_profile_snapshot_resolver.py services\api\src\game_predictor_api\application\jobs.py services\worker\src\game_predictor_worker\images\shape_geometry_v2\preflight.py
```

## Risks / open questions

- G06 nie tworzy jeszcze aktywnego profilu. Testy używają kontrolowanego
  snapshotu/mocked repository; w zwykłej instalacji resolver nie zmienia
  historycznego preflightu aż do atomowej aktywacji G07.
- Wspólny profile nie zastępuje ręcznych danych ani nie ustanawia progu jakości
  automatu. G07 dopiero kwalifikuje wersję, a G05 określi użycie propozycji w
  pilocie.

## Outcome

Wypełnia agent po pracy.

### Changed

- Dodano resolver aktywnego profilu z pełną kontrolą checksumy profilu i jego
  dowodów, bez limitu historii kandydatów oraz bez routingu po grze.
- Snapshot v4 wiąże descriptory osobną checksumą; parser workera odrzuca
  każdą zmianę descriptorów pod wcześniejszym checksumem profilu.
- Preflight v4 używa tylko lokalnego verifiera G02. Nie tworzy legacy
  registrara ani nie ładuje jego kotwic, więc niedostępna historyczna kotwica
  nie blokuje poprawnego joba v4.

### Verification results

- 67 testów preflightu, resolvera, repozytorium i regresji jobów przeszło.
- Ruff przeszedł dla zmienionego pionu. Ograniczony mypy czterech nowych i
  zmienionych modułów źródłowych przeszedł; zachowane ostrzeżenie konfiguracji
  optional ONNX nie dotyczy G03.
- Astra Medium znalazła trzy P2 (limit 100 kandydatów, obowiązkowe legacy
  kotwice oraz brak pełnej kontroli checksumy). Wszystkie naprawiono wraz z
  testami; końcowy re-audyt nie ma P0–P3.

### Not completed

- Aktywacja/kwalifikacja profilu, konfiguracja gry i pilot importu pozostają w
  G04, G07 i G05.

### Documentation updates

- Uaktualniono `CURRENT_STATE.md`, `DATA_MODEL.md`,
  `VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md` i D-423.

### Recommended next task

- G04 — tworzenie i gotowość gry.
