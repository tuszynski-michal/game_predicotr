---
title: TASK-0323 read-only Structured Geometry feasibility spike
status: done
last_updated: 2026-08-30
---

# TASK-0323 — Read-only Structured Geometry Feasibility Spike

## Status

`done`

## Goal

Ocenić na ograniczonym, rzeczywistym korpusie, czy istniejący Structured OpenCV
ma wystarczający sygnał do dalszego rozwoju. Spike ma być audytowalny i
niedestrukcyjny; nie jest bramką 95/98 ani produkcyjnym rolloutem.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/V0_10_VIRTUAL_GEOMETRY_CUTOVER.md`
- `ai_docs/quality/m5-corpus-manifest.json`
- `ai_docs/quality/m5-golden-annotations.json`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Dodać wersjonowany, read-only kontrakt wejścia i raportu spike'a.
- Ograniczyć wykonanie do 30–50 rzeczywistych zdjęć i zweryfikowanych JPEG-ów.
- Porównać legacy detected quad, globalną known-layout projection i finalny
  wynik istniejącego Structured OpenCV.
- Raportować osobno dowody ramki, LSD, Hough, profile gradientów, regularność
  5×3 i pomocnicze pokrycie centrów symboli.
- Dla każdego zdjęcia generować source overlay, contact sheet 15 pól każdej
  planszy, reason codes, confidence components i checksummy artefaktów.
- Walidować reprezentatywność: kilka gier, pełne i częściowe strony, warunki
  jakościowe oraz historyczne false-success. Brak pokrycia kończy się
  `insufficient_corpus`, bez wymyślania GO/NO-GO.
- Uruchomić spike na istniejącym korpusie M5 i zapisać faktyczny raport wraz z
  jawnymi ograniczeniami tego korpusu.

## Out of scope

- Bez zmian bazy, migracji, API, OpenAPI i UI.
- Bez zapisów produkcyjnych, canonical ownership i verified labels.
- Bez przełączania feature flag, rolloutu albo pełnego backfillu.
- Bez strojenia produkcyjnych progów i bez deklarowania bramki 95/98.
- Bez keypoint rollout, segmentacji i treningu modelu.

## Acceptance criteria

- [x] Runner nie importuje warstwy storage/API i nie wykonuje zapisów poza
  wskazanym katalogiem raportu.
- [x] Manifest odrzuca mniej niż 30, więcej niż 50, zmienione JPEG-i i
  niekompletne adnotacje.
- [x] Reprezentatywność jest wyliczana, a nie zakładana.
- [x] Każdy aktywny slot ma porównanie trzech kandydatów oraz surowe sygnały.
- [x] Każde zdjęcie ma checksumowany overlay i contact sheet cropów.
- [x] Historyczny false-success jest jawnie oznaczony i nie jest pomijany.
- [x] Raport odróżnia wynik techniczny od gotowości korpusu.
- [x] Testy, Ruff, format i scoped mypy przechodzą.

## Compatibility strategy

Spike korzysta z publicznych kontraktów silnika 0310/0311, ale nie zmienia ich
wyniku ani konfiguracji. Zakodowane progi v1 są raportowane jako eksperymentalna
konfiguracja kandydata. Wynik spike'a nie zmienia istniejących jobów.

## Risks

- Wersjonowany korpus M5 zawiera 43 obrazy jednej gry i wyłącznie pełne strony.
  Jest wystarczający do wykonania technicznego, lecz nie do decyzji GO/NO-GO.
- Legacy `boardQuad` w M5 jest wynikiem historycznego detektora korpusu, nie
  pełnym replayem produkcyjnego joba v20; raport musi to opisać bez utożsamiania
  obu proveniencji.

## Planned commit

`v0.10.16 - add read-only geometry feasibility spike`

## Outcome

Dodano izolowany runner, wersjonowany manifest wejściowy oraz deterministyczny
raport `structured-geometry-feasibility-report-v1`. Runner zweryfikował 43
rzeczywiste JPEG-i i 387 adnotowanych plansz, po czym utworzył 43 diagnostyczne
JSON-y, 43 source overlaye i 43 contact sheets. Raport ma SHA-256
`ce94bcf8d643c0b7f7fea64e1e57861cc7902a07231ce26a29dc1bbb3f46fdb6`.

Korpus otrzymał stan `insufficient_corpus`: obejmuje tylko jedną grę, wyłącznie
pełne strony, jeden historyczny false-success i nie zawiera klasy blur. Nie
wyliczono ani nie zaliczono bramki 95/98; `rolloutAuthorized=false`.

Wynik techniczny:

- `genericGlobalProjection`: 0/387 dostępnych finalnych quadów;
- `knownLayoutProjection`: 323/324 dostępnych quadów poprawnych w
  eksperymentalnej granicy 2,5% przekątnej;
- `oracleInitializedLocalRefinement`: 380/382 poprawnych;
- `structuredHybrid`: 309/312 poprawnych;
- historyczny corpus detector: 27/27 dostępnych porównań poprawnych.

Bieżące hard gates skierowały wszystkie plansze do ręcznej korekty, przede
wszystkim przez brak pełnego pokrycia linii pionowych, poziomych i przecięć.
Wniosek jest warunkowy: istnieje sygnał dla ramki zewnętrznej, znanego układu i
regularności, ale obecny korpus nie uprawnia do zmiany produkcyjnego silnika.

Weryfikacja:

- łączny scoped pytest dla feasibility, global initialization i line refinement
  — 23 passed;
- Ruff format/check dla runnera, modułu i testów — passed;
- scoped mypy modułu z `services/api/src;services/worker/src` — passed;
- jeden bounded przebieg rzeczywistego runnera — completed; bez benchmarku,
  zapisu danych produkcyjnych i zmian bazy.
