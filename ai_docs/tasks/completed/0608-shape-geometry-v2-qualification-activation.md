---
title: Kwalifikacja i aktywacja wspólnej geometrii shape v2
status: done
task_id: TASK-0608
---

# TASK-0608 — kwalifikacja i aktywacja wspólnej geometrii shape v2

## Status

`done`

## Goal

Deterministycznie kwalifikować kandydat wspólnego profilu geometrii i atomowo
aktywować go tylko po integralnym, pełnym raporcie replayu, regresji i transferu.

## Context

G06 przechowuje niezmienne kandydaty descriptor-only, a G03 i G04 potrafią
bezpiecznie użyć jednego profilu `active`. Brakuje bramki, która po korekcie
sprawdza kandydata i publikuje nową wersję bez utraty poprzedniej aktywnej
wersji. G05 będzie dostarczać kandydaty oraz rzeczywiste raporty z pilota;
G07 ma przygotować wspólny, trwały mechanizm kwalifikacji bez umieszczania w
bibliotece obrazów, `game_id`, OCR, sekwencji ani lokalnych kotwic.

## Dependencies / entry conditions

- G06 (`v0.10.346`) udostępnia append-only profile `candidate`, `active`,
  `rejected` i `retired`, integralność checksumm oraz częściowy indeks jednego
  aktywnego profilu na rodzinę/topologię.
- G03 (`v0.10.347`) i G04 (`v0.10.348`) używają wyłącznie integralnego,
  pojedynczego profilu `active` oraz fail-closed reagują na brak i konflikt.
- Nie ma w repozytorium operator-owned corpusów ani raportów kwalifikacji;
  mechanizm musi zachować kandydata w stanie `candidate` jako `not_evaluable`,
  a nie tworzyć fikcyjnego wyniku lub blokować tworzenie gry.

## Recommended execution

