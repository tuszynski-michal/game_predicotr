---
title: Interfejs pełnej selekcji
status: todo
last_updated: 2026-10-11
---

# TASK-0977 — Interfejs pełnej selekcji

## Status

`todo`

## Goal

Zakończyć nową partię JPEG-ów i wznowić ją w aplikacji Windows z semantyką Reviewera.

## Context

Obecny operator-local Reviewer zależy od dostępu do strony przez host i tunel.
Nowy selektor działa lokalnie; zdjęcia i wyniki pozostają u odbiorcy. Proton
Drive jest obsługiwany poza aplikacją. Task realizuje wyłącznie odpowiedni
fragment zaakceptowanego planu.

## Dependencies / entry conditions

TASK-0976 zakończony i zacommitowany. Końcowy audyt operatora po całym zakresie. Przed kodowaniem porównać obecne zachowanie RemoteManualSelectionWorkspace z planem.

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
- ai_docs/delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md — TASK-0977
- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md — Lokalny selektor Windows
- ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md — obowiązująca sekcja operator-local
- ai_docs/architecture/CODE_MAP.md
- ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md

## Scope

- Nowy projekt, Otwórz projekt, Kontynuuj, source/project/output lokalizacje i status trwałego zapisu.
- Własny UI, import wyłącznie rdzenia, bez refaktoru komponentów Admina/Reviewera.
- Enter/F, Tab, A/Ctrl+Z, nawigacja i skok; kolejność źródła niezależna od numeracji.
- rangeForStart, first/last/direction, końcowy krótki zakres; brak dowolnego zakresu 1–9.
- Fullscreen, zoom 100–3000%, scroll obie osie, bounded cache ±3, bez miniaturek.
- Undo i restart z checksum ownership; restart dopiero po preview i potwierdzeniu.
- Otwieranie katalogu wyników/logów; blokady UI odpowiadają realnym mutacjom/recovery.

## Out of scope

Legacy adoption, OCR, trace uczenia, repair, upload, wspólny pakiet UI i zmiany webowych selektorów.

## Acceptance criteria

- [ ] Skróty i numeracja mają semantykę Reviewera; akceptacja nie wyprzedza trwałego zapisu.
- [ ] Tryb rosnący/malejący nawigują po tej samej naturalnej liście; końcowa granica jest respektowana.
- [ ] Powtórzony klik/klawisz nie zapisuje tej samej decyzji dwa razy.
- [ ] Restart/reopen odtwarzają JPEG, zakres, kierunek, skok i widok; recovery blokuje mutacje.
- [ ] Undo/restart nigdy nie usuwają obcego/zmienionego JPEG-a ani źródła.
- [ ] Bounded preview zwalnia stare zasoby, a stan loading/error/empty jest widoczny.

## Technical notes

F zachowuje bieżący JPEG jak Reviewer, Enter ma zachowanie Reviewera; nie przenoś niescalonej semantyki Admina. Skoki są listą 1–10,15,20, nie każdym numerem do 20. Edytor respektuje rangeForStart (9 lub końcówka). Mutacje są szeregowane; busy nie resetuje scrolla. Restart jest destrukcyjną funkcją, nie zgodą na jej wykonanie na zdjęciach użytkownika.

## Expected files

- Nowe, proponowane: apps/selector-desktop/src/renderer/ i test/renderer*.test.*.
- Istniejące tylko do odczytu: RemoteManualSelectionWorkspace i helpery rdzenia.
- Dokumentacja: requirements/MANUAL_IMAGE_SELECTION.md i guide selektora.

## Test cases

- Nowa sesja, pusty katalog, błędny JPEG, głęboko zagnieżdżone naturalne nazwy.
- Ascending/descending, Enter/F/Tab, manual range correction zgodna z końcówką, undo.
- Podwójny submit, repeat klawisza, skróty w input/select; recovery/stale async callback.
- Zoom, fullscreen i scroll przy zmianie obrazu; cache nie rośnie z kolekcją.
- Missing folder → relink; restart cancelled/confirmed na kopii testowych danych.

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

Istnieją różnice skrótów Admina i Reviewera; punktem odniesienia jest Reviewer. Nie wybieraj niejawnie nowej semantyki.

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

TASK-0979, następnie uruchomiony przez operatora TASK-0978.
