---
title: Projekt, manifest i odzyskiwanie
status: todo
last_updated: 2026-10-11
---

# TASK-0976 — Projekt, manifest i odzyskiwanie

## Status

`todo`

## Goal

Zachować dokładnie raz każdą potwierdzoną decyzję i pozycję po awarii procesu albo utracie odpowiedzi lokalnego transportu.

## Context

Obecny operator-local Reviewer zależy od dostępu do strony przez host i tunel.
Nowy selektor działa lokalnie; zdjęcia i wyniki pozostają u odbiorcy. Proton
Drive jest obsługiwany poza aplikacją. Task realizuje wyłącznie odpowiedni
fragment zaakceptowanego planu.

## Dependencies / entry conditions

TASK-0975 zakończony i osobno zacommitowany; końcowy audyt operatora po całym zakresie. Czytaj ponownie sekcję trwałości planu przed kodowaniem.

## Recommended execution

`gpt-6.1-sol / high`. Operator wykona końcowy audyt całego zakresu; zalecany model
`claude-sonnet-5-5 / high`. CLI audytora nie jest bramką implementacji.
Konfiguracja odpowiada tabeli planu. Eskaluj, gdy zmiana wymaga innego modelu
własności danych, nowych reguł domeny lub niezgodnego formatu. Nie zmieniaj
modelu/reasoning niejawnie. Wyjątek operatora: bez audytu przed każdym commitem; końcowy przegląd po pięciu taskach.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md — D-545
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md — TASK-0976
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md — obowiązująca sekcja operator-local
- ai_docs/architecture/CODE_MAP.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md

## Scope

- Wersjonowany projekt, źródło tylko do odczytu, osobny wynik i lokalna lista ostatnich projektów.
- Temp/sync/replace, ostatnia poprawna kopia i dziennik przygotowanie → JPEG zapisany → decyzja zatwierdzona.
- Idempotencja identyfikatora operacji, recovery przed mutacjami i eksport operator-local schema v2.
- Strumieniowy zapis oryginalnego JPEG i weryfikacja SHA-256; pliki seq_<start>-<end>.jpg.
- Plik blokady projektu utworzony atomowo, tożsamość właściciela/hosta/procesu, sprawdzanie porzuconej blokady.
- Relink brakujących katalogów bez resetu i fail-closed ochrona obcych danych.
- Testy awarii w czystym Node z wstrzykiwanym adapterem i realnym nowym procesem.

## Out of scope

UI całej selekcji, IndexedDB, nowa baza danych, multiwriter przez chmurę, benchmarki i operacje na danych operatora.

## Acceptance criteria

- [ ] Potwierdzenie jest możliwe dopiero po trwałym commicie JPEG/stanu; restart odtwarza potwierdzony wybór.
- [ ] Przerwanie każdej fazy i ponowienie nie tworzą podwójnej decyzji ani zakresu.
- [ ] Konflikt ID z innym poleceniem, obca checksuma i plik blokady nieznanego właściciela zatrzymują zapis.
- [ ] Brak miejsca/błąd replace zachowują wcześniejsze decyzje i journal; UI dostaje stabilny kod błędu.
- [ ] Manifest jest operator_local v2, nie items; katalog wyniku zawiera wyłącznie zgodne artefakty.
- [ ] Test recovery działa z nowego procesu i rzeczywistych plików Windows, nie tylko mocków.

## Technical notes

Projekt jest źródłem prawdy; manifest jest projekcją. Przy restarcie najpierw dowiedź fazy operacji z checksum i zapisów. Nie kasuj journalu po błędzie ani poprzedniego stanu przed udaną podmianą. Sam timeout heartbeat nie wystarcza do przejęcia; host/PID/tożsamość procesu muszą być jednoznaczne. Nie rozszerzaj roli requestSingleInstanceLock na synchronizowany filesystem. Uchwyt/bajt JPEG nie jest przechowywany w indeksie projektu.

## Expected files

- Nowe, proponowane: apps/selector-desktop/src/project/, src/filesystem/, src/manifest/ i test/project*.test.mjs.
- Istniejący kontrakt jako wzorzec, bez edycji: apps/reviewer/src/features/manual-selection/operator-local-selection-output.ts — OperatorLocalOutputManifestV2.
- Wspólny rdzeń jako dependency: packages/manual-image-selection-core/src/index.ts.
- Dokumentacja architektury/wymagań i guide operatora.

## Test cases

- Awaria przed/po zapisaniu zamiaru, JPEG, decyzji, manifestu i finalizacji; nowy proces odzyskuje wynik.
- Utrata odpowiedzi IPC po commicie, retry tego samego ID oraz konflikt argumentów.
- ENOSPC, brak uprawnień, uszkodzony stan/backup, odmowa rename i obcy plik seq.
- Druga instancja, aktywny lock, porzucony własny lock i nieznany host.
- Podpięcie tego samego źródła po przeniesieniu bez zerowania; rozbieżne źródło blokuje.

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

Gwarancje synchronizacji i replace muszą być sprawdzone na Windows. Nie obiecuj odporności na uszkodzenie sprzętu ani pracy w synchronizowanym folderze.

## Outcome

### Changed

Przygotowano specyfikację taska i zaakceptowany plan. Implementacja nie została rozpoczęta.

### Verification results

Kontrole przygotowanej dokumentacji: check_decision_links.py PASS (542 odnośniki/wpisy/wiersze indeksu), check_current_state_window.py PASS (47 aktywnych tasków, 10 done). Testów implementacji nie uruchamiano.

### Not completed

Kryteria implementacyjne pozostają do wykonania. Audyt operatora jest odłożony do końca pięciu tasków.

### Documentation updates

Task, plan, D-545 i wpisy źródeł prawdy opisują zaakceptowany zamiar.

### Recommended next task

TASK-0977 po commicie 0976; końcowy audyt operatora po pięciu taskach.
