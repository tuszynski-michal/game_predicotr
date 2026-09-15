---
title: Odtwarzanie ukończonego preflightu po zmianie profilu uczenia
status: done
last_updated: 2026-09-15
---

# TASK-0550 — odtwarzanie ukończonego preflightu po zmianie profilu uczenia

## Status

`done`

## Goal

Ukończony preflight geometrii ma pozostać dostępny w raporcie swojego stagingu
i odblokowywać dalszą operację, nawet gdy późniejsza ręczna korekta w innym
katalogu zmieni bieżący profil uczenia częściowych siatek.

## Context

Job `ce92281c-cca1-4ba7-bb1e-5354f14e5afe` dla stagingu
`128269 - 149634 cut` zakończył się z niezmiennym manifestem geometrii. Przed
ponownym otwarciem raportu zapisano trzy korekty, których checksumy nie
występują w manifeście źródeł tego stagingu. Zmieniło to globalny profil
uczenia z 31 do 34 rewizji. Backend porównuje pełny snapshot lateral ukończonego
joba z profilem wyliczonym w chwili otwierania raportu, więc nie zwraca gotowego
wyniku. Ponowne kliknięcie utworzyło job
`55fde594-935d-4e0b-8d34-e3a1088dc74b` dla tego samego stagingu.

## Dependencies / entry conditions

- Manifest ukończonego preflightu jest checksumowany i przypięty do gry,
  stagingu, manifestu źródeł oraz snapshotu polityki.
- Snapshoty lateral v1, v2 i v3 mają ścisłą walidację kontraktu.
- Jawne uruchomienie nowego preflightu nadal używa aktualnego profilu uczenia.

## Recommended execution

