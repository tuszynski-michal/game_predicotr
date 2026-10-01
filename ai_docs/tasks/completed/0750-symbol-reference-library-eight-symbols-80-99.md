---
title: TASK-0750 — B3 — zapis biblioteki wzorców dla oczekujących komórek ośmiu symboli z pewnością 80–99%
status: done
last_updated: 2026-09-30
---

# TASK-0750 — B3 — zapis biblioteki wzorców dla oczekujących komórek ośmiu symboli z pewnością 80–99%

## Status

`done`

## Goal

Trzeci przebieg D-466: pewne propozycje biblioteki wzorców zapisane jako nowa
wersja predykcji dla oczekujących komórek z predykcją modelu dla symboli 1–8
i pewnością modelu powyżej 80% i poniżej 99% w grze `777`.

## Context

Polecenie operatora 2026-09-30 („przepuść 80–100%”). Pomiar skali: 80–99% —
335 tys. komórek; 99–<100% — 6,16 mln; 100% — 0,92 mln. Całość wymagałaby ok.
35 h renderowania, ok. 24 h zapisu i ok. 90 GB cache przy 49 GB wolnego
miejsca, a przy ≥ 99% zapis głównie obniżałby pewność potwierdzeń do 0,99.
Operator wybrał wariant „tylko 80–99%”.

## Dependencies / entry conditions

- TASK-0749 done (`v1.7.81`).

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo); audyt `claude-opus-5-5`
tylko przy zmianach kodu.

## Relevant docs

- `ai_docs/process/DECISION_LOG.md` (D-466)
- `ai_docs/tasks/completed/0749-symbol-reference-library-eight-symbols-up-to-80.md`

## Scope

- Dla każdego symbolu manifest `apply-preview --min-confidence 0.80000001
  --max-confidence 0.99` (narzędzie: `pewność >= min` i `< max`; 80% dokładnie
  objął TASK-0749), zapis porcjami, `apply-verify`.

## Out of scope

- Pewność ≥ 99%, inne symbole, zatwierdzanie komórek.

## Acceptance criteria

- [x] Osiem manifestów z sumami kontrolnymi; zapis tylko dla tych sum.
- [x] Zapis bez błędów (plansze `stale` dopuszczalne i opisane).
- [x] `apply-verify` zgodny z manifestami.

## Technical notes

- Sterownik jak w TASK-0749 (podgląd do końca, zapis porcjami po 100 s,
  weryfikacja; kod inny niż 0/3 zatrzymuje przebieg).

## Test cases

- `apply-verify` po każdym symbolu; liczniki po całości.

## Outcome

- Przebieg 2026-09-30 05:25–20:01 UTC (sterownik w tle; od Winogronu
  uruchamiany z głównego checkoutu, żeby edycje w worktree nie przerywały
  zapisu; budżet porcji obniżony do 80 s po jednym przekroczeniu limitu
  procesu). Manifesty w worktree
  `artifacts/symbol-reference-library/apply-<symbol>-80-99/` (poza Gitem):

  | Symbol modelu | Komórki w zakresie | Zapisane | Potwierdzenia | Zmiany (największe) | Plansze | Manifest |
  | --- | --- | --- | --- | --- | --- | --- |
  | Cytryna | 16 104 | 10 479 | 5 437 | 5 042 (Arbuz 2 173, Gwiazda 1 879, Pomarańcz 812) | 8 638 | `0b1c7f67…` |
  | Wiśnia | 26 936 | 25 477 | 24 713 | 764 (Gwiazda 359) | 21 063 | `dad37f4f…` |
  | Siedem | 35 364 | 28 488 | 26 366 | 2 122 (Gwiazda 941, Pomarańcz 607) | 22 111 | `d511cc89…` |
  | Winogron | 39 940 | 36 651 | 27 462 | 9 189 (Śliwka 3 483, Siedem 2 050, Wiśnia 1 753) | 29 448 | `e3ce46e1…` |
  | Śliwka | 41 085 | 30 331 | 23 943 | 6 388 (Winogron 5 919) | 23 360 | `ab2243bb…` |
  | Arbuz | 52 986 | 48 598 (+1 `stale`) | 41 538 | 7 060 (Wiśnia 2 956, Pomarańcz 1 495) | 37 127 | `ed2d4b4a…` |
  | Pomarańcz | 58 074 | 54 474 | 53 568 | 906 (Arbuz 412, Gwiazda 313) | 42 888 | `863ea8fd…` |
  | Gwiazda | 64 214 | 63 396 | 62 863 | 533 (Wiśnia 410) | 41 988 | `68216695…` |

  Razem 297 894 komórki na 226 623 planszach; 0 błędów; 1 plansza
  `stale:cell_changed` (decyzja operatora w trakcie); 1 zakleszczenie z
  równoległą pracą w Adminie, wznowione. `apply-verify` każdego symbolu
  zgodny z manifestem.
- Stan po przebiegu (oczekujące): komórki z pewnością 0,99 (biblioteka):
  Arbuz 54 984, Cytryna 7 462, Gwiazda 77 693, Pomarańcz 66 680, Siedem
  34 544, Śliwka 36 631, Winogron 45 202, Wiśnia 37 886 — łącznie
  361 082; wersji `symbol-reference-library-v1`: 284 240. Bez pewnej
  propozycji w paśmie 80–99% (filtr „Stary model” + „80–<99%”): Śliwka
  10 784, Siedem 6 890, Cytryna 5 656, Arbuz 4 429, Pomarańcz 3 637,
  Winogron 3 305, Wiśnia 1 482, Gwiazda 877 — razem 37 060.
- Kontrola wzrokowa próbek: Cytryna → Arbuz / Gwiazda / Cytryna (30 na
  grupę) zgodne z propozycją; pozostałe grupy zmian powtarzają wzorce
  sprawdzone w TASK-0749.
- Wolne miejsce na C: spadło z 33 do 29 GB (martwe wiersze po aktualizacjach
  komórek; do odzyskania w S3 planu D-467).
