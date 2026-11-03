---
title: Spójne przyciski i odstępy jakości rozpoznawania
status: done
last_updated: 2026-11-02
---

# TASK-1133 — Spójne przyciski i odstępy jakości rozpoznawania

## Status

`done`

## Goal

Zastąpić natywne szare przyciski akcji paneli geometrii istniejącymi wariantami
primary/secondary i rozdzielić sąsiadujące akcje w jakości rozpoznawania.

## Context

Operator wskazał niespójne przyciski i stykające się Ulepsz rozpoznawanie /
Przelicz oczekujące plansze. Nowe panele V3 nie mają klas z packages/ui/buttons.css.
Lokalna klasa buttonRow nie ma reguły układu w tym obszarze.

## Dependencies / entry conditions

Main v1.7.522, brak cudzych zmian śledzonych. Numery 1124–1132 zarezerwowane
w równoległym planie; 1133 wolny. API pozostaje bez zmian.

## Recommended execution

gpt-6.1-sol/high. Mała poprawka prezentacji; bez delegowania. Przed commitem
niezależny Claude Code claude-opus-5-5/high, zgodnie z ustaleniem operatora.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md, TASK_TEMPLATE.md, DEFINITION_OF_DONE.md
- ai_docs/requirements/ADMIN_APP.md (Forma aplikacji)
- ai_docs/architecture/VISION_LAB.md (panel geometrii)
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md (model-quality)
- packages/ui/src/buttons.css (źródło istniejących wariantów)

## Scope

Klasy przycisków w apps/admin/src/features/model-quality/*.tsx, lokalne odstępy
w globals.css / grid-correction-learning.css i dokumentacja wymagań. Zachować
obsługę akcji, disabled, polling, etykiety i guardy wszystkich konsumentów.

## Out of scope

API, baza, uczenie/aktywacja, restart usług, nowy system przycisków i style
innych obszarów. Merge/push wymagają akceptacji wyniku.

## Acceptance criteria

- [x] Przyciski akcji geometrii używają istniejącego primaryButton lub secondaryButton.
- [x] Główne start/zastosowanie są primary, odczyty/nawigacja/anulowanie secondary.
- [x] Akcje symboli i geometrii mają odstęp i zawijają się na wąskim ekranie.
- [x] Istniejące interakcje, scoped lint/typecheck i docs:check PASS.
- [x] Oględziny działającego panelu bez uruchomienia treningu; audyt bez P0/P1.
- [x] Outcome, task-close, osobny commit i record-hash.

## Technical notes

Stosować klasy istniejącego arkusza packages/ui, bez kopiowania kolorów.
Zakres CSS ograniczyć do jakości rozpoznawania. Działający Admin dev sam
odświeża samą prezentację (HMR), bez restartu usług.

## Expected files

Istniejące: model-quality/*.tsx z natywnymi button; globals.css,
grid-correction-learning.css, ADMIN_APP.md; task i CURRENT_STATE.
Bez nowych modułów/publicznych symboli; mapa kodu powinna pozostać aktualna.

## Test cases / Verification

Istniejące test-interactions paneli geometrii i symboli, scoped ESLint,
TypeScript oraz docs/map checks. Pełny build nie jest potrzebny dla tej zmiany
klas/układu i nie ingeruje się w cache aktywnego Admin dev. Oględziny szerokości desktop i mobile.
Bez nowych testów odwzorowujących same klasy CSS. Komendy z limitem <=110 s,
audyt wewnętrzny 480 s / zewnętrzny 570 s.

## Risks / open questions

Brak blokujących pytań. Zmiana tylko prezentacji. Nie uruchamiać przycisków
treningu/aktywacji podczas sprawdzania wyglądu.

## Outcome

Commit: v1.7.523 / `009217d2fb25aa63b194fed5c4978de8c151e283`.

### Assumptions recorded before coding

Praca na gałęzi roboczej w D:/game_predicotr, żeby istniejący Admin dev pokazał
żądaną zmianę prezentacji bez osobnej instancji i restartu. Ref main pozostaje
nieruszony do jawnej akceptacji scalenia; inne worktrees zachowane.

### Changed

79 przycisków w 12 panelach geometrii dostało istniejące klasy primary/secondary.
Osiem grup sąsiadujących akcji otrzymało buttonRow. Lokalne reguły flex-wrap/gap
naprawiają odstęp akcji symboli i geometrii oraz pola zaawansowane. Usunięto
lokalny padding przycisków uczenia, aby używały tego samego wyglądu co wzorzec.
Kolorów nie skopiowano; używany jest packages/ui/src/buttons.css.


### Verification results

87/87 istniejących interakcji PASS (7 plików, 6.03 s wrapper / 5.534 s testy).
Scoped ESLint 12 TSX PASS (14.69 s); pełny frontend tsc --noEmit PASS (15.72 s).
Prettier 14 plików PASS. docs:check, code-map:check i git diff --check PASS.
Nie dodawano testów odwzorowujących klasy CSS. Pełny build pominięty celowo:
zmiana samej prezentacji, weryfikowana przez tsc, istniejące interakcje oraz
kompilację HMR działającego Admina, bez ingerencji w jego cache produkcyjnym buildem.

Przeglądarka, rzeczywista gra Mumie a2: oba primary mają rgb(112,225,180),
secondary rgba(255,255,255,0.035). Symbole mają wysokość 42 px; geometria po
poprawce P2 zachowuje wcześniejsze minimum 44 px przez --button-height, bez
kopiowania kolorów ani paddingu.
Odstęp Ulepsz rozpoznawanie / Przelicz oczekujące wynosi 12 px. Brak przycisków
HTML button bez primary/secondary w Geometrii V3. Przy 390 px szerokości akcje
zawijają się z pionową przerwą 12 px i mieszczą się w ekranie. Rozmiar podglądu
przywrócono; brak błędów konsoli. Nie wykonywano akcji treningu ani publikacji.

Zauważono niezależny, istniejący komunikat błędu GPU w dwóch próbach uczenia
operatora. Ten task zmienia wyłącznie wygląd i nie diagnozuje ani nie naprawia
tego problemu. Nie uruchamiano wznowienia/treningu podczas oględzin.


### Cross audit

[Claude Code Opus 5.5/high](../../quality/TASK-1133_AUDIT_claude-opus-5-5.md): PASS,
runda 1, bez P0/P1. Obie uwagi P2 naprawiono w jednej rundzie: osobna klasa grid
z odstępem dla odzyskiwania polecenia reinference oraz --button-height:44px dla
panelu uczenia. Po poprawkach 24/24 interakcji dotkniętych paneli PASS, scoped
ESLint i frontend tsc PASS; przeglądarka potwierdziła 44 px i niezmienione kolory.
Bez kolejnej rundy audytu dla samych poprawek P2. Raport audytora zachowano.

### Not completed

Merge/push oraz wszelkie operacje na modelach poza zakresem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1133 | gpt-6.1-sol | high | Ograniczona poprawka prezentacji i regresja istniejących akcji | Claude Code claude-opus-5-5/high przed commitem |
