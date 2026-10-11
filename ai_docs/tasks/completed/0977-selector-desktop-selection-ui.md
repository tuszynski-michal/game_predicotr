---
title: Interfejs pełnej selekcji
status: done
last_updated: 2026-10-11
---

# TASK-0977 — Interfejs pełnej selekcji

## Status

`done`

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

- [x] Skróty i numeracja mają semantykę Reviewera; akceptacja nie wyprzedza trwałego zapisu.
- [x] Tryb rosnący/malejący nawigują po tej samej naturalnej liście; końcowa granica jest respektowana.
- [x] Powtórzony klik/klawisz nie zapisuje tej samej decyzji dwa razy.
- [x] Restart/reopen odtwarzają JPEG, zakres, kierunek, skok i widok; recovery blokuje mutacje.
- [x] Undo/restart nigdy nie usuwają obcego/zmienionego JPEG-a ani źródła.
- [x] Bounded preview zwalnia stare zasoby, a stan loading/error/empty jest widoczny.

## Technical notes

Reviewer `remote-manual-selection-workspace.tsx:437`, `:548`, `:729`:
Enter/F wykonują tę samą akceptację i przesuwają źródło o jeden (z końcowym
clamp), niezależnie od navigationStep. Tab pomija zakres i zachowuje bieżące
zdjęcie. Kierunek zmienia numerację, nie porządek zdjęć. Testy i UI muszą
zachować te reguły; nie przenosić odmiennych zachowań innych konsumentów rdzenia.

Skoki są listą 1–10,15,20, nie każdym numerem do20. Edytor respektuje rangeForStart (9 lub końcówka). Mutacje są szeregowane; busy nie resetuje scrolla. Restart jest destrukcyjną funkcją, nie zgodą na jej wykonanie na zdjęciach użytkownika.

Założenie implementacyjne: krok nawigacji, zoom i obie pozycje scrolla są
pomocniczym cache'em widoku w userData według stabilnego projectId. Natywna
warstwa waliduje i serializuje atomowy zapis; zamknięcie/zmiana projektu
rozlicza oczekujące zapisy. Brak/uszkodzenie cache'u przywraca domyślny widok,
bez resetowania projektu, decyzji lub kursora. Kopia projektu zachowuje pracę;
preferencje widoku nie są wymaganym dowodem jej tożsamości.

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
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/manual-image-selection-core
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run typecheck --workspace @game-predictor/manual-image-selection-core
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/reviewer
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run docs:check
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run code-map:check
```

Powyższe skrypty istnieją w repo. W nowym worktree wymagają dostępnych
zależności oraz interpreterów; przygotowanie środowiska nie uprawnia do
restartu usług ani migracji. TASK-0975 dodał test/lint/typecheck/build/package/make aplikacji desktopowej.
Dla bieżącego taska należy zapisać sprawdzone komendy i wyniki w Outcome. Skrypty desktopu istnieją po0975; ich wynik dla bieżącego taska wymaga osobnego wykonania.
Testy Reviewera sprawdzają zgodność kontraktu; nie zastępują odbioru Electrona.
Po zmianie modułów/symboli zregenerować mapę, potem sprawdzić code-map:check.

## Risks / open questions

Istnieją różnice skrótów Admina i Reviewera; punktem odniesienia jest Reviewer. Nie wybieraj niejawnie nowej semantyki.

## Outcome

### Changed

Zaimplementowano nowy projekt/otwarcie/kontynuację, własny workspace React i
natywny koordynator. Enter/F przesuwa źródło o jeden, Tab pomija zakres bez
zmiany zdjęcia. Numeracja, krótka końcówka, skoki, undo oraz restart korzystają
z rdzenia i trwałego writera. Powtórzenia, podwójny submit, błędny JPEG i
recovery blokują nowe decyzje. UI odczytuje świeży snapshot po zatwierdzeniu.
IPC przenosi opaque imageId, nigdy dowolny imagePath. Zoom, fullscreen,
przewijanie obu osi i cache do7 obrazów mają odrębny stan prezentacji.
Atomowy cache widoku userData jest rozliczany przy zamknięciu/zmianie projektu.
Relink jest dostępny także w zdrowym projekcie dla jawnego podłączenia kopii
wyniku; oryginalne bindingi nie są zmieniane automatycznie.

Commit implementacji: v1.7.320 / `0121ce8f1bd3604977e1c60872da43a4110326d7`.

### Verification results

Z workspace aplikacji: `node scripts/run-bounded.mjs 30 npm run test:ui` PASS3/3;
`node scripts/run-bounded.mjs 60 node scripts/smoke-shortcuts.mjs` PASS;
`node scripts/run-bounded.mjs 120 npm run smoke:packaged` PASS. Lint, typecheck,
Prettier, diff --check, build i package PASS. Realny EXE na własnych fixture
sprawdzono z izolowanym userData: Enter/F/Tab, obu kierunkach, krok20,
inputguard, repeat/double-click, undo, zoom/scroll/fullscreen, cache7,
nowy proces/kontynuacja, missingoutput/relink, kopia projektu ze starymi
bindingami i jawny relink kopii output, terminalrange oraz confirmedrestart
wyłącznie kopii. Oryginalny output nie zmienił się. Screenshoty konfiguracji
oraz workspace sprawdzono wizualnie. Pierwsze oczekiwanie testu malejącego
odczytywało snapshot przed końcem operacji; poprawiono synchronizację testu
na wyrenderowany stan, bez zmiany logiki projektu.

Nie powtarzano50 testów0976 ani rdzenia/Reviewera: ich moduły pozostały bez
zmian. Mapy zregenerowano; docs:check PASS (542 decyzje/odnośniki,44 aktywne taski,
10 done), code-map:check PASS i ruff check/format generatora PASS.

### Not completed

Końcowy audyt operatora po pięciu taskach, ZIP wydania i fizyczny odbiór0979.
Nie testowano Androida: ten produkt jest aplikacją Windows11 x64.
Nie wykonywano usług API/Admin, benchmarków, uploadu ani operacji danych operatora.

### Documentation updates

Uaktualniono wymagania, architekturę, plan, instrukcję, mapy i CURRENT_STATE.
Task przeniesiono do completed. Instrukcja opisuje rzeczywiste etykiety UI;
odbiór drugiego komputera pozostaje osobną bramką.

### Recommended next task

TASK-0979 — paczka i instrukcja odbioru; następnie0978 zgodnie z poleceniem pięciu tasków.
