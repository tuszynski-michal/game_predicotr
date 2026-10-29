---
title: Kopia reguł i wypłat Mumie a1 do nowej gry
status: done
last_updated: 2026-10-29
---

# TASK-1109 — Kopia reguł i wypłat Mumie a1 do nowej gry

## Status

`done`

## Goal

Zapisać w Mumie a2 pełną, zgodną kopię najnowszych opublikowanych reguł Mumie a1, z wymiarami, kosztem spinu, liniami i wypłatami.

## Context

Operator poprosił o skopiowanie reguł i payout po błędzie importu `GAME_BOARD_TOPOLOGY_REQUIRED`. Gra używana przez import to `mumie-aktu2` / `246a1f54-eee8-49d5-b11a-0fde70e5eecd`, nie drugi rekord o nazwie Mumie a2. Ma 10 aktywnych symboli i zero wersji reguł. Źródło `mumie` ma najnowszą opublikowaną wersję 3, UUID `4482fb16-a910-4dfa-b594-d2dbd1cf9aed`, 3 × 5, koszt spinu 10 kredytów, 5 linii i 34 wypłaty.

## Dependencies / entry conditions

Kody, status i role dziesięciu symboli oraz rodzaj supergry obu gier są zgodne. Numery mobileCode Ra i Sarkofagu różnią się; mapowanie musi korzystać z kodów domenowych, nie numerów ani UUID źródła.

## Recommended execution

Bieżąca sesja Codex; ograniczona operacja istniejącym API, bez implementacji, planu, delegowania i dodatkowego audytu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` — Games, Payout rules i publikacja.
- `ai_docs/architecture/API_CONTRACT.md` — Rules versions i Payout rule.
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Kopia najnowszej opublikowanej wersji jako szkic w nowej grze.
- Wymiary, koszt spinu, wszystkie linie, minimum symboli, statusy i wypłaty.
- Snapshot źródła i celu, zapis wykonanych żądań i odpowiedzi, porównanie semantyczne w nowym procesie.

## Out of scope

Publikacja, zmiana źródła, zmiana katalogu symboli i mobileCode, kopiowanie obrazów lub modeli, start importu, zmiana kodu lub API, migracja, restart, merge i push.

## Acceptance criteria

- [x] Docelowy szkic ma 3 rzędy, 5 kolumn i koszt spinu 10.
- [x] Pięć linii i 34 wypłaty są identyczne po mapowaniu symboli po kodzie.
- [x] Dziesięć konfiguracji symboli ma zgodne minima i statusy, w tym Mumia jako Wild i trigger 3.
- [x] Raport gotowości publikacji jest ready, bez publikowania.
- [x] Nowy proces potwierdza zgodność kopii i brak zmiany źródła.
- [x] Dokumentacja przechodzi docs:check; task zamknięty skillem task-close.

## Technical notes

Przed zapisem snapshot i walidacja dokładnego zakresu. Nowy szkic powstaje tylko przy pustej liście wersji docelowych. Po utracie odpowiedzi nie ponawiać ślepo tworzenia; porównać listę wersji i zapisany dziennik. Żądania mają limit 15 s, cały przebieg 120 s. Istniejące endpointy, bez bezpośredniego SQL. Kopia pozostaje szkicem, wystarczającym do określenia wymiarów importu.

## Expected files

- Nowy: niniejszy task (po zakończeniu w completed).
- Nowy: `ai_docs/quality/MUMIE_RULES_COPY_20261029.json` — snapshoty, mapowanie i receipty.
- Istniejące: `CURRENT_STATE.md` i archiwum stanu, aktualizowane przez task-close.

## Test cases

Normalizacja źródła i celu przez kody symboli: porównać wymiary, spinCost, rowPath, kolejność i statusy linii, minima, matchLength, payoutCredits oraz aktywność. Raport publikacji bez blokad. Źródło bez zmian.

## Verification

HTTP timeout 15 s, limit przebiegu 120 s. Nowy proces odczytuje kopię i źródło. `npm run docs:check` z limitem 120 s.

## Risks / open questions

Przyjęto najnowszą opublikowaną wersję źródła, a nie historyczną stawkę 100 kredytów; operator otrzymał tę informację przed zapisem. Brak potrzeby zmiany modelu domenowego lub architektury.

## Outcome

Commit: v1.7.508 (hash dopisuje kolejny commit).

### Changed

- Utworzono szkic reguł v1 (`c7854ca8-3b8b-44a1-acc7-37d11128ce76`) w grze `mumie-aktu2`, kopię opublikowanej wersji v3 Mumie a1: 3 × 5, koszt 10 kredytów, 5 linii, 10 konfiguracji symboli i 34 wypłaty.
- Symbole mapowano po kodach, zachowując docelowe UUID, mobileCode, obrazy i role. Nie zmieniono źródła ani katalogu symboli docelowej gry.
- Zapisano snapshot i dziennik 50 potwierdzonych zapisów HTTP w `ai_docs/quality/MUMIE_RULES_COPY_20261029.json`.

### Verification results

- Nowy proces 2026-10-29 21:54:49 UTC: pełna zgodność semantyczna wymiarów, kosztu, linii, minimów i wypłat. SHA znormalizowanej konfiguracji: `52769e533951a4a65ff2f367668f35912f327820316c2da9dd9b02eb57a30d1f`.
- Gotowość publikacji: `ready=true`, zero blokad. Wersja pozostaje `draft`; katalogi symboli oraz źródłowe reguły, linie i wypłaty są niezmienione.
- `npm run docs:check`: PASS — decyzje i kotwice, okno stanu, wszystkie 11 budżetów i kopie skillów. Odczyt startowy 43 408 B.
- Definition of Done: kryteria operacyjne spełnione. Kod, API i schemat bez zmian, więc lint, typecheck, migracje i testy implementacji nie dotyczą tej operacji. Żaden plan nie wymaga dodatkowego audytu.

### Not completed

Nie publikowano reguł i nie uruchamiano importu, treningu, usług, migracji, merge ani push. Nie zmieniono drugiego rekordu Mumie a2 (`mumie-a2`).

### Documentation updates

Task, snapshot z dziennikiem i wpis ukończenia w stanie projektu. Użyto istniejącego API; wymagania i architektura nie zmieniły się.

### Recommended next task

Odświeżyć raport importu dla `mumie-aktu2`, ponownie potwierdzić pominięcie zdjęcia bez przypisania i uruchomić import. Reguły pozostały szkicem do dalszej edycji i osobnej publikacji.
