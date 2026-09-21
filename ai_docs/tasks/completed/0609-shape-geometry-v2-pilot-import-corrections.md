---
title: Pilot korekt i transferu wspólnej geometrii shape v2
status: done
task_id: TASK-0609
---

# TASK-0609 — pilot korekt i transferu wspólnej geometrii shape v2

## Status

`done`

## Goal

Dostarczyć deterministyczny, lokalny workflow pilota „istniejący profil → Mumie → zaakceptowana korekta → Gang”, który tworzy wyłącznie descriptorowego kandydata i raport kwalifikacji G07 albo jawny wynik `not_evaluable`.

## Context

G00–G04 potrafią mierzyć korpus i lokalnie weryfikować profil, G06 przechowuje kandydatów, a G07 bezpiecznie je kwalifikuje. Brakuje spójnego wejścia z zatwierdzonej korekty Mumii, pomiaru transferu do Gangu i wewnętrznego przekazania prawidłowego kandydata oraz raportu do istniejących granic zapisu. Operator-owned corpus nie jest jeszcze częścią repozytorium, więc implementacja musi być kompletna i testowalna bez fabrykowania wyników na danych produkcyjnych.

## Dependencies / entry conditions

- G00 (`v0.10.338`) dostarcza read-only manifest, zamrożony inwentarz, anotacje i rozdział `development`/`calibration`/`acceptance`.
- G02 (`v0.10.345`) oraz G03 (`v0.10.347`) zachowują lokalną weryfikację pikseli i obowiązkowe ręczne potwierdzenie.
- G06 (`v0.10.346`) przyjmuje tylko poprawnego, descriptor-only kandydata; G07 (`v0.10.349`) sprawdza raport i atomowo aktywuje wyłącznie wynik `passed`.
- Rzeczywiste źródła Mumii i Gangu, ich zamrożone snapshots oraz decyzje operatora pozostają operator-owned. Ich brak nie blokuje implementacji, lecz kończy konkretny pilot `not_evaluable`.

## Recommended execution

