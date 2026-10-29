---
title: Plan płynności i niezawodności Selektora Windows
status: done
last_updated: 2026-10-29
---

# TASK-1103 — Plan płynności i niezawodności Selektora

## Status

`done` — plan gotowy; operator 2026-10-29 polecił kontynuować bez
audytu planu. Dokumentacja zamknięta; implementacja nieuruchomiona.

## Goal

Dostarczyć dokładny plan usunięcia przycięć i cichego pomijania F oraz zapisać
diagnostykę dostępu do Claude i decyzję operatora o pominięciu audytu planu,
bez implementacji aplikacji.

## Context

Operator zgłosił sporadyczny brak wyboru po F oraz przycięcia przy przechodzeniu
między zdjęciami. Poprosił o plan i jego audyt przed propozycją wdrożenia.
Po sprawdzeniu dostępu do Claude Code i próbie Fable operator zrezygnował
z audytu tego planu. Wcześniejsza diagnoza Codex nie była audytem Claude i nie dowodzi przyczyny
na urządzeniu odbiorcy. Osobno trzeba rozliczyć możliwość wpływu antywirusa.

## Dependencies / entry conditions

- Baza main `1c9c13fd72503b8bbc06584a81f6f3a7945fb3c0`; gałąź robocza
  `codex/selector-reliability-plan`. Nie dotykać wcześniejszych zmian operatora.
- Odczyt AGENTS.md, README, CURRENT_STATE, indeksu decyzji, PLAN_STANDARD,
  TASK_TEMPLATE, wymagań i architektury selekcji oraz skilla claude-audit.
- Zgoda na ten task dotyczy planu i audytu. Implementacja TASK-1104–1107,
  wydanie, merge/push i zmiana ochrony Windows nie są zlecone.

## Recommended execution

Rekomendacja wykonawcza planu: `gpt-6.1-sol` / `high`. Sesja nie udostępnia
odczytu własnego dokładnego identyfikatora modelu; nie deklarujemy zmiany modelu
ani faktycznego wykonania pod rekomendowanym identyfikatorem. Audyt planu
pominięty decyzją operatora 2026-10-29 („Kontynuuj bez audytu”). Poprzednia
próba Fable nie zwróciła odpowiedzi modelu. Przyszłe audyty implementacji
są osobnym zakresem, warunkowym do dostępności modelu.

## Relevant docs

- `AGENTS.md` i `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/process/PLAN_STANDARD.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`.
- `ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md` — **audytować
  cały plan**, w tym TASK-1104–1107, nie tylko opis TASK-1103. Przedmiotem
  audytu jest wykonalność i bezpieczeństwo proponowanych zmian, nie ich
  nieistniejąca implementacja. Wynik audytu wpisywany po uruchomieniu.
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`.
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`.
- D-545, D-546, D-547: kotwice w sekcji Relevant docs planu; pełne wpisy
  `ai_docs/process/decisions/DECISION_LOG_2026.md` (sekcje selektora).
- `ai_docs/architecture/CODE_MAP.md`, `CODE_MAP_SYMBOLS.md` (obszar selector).
- `ai_docs/quality/SELECTOR_OUTPUT_FOLDER_1_0_3_20261023.md`.
- `.codex/skills/claude-audit/SKILL.md`, `.agents/skills/task-close/SKILL.md`.
- `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md`.

## Scope

Plan z faktami/hipotezami, regułami F i płynnej nawigacji, odpowiedzialnościami
modułów, kontraktem IPC, granicami pamięci, błędami/retry, testami i odbiorem.
Zapis prób dostępu do Claude oraz rezygnacji operatora z audytu planu.
Aktualizacja indeksu dokumentów i stanu oraz commit samego taska planistycznego.

## Out of scope

Kod/zależności aplikacji, nowe wydanie, serwery, dane/oryginały operatora,
duże benchmarki, zmiany polityki ochrony, merge i push. Audyt nie może wymagać
zaliczonych testów proponowanej implementacji; musi ocenić ich zaplanowanie.

