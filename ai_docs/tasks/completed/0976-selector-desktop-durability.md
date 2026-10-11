---
title: Projekt, manifest i odzyskiwanie
status: done
last_updated: 2026-10-11
---

# TASK-0976 — Projekt, manifest i odzyskiwanie

## Status

`done`

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
- Przejściowa atomowa blokada outputu podczas transakcji chroni także wyścig dwóch różnych projektów; znika przed potwierdzeniem, bez rozszerzania finalnego manifestu.
- Relink brakujących katalogów bez resetu i fail-closed ochrona obcych danych.
- Testy awarii w czystym Node z wstrzykiwanym adapterem i realnym nowym procesem.

## Out of scope

UI całej selekcji, IndexedDB, nowa baza danych, multiwriter przez chmurę, benchmarki i operacje na danych operatora.

## Acceptance criteria

- [x] Potwierdzenie jest możliwe dopiero po trwałym commicie JPEG/stanu; restart odtwarza potwierdzony wybór.
- [x] Przerwanie każdej fazy i ponowienie nie tworzą podwójnej decyzji ani zakresu.
- [x] Konflikt ID z innym poleceniem, obca checksuma i plik blokady nieznanego właściciela zatrzymują zapis.
- [x] Brak miejsca/błąd replace zachowują wcześniejsze decyzje i journal; UI dostaje stabilny kod błędu.
- [x] Manifest jest operator_local v2, nie items; katalog wyniku zawiera wyłącznie zgodne artefakty.
- [x] Test recovery działa z nowego procesu i rzeczywistych plików Windows, nie tylko mocków.

## Technical notes

Projekt jest źródłem prawdy; manifest jest projekcją. Przy restarcie najpierw dowiedź fazy operacji z checksum i zapisów. Nie kasuj journalu po błędzie ani poprzedniego stanu przed udaną podmianą. Sam timeout heartbeat nie wystarcza do przejęcia; host/PID/tożsamość procesu muszą być jednoznaczne. Nie rozszerzaj roli requestSingleInstanceLock na synchronizowany filesystem. Uchwyt/bajt JPEG nie jest przechowywany w indeksie projektu.

Granice lokalności: odrzucać reparse pointy, udziały i dyski sieciowe oraz
znane korzenie synchronizacji. Konfiguracji dowolnego zewnętrznego klienta
synchronizacji nie można dowieść wyłącznie ze ścieżki. Utworzenie projektu
wymaga jawnego oświadczenia użytkownika, że wybrał lokalny folder poza
synchronizacją; UI0977 pokaże ten warunek. Nie obiecujemy wykrywania każdego
klienta synchronizacji ani blokady rozproszonej.

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

Gwarancje synchronizacji i replace muszą być sprawdzone na Windows. Nie obiecuj odporności na uszkodzenie sprzętu ani pracy w synchronizowanym folderze.

## Outcome

### Changed

Zaimplementowano wersjonowany projekt, dziennik transakcji, ostatnią poprawną
kopię, trwałe receipts i odzyskiwanie przed odblokowaniem mutacji. Zapis JPEG
jest strumieniowy, zachowuje bajty i publikuje zgodny manifest operator-local v2.
Projekt przechowuje ścieżkę kursora; brak katalogu pozwala na relink bez resetu.
Atomowy lock projektu i przejściowa lease wyniku chronią aktywnych oraz
nieznanych właścicieli. Recovery przejmuje wyłącznie potwierdzony martwy proces
tego komputera. Obce pliki, checksumy i konflikt identyfikatora operacji blokują
zapis. Cache ostatnich projektów nie jest źródłem prawdy.

Commit implementacji: wersja v1.7.319; pełny hash zostanie dopisany po commicie.

### Verification results

50 unikalnych testów PASS: pełny desktopowy przebieg 48/48 w 109.949 s oraz
uzupełniające grupy 4/4 (15.415 s) i 2/2 (13.795 s), zawierające dwa później
dodane przypadki. Testy obejmują przerwania każdej fazy, realny nowy proces,
utratę odpowiedzi/retry, ENOSPC/rename, uszkodzony stan, obcy JPEG, aktywną i
nieznaną blokadę, dwa projekty współdzielące output, relink i nieobsługiwaną
wersję projektu. Końcowe lint, typecheck, build i Prettier check PASS.
Komendy miały limit do 120 s; testy natywnych plików wykonano poza sandboxem.

Rdzeń 110/110 i Reviewer 264/264 PASS wykonano w0975; nie powtarzano ich bez
zmian tych modułów. Mapy zregenerowano; docs:check PASS (542 decyzje/odnośniki,45 aktywnych tasków,
10 done), code-map:check PASS, ruff check/format generatora PASS.

### Not completed

Nie wykonano zewnętrznego audytu: operator przeniósł go na koniec pięciu tasków.
Nie wykonano odbioru na drugim komputerze ani restartu Windows. Gwarancja
obejmuje awarię procesu; Node na Windows nie zapewnia fsync katalogu ani
odporności na zanik zasilania/uszkodzenie sprzętu. Po zabiciu procesu mogą
pozostać nieaktywne pliki temp; recovery nie usuwa ich automatycznie.
Dowolnego klienta synchronizacji nie można wykryć ze ścieżki, dlatego utworzenie
projektu wymaga potwierdzenia lokalnego katalogu poza synchronizacją.

### Documentation updates

Uaktualniono architekturę, wymagania, instrukcję, plan, D-545, mapy i stan prac.
Plik taska przeniesiono do completed. Dokumentacja nie deklaruje odbioru wydania.

### Recommended next task

TASK-0977 — pełny interfejs selekcji; potem0979 i0978. Audyt operatora na końcu.
