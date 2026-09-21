---
title: TASK-0602 Shape geometry v2 corpus and v1.1 baseline
status: done
last_updated: 2026-09-21
---

# TASK-0602 — Korpus, protokół pomiaru i baseline geometrii shape v2

## Status

`done`

## Goal

Udostępnić checksum-bound, rozdzielony corpus i read-only baseline istniejącego
silnika `selective_board_review_v1_1` dla gier 777, Blazing, Gang, Reels i
Mumie, bez dostępu wykonawcy do materiału acceptance.

## Context

Silnik `shape_frame_geometry_v2_0` nie istnieje jeszcze. G00 ustanawia dane,
metryki i odtwarzalny punkt odniesienia, aby kolejne zadania nie stroiły
algorytmu na materiale odbiorowym ani nie mieszały błędów v1.1 z regresjami v2.

## Dependencies / entry conditions

- Właściciel zaakceptował `TEMP PLAN V2 GEOMETRY.md` 2026-09-21.
- Istniejący offline rejestrator `VerifiedPageRegistrar` jest źródłem pomiaru
  v1.1; nie wolno wykonywać joba, migracji, importu ani zapisu do bazy.
- Rzeczywiste obrazy i ręczne anotacje nie są częścią repozytorium. Ich brak
  ma dawać `not_evaluable`, a nie syntetyczny wynik lub niejawne użycie danych
  produkcyjnych.

## Recommended execution

`gpt-5.6-terra`, reasoning `xhigh`: task łączy ochronę splitów,
deterministyczną proweniencję i użycie istniejącej geometrii. Niezależny review
`gpt-6-astra`, reasoning `medium`, jest obowiązkowy przed commitem. Każdy
błąd krytyczny (wyciek acceptance, pomieszanie gry, fałszywy automat, utrata
kolejności, nieodtwarzalny snapshot) zatrzymuje plan; pozostałe uwagi są
naprawiane i ponownie audytowane w tym tasku.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `TEMP PLAN V2 GEOMETRY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/quality/BOARD_CELL_GEOMETRY_V19_ROLLOUT.md`

## Scope

- Kontrakt corpusów v2 z oddzielnym manifestem `executor` (development i
  calibration) oraz `acceptance` (wyłącznie odbiór), SHA-256, rodziną nagrania,
  rolą danych, kolejnością źródła i topologią 3 × 5.
- Read-only zamrożenie inwentarza, wykrywanie driftu, duplikatów bajtowych i
  rodzin przekraczających split; raport nie zalicza duplikatu jako niezależnego
  dowodu.
- Protokół ręcznych anotacji niezależnych od predykcji oraz deterministyczny
  wybór jednej pełnej kotwicy v2 na grę z developmentu.
- Read-only runner baseline v1.1: maksymalnie dziesięć źródeł na grę,
  z przypiętym istniejącym profilem, EXIF transpose, pełnym wynikiem rejestracji
  lub kontrolowanym powodem braku wyniku oraz możliwością byte-for-byte checku.
- Wersjonowany dokument definicji metryk i lokalne przykłady bez JPEG-ów,
  ścieżek hosta i danych acceptance.

## Out of scope

- Implementacja, API, UI, migracja, preflight produkcyjny, worker lub rollout
  `shape_frame_geometry_v2_0`.
- Dobór progów, strojenie, dostęp do zdjęć/anotacji/wyników acceptance,
  aktywacja automatu, biblioteka wspólnej wiedzy oraz import danych użytkownika.
- Zmiana działania albo fingerprintów v1.0/v1.1.

## Acceptance criteria

- [x] Manifest wykonawczy odrzuca split acceptance, a manifest acceptance
  odrzuca development/calibration; baseline nie przyjmuje manifestu acceptance.
- [x] Każde źródło ma bezpieczną ścieżkę względną, SHA-256, grę, split,
  rodzinę nagrania, deterministyczny ordinal i deklarację topologii 3 × 5.
- [x] Zamrożony inwentarz wykrywa zmianę bajtów, źródła, rodziny, splitu,
  duplikaty przez granicę acceptance oraz podział jednej rodziny między splity.
- [x] Wybór kotwicy jest niezależny od predykcji i stabilny względem kolejności
  wpisów; ucięcie pionowe, niepełna strona albo inna topologia nie kwalifikują
  źródła.
- [x] Baseline v1.1 jest ograniczony do dziesięciu źródeł na grę, zachowuje
  wynik i profile w checksum-bound raporcie, normalizuje EXIF i nie mutuje
  corpusów ani danych aplikacji.
- [x] Brak lokalnych danych lub profilu kończy raport jawnie `not_evaluable` /
  `not_configured`; nie jest sukcesem i nie odblokowuje kolejnego etapu.

## Technical notes

`ShapeGeometryCorpusManifest` pozostaje framework-free i jest używany tylko
przez narzędzia jakości. Każdy manifest ma pojedynczą widoczność: `executor`
zawiera wyłącznie development/calibration, a `acceptance` tylko acceptance.
Jedynie niezależny operator może porównać dwa już zamrożone inwentarze;
narzędzie uruchamiające baseline przyjmuje wyłącznie manifest `executor`.

