---
title: TASK-0833 — B6 — zapis biblioteki wzorców dla oczekujących komórek Arbuz z pewnością ≥ 99%
status: in_progress
last_updated: 2026-10-04
---

# TASK-0833 — B6 — zapis biblioteki wzorców dla oczekujących komórek Arbuz z pewnością ≥ 99%

## Status

`in_progress`

## Goal

Szósty przebieg D-466: pewne propozycje biblioteki wzorców zapisane jako nowa
wersja predykcji dla oczekujących komórek z predykcją modelu Arbuz i pewnością
modelu ≥ 99% (łącznie z 100%) w grze `777`.

## Context

Polecenie operatora 2026-10-04: Arbuz po zakończeniu całej Śliwki (TASK-0832),
z zakończeniem nocnej części do 2026-10-05 11:00–12:00 czasu lokalnego (09:00–10:00
UTC), bo operator robi wtedy restart i migracje. Reszta Arbuza po restarcie.
Polecenie jest zgodą na zapis wymaganą przez D-466.

Pomiar 2026-10-04 (oczekujące, `virtual_source`, bez flagi jakości, pełna
widoczność, bez komórek przepisanych już przez bibliotekę): 836 159 komórek,
723 344 w paśmie 99–<100% i 112 815 równych 100%.

## Dependencies / entry conditions

- TASK-0832 zakończony: sterownik startuje po wpisie `driver done` w logu
  Śliwki i nie startuje, jeśli tamten przebieg się zatrzymał.
- `--shard` (TASK-0829) jest na gałęzi integracyjnej; przebieg używa skryptu z
  głównego checkoutu.

## Recommended execution

`claude-opus-5-5`, reasoning `high`; kontrola po zapisie odczytem bazy.

## Relevant docs

- `ai_docs/process/DECISION_LOG.md` (D-466)
- `ai_docs/tasks/0832-symbol-reference-library-sliwka-99-100.md`

## Scope

Piętnaście części, od najniższej pewności (tam biblioteka zmienia najwięcej),
każda kolejno: `apply-preview` do końca, `apply`, `apply-verify`:

| Część | `--min-confidence` | `--max-confidence` | `--shard` | Komórki |
| --- | --- | --- | --- | --- |
| 01 | 0.99000001 | 0.99821398 | 0/1 | 57 867 |
| 02 | 0.99821398 | 0.99951685 | 0/1 | 57 867 |
| 03 | 0.99951685 | 0.9998546 | 0/1 | 57 864 |
| 04 | 0.9998546 | 0.99995635 | 0/1 | 57 868 |
| 05 | 0.99995635 | 0.99998669 | 0/1 | 57 841 |
| 06 | 0.99998669 | 0.99999564 | 0/1 | 57 819 |
| 07 | 0.99999564 | 0.99999847 | 0/1 | 57 646 |
| 08 | 0.99999847 | 0.99999944 | 0/1 | 57 219 |
| 09 | 0.99999944 | 0.99999979 | 0/1 | 56 488 |
| 10 | 0.99999979 | 0.99999992 | 0/1 | 53 346 |
| 11 | 0.99999992 | 0.99999997 | 0/1 | 49 334 |
| 12 | 0.99999997 | 0.99999999 | 0/1 | 46 026 |
| 13 | 0.99999999 | 1.0 | 0/1 | 56 159 |
| 14–15 | 1.0 | 1.0001 | 0/2, 1/2 | 56 504, 56 311 |

- Okno nocne: żadna nowa część nie startuje po 2026-10-05 07:00 UTC, a po
  09:15 UTC sterownik nie zaczyna nowej rundy (część przerwana w ten sposób
  jest wznawialna). Pozostałe części po restarcie i migracjach operatora.

## Out of scope

- Inne symbole, zatwierdzanie komórek, zmiany kodu narzędzia.

## Acceptance criteria

- [ ] Manifest z sumą kontrolną dla każdej wykonanej części; zapis tylko dla tych sum.
- [ ] Zapis bez błędów (plansze `stale` dopuszczalne i opisane).
- [ ] `apply-verify` każdej części zgodny z manifestem.
- [ ] Wszystkie piętnaście części (po restarcie operatora).

## Technical notes

- Sterownik jak w TASK-0828/0832 (budżet podglądu 300 s, zapisu 240 s, twardy
  limit procesu 600 s; kod 3 = powtórz). Manifesty w worktree
  `artifacts/symbol-reference-library/apply-arbuz-ge99-<NN>/`, log
  `arbuz-ge99-driver.log`.

## Test cases

- `apply-verify` po każdej części; liczniki po całości.

## Stan i wznowienie

- Stan 2026-10-04 18:15 UTC: sterownik czeka w tle na `driver done` Śliwki
  (TASK-0832); żadna część nie jest jeszcze zaczęta. Spodziewane w nocy
  części 01–05 (~290 tys. komórek), koniec ~08:30 UTC.
- Po restarcie i migracjach operatora: wznowienie od pierwszej części bez
  `apply-verify.json` w `artifacts/symbol-reference-library/apply-arbuz-ge99-<NN>/`
  (worktree), poleceniem z `artifacts/symbol-reference-library/drivers/README.md`
  (`run-arbuz-ge99.ps1 -FirstPart N` z odległymi `-NoNewPartAfterUtc` i
  `-HardStopUtc`). Część przerwana twardym limitem zaczyna od nowego podglądu;
  zapisane już komórki wypadają jako `already_library_prediction`.

## Outcome

W toku.
