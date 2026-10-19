---
title: Profil stawek Mumii przy aliasie shared w linkach
status: done
last_updated: 2026-10-19
---

# TASK-1064 — Profil stawek Mumii w linkach

## Status

`done`

## Goal

Istniejący link Mumii wybiera profil 1/2/5/10/20 zł i skaluje wypłaty z rzeczywistego
`gameId` odpowiedzi, także gdy adresowanie wspólnego UI używa aliasu `shared`.

## Context

Regresja TASK-1063: kontrolki i formatowanie tabeli używały identyfikatora
adresowania API, który dla udostępnień i paneli wielu gier jest aliasem `shared`.
Wykres używał już rzeczywistego identyfikatora odpowiedzi. Dodatkowo działający
Reviewer to `next start` na 3001, PID 46400; build z 2026-10-19 11:21:06 poprzedza
implementację stawek z 21:15:44. Odświeżenie nie przebudowuje produkcyjnej aplikacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`, tymczasowy profil Mumii.
- `ai_docs/architecture/API_CONTRACT.md`, kalkulator i D-565.

## Scope

Kontrolki, formatowanie wyników i kontekst korekty korzystają z `result.gameId`;
alias API pozostaje bez zmian. Testy dla UUID Admina i aliasu `shared`.
Nie ma decyzji produktowej ani zmiany API. Pliki: komponent kalkulatora, jego
test interakcji, wymagania, mapa kodu i dokumentacja zadania.

## Out of scope

Build, restart i uruchamianie usług wymagają osobnego polecenia operatora.
Bez migracji, zmiany stawek innych gier, nowego linku i operacji danych.

## Acceptance criteria

- [x] Regresja `shared` odtworzona testem przed poprawką.
- [x] Alias `shared` i UUID Mumii oferują 1/2/5/10/20 zł.
- [x] Wypłata 10 kredytów przy wyborze 5 zł jest pokazana jako 5 zł w tabeli.
- [x] Pozostałe interakcje, lint, typy, docs:check i mapa kodu przechodzą.
- [x] Diagnostyka odróżnia kod w main od produkcyjnego builda Reviewera.

## Verification

Z katalogu repozytorium, komendy przez subprocess z timeout=120 s:

```powershell
node node_modules/tsx/dist/cli.mjs --tsconfig packages/board-search-ui/tsconfig.json --test packages/board-search-ui/test-interactions/board-search-approximate-win.test.mjs
npm run typecheck --workspace @game-predictor/board-search-ui
npm run lint --workspace @game-predictor/board-search-ui
npm run docs:check
npm run code-map:check
```

## Outcome

Commit: v1.7.437 / `979d81cba64000fcf358ad5ef5294483fdd9e529`.

### Changed

- Kontrolki wybierają profil z UUID bieżącej odpowiedzi kalkulatora.
  Tabela i kontekst korekty korzystają z tego samego UUID co wykres.
  Techniczne adresowanie `shared` nie zmienia się.
- Test profilu rozbudowany o faktyczną wypłatę w tabeli; wykonywany zarówno
  dla UUID Admina, jak i aliasu udostępnienia. Kryteria porównano punkt po punkcie.

### Verification results

- Przed poprawką test aliasu `shared` odtworzył listę 1/1,20/2/4/6/10/20 zł
  zamiast 1/2/5/10/20 zł. Po poprawce 25 testów interakcji PASS, w tym oba
  przypadki pokazujące 10 kredytów jako 5 zł przy stawce 5 zł.
- Typecheck, lint i formatowanie zmienionych plików board-search-ui: PASS.
- Mapa kodu zregenerowana bez różnicy treści; code-map:check PASS.
- docs:check PASS przy zamknięciu zadania.
- Odczyt procesów potwierdził `next start --port 3001`, PID 46400, a odczyt
  BUILD_ID build z 11:21:06, starszy niż poprawka 21:15:44. Bez zmiany stanu usług.

### Not completed

- Nowa poprawka nie jest jeszcze scalona. Nie przebudowano ani nie
  restartowano produkcyjnego Reviewera; nie potwierdzono odbioru na telefonie.
- Bez audytu wymaganego przez plan, delegowania, migracji i zmiany API.

### Documentation updates

ADMIN_APP wyjaśnia UUID odpowiedzi i alias adresowania oraz konieczność
przebudowania i restartu produkcyjnego Reviewera po zmianie kodu.
CURRENT_STATE i archiwum aktualizowane przez task-close.

### Recommended next task

Po odbiorze poprawki: scalenie, przebudowanie i restart samego Reviewera
z osobną zgodą operatora, zachowując istniejący tunel i link.