`gpt-6-astra` z reasoning `high`. Zmiana dotyczy granicy trwałości joba i
tożsamości raportu; wymaga zachowania ścisłej walidacji wersjonowanego snapshotu
oraz testu scenariusza po zmianie profilu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0540-accept-current-lateral-partial-preflight-identity.md`
- `ai_docs/tasks/completed/0543-ready-staging-lifecycle-label.md`

## Scope

- Odtwarzać najnowszy preflight należący do gry, stagingu i manifestu źródeł,
  jeżeli ma brak wariantu dla raportu standardowego albo kompletny, znany
  snapshot lateral dla raportu v4.
- Nie porównywać przypiętego profilu uczenia ukończonego joba z profilem
  wyliczonym później przy samym otwarciu raportu.
- Nadal odrzucać obcy wariant, niepełny snapshot, nieznaną wersję polityki,
  inną grę, staging lub checksumę manifestu.
- Dodać regresję zmiany profilu uczenia po utworzeniu joba oraz zachować
  idempotencję jawnego uruchomienia przy niezmienionych wejściach.
- Uaktualnić wymagania, kontrakt API i stan projektu.

## Out of scope

- Retry, anulowanie albo usuwanie któregokolwiek z istniejących jobów.
- Modyfikacja manifestów, ręcznych korekt lub danych stagingu.
- Zmiana algorytmu wykrywania geometrii i zawartości snapshotów v1/v2/v3.
- Automatyczne uruchamianie nowego preflightu przy otwarciu raportu.

## Acceptance criteria

- [x] Ukończony preflight v2 pozostaje gotowy po zmianie globalnego profilu
      uczenia na nowszy snapshot.
- [x] Ukończony preflight v3 z przypiętym starszym profilem również pozostaje
      gotowy.
- [x] Nieznany lub dryfujący snapshot nadal nie pasuje do raportu.
- [x] Raport standardowy nie przyjmuje joba lateral, a raport lateral nie
      przyjmuje joba standardowego.
- [x] Odczyt raportu nie tworzy joba; jawna akcja przygotowania zachowuje obecną
      idempotencję aktualnych wejść.
- [x] Skoncentrowane testy API i domeny przechodzą.

## Technical notes

`get_page_geometry_preflight_by_source_selection` używa dziś
`_current_lateral_partial_policy(...).to_payload()` jako kryterium wyszukania.
To kryterium miesza zgodność wariantu z aktualnością profilu uczenia. Odtwarzanie
ma zamiast tego parsować przypięty payload przez
`LateralPartialGeometrySnapshot.from_payload`; parser potwierdza dokładny zestaw
pól, wersję, stałe i checksumę. Najnowszy zgodny job zachowuje pierwszeństwo.
Tworzenie nowego joba nadal oblicza bieżący snapshot i jego input key.

## Expected files

- `services/api/src/game_predictor_api/application/jobs.py`
- `services/api/tests/test_image_imports_api.py`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Test cases

- Historyczny v2 + późniejszy bieżący profil → historyczny job jest zwracany.
- Historyczny v3 + inny późniejszy profil → historyczny job jest zwracany.
- Nowszy niepełny/nieznany lateral payload → jest pomijany, starszy poprawny
  snapshot nadal może zostać odtworzony.
- Standardowy raport + brak lateral payload → dopasowanie.
- Raport v4 + brak lateral payload → brak dopasowania.

## Verification

```powershell
python -m pytest services/api/tests/test_image_imports_api.py -q
python -m pytest services/api/tests/test_jobs_domain.py -q
python -m ruff check services/api/src/game_predictor_api/application/jobs.py services/api/tests/test_image_imports_api.py
python -m mypy services/api/src/game_predictor_api/application/jobs.py
```

## Risks / open questions

- Zwracany manifest pozostaje wynikiem starszego, ale dokładnie przypiętego
  profilu. Jest odtwarzalny i bezpieczny; późniejsze dane uczące wpływają na
  nowe jawnie uruchomione preflighty, nie unieważniają historycznego artefaktu.
- Brak pytań blokujących.

## Outcome

### Changed

- Wspólny predykat odtwarzania sprawdza brak wariantu standardowego albo
  kompletny, znany snapshot lateral v1/v2/v3. Nie porównuje przypiętego profilu
  z profilem wyliczonym później.
- Raport browser stagingu i dopasowanie istniejącego importu używają tej samej
  reguły. Nowe jawnie uruchamiane joby nadal przypinają aktualny profil i pełny
  input key.
- Nie zmieniono jobów, manifestów, korekt ani danych użytkownika.

### Verification results

- Regresje lookupu wariantu v4: 3/3 passed, w tym ukończony preflight po
  zmianie profilu oraz odrzucenie niepełnego snapshotu.
- Testy domeny jobów: 19/19 passed.
- Ruff check i format dla zmienionego kodu: passed.
- Skoncentrowany mypy dla `application/jobs.py`: passed.
- Pełny `test_image_imports_api.py`: 38 passed; jeden wcześniejszy test listy
  korekt nie przechodzi, ponieważ jego lokalny fake `OverrideSnapshot` nie ma
  metody `partial_grid_training_profile` wymaganej przez kod TASK-0549. Błąd
  nie dotyczy zmienionej ścieżki i pozostał poza tym taskiem.
- Pełny typecheck repozytorium nadal zgłasza 36 wcześniejszych błędów w siedmiu
  plikach spoza zakresu; zmieniony moduł przechodzi kontrolę osobno.
- Działające API odtworzyło job `55fde594-935d-4e0b-8d34-e3a1088dc74b`
  jako `completed`, `artifactReady=true`, bez blockera. Dwa kolejne odczyty
  utrzymały liczbę jobów walidacji 36→36.

### Not completed

- Nie naprawiano wcześniejszej atrapy testowej ani wcześniejszych błędów
  pełnego typechecku, zgodnie z granicą bieżącego taska.
- Nie uruchamiano retry ani nowego preflightu i nie modyfikowano danych.

### Documentation updates

- Zaktualizowano wymagania importu, zachowanie Admina, kontrakt API oraz
  `CURRENT_STATE.md`.

### Recommended next task

- Osobno uzupełnić fake `OverrideSnapshot` w starszym teście i uporządkować
  istniejący dług techniczny pełnego typechecku.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0550 — odtwarzanie ukończonego preflightu po zmianie profilu uczenia | gpt-6-astra | high | Zmiana naprawia trwałość checksumowanego workflowu i musi zachować ścisłą granicę tożsamości wariantu. | Nie; parser kontraktu i regresje v2/v3 chronią granicę. |
