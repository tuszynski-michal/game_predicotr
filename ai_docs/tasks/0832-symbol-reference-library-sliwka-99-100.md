---
title: TASK-0832 — B5 — zapis biblioteki wzorców dla oczekujących komórek Śliwka z pewnością ≥ 99%
status: in_progress
last_updated: 2026-10-03
---

# TASK-0832 — B5 — zapis biblioteki wzorców dla oczekujących komórek Śliwka z pewnością ≥ 99%

## Status

`in_progress`

## Goal

Piąty przebieg D-466: pewne propozycje biblioteki wzorców zapisane jako nowa
wersja predykcji dla oczekujących komórek z predykcją modelu Śliwka i pewnością
modelu ≥ 99% (łącznie z 100%) w grze `777`.

## Context

Polecenie operatora 2026-10-03: po Winogronie (TASK-0828) zająć się Śliwką.
Polecenie jest zgodą na zapis wymaganą przez D-466.

Pomiar 2026-10-03 (oczekujące, `virtual_source`, bez flagi jakości, pełna
widoczność, bez komórek przepisanych już przez bibliotekę): 923 665 komórek,
581 899 w paśmie 99–<100% i 341 766 równych 100%.

## Dependencies / entry conditions

- TASK-0828 zakończony (sterownik startuje po wpisie `driver done` w logu
  Winogronu i nie startuje, jeśli tamten przebieg się zatrzymał).
- TASK-0829 (`--shard`, `v1.7.176`) — scalony do
  `v1.1-vision-lab-hybrid-geometry` i wypchnięty za zgodą operatora
  2026-10-03; przebieg używa skryptu z worktree
  `worktrees/symbol-reference-library` (ten sam commit; bez edycji skryptu i
  zmiany gałęzi w worktree w trakcie przebiegu).

## Recommended execution

`claude-opus-5-5`, reasoning `high`; kontrola po zapisie odczytem bazy.

## Relevant docs

- `ai_docs/process/DECISION_LOG.md` (D-466)
- `ai_docs/tasks/0828-symbol-reference-library-winogron-99-100.md`
- `ai_docs/tasks/completed/0829-symbol-reference-preview-shards.md`

## Scope

Szesnaście części, każda kolejno: `apply-preview` do końca, `apply`, `apply-verify`:

| Część | `--min-confidence` | `--max-confidence` | `--shard` | Komórki |
| --- | --- | --- | --- | --- |
| 01 | 0.99000001 | 0.99924238 | 0/1 | 58 189 |
| 02 | 0.99924238 | 0.99987876 | 0/1 | 58 187 |
| 03 | 0.99987876 | 0.99997099 | 0/1 | 58 187 |
| 04 | 0.99997099 | 0.99999109 | 0/1 | 58 148 |
| 05 | 0.99999109 | 0.99999678 | 0/1 | 58 114 |
| 06 | 0.99999678 | 0.99999877 | 0/1 | 58 143 |
| 07 | 0.99999877 | 0.9999996 | 0/1 | 57 609 |
| 08 | 0.9999996 | 0.99999992 | 0/1 | 57 348 |
| 09 | 0.99999992 | 0.99999998 | 0/1 | 44 790 |
| 10 | 0.99999998 | 1.0 | 0/1 | 73 184 |
| 11–16 | 1.0 | 1.0001 | 0/6 … 5/6 | 56 762–57 152 |

## Out of scope

- Arbuz i inne symbole, zatwierdzanie komórek, zmiany kodu narzędzia.

## Acceptance criteria

- [ ] Szesnaście manifestów z sumami kontrolnymi; zapis tylko dla tych sum.
- [ ] Zapis bez błędów (plansze `stale` dopuszczalne i opisane).
- [ ] `apply-verify` każdej części zgodny z manifestem.

## Technical notes

- Sterownik jak w TASK-0828 (budżet podglądu 300 s, zapisu 240 s, twardy limit
  procesu 600 s; kod 3 = powtórz, inny kod zatrzymuje przebieg). Manifesty w
  worktree `artifacts/symbol-reference-library/apply-sliwka-ge99-<NN>/`, log
  `sliwka-ge99-driver.log`.
- Kanarek pominięty: zapis (`apply`) jest tym samym kodem co w TASK-0828, gdzie
  kanarek przeszedł; zmiana TASK-0829 dotyczy tylko wyboru komórek podglądu.
- W grupie Winogron → Śliwka (TASK-0828) część wycinków wyglądała na przesuniętą
  siatkę; przy przeglądzie zmian Śliwki sprawdzić to samo zjawisko.