## Acceptance criteria

- [x] Plan opisuje wszystkie zgłoszenia i chroni właściwy imageId/range,
  trwałość po crashu, nieograniczoną liczbę JPEG-ów i zgodność starszych projektów.
- [x] Zadania mają zakres, warunki wejścia, pliki/symbole, błędy i retry,
  kryteria, scenariusze testów, komendy i ryzyka, plus końcową tabelę modeli.
- [x] Zapisano jawne odstąpienie operatora od audytu zgodnie z AGENTS.md;
  brak fałszywego werdyktu PASS i przypisanych Claude znalezisk.
- [x] `npm run docs:check` PASS po skryptowym zamknięciu taska: 1 aktywny task,
  10 wpisów done, 11/11 budżetów i obie pary mirrorów skilli zgodne.
- [x] Plan i raport określają ograniczenia i przyszły koszt 3–5 godzin;
  implementacja wymaga osobnej akceptacji zakresu i kosztu.

## Technical notes

Źródło prawdy pozostaje ProjectStore i dotychczasowe pliki head/journal/ledger.
Optymistyczny podgląd jest oznaczonym stanem oczekującym, nie trwałą decyzją.
Reguły interakcji są w planie proposed; nie zmieniać zaakceptowanych decyzji
produktowych przed zgodą operatora. Zachować rozróżnienie audytu planu i kodu.

## Expected files

- Nowy plan `ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md`.
- Ten task; niezależny raport audytu nie powstał i nie jest już wymagany
  w TASK-1103 po rezygnacji operatora.
- Nowy zapis blokera `ai_docs/quality/TASK-1103_CLAUDE_AUDIT_BLOCKER.md`;
  nie tworzyć pozornego rozliczenia znalezisk nieistniejącego audytu.
- Istniejące `ai_docs/DOC_INDEX.md`, `ai_docs/process/CURRENT_STATE.md`;
  skryptowe zamknięcie obejmie archiwum i przeniesienie taska do completed.

## Test cases

Statyczne pokrycie: delayed navigate→F, decode, repeat/duplikaty, zły JPEG,
anulowanie, crash i utracona odpowiedź, zgodność IPC, sourceId/revision,
budżet preview, zimny/ciepły podgląd, ZIP i pomiar ochrony bez jej wyłączania.
To scenariusze wymagane w planie, nie twierdzenie o ich wykonaniu.

## Verification

Z repo root, kontrolowane procesy: docs:check (120 s), git diff --check (30 s),
przegląd kryteriów PLAN_STANDARD/TASK_TEMPLATE i ścieżek z kodu. Historyczne
polecenie audytu (nie uruchamiać ponownie po rezygnacji operatora):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_task.ps1 `
  -Task 1103 -Auditor claude -Base HEAD -Model claude-fable-5-1 -Effort medium `
  -Paths ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md,ai_docs/tasks/1103-selector-fluency-plan.md,ai_docs/DOC_INDEX.md,ai_docs/process/CURRENT_STATE.md `
  -Plan ai_docs/delivery/SELECTOR_FLUENCY_RELIABILITY_PLAN_20261029.md -TimeoutSec 480
```

Powyższe polecenie wymagałoby nowego zlecenia audytu. Historyczne próby nie
stanowią zakończonego przeglądu. Nie deklarować PASS na podstawie logowania.

## Risks / open questions

Wersja i środowisko odbiorcy nieznane; nie blokują planu. Własnego dokładnego
modelu sesji nie odczytano. Polecenie Claude ma potwierdzić dostępność i wynik,
nie wolno nazwać samego --version audytem. Wcześniejsze czasy 1–2 godzin nie
obejmują pełnej teraz żądanej pracy nad płynnością; plan podaje 3–5 godzin
przyszłej implementacji, wymagających osobnej zgody.

