---
title: TASK-0965 — Decyzja D-541, dokumentacja i odbiór braków geometrii na żywych danych
status: todo
last_updated: 2026-10-10
---

# TASK-0965 — Decyzja D-541, dokumentacja i odbiór braków geometrii na żywych danych

## Status

`todo`

## Goal

Zakres lokalnego Reviewera (gra, zakładka „Braki zdjęć”, „Siatka
niepotwierdzona” tylko jako licznik) jest zapisany jako decyzja D-541 i
zweryfikowany na żywych danych Mumii i 777.

## Context

Plan: `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`. D-462
definiuje kolejkę korekty bez walidacji gotowych siatek; D-484 definiuje
kompletność i diagnostykę. Ten task dopisuje decyzję łączącą oba i zamyka plan
odbiorem.

## Dependencies / entry conditions

- TASK-0961–0964 `done`.
- Uruchomione lokalnie API (8000), Admin (3000) i Reviewer (3001) z
  kodem z tej gałęzi. Restart API i `npm run reviewer:build` wykonuje operator
  albo wymaga jego jawnej zgody (równoległe instancje API na jednej bazie —
  nie restartuj na własną rękę).
- Numer decyzji D-541 i wersja `vX.Y.N` sprawdzone na końcówce
  `v1.1-vision-lab-hybrid-geometry` bezpośrednio przed zapisem i przed
  scaleniem.

## Recommended execution

`claude-sonnet-5-5`, `medium` — zgodnie z tabelą planu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`
- `ai_docs/architecture/CODE_MAP.md`

## Scope

1. `DECISION_LOG.md` (indeks) i `decisions/DECISION_LOG_2026.md`: D-541 —
   lokalny Reviewer pracuje w zakresie gry; zakładka „Braki zdjęć” obejmuje
   realne braki (D-484: `incomplete_missing`, `incomplete_partial`,
   `import_failed`, `no_source_geometry`); „Siatka niepotwierdzona” pozostaje
   licznikiem w Adminie i nie jest kolejką (D-462 bez zmian w tej części);
   UI wyjątków bramki usunięte z Admina (API i audyt zostają); doprecyzowanie
   D-462 „Correction queue” i D-484 „diagnostyka”.
2. `CURRENT_STATE.md` zgodnie z regułą okna kroczącego; `API_CONTRACT.md`
   (parametry `counts`, `gapsOnly`, pole `humanApproved`); `CODE_MAP.md`
   (nowe moduły Reviewera, usunięte moduły Admina).
3. Odbiór na żywych danych (lista kontrolna poniżej) z zapisem wyników w
   `Outcome`.

## Out of scope

- Zmiany kodu aplikacji poza poprawkami wykrytymi w odbiorze (taki błąd
  wraca do właściwego taska, nie jest łatany tutaj po cichu).
- Scalanie i push (osobna zgoda operatora; patrz `merge-means-push`).

## Acceptance criteria

- [ ] D-541 w indeksie i w pliku decyzji, z odwołaniami do D-462/D-484.
- [ ] Odbiór — Mumie: Admin pokazuje „4 … 51 541”; „Otwórz lokalnie” otwiera
      Reviewer bez importu; „Braki zdjęć” = 4 zdjęcia; zdjęcia widoczne od
      razu; „Do korekty” = 0 z czytelnym stanem pustym.
- [ ] Odbiór — 777: „Do korekty” pokazuje 255 w czasie ≤ 3 s na planszę;
      „Plansza częściowa” pokazuje zdjęcia z ukrytymi zatwierdzonymi ręcznie;
      zapis jednej siatki testowej tylko za zgodą operatora (zapis zmienia
      dane).
- [ ] Pomiary czasu: `counts=correction` ≤ 3 s, `gapsOnly` ≤ 12 s na stronę.
- [ ] `npm run docs:check` zielone; `git diff --cached --check` czysty.

## Technical notes

Odbiór jest tylko do odczytu, poza jawnie uzgodnionym zapisem jednej siatki.
Dowody: zrzuty lub opis z przeglądarki (wbudowana przeglądarka aplikacji),
czasy z `curl -w`. Nie uruchamiaj benchmarków. Jeśli budżet czasu nie jest
spełniony, task kończy się jako `blocked` z wynikiem pomiaru; plan wymaga
korekty (TASK-0961), nie obejścia.

## Expected files

- Istniejące: `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/process/decisions/DECISION_LOG_2026.md`,
  `ai_docs/process/CURRENT_STATE.md`,
  `ai_docs/architecture/API_CONTRACT.md`,
  `ai_docs/architecture/CODE_MAP.md`.
- Nowe: brak.

## Test cases

- Lista kontrolna odbioru z kryteriów akceptacji; każda pozycja z wynikiem
  tak/nie i dowodem.

## Verification

```powershell
# katalog: korzeń worktree; timeout <= 120 s na komendę
npm run docs:check
git diff --cached --check
```

Zaliczenie: powyższe zielone oraz wypełniona lista odbioru w `Outcome`.
Testy planowane nie są wynikami wykonania.

## Risks / open questions

- Dane w bazie zmieniają się w trakcie importów — liczby w odbiorze mogą
  różnić się od liczb z planu; zapisz stan z dnia odbioru.
- `CODE_MAP.md` jest w głównym checkoucie zmodyfikowany przez inną pracę —
  uzgodnij zmiany względem końcówki gałęzi integracyjnej.

## Outcome

Wypełnia agent po pracy.

### Changed

- ...

### Verification results

- ...

### Not completed

- ...

### Documentation updates

- ...

### Recommended next task

- Opcjonalnie: przywrócenie UI wyjątków bramki; blokada ponownego importu
  tych samych zdjęć (osobna sesja).
