---
title: Fundament aplikacji Windows i pakowanie
status: done
last_updated: 2026-10-11
---

# TASK-0975 — Fundament aplikacji Windows i pakowanie

## Status

`done`

## Goal

Uruchomić samodzielną paczkę Windows i wyświetlić lokalny JPEG bez hosta, internetu ani narzędzi deweloperskich.

## Context

Obecny operator-local Reviewer zależy od dostępu do strony przez host i tunel.
Nowy selektor działa lokalnie; zdjęcia i wyniki pozostają u odbiorcy. Proton
Drive jest obsługiwany poza aplikacją. Task realizuje wyłącznie odpowiedni
fragment zaakceptowanego planu.

## Dependencies / entry conditions

Zaakceptowany plan, zgoda kosztowa 2026-10-11 i późniejsze jawne polecenie implementacji pięciu tasków bez oczekiwania na CLI. Audyt wykona operator na końcu zakresu. Bazą jest bb883b5902cb0934b9732d1bc24361d01085051d (v1.7.316).

## Recommended execution

`gpt-6.1-sol / medium`. Operator wykona końcowy audyt całego zakresu; zalecany model
`claude-sonnet-5-5 / medium`. CLI audytora nie jest bramką implementacji.
Konfiguracja odpowiada tabeli planu. Eskaluj, gdy zmiana wymaga innego modelu
własności danych, nowych reguł domeny lub niezgodnego formatu. Nie zmieniaj
modelu/reasoning niejawnie. Wyjątek operatora: bez audytu przed każdym commitem; końcowy przegląd po pięciu taskach.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-545
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md — TASK-0975
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md — obowiązująca sekcja operator-local
- ai_docs/architecture/CODE_MAP.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md

## Scope

- Nowy workspace apps/selector-desktop: Electron, React, TypeScript, Forge ZIP Windows x64.
- Typowane IPC z walidacją nadawcy i argumentów; renderer używa identyfikatorów źródła, a nie ścieżek.
- Własny protokół zdjęć: strumieniowanie spod wybranego korzenia, bez base64.
- Sandbox, contextIsolation, nodeIntegration=false, CSP, blokada nowych okien/nawigacji.
- Rotowany log diagnostyczny i otwieranie katalogu logów; brak treści JPEG w logach.
- Przypięte zależności, polityka wymaganych skryptów instalacyjnych, bez custom ELECTRON_MIRROR.
- Nowy obszar AREAS w generatorze mapy kodu i kontrola objęcia workspace'u root quality.

## Out of scope

Trwałe projekty, UI pełnej selekcji, legacy adoption, instalator, podpis kodu, serwery/API oraz zmiany Admina i Reviewera.

## Acceptance criteria

- [x] Paczka działa offline i pokazuje lokalny JPEG; brak runtime zależnego od hosta.
- [x] Anulowanie pickera zachowuje prawidłowy stan, odczyt spoza korzenia i reparse point są odmawiane.
- [x] Renderer nie otrzymuje ogólnego filesystem API; nie można otworzyć zewnętrznej strony/okna.
- [x] Testy, lint, typecheck i pakowanie nowego workspace'u przechodzą; mapa go obejmuje.
- [x] Ograniczenie lokalnego smoke testu jest zapisane; rzeczywisty drugi komputer sprawdza TASK-0979.

## Technical notes

Nie uruchamiaj usług głównego repo. Nowy renderer jest statycznie dołączony do paczki. Zablokuj wyjście poza korzeń zarówno leksykalnie, jak i na rzeczywistym filesystem. Publiczne IPC przyjmuje dane z walidowanych typów i sprawdza origin/frame. Politykę postinstall sprawdź w obecnej wersji npm, nie zakładaj samego znaczenia klucza allowScripts.

## Expected files

- Nowe, proponowane: apps/selector-desktop/package.json, forge.config.ts, src/main.ts, src/preload.ts, src/contracts.ts, src/renderer/ oraz test/.
- Istniejące: package.json i package-lock.json — workspaces, skrypty instalacyjne i dependencies.
- Istniejący: scripts/generate_code_map.py — AREAS; generowane CODE_MAP.md i CODE_MAP_SYMBOLS.md.
- Dokumentacja: architecture/TECH_STACK.md i nowa guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md.

## Test cases

- Picker success/cancel/read failure; JPEG z właściwego i niewłaściwego korzenia.
- Traversal, dowolna ścieżka przekazana zamiast ID, nieprawidłowy nadawca IPC, symlink/junction.
- Spakowany UI offline, brak zewnętrznych requestów i nowych okien.
- Nowy proces instalacji/builda korzysta z przypiętych zależności bez sesyjnych obejść.

## Verification

