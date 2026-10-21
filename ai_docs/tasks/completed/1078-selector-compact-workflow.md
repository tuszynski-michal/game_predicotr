---
title: Kompaktowy selektor Windows i granica numeracji
status: done
last_updated: 2026-10-21
---

# TASK-1078 — Kompaktowy selektor Windows i granica numeracji

## Status

`done`

## Goal

Uprościć selekcję zdjęć do jednego wejścia i kompaktowego sterowania, z numeracją do 500000 oraz edycją kierunku.

## Context

Operator zgłosił osiem poprawek interfejsu oraz zmianę kierunku w edycji zakresu. Zatwierdził cały zakres i koszt 45–75 minut 2026-10-21. Zadanie nie jest etapem historycznych, ukończonych planów selektora.

## Dependencies / entry conditions

Gałąź od main `ef50ddbb`. Zastane usunięcia w artifacts/v7-main-panel-entry-20261007 oraz worktrees/cloudflare-link-health należą do operatora. Nie są częścią zadania.

## Recommended execution

Rekomendacja: `gpt-6.1-sol`, reasoning `high` (dostępność potwierdzona listą modeli środowiska). Wykonanie w bieżącej sesji bez delegowania. Osobny audyt nie jest wymagany przez plan; kontrolę stanowią regresje lokalnego zapisu i test interfejsu na izolowanych danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md`
- `ai_docs/quality/OFFLINE_PHOTO_SELECTOR_RELEASE_1_0_1_20261021.md`
- D-567: `ai_docs/process/decisions/DECISION_LOG_2026.md#d-567--edytowalny-kierunek-i-granica-500000-w-selektorze-windows`

## Scope

- Jedno wejście „Wybierz folder zdjęć”: źródło, projekt albo wynik z manifestem; dotychczasowe dowody tożsamości i preview przejęcia pozostają obowiązkowe.
- Usunięcie checkboxa potwierdzenia lokalnego dysku i rutynowych opisów lokalności; natywne sprawdzanie katalogów pozostaje.
- Kompaktowy nagłówek: skok, zoom, pełny ekran i „Wybierz kolejny folder”; bez logów podczas selekcji, bez przycisków poprzednie/następne.
- Jeden rząd „Wybierz”, „Pomiń”, „Cofnij”, „Zakres”; nazwa zdjęcia pod sterowaniem. Dolne operacje projektu pozostają.
- Uzupełnienie operatora: wspólny styl przycisków głównej aplikacji, kompaktowa wysokość 32 px w selektorze. Domyślny wygląd pozostałych konsumentów pozostaje bez zmian.
- Kolejny folder zachowuje grę i kierunek; anulowanie konfiguracji zachowuje poprzedni projekt.
- Limit nowych zakresów 500000. Pusta ostatnia plansza oznacza ten limit. Starszy zapis bez granicy otrzymuje ją transakcyjnie przy kolejnej decyzji/edycji, jeśli historia jest zgodna. Istniejące błędne JPEG-i nie są przepisywane; wymagają cofnięcia wyboru.
- Edycja zakresu zmienia kierunek dalszej pracy i może wznowić zakończoną numerację. Nie modyfikuje dotychczasowych decyzji. Kierunek nie zmienia naturalnej kolejności zdjęć.

## Out of scope

Webowy Reviewer, API, baza danych, dane operatora, automatyczny restart uruchomionego programu, scalenie i push.

## Acceptance criteria

- [x] Wszystkie elementy Scope działają w nowej paczce Windows.
- [x] Zakres 499996 kończy się na 500000; nazwa, liczba plansz i manifest są zgodne po restarcie.
- [x] Zmiana kierunku, ponowienie operacji i odzyskiwanie zapisu zachowują decyzje.
- [x] Wybór istniejącego źródła/projektu i przejęcie manifestu zachowują walidację plików.
- [x] Anulowanie wyboru kolejnego folderu i konfiguracji nie gubi bieżącej pracy.
- [x] Testy zmienionych części, lint, typecheck, build i docs:check przechodzą.

## Expected files

- `apps/selector-desktop/src/renderer/App.tsx`, `style.css` — ekran i sterowanie.
- `apps/selector-desktop/src/contracts.ts` — wynik rozpoznania folderu i kierunek polecenia range.
- `apps/selector-desktop/src/native/project-controller.ts` — begin, legacyAdopt, execute, validateCreate.
- `apps/selector-desktop/src/project/{project-store,project-storage,state-codec,types}.ts` — trwała konfiguracja zakresu.
- Testy i skrypty smoke selektora, wersja paczki oraz dokumentacja właścicielska.

## Test cases

