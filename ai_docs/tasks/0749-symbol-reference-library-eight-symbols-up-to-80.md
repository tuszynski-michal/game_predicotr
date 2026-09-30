---
title: TASK-0749 — B2 — zapis biblioteki wzorców dla oczekujących komórek ośmiu symboli z pewnością ≤ 80%
status: in_progress
last_updated: 2026-09-30
---

# TASK-0749 — B2 — zapis biblioteki wzorców dla oczekujących komórek ośmiu symboli z pewnością ≤ 80%

## Status

`in_progress`

## Goal

Drugi przebieg D-466: pewne propozycje biblioteki wzorców zapisane jako nowa
wersja predykcji dla oczekujących komórek z predykcją modelu Wiśnia,
Winogron, Cytryna, Pomarańcz, Śliwka, Arbuz, Gwiazda i Siedem oraz
pewnością modelu ≤ 80% w grze `777`.

## Context

Polecenie operatora 2026-09-30: przepuścić przez nowy algorytm wszystkie
oczekujące symbole 1–8 z jakością rozpoznania równą lub mniejszą od 80%;
komórki powyżej 80% i pozostałe symbole zostają bez zmian. Polecenie jest
zgodą na zapis wymaganą przez D-466.

## Dependencies / entry conditions

- TASK-0744–0746 i TASK-0748 scalone do `v1.1-vision-lab-hybrid-geometry`.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo); kontrola po zapisie
odczytem bazy.

## Relevant docs

- `ai_docs/process/DECISION_LOG.md` (D-466)
- `ai_docs/tasks/completed/0744-symbol-reference-library-writer.md`
- `ai_docs/tasks/completed/0748-symbol-reference-library-arbuz-below-60.md`

## Scope

- Dla każdego symbolu osobny manifest (`apply-preview --symbol <KOD>
  --max-confidence 0.80000001`; narzędzie porównuje `pewność < max`, więc
  granica obejmuje 80%), zapis (`apply`) w porcjach i `apply-verify`.
- Arbuz: komórki zapisane w B1 są wykluczane (`already_library_prediction`).

## Out of scope

- Komórki z pewnością > 80%, inne symbole, zatwierdzanie komórek.

## Acceptance criteria

- [ ] Osiem manifestów z sumami kontrolnymi; zapis tylko dla tych sum.
- [ ] Zapis bez błędów; `apply-verify` zgodny z manifestami.
- [ ] Liczniki filtra „Nowy algorytm” zgodne z sumą zapisów.

## Technical notes

- Sterownik: kolejno dla każdego symbolu podgląd do końca (kod 3 = powtórz),
  zapis porcjami po 100 s, weryfikacja; każdy inny kod zatrzymuje przebieg.

## Test cases

- `apply-verify` po każdym symbolu; liczniki API po całości.

## Outcome

Wypełnia agent po pracy.