## Outcome

Commit: v1.7.494 (hash dopisuje kolejny commit).

### Changed

- Przygotowano proposed plan z czterema przyszłymi taskami wykonawczymi.
- Doprecyzowano, że manifest zawiera kursor: nie można go pomijać w wysłanej
  nawigacji bez zmiany kontraktu; plan zachowuje cały mechanizm trwałości.
- Audyt planu pominięto na wyraźne polecenie operatora 2026-10-29
  „Kontynuuj bez audytu”. Nie powstał werdykt niezależnego audytora.
- Kontrola własna planu pokrywa wymagania, błędy/retry, trwałość, granice
  pamięci i kosztów oraz tabelę modeli. To nie audyt krzyżowy.

### Verification results

- Odczyt i porównanie kodu App, ImageViewer, contracts/preload/main,
  ProjectController, ProjectStore, source registry i manifestu.
- Poprzednia ograniczona próba komponentu: F podczas nawigacji/decode
  nie wysyła accept, gotowe zdjęcie wysyła jeden accept; to nie test Electron.
- Istniejący celowany test skrótów: 1/1 PASS w poprzedniej analizie.
- `npm.cmd run docs:check`: PASS przed próbami audytu (2 aktywne taski,
  10 wpisów done, 11/11 budżetów). Ponowna kontrola po zapisie blokera poniżej.
- Skrypt audytu: pierwsze wywołanie i próba z dostępem do sieci zakończyły się
  kodem CLI 1, bez raportu. Nie stanowią rund zakończonego audytu.
- CLI wykryte przez resolver skryptu, `--version` działa; `auth status`
  potwierdza loggedIn=true. Ograniczona próba modelu przez stdin (bez czytania
  repo) ujawniła blokadę subskrypcji przez organizację. Dostępność modelu
  `claude-opus-5-5` i audyt pozostają niezweryfikowane.
- Szczegóły: `ai_docs/quality/TASK-1103_CLAUDE_AUDIT_BLOCKER.md`.
- Po zapisie blokera: `npm.cmd run docs:check` PASS (2 aktywne taski,
  10 wpisów done, 11/11 budżetów); `git diff --check` PASS. Diff kodu
  selektora i lockfile jest pusty. Nie uruchamiano nowych testów aplikacji.
- Na dodatkowe zlecenie potwierdzono zgodność konta CLI i Claude desktop,
  profil Max oraz brak nadpisania konta/API w środowisku i ustawieniach.
  Fable 5.1 widnieje w cache modeli. Faktyczne wywołanie `claude-fable-5-1`
  / medium, limit 60 s, zakończyło się kodem 1, `is_error=true`, pustym
  modelUsage i komunikatem organizacji o wyłączonej subskrypcji Code.
  Proces zakończony; po poleceniu pominięcia audytu nie wykonano dalszych prób.
- Zamknięcie przez `close_task.py`: dry-run i właściwe zamknięcie PASS;
  docs:check po zamknięciu PASS. Lint/typecheck/testy aplikacji nie dotyczą
  zmiany wyłącznie dokumentacyjnej. Nie regenerowano mapy kodu (brak zmian
  modułów i publicznych symboli).

### Not completed

- Implementacja, pomiar na komputerze odbiorcy, nowe ZIP, merge/push: poza zgodą.
- Audyt planu i rozliczenie jego znalezisk niewykonane; operator jawnie
  odstąpił od audytu. Plan pozostaje proposed, bez zatwierdzenia implementacji.

### Documentation updates

- Plan, ten task, DOC_INDEX, CURRENT_STATE i zapis blokady audytu.

### Recommended next task

- TASK-1104 po akceptacji planu i kosztu implementacji; przed zadaniami
  wymagającymi niezależnego review potwierdzić dostępność Fable albo uzyskać
  osobną decyzję operatora. Nie wznawiać audytu planu bez nowego zlecenia.