gpt-5.6-terra, xhigh — pion łączy rozdzielone dane korpusowe, korekty operatora, proweniencję transferu oraz dwie istniejące granice zapisu bez mieszania magazynów gier. Niezależny audyt gpt-6-astra, medium jest obowiązkowy po implementacji; P0/P1 zatrzymuje plan, a P2/P3 trzeba naprawić i poddać re-audytowi przed zamknięciem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md` (G05)
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `services/worker/src/game_predictor_worker/images/shape_geometry_v2/corpus.py`
- `services/worker/src/game_predictor_worker/images/shape_geometry_v2/experiment.py`
- `services/api/src/game_predictor_api/domain/global_geometry_library.py`
- `services/api/src/game_predictor_api/domain/global_geometry_qualification.py`

## Scope

- Dodać wersjonowany, local-only kontrakt pilota przypinający manifest executor, inventory i anotacje oraz pięć uporządkowanych etapów: zaakceptowaną korektę Mumii, replay Mumii, regresję istniejącego profilu, regresję kandydata oraz transfer do Gangu albo innej zgodnej gry. Regresja obejmuje pełną, jawną kohortę wcześniejszych gier.
- Weryfikować kompletność każdej fazy wyłącznie na źródłach `development` i `calibration` wskazanych przez manifest. `acceptance`, brak źródła, drift checksumy, inna gra albo niezatwierdzona korekta dają deterministyczne `not_evaluable`; nie powstaje fikcyjna metryka ani zapis.
- Z poprawnej, zatwierdzonej korekty budować wyłącznie istniejący kontrakt `GlobalGeometryCandidate`; wejściowe identyfikatory i checksumy źródeł pozostają w lokalnym raporcie, a kandydat i payload G07 nie zawierają obrazów, ścieżek, `game_id`, OCR, symboli, sekwencji, layoutów ani lokalnych kotwic.
- Z pełnych obserwacji budować raport G07 z rzeczywistymi mianownikami replayu, regresji i transferu. Raport wiąże checksumy snapshotów, bieżącą checksumę baseline oraz proweniencję, ale nie zastępuje walidacji G07.
- Dodać wewnętrzny serwis aplikacyjny, który przekazuje zbudowanego kandydata do istniejącej biblioteki, a następnie kwalifikuje dokładnie ten zwrócony profil przez G07 z rozłącznymi kluczami idempotencji. Nie dodawać endpointu, UI, joba importowego ani transakcji obejmującej magazyny gier.
- Dodać lokalne polecenie do generowania raportu pilota z przekazanych ścieżek artefaktów operatora. Polecenie nie łączy się z bazą ani nie publikuje profilu.

## Out of scope

- Import layoutów, tworzenie source revisions, automatyczne zatwierdzanie quadów, modele symboli, OCR, payouty, sekwencje i jakikolwiek zapis do `game_data_v2`.
- Endpoint lub ekran Admina do uruchamiania pilota, uruchomienie na danych użytkownika, publikacja do bazy przez polecenie lokalne oraz migracja Alembic.
- Użycie `acceptance`; niezależny odbiór i decyzja o wydaniu należą do G08.
- Treasure i strony bez pełnej ramki.

## Acceptance criteria

- [ ] Pilot wymusza kolejność istniejąca wiedza → Mumie → zaakceptowana korekta → transfer do gry spoza wkładu i nie dopuszcza zastąpienia jej nazwą gry, kolorem ramki ani lokalną kotwicą.
- [ ] Każda faza ma checksummowany snapshot, a każda obserwacja jest przypięta do checksumy badanego profilu. Wynik osobno liczy oczekiwane, ocenione, poprawne i błędne automaty, review, korektę, potwierdzenie oraz czas operatora; brak, drift, `acceptance` lub niekompletność daje `not_evaluable` bez fałszywego sukcesu.
- [ ] Kandydat powstaje tylko po potwierdzonej korekcie i spełnia zamknięty descriptor-only kontrakt G06; transfer target nie może wystąpić we wkładzie kandydata.
- [ ] Pełny wynik przekazuje kandydat do istniejącego repozytorium i raport do G07 przez wewnętrzny serwis; retry zachowuje idempotencję, a niepowodzenie nie miesza danych gier ani nie uruchamia importu.
- [ ] Polecenie lokalne jest read-only, deterministyczne po restarcie i nie przyjmuje ścieżek do payloadu globalnej biblioteki.
- [ ] Testy workera i API, lint, typecheck oraz audyt Astra Medium potwierdzają zmianę.

## Technical notes

Kontrakt obserwacji przechowuje lokalnie identyfikator źródła, jego SHA, checksumę badanego profilu, fazę, wynik automatu, czas aktywnej pracy operatora i fakt zaakceptowania korekty. Runner najpierw ponownie zamraża inwentarz i sprawdza manifest/anotacje, potem porównuje komplet oczekiwanych źródeł z obserwacjami w każdej mierzonej fazie. Dwa warianty regresji muszą ocenić identyczną, niepustą kohortę gier stanowiących wcześniejszą wiedzę; tylko wtedy wyprowadzana jest redukcja korekt, review i czasu operatora. `mummies_correction` może zasilić kandydata tylko po ręcznej akceptacji; `mummies_replay`, dwa warianty regresji i `transfer` wyprowadzają osobne snapshoty. Kandydat jest tworzony wyłącznie przez `build_global_geometry_candidate`, a raport przez `build_global_geometry_qualification_report`; oba istniejące kontrakty pozostają jedynymi właścicielami walidacji descriptorów oraz kwalifikacji.

Serwis aplikacyjny przyjmuje już zbudowany wynik pilota, używa dwóch rozłącznych UUID i wywołuje `create_candidate`, a następnie `qualify_candidate` dla profilu zwróconego przez repozytorium. Warstwę transakcyjną zapewnia istniejący caller sesji publicznego control plane; serwis nie otwiera magazynu gry. Brak danych zwraca lokalny wynik oczekiwania i nie wywołuje serwisu publikacji.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/images/shape_geometry_v2/pilot.py`, `scripts/run_shape_geometry_v2_pilot.py`, `services/api/src/game_predictor_api/application/global_geometry_pilot.py` oraz testy workera i API.
- Istniejące: `services/worker/src/game_predictor_worker/images/shape_geometry_v2/corpus.py`, `services/api/src/game_predictor_api/domain/global_geometry_library.py`, `services/api/src/game_predictor_api/domain/global_geometry_qualification.py`, dokumentacja architektury i stanu.