Z katalogu worktree selektora. Każda skończona komenda ma timeout do 120 s;
znany dłuższy build tylko po uprzedniej informacji i osobnym limicie.

```powershell
npm run test --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run test --workspace @game-predictor/reviewer
npm run docs:check
npm run code-map:check
```

Powyższe skrypty istnieją w repo. W nowym worktree wymagają dostępnych
zależności oraz interpreterów; przygotowanie środowiska nie uprawnia do
restartu usług ani migracji. TASK-0975 ma dodać test/lint/typecheck/build/
package/make aplikacji desktopowej, a następnie zapisać sprawdzone komendy
i wyniki w Outcome. Te skrypty są teraz proponowane, nie wykonane.
Testy Reviewera sprawdzają zgodność kontraktu; nie zastępują odbioru Electrona.
Po zmianie modułów/symboli zregenerować mapę, potem sprawdzić code-map:check.

## Risks / open questions

Audyt przed startem/commitem został odroczony przez operatora do końca zakresu. Pakowanie może wymagać pobrania zależności; odbiór źródła i autora paczki na urządzeniu odbiorcy należy do 0979.

## Outcome

### Changed

Commit implementacji: v1.7.318, `00331d5776c462a3dd91e4d9113b39d0223fe6c4`. Zapis po commicie wchodzi z następnym taskiem.

- Workspace Electron/React/TypeScript, statyczny renderer, Forge ZIP Windows x64, typed IPC i strumieniowanie JPEG przez własny protokół.
- Walidacja nadawcy i argumentów, identyfikatory indeksu, sandbox/CSP oraz blokada sieci, nawigacji, nowych okien i uprawnień.
- Naturalny indeks do 15 000 JPEG; dodatkowa defensywna granica 100 000 wpisów katalogowych. Kontrola symlink/junction i atrybutu Windows ReparsePoint. Rotowane logi.
- Root workspace quality, przypięte zależności/lockfile, wyłącznie allowScripts esbuild@0.25.12, mapa kodu i ignorowanie wygenerowanych plików w formatowaniu.
- Rozwiązanie nowych zależności podniosło współdzielone terser5.49.0→5.51.2 i is-core-module2.16.2→2.17.0, wymagane przez nowe pakiety. Wybrany pin typescript-eslint8.71.1 podniósł współdzieloną rodzinę z8.65.0; poprzednia wersja również obsługiwała TypeScript6. Npm odświeżył także dopuszczone wersje minimatch10.2.5→10.2.6 i brace-expansion5.0.8→5.0.12. Są to jawne zmiany lockfile, bez zmian komponentów webowych.
- Przygotowanie dokumentacji: v1.7.317, commit `e91b365cd02bf50ff914b1c4cda0b732432f8f3a`; nie był to commit implementacji.

### Verification results

- Native tests 7/7 PASS; lint, typecheck, build, package, make, scoped format, docs:check i code-map:check PASS. Komendy ograniczone do 45–120 sekund.
- Packaged EXE smoke PASS: poprawny JPEG 1×1 z lokalnego źródła, blokada fetch i nowych okien, anulowanie pickera zachowuje podgląd; kontrolowany proces zamknięty.
- Rdzeń: 110/110 PASS oraz typecheck PASS. Reviewer: 264/264 PASS poza piaskownicą. Pierwszy bieg Reviewera miał pięć błędów 502 od blokady połączeń do lokalnych fixture'ów; bez zmian kodu po powtórzeniu wszystkie przeszły.
- Testy realpath/junction i packaged smoke wymagały eskalacji ograniczeń piaskownicy. Instalacja npm11.19.0 zgodna z engine; ostrzeżenia istniejących niezatwierdzonych postinstall esbuild@0.28.1 i sharp@0.34.5 pozostawiono poza zakresem.
- ZIP fundamentu: `apps/selector-desktop/out/make/zip/win32/x64/Selektor zdjec-win32-x64-0.1.0.zip`, 149372115 bajtów, SHA-256 `93581085b6fd0b26cd2386bd8f9e57c2770967d64d7ac0052eb9b308a4489570`. To paczka podglądu, nie pełnego selektora.

### Not completed

- Trwałe projekty i pełna selekcja należą do 0976/0977; odbiór drugiego komputera, restart Windows i realna dystrybucja do 0979.
- Audyt operatora odłożony na koniec pięciu tasków jego wyraźnym poleceniem. Nie wykonywano zastępczego audytu ani zmian API/Admin/Reviewer.

### Documentation updates

Plan, taski, D-545 i CURRENT_STATE zachowują jawny wyjątek audytu oraz uruchomienie 0978. TECH_STACK, wymagania/architektura i guide rozróżniają gotowy fundament od planowanych dalszych funkcji.

### Recommended next task

TASK-0976, następnie 0977/0979/0978; końcowy audyt operatora.