gpt-5.6-terra, xhigh — zadanie wymaga spójnej reguły jakości, niezmiennego
audytu kwalifikacji i atomowej zmiany dwóch statusów pod konkurencją.
Niezależny audyt gpt-6-astra, medium jest obowiązkowy po implementacji;
P0/P1 zatrzymuje plan, a P2/P3 trzeba naprawić i poddać re-audytowi przed
zamknięciem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md` (G07)
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `services/api/src/game_predictor_api/domain/global_geometry_library.py`
- `services/api/src/game_predictor_api/storage/global_geometry_library_repository.py`

## Scope

- Dodać append-only, checksummowany rekord kwalifikacji kandydata oraz
  idempotentny receipt komendy. Rekord zawiera tylko wersję polityki,
  checksumy snapshotów, liczniki i krótkie referencje proweniencji; nie
  zawiera obrazów, ścieżek, danych importu, `game_id`, symboli ani kotwic.
- Zaimplementować czystą politykę kwalifikacji: odtworzenie integralności
  profilu, zgodność rodziny/topologii, kompletny replay, regresja względem
  poprzedniego profilu i test transferu na referencji gry spoza wkładu
  kandydata. Każdy brakujący lub niespójny dowód daje `not_evaluable`; błąd
  jakości daje `rejected` z trwałym kodem powodu.
- W jednym commitcie transakcji kwalifikator blokuje odpowiednie rekordy,
  zapisuje wynik, a wyłącznie dla wyniku `passed` wycofuje poprzedni `active`
  do `retired` i promuje wskazany `candidate` do `active`. Błąd zapisu,
  konflikt lub nieaktualny stan musi wycofać całość i zachować poprzedni
  profil aktywny.
- Udostępnić serwis aplikacyjny jako wewnętrzną granicę wywoływaną przez
  późniejszy pilot. Nie wystawiać jeszcze UI, endpointu ani automatycznego
  importu: G05 dostarczy wykonanie na zatwierdzonych korektach i danych.
- Uzupełnić model danych i decision log, a testy objąć przypadki sukcesu,
  jakościowej odmowy, braku dowodów, leaku transferu, retry oraz konkurencji.

## Out of scope

- Pobieranie obrazów, uruchomienie realnego corpusów, automatyczne tworzenie
  kandydata z korekty i pilot Mumie → Gang (G05).
- API/UI do ręcznej aktywacji, lokalne profile i aktywacje grid calibration.
- Wykonanie migracji na danych użytkownika, import domenowy lub Treasure/v3/v4.

## Acceptance criteria

- [ ] Kandydat przechodzi do `active` tylko z integralnym, kompletnym raportem
  zgodnym z rodziną/topologią i polityką; poprzedni `active` jest wtedy
  `retired` w tej samej transakcji.
- [ ] Brak raportu, niepełny replay, checksum drift albo udział testowanej gry
  w wkładzie profilu nie aktywuje profilu i pozostawia poprzednią wersję.
- [ ] Regresja lub błąd jakości zapisuje trwały wynik/reason code i oznacza
  wyłącznie wskazanego kandydata jako `rejected`; nie wybiera starszego
  kandydata ani nie ukrywa błędu jako sukcesu.
- [ ] Retry identycznej komendy zwraca pierwotny wynik; inny payload z tym
  samym kluczem jest konfliktem, a współbieżna kwalifikacja nie daje dwóch
  profili `active`.
- [ ] Biblioteka, snapshot resolver i gotowość G04 zachowują descriptor-only
  izolację oraz w czasie błędu nadal fail-closed.
- [ ] Migracja, testy domeny/repozytorium, lint, typecheck i audyt Astra
  Medium potwierdzają zmianę.

## Technical notes

Nowy raport kwalifikacji jest wejściem z późniejszego workerowego replayu, ale
kwalifikator sam odtwarza checksumę kandydata i porównuje wynik z aktualnym
stanem pod blokadą. `not_evaluable` jest trwałym wynikiem audytowym bez zmiany
statusu kandydata; `rejected` przechodzi przez istniejący dozwolony trigger.
Tylko `passed` może wykonać kolejność `active → retired`, potem
`candidate → active`; całość pozostaje w jednej transakcji, więc naruszenie
unikalnego indeksu lub triggera wycofuje oba przejścia. Historyczne joby mają
przypięte snapshoty i nie są zmieniane przez aktywację.

## Expected files

- Istniejące: `domain/global_geometry_library.py`,
  `storage/global_geometry_library_repository.py`, modele SQLAlchemy i migracje
  Alembic biblioteki globalnej.
- Nowe: moduł polityki/serwisu kwalifikacji oraz testy domeny i repozytorium.
- Istniejące: `DATA_MODEL.md`, `VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`,
  `CURRENT_STATE.md`, `DECISION_LOG.md`.

## Test cases

- Integralny kandydat i pełny raport bez regresji oraz bez leaku transferu →
  nowy `active`, poprzedni `active` → `retired`, trwały receipt i wynik.
- Brak raportu albo niepełny replay → `not_evaluable`, kandydat i poprzedni
  `active` bez zmian.
- Niepoprawna checksum, regresja lub leak target game → wynik `rejected` z
  kodem, tylko kandydat odrzucony, poprzedni `active` zachowany.
- Retry, konflikt idempotency, aktualizacja po zmianie aktywnego profilu i
  błąd flush → stabilny wynik albo rollback wszystkich zapisywanych stanów.
- Migracja instaluje append-only ochronę i bezpieczny downgrade z blokadą
  danych; resolver G03/G04 nie interpretuje niezaliczonego kandydata jako active.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
# timeout: maks. 120 s na komendę
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services\api\tests\test_global_geometry* services\api\tests\test_shape_geometry_game_readiness.py -q --basetemp .runtime\pytest-shape-v2-g07
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check services\api\src\game_predictor_api\domain\global_geometry_library.py services\api\src\game_predictor_api\storage\global_geometry_library_repository.py
```

## Risks / open questions

- Rzeczywisty raport powstanie dopiero z operator-owned corpusów w G05. Do tego
  czasu nie ma aktywacji przez brak mianownika; nie jest to negatywna ocena
  kandydata.
- G07 nie może zaufać samej deklaracji z UI. Raport stanowi zamrożony,
  checksummowany artefakt wejściowy, a polityka ponownie sprawdza jego związek
  z kandydatem i jego proweniencją.

## Outcome

Wypełnia agent po pracy.

### Changed

- Pending.

### Verification results

- Pending.

### Not completed

- Pending.

### Documentation updates

- Pending.

### Recommended next task

- G05 — pilot importu i korekt.