## Test cases

- Kompletne Mumie i Gang, zaakceptowana korekta i transfer bez wkładu targetu → descriptorowy kandydat, pełny raport G07 z poprawnymi mianownikami oraz przekazanie do serwisów istniejącej biblioteki.
- Brak akceptacji korekty, brak źródła w fazie, niespójny SHA, źródło `acceptance`, target we wkładzie albo niezgodne game ref → `not_evaluable` lub stabilny błąd przed zapisem.
- Błędny automat jest liczony niezależnie od review i korekty; regresja zawiera porównywalne zestawy baseline/kandydat.
- Retry identycznego przekazania używa wyników repozytorium; ponowienie z tym samym kluczem i inną treścią kończy się konfliktem z istniejącej warstwy.
- Polecenie uruchomione drugi raz z tymi samymi artefaktami daje bitowo identyczny JSON, a bez danych operatora nie inicjuje zapisu ani importu.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
# timeout: maks. 120 s na komendę
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services\worker\tests\test_shape_geometry_v2_pilot.py services\api\tests\test_global_geometry_pilot.py services\api\tests\test_global_geometry_qualification.py -q --basetemp .runtime\pytest-shape-v2-g05
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check services\worker\src\game_predictor_worker\images\shape_geometry_v2\pilot.py services\api\src\game_predictor_api\application\global_geometry_pilot.py scripts\run_shape_geometry_v2_pilot.py
```

## Risks / open questions

- Bez operator-owned snapshots i akceptacji wynik lokalnego commandu jest celowo `not_evaluable`; nie jest dowodem skuteczności ani powodem aktywacji.
- Semantyczne wybranie innej zgodnej gry transferowej jest wejściem kontraktu, nie listą zakodowaną w silniku. Pierwszy materiał ma używać Mumii i Gangu zgodnie z planem.

## Outcome

Ukończono 2026-09-22.

### Changed

- Dodano lokalny, deterministyczny runner i polecenie G05. Runner nie łączy się z bazą ani nie publikuje; buduje wyłącznie descriptorowego kandydata i raport G07 albo wynik `not_evaluable`.
- Obserwacje są przypięte do SHA źródła oraz checksumy baseline albo kandydata. Zmiana payloadu profilu, brak akceptacji korekty, niepełna faza, niezgodna kohorta albo `acceptance` blokują publikację.
- Regresja obejmuje pełny, jawny zbiór wcześniejszych gier i porównuje identyczne źródła. Wynik mierzy osobno automaty, review, korektę, potwierdzenie i czas operatora; redukcja pracy powstaje tylko dla kompletnej, niepustej kohorty.
- Dodano wewnętrzny serwis przekazujący poprawny wynik do istniejących granic G06/G07 przez rozłączne klucze idempotencji.

### Verification results

- 27 testów G05 oraz zależnych kwalifikacji przeszło w kontroli skoncentrowanej; szerszy zestaw corpus–biblioteka–kwalifikacja również przeszedł.
- Ruff, sprawdzenie formatu i ograniczony mypy dla zmienionych modułów przeszły.
- Astra Medium: pierwszy audyt zgłosił trzy P2, re-audyt jedną P2; wszystkie naprawiono z regresjami. Końcowy re-audyt nie ma P0–P3.

### Not completed

- Nie uruchomiono pilota na operator-owned corpusach ani nie opublikowano profilu. Nie dodano endpointu, UI, migracji, importu ani zmian `game_data_v2`.

### Documentation updates

- Zaktualizowano `DATA_MODEL.md`, `VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`, `DECISION_LOG.md` (D-426) oraz `CURRENT_STATE.md`.

### Recommended next task

- G08 — niezależny odbiór.