Nowy projekt, źródło po restarcie, bezpośredni folder projektu, stary manifest z dowodami, błędny manifest, anulowanie dialogu, nowy folder tej samej gry, oba kierunki, granica 500000, niepoprawne liczby, zmiana kierunku po terminalnej decyzji, utrata odpowiedzi i restart procesu.

## Verification

Komendy z katalogu głównego, każda ograniczona istniejącym `apps/selector-desktop/scripts/run-bounded.mjs` do 120 s: testy selektora, lint, typecheck, build, docs:check i code-map:check. Pakowanie i test Electron na izolowanych fixture'ach, bez przejmowania procesu operatora.

## Risks / open questions

Brak blokujących pytań. Limit 500000 jest poleceniem operatora dla selektora Windows; wspólny rdzeń i inne aplikacje nie zmieniają kontraktu. Zmiana kierunku dotyczy dalszych decyzji; undo usuwa ostatnią decyzję i zachowuje aktualnie wybrany kierunek.

## Outcome

Commit: v1.7.451 (hash dopisuje kolejny commit).

### Changed

- Zrealizowano wszystkie osiem poprawek operatora, zmianę kierunku oraz późniejsze uzupełnienie stylu i wysokości przycisków.
- Jedno rozpoznawanie folderu źródła, projektu i manifestu. Przejęcie zachowuje preview i ponownie sprawdza dowody przed zapisem do nowych katalogów. Błędne manifesty nie są zmieniane.
- Kompaktowy interfejs, wspólna paleta i primaryButton/secondaryButton z Adminem, wysokość 32 px; domyślny styl Admina pozostaje 42 px. Natywne kontrole lokalizacji pozostały mimo usunięcia checkboxa.
- Limit 500000 w konfiguracji, JPEG-ach i manifeście. Zmiana kierunku ma trwały, idempotentny zapis w ledgerze; może wznowić terminalną selekcję. Wcześniejsze decyzje i naturalny porządek zdjęć pozostają.
- Kolejny folder zachowuje grę i kierunek. Anulowanie oraz błąd utworzenia nowej partii zachowują poprzedni projekt.

### Verification results

- Pełne pokrycie 269 testów selektora w grupach. Pierwszy pełny przebieg: 267/268, wykryta regresja importu terminalnego v1 naprawiona. Końcowy przebieg monolityczny przekroczył 120 s; do tego momentu wszystkie wykonane przypadki zaliczone. Pozostałe dwa scenariusze compact-persistence zaliczone osobno, pozostałe pliki 171/172; ostatni błąd pochodził z nieoczekiwanego równoległego zamknięcia workera w nowym teście. Naprawiono hook sprzątający bez osłabiania asercji; cały legacy-contract zaliczony 27/27. Brak otwartych porażek; procesy po timeout sprawdzone, brak osieroconych procesów testowych.
- Lint, typecheck i formatowanie zmienionych plików: PASS. Bundlowanie CSS Admina ze współdzielonymi importami: PASS. code-map:check oraz docs:check: PASS.
- Zbudowano ZIP 1.0.1 i zweryfikowano SHA-256, strukturę app.asar oraz uruchomienie rozpakowanego EXE. Trzy scenariusze finalnego ZIP-a: workflow, legacy i start — PASS. Workflow potwierdza rzeczywiste 32 px, kolor, domyślne 42 px współdzielonego stylu, rzędy kontrolek, fullscreen, zakres 499996–500000, pięć plansz, zmianę kierunku, anulowanie i nowy proces.
- Test przerwania procesu po prepared i retry tej samej zmiany kierunku oraz granicy: PASS. Błędy środowiska piaskownicy rozwiązywano uruchomieniem natywnych kontroli z odpowiednimi uprawnieniami, bez zmian mechanizmu bezpieczeństwa.
- Audyt krzyżowy nie był wymagany przez plan; zadanie zlecono bez planu wymagającego audytu. Nie delegowano.

### Not completed

- Nie zmieniano danych i aktywnego programu operatora, nie uruchamiano jego usług, migracji, benchmarków ani testu na drugim komputerze. Nie wykonano scalenia ani push.
- Poprzednie pliki z zakresem przekraczającym 500000 wymagają cofnięcia błędnego wyboru i ponownego zapisu; nie są automatycznie nadpisywane.

### Documentation updates

Wymagania, architektura, D-567 i indeks decyzji, instrukcja operatora, raport wydania, DOC_INDEX, mapa kodu i stan zadania. Kryteria akceptacji i właściwe punkty Definition of Done spełnione; Android nie dotyczy aplikacji Electron Windows.

### Recommended next task

Odbiór paczki 1.0.1 przez operatora, akceptacja wyniku i osobna zgoda na scalenie. Końcowy ZIP po commicie jest odtwarzany z tą samą implementacją, a jego pochodzenie i sumy zapisuje raport wydania.