Topologia strony jest jawna: układ plansz 3 × 3 i komórki planszy 3 × 5,
z ciągłymi aktywnymi slotami w kolejności row-major. `captureFamilyId` jest
zadeklarowaną relacją podobnych klatek; ten sam identyfikator nie może wystąpić
w różnych splitach. Identyczny SHA może być zgłoszony w raporcie jako kopia,
ale nie zwiększa niezależnej liczności i nie może przekroczyć granicy
executor/acceptance.

Ręczna anotacja opisuje kompletność strony przed wykonaniem predykcji. Kotwica
może pochodzić tylko z pełnej, ręcznie zakwalifikowanej strony development o
zgodnej topologii i `anchorCandidate=true`; wybór sortuje `captureFamilyId`,
`sourceOrdinal`, a następnie SHA. Raport zapisuje wybraną kotwicę i przyczyny
odrzucenia wcześniejszych kandydatów.

Runner baseline ładuje jedynie istniejący, przypięty profil
`VerifiedPageRegistrar` i obrazy opisane w manifeście wykonawczym. Ścieżki są
sprawdzane pod corpus rootem, obraz przechodzi EXIF transpose do RGB, a wynik
jest `registered`, `review_required`, `source_error` albo `not_configured`.
Nie porównuje quadów z niezatwierdzoną tolerancją: G01 ustali bramki. Check
ponownie wylicza identyczny raport i porównuje kanoniczne bajty.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/images/shape_geometry_v2/corpus.py`.
- Nowe: `services/worker/tests/test_shape_geometry_v2_corpus.py`.
- Nowe: `scripts/freeze_shape_geometry_v2_corpus.py`.
- Nowe: `scripts/run_shape_geometry_v2_v11_baseline.py`.
- Nowe: `ai_docs/quality/SHAPE_GEOMETRY_V2_MEASUREMENT_PROTOCOL.md`.
- Nowe: lokalne przykłady manifestu i anotacji w `ai_docs/quality/`.
- Istniejące: `TEMP PLAN V2 GEOMETRY.md`, `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/process/CURRENT_STATE.md` i ta karta.

## Test cases

- Manifest o niewłaściwej widoczności, źródle poza rootem, nieprawidłowym SHA,
  nieciągłym slocie lub topologii innej niż 3 × 5 jest odrzucony.
- Zmiana JPEG-a, duplikat przez boundary i jedna rodzina w dwóch splitach
  blokują kontrolę splitów; kopia w jednym splicie jest jawnie raportowana.
- Permutacja wpisów nie zmienia inwentarza ani kotwicy; kandydat z ucięciem
  góra/dół, niepełną stroną lub inną topologią nie może zostać kotwicą.
- Syntetyczna pełna strona z przypiętym profilem v1.1 daje odtwarzalny wynik;
  uszkodzony obraz i brak profilu pozostają kontrolowanym wynikiem bez mutacji.
- Baseline odrzuca manifest acceptance, limit większy niż 10 i różnicę względem
  przypiętego raportu.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_shape_geometry_v2_corpus.py -q --basetemp .runtime/pytest-shape-v2
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/shape_geometry_v2 scripts/freeze_shape_geometry_v2_corpus.py scripts/run_shape_geometry_v2_v11_baseline.py services/worker/tests/test_shape_geometry_v2_corpus.py
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/images/shape_geometry_v2/corpus.py
```

## Risks / open questions

- Realne corpusy, profile i anotacje są operator-owned. G00 dostarcza
  fail-closed narzędzie i nie może tworzyć zastępczych danych.
- Podobne, ale nieidentyczne klatki wymagają poprawnego `captureFamilyId` od
  operatora; automatyczny hash nie zastępuje tej klasyfikacji.

## Outcome

Utworzono framework-free kontrakt corpusów `shape_geometry_v2`, dwa lokalne
formaty manifestów, zamrożony inwentarz oraz narzędzia do kontroli granicy
splitów i odtwarzalnego baseline istniejącego `selective_board_review_v1_1`.
Korpus executor i acceptance są rozdzielone fail-closed; runner odrzuca
acceptance przed odczytem inwentarza lub obrazu. Baseline odczytuje JPEG tylko
z aktualnie atestowanych bajtów, normalizuje EXIF do RGB, ogranicza pomiar do
dziesięciu źródeł na grę i nie zapisuje danych aplikacji.

Dodano protokół metryk, lokalne przykłady bez obrazów oraz anotacje niezależne
od predykcji. Brak rzeczywistych corpusów, profili i anotacji w repozytorium
celowo daje `not_evaluable` lub `not_configured`; G00 nie tworzy danych
zastępczych i nie odblokowuje G01.

Weryfikacja zakończona powodzeniem:

```powershell
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_shape_geometry_v2_corpus.py -q --basetemp .runtime/pytest-shape-v2
# 9 passed
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check --no-cache services/worker/src/game_predictor_worker/images/shape_geometry_v2 services/worker/tests/test_shape_geometry_v2_corpus.py scripts/freeze_shape_geometry_v2_corpus.py scripts/run_shape_geometry_v2_v11_baseline.py
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m mypy --no-incremental --follow-imports=skip services/worker/src/game_predictor_worker/images/shape_geometry_v2/corpus.py
```

Końcowy niezależny audyt `gpt-6-astra`, reasoning `medium`, nie wykazał
usterek P0–P2. Następny krok G01 wymaga operator-owned executor corpusu,
przypiętych profili v1.1 i anotacji; po analizie użytkownik zatwierdza bramki
liczbowe przed G02.
