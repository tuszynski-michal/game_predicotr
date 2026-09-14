# TASK-0539 — rzeczywisty etap preflightu geometrii w stagingu

## Status

`done`

## Goal

Pokazać w kafelku stagingu rzeczywistą fazę preflightu geometrii oraz odróżnić
tymczasowo nierozstrzygnięte zdjęcia od końcowo odroczonych, bez osłabienia
bramki końcowego manifestu.

## Context

Job `d633a302-7cc1-4472-8349-5f8c8b883ab2` dla stagingu
`93853 -117828 cut` pokazał `processing · 2664/2664 · zarejestrowane 2634 ·
odroczone 0`. Globalne `2664/2664` oznaczało zakończenie pierwszego przejścia,
podczas gdy worker wykonywał jeszcze dwa przebiegi auto-anchor. API poprawnie
zwracało fazę, postęp fazy i tymczasową liczbę nierozstrzygniętych źródeł, ale
kafelek stagingu pomijał te pola. Dalsza akcja pozostawała prawidłowo
zablokowana do zapisu niezmiennego manifestu, lecz UI wyglądało jak zakończone.

## Dependencies / entry conditions

- API zwraca `progress.pageGeometryPreflight` z fazą, licznikami fazy,
  numerem przebiegu i `provisionalReviewRequired`.
- Wspólny `jobProgressLabel` ma już zgodną prezentację faz preflightu.
- Start importu wymaga statusu `completed` i checksummy manifestu geometrii.

## Recommended execution

`gpt-5.6-sol`, reasoning `high`. Zmiana jest ograniczona do istniejącego
kontraktu prezentacji i testów Admina. Eskalacja do mocniejszego modelu jest
potrzebna tylko wtedy, gdy diagnoza ujawni błąd trwałości joba albo manifestu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0456-page-geometry-preflight-progress.md`

## Scope

- Użyć wspólnej prezentacji fazy joba w kafelku gotowego stagingu.
- Podczas `processing` pokazać tymczasową liczbę zdjęć nadal wymagających
  rozstrzygnięcia przez dodatkowe dopasowanie.
- Etykietę końcowo odroczonych zdjęć pokazywać dopiero dla terminalnego wyniku.
- Dodać regresję kontraktu panelu i zaktualizować dokumentację.
- Monitorować wskazany job do terminalnego statusu lub potwierdzonego aktywnego
  heartbeat bez ingerencji w dane.

## Out of scope

- Dopuszczenie importu przed ukończeniem manifestu geometrii.
- Zmiana algorytmu, progów, liczby przebiegów auto-anchor lub wyników joba.
- Anulowanie, ponowienie albo ręczna modyfikacja wskazanego joba.
- Zmiana API, OpenAPI lub schematu bazy.

## Acceptance criteria

- [x] Kafelek stagingu pokazuje `Pierwszy przebieg`, `Dodatkowe dopasowanie
      X/Y` albo zapis manifestu zgodnie z bieżącą fazą API.
- [x] Przy aktywnym auto-anchor liczba nierozstrzygniętych pochodzi z
      `provisionalReviewRequired`, a etykieta nie nazywa jej wynikiem końcowym.
- [x] Po terminalnym wyniku UI ponownie pokazuje końcową liczbę odroczonych.
- [x] Start importu pozostaje zablokowany do statusu `completed` i checksummy
      manifestu.
- [x] Testy Admina, typecheck, lint i build przechodzą.

## Technical notes

Źródłem prawdy dla etapu jest `JobResponse.progress.pageGeometryPreflight`, a
nie globalne `progress.current/total`. Globalny licznik pozostaje monotoniczny
i po pierwszym przejściu może wynosić `N/N`, choć auto-anchor nadal pracuje.
Kafelek ma użyć istniejącego `jobProgressLabel(job)`. Gdy job jest aktywny i
faza nie jest kompletna, dodatkowa metryka pokazuje
`provisionalReviewRequired` jako `jeszcze nierozstrzygnięte`; dopiero status
terminalny używa bieżącego licznika kolejki korekty jako `odroczone zdjęcia`.
Brak szczegółowego payloadu w historycznym jobie zachowuje bezpieczny fallback
wspólnego prezentera.

## Expected files

- Istniejący
  `apps/admin/src/features/imports/image-folder-import-panel.tsx` — prezentacja
  fazy i tymczasowego licznika.
- Istniejący `apps/admin/src/features/imports/image-folder-import-state.ts` —
  czysta funkcja rozróżniająca licznik tymczasowy i końcowy.
- Istniejący `apps/admin/test/image-folder-import-panel-contract.test.mjs` —
  regresja użycia pełnego postępu.
- Istniejący `apps/admin/test/image-folder-import-state.test.mjs` — przypadki
  aktywnego, ukończonego i historycznego checkpointu.
- Dokumentacja wskazana w `Relevant docs`.

## Test cases

- `auto_anchor_retry`, przebieg 2/2, `0/7`, provisional 7 → UI pokazuje
  dodatkowe dopasowanie i siedem nierozstrzygniętych.
- `completed`, manifest obecny, review 7 → UI pokazuje siedem odroczonych.
- Historyczny payload bez fazy → wspólny fallback bez fałszywej deklaracji
  ukończenia.
- Aktywny job bez checksummy manifestu → przycisk importu nadal disabled.

## Verification

```powershell
npm test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

Kryterium zaliczenia: komendy kończą się kodem 0, kontrakt panelu używa pełnej
fazy preflightu, a rzeczywisty job ma świeży heartbeat lub status terminalny.

## Risks / open questions

- `provisionalReviewRequired` może maleć po kolejnych przebiegach i dlatego nie
  może być publikowane jako monotoniczny licznik `review`; UI musi nazywać je
  stanem tymczasowym.
- Brak pytań blokujących. Obecny job ma świeży heartbeat i wykonuje ostatni
  przebieg; nie ma podstaw do retry ani restartu workera.

## Outcome

- Kafelek gotowego stagingu używa wspólnego `jobProgressLabel`, więc pokazuje
  rzeczywistą fazę pierwszego przebiegu, dodatkowego dopasowania i zapisu
  manifestu mimo globalnego `N/N`.
- Aktywny job opisuje `provisionalReviewRequired` jako zdjęcia jeszcze
  nierozstrzygnięte. Dopiero `completed` pokazuje stan kolejki jako zdjęcia
  odroczone; historyczny aktywny checkpoint bez szczegółów pokazuje bezpieczny
  brak gotowego wyniku.
- Nie zmieniono bramki importu: nadal wymaga ukończonego preflightu i checksummy
  manifestu.
- Job `d633a302-7cc1-4472-8349-5f8c8b883ab2` ukończył się bez błędu z wynikiem
  2660 zarejestrowanych i 4 odroczone. Ponownie odtworzony raport zwraca
  `geometryPreflightArtifactReady=true`, brak blokera i checksumę manifestu
  `78032e1c8b5ef58d6b0c07a51271eaf38166780a5b8b3723098ea0832ceff3ce`.
- Przeszły testy skoncentrowane, pełny zestaw testów Admina, typecheck, lint i
  build produkcyjny.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0539 — rzeczywisty etap preflightu geometrii w stagingu | gpt-5.6-sol | high | Istniejący kontrakt API i prezenter zawierają potrzebne dane; zmiana wymaga spójnego UI i ochrony bramki manifestu. | Nie; regresja panelu i istniejące testy prezentera pokrywają ryzyko. |
