---
title: Naturalna komunikacja i oszczędzanie kontekstu
status: done
last_updated: 2026-11-04
---

# TASK-1159 — Naturalna komunikacja i oszczędzanie kontekstu

## Status

`done`

## Goal

Usunąć automatyczne wymuszanie Caveman w instrukcjach projektu i zastąpić je
normalną komunikacją oraz zasadami ograniczania zbędnego kontekstu i wyników narzędzi.

## Context

Operator zlecił usunięcie Caveman, ponieważ nie widzi istotnych oszczędności,
i zapisanie trwałej reguły oszczędzania tokenów bez pogarszania komunikacji.

## Dependencies / entry conditions

- Bezpośrednie polecenie operatora z 2026-11-04; bez osobnego planu.
- Zakres: instrukcje tego repozytorium, nie globalne odinstalowanie osobistego skilla.
- Brak pytań blokujących; model domeny, API i architektura produktu bez zmian.

## Recommended execution

Bieżąca sesja Codex, bez delegowania i dodatkowego audytu: mała zmiana dokumentacji
procesowej, niewymagająca planu wykonawczego ani zmiany modelu.

## Relevant docs

- `AGENTS.md`
- `CLAUDE.md`
- `ai_docs/guides/TOKEN_TOOLING.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `.agents/skills/task-close/SKILL.md`

## Scope

- Naturalna komunikacja i brak automatycznego uruchamiania skilli stylu rozmowy.
- Celowane odczyty, ograniczone wyniki narzędzi, unikanie powtórzeń i duplikacji reguł.
- Spójność instrukcji Codex i Claude; zachowanie obowiązkowych kontroli jakości.

## Out of scope

- Globalna konfiguracja użytkownika i pliki skilla poza repozytorium.
- Kod produktu, usługi, dane, pomiar tokenów, merge i push.

## Acceptance criteria

- [x] `AGENTS.md` i `CLAUDE.md` nie nakazują Caveman.
- [x] Reguła wymaga naturalnej komunikacji i oszczędzania przez sposób pracy.
- [x] Obowiązkowe odczyty i kontrole pozostają wymagane, bez obietnic oszczędności bez pomiaru.
- [x] Zapisane pliki sprawdzone w nowym procesie; `docs:check` przechodzi.

## Technical notes

Właścicielem reguły jest `AGENTS.md`; `CLAUDE.md` zawiera krótką instrukcję
startową i odsyła do właściciela. Historyczne raporty pozostają bez zmian.

## Expected files

- Istniejące: `AGENTS.md`, reguła rozmowy i sekcja „Oszczędzanie kontekstu”.
- Istniejące: `CLAUDE.md`, pierwsza reguła startowa.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`; archiwum aktualizuje `close_task.py`.
- Nowy: ten plik zadania, następnie przeniesiony do `completed/` przez skrypt.

## Test cases

- Wyszukiwanie Caveman w obu aktywnych instrukcjach nie daje trafień.
- Odczyt zapisanych reguł w nowym procesie potwierdza naturalny język i zachowanie kontroli.
- `git diff --check` oraz `npm run docs:check` kończą się kodem 0.

## Verification

Z katalogu repozytorium, każda komenda z limitem 120 s:

```powershell
rg -n -i caveman AGENTS.md CLAUDE.md
git diff --check
npm run docs:check
```

Pierwsza komenda: oczekiwany kod 1 (brak dopasowań); pozostałe: kod 0.
Testy aplikacji, lint kodu i typecheck nie dotyczą zmiany samych instrukcji Markdown.

## Risks / open questions

- To reguły dla agentów, a nie miernik ani techniczny limit zużycia tokenów.
- Istniejące czaty mogą mieć poprzednią treść instrukcji; bieżące polecenie
  operatora odwołuje dawny styl, a nowe sesje odczytają zapisane pliki.

## Outcome

Commit: v1.7.558 / `fa5156c97d1216081a82041e7398bf765baaa6a0`.

### Changed

- Usunięto automatyczne wymuszanie Caveman w `AGENTS.md` i `CLAUDE.md`.
- Wprowadzono naturalną komunikację i ograniczanie zbędnych odczytów,
  wyników narzędzi, powtórnych kontroli oraz kopiowania dokumentacji.
- Zachowano obowiązkowe odczyty i kontrole jakości; skala oszczędności
  wymaga pomiaru. Właścicielem reguły pozostaje `AGENTS.md`.

### Verification results

- Odczyt plików i asercje w nowym procesie Python: PASS — brak Caveman w obu
  instrukcjach, naturalny język, oszczędzanie kontekstu i obowiązkowe kontrole.
- `git diff --check`: PASS.
- `npm run docs:check`: PASS — linki decyzji, okno stanu, wszystkie 11 budżetów
  odczytu startowego i 2 pary kopii skilli. Odczyt startowy: 43 976 B / 45 000 B.
- Skrócono istniejący akapit pilota bez zmiany wymagań, aby nowa reguła mieściła
  się również po zapisaniu instrukcji z końcami linii CRLF na Windows.
- Brak osobnego planu wymagającego audytu; audyt krzyżowy nie jest wymagany.

### Not completed

- Brak pomiaru tokenów; nie deklarowano ilościowego zysku.
- Nie odinstalowano globalnego skilla, nie zmieniono kodu ani usług.
- Bez merge i push; zmiana pozostaje na `codex/normal-communication`.

### Documentation updates

- Dwie instrukcje agentów, task i zapis stanu przez `task-close`.
- Brak zmian wymagań produktu, architektury i decyzji domenowych.

### Recommended next task

- Brak koniecznego kolejnego taska. Integracja po akceptacji operatora.