## Test cases

- `apply-verify` po każdej części; liczniki po całości.

## Stan i wznowienie

- **Stan 2026-10-04 18:32 UTC — przebieg zatrzymany na polecenie operatora
  (reset i migracje).** Żaden sterownik nie działa.
- Części 01–13: zakończone i sprawdzone (`apply-verify.json` w każdym katalogu).
- Część 14 (`3/6`): niedokończona. Manifest `5e29c551…`, zapisane 9 052 z
  47 207 plansz (pokwitowania `apply-receipts-5e29c551050a.jsonl`), bez
  `apply-verify`. Zatrzymanie 18:28 UTC na granicy rundy, potem krótkie
  wznowienie i zatrzymanie 18:32 UTC w trakcie rundy — jedna plansza mogła
  zostać zapisana bez pokwitowania, więc **nie wznawiać na starym manifeście**.
- Części 15–16: niezaczęte.
- **Wznowienie po restarcie:** `drivers/run-sliwka-ge99.ps1 -FirstPart 14`
  (polecenie w `artifacts/symbol-reference-library/drivers/README.md` w
  worktree). Część 14 zrobi nowy podgląd: zapisane już komórki mają pewność
  0,99, więc wypadają z zakresu `1.0–1.0001`, a podgląd obejmie tylko resztę.
  Potem 15 i 16. Arbuz (TASK-0833) dopiero po `driver done` Śliwki.
- Sterowniki, skrypt podglądu i instrukcje: worktree
  `artifacts/symbol-reference-library/drivers/` (`README.md`).

## Outcome

- Start 2026-10-03 17:22 UTC (po `driver done` Winogronu).

  | Część | Komórki | Cele | Plansze | Manifest | Zapis (UTC) | `apply-verify` |
  | --- | --- | --- | --- | --- | --- | --- |
  | 01 | 58 189 | 36 006 | 29 099 | `2d3e1e45…` | 17:42–18:42 | 36 006 `library_prediction`, 0 błędów |
  | 02 | 58 187 | 35 203 | 30 402 | `7f160d44…` | 19:05–20:08 | 35 203 `library_prediction`, 0 błędów |
  | 03 | 58 187 | 39 234 | 33 829 | `ec06c6cc…` | 20:31–21:42 | 39 234 `library_prediction`, 0 błędów |
  | 04 | 58 148 | 44 666 | 37 825 | `ffe910aa…` | 22:00–23:45 | 44 666 `library_prediction`, 0 błędów |
  | 05 | 58 114 | 48 519 | 40 257 | `40bb0840…` | 00:06–01:49 (4.10) | 48 519 `library_prediction`, 0 błędów |
  | 06 | 58 143 | 50 493 | 41 223 | `174a5c10…` | 02:08–03:32 | 50 493 `library_prediction`, 0 błędów |
  | 07 | 57 609 | 51 717 | 42 276 | `844f47d7…` | 03:51–05:18 | 51 717 `library_prediction`, 0 błędów |
  | 08 | 57 348 | 53 934 | 45 846 | `b605161b…` | 05:37–07:11 | 53 934 `library_prediction`, 0 błędów |
  | 09 | 44 790 | 43 316 | 37 683 | `f870c50c…` | 07:30–08:52 | 43 316 `library_prediction`, 0 błędów |
  | 10 | 73 184 | 71 059 | 56 961 | `ad1a6303…` | 09:18–11:29 | 71 059 `library_prediction`, 0 błędów |
  | 11 (`0/6`) | 56 919 | 55 722 | 47 089 | `21ac9cc6…` | 11:50–13:34 | 55 722 `library_prediction`, 0 błędów |
  | 12 (`1/6`) | 56 762 | 55 517 | 46 745 | `cc13c839…` | 13:54–15:38 | 55 517 `library_prediction`, 0 błędów |
  | 13 (`2/6`) | 57 049 | 55 831 | 47 107 | `24b6e2ad…` | 15:58–17:44 | 55 831 `library_prediction`, 0 błędów |

  Propozycje (zmiany symbolu / do przeglądu): 01 — 1 463 (Winogron 1 342,
  Wiśnia 70) / 22 164; 02 — 331 (Winogron 311) / 22 971; 03 — 132 / 18 937; 04 — 68 / 13 478; 05 — 49 / 9 584; 06 — 21 / 7 639; 07 — 26 / 5 878; 08 — 29 / 3 403; 09 — 23 / 1 467; 10 — 14 / 2 109; 11 — 4 / 1 187; 12 — 5 / 1 222; 13 — 5 / 1 199.
