---
title: TASK-0749 — B2 — zapis biblioteki wzorców dla oczekujących komórek ośmiu symboli z pewnością ≤ 80%
status: done
last_updated: 2026-09-30
---

# TASK-0749 — B2 — zapis biblioteki wzorców dla oczekujących komórek ośmiu symboli z pewnością ≤ 80%

## Status

`done`

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

- [x] Osiem manifestów z sumami kontrolnymi; zapis tylko dla tych sum.
- [x] Zapis bez błędów; `apply-verify` zgodny z manifestami.
- [x] Liczniki filtra „Nowy algorytm” zgodne z sumą zapisów.

## Technical notes

- Sterownik: kolejno dla każdego symbolu podgląd do końca (kod 3 = powtórz),
  zapis porcjami po 100 s, weryfikacja; każdy inny kod zatrzymuje przebieg.

## Test cases

- `apply-verify` po każdym symbolu; liczniki API po całości.

## Outcome

- Przebieg 2026-09-30 00:35–03:48 UTC, sterownik w tle (podgląd do końca,
  zapis porcjami po 100 s, `apply-verify`). Manifesty w worktree
  `artifacts/symbol-reference-library/apply-<symbol>-le80/` (poza Gitem):

  | Symbol modelu | Komórki w zakresie | Zapisane | Potwierdzenia | Zmiany (największe) | Plansze | Manifest sha256 |
  | --- | --- | --- | --- | --- | --- | --- |
  | Wiśnia | 6 429 | 5 642 | 5 237 | 405 (Pomarańcz 93, Arbuz 74, Winogron 74) | 5 385 | `492b7b07…` |
  | Winogron | 13 140 | 11 889 | 7 079 | 4 810 (Śliwka 2 538, Siedem 805, Wiśnia 683) | 11 015 | `1f6466b8…` |
  | Cytryna | 2 180 | 1 222 | 895 | 327 (Pomarańcz 198) | 1 168 | `a0348bac…` |
  | Pomarańcz | 11 707 | 10 507 (+1 `stale`) | 7 838 | 2 670 (Arbuz 1 571, Gwiazda 874) | 9 522 | `dfb0737e…` |
  | Śliwka | 12 817 | 10 801 | 6 541 | 4 260 (Winogron 3 867, Cytryna 151) | 9 632 | `46639c75…` |
  | Arbuz | 8 948 | 7 738 | 5 384 | 2 354 (Wiśnia 824, Pomarańcz 666) | 7 093 | `74525086…` |
  | Gwiazda | 9 173 | 8 806 | 8 197 | 609 (Wiśnia 448) | 7 634 | `ffd0fee5…` |
  | Siedem | 4 137 | 3 671 | 3 511 | 160 (Wiśnia 66) | 3 465 | `611fe8ed…` |

  Razem 60 276 komórek na 54 914 planszach; 0 błędów po poprawkach, 1
  plansza `stale`. `apply-verify` dla każdego symbolu: wszystkie cele z
  predykcją biblioteki (Pomarańcz: 1 `unchanged` — plansza `stale`).
- Stan po przebiegu (oczekujące, filtr „Nowy algorytm”, razem z B1): Arbuz
  9 965, Cytryna 1 296, Gwiazda 9 808, Pomarańcz 9 271, Siedem 4 959, Śliwka
  9 143, Winogron 11 197, Wiśnia 7 554 — łącznie 63 193 komórki; 57 617
  wersji `symbol-reference-library-v1`. Bez pewnej propozycji (przy
  predykcji modelu, pewność ≤ 80%) zostało 8 313 komórek.
- Kontrola wzrokowa próbek (30–40 cropów na grupę): Winogron → Siedem,
  Winogron → Śliwka, Pomarańcz → Arbuz (porównane ze zweryfikowanymi
  wzorcami Arbuza: przekrój z falistą skórką), Pomarańcz → Gwiazda,
  Śliwka → Winogron — zgodne z propozycją; rozmyte kafelki Śliwka →
  Winogron są najmniej pewną częścią.
- Poprawki narzędzia w trakcie (audyt `claude-opus-5-5` po każdej):
  `v1.7.79` — wyszukiwanie po `uuid` zamiast `::text` (44 s → ~16 ms na 1000
  id) i wznawialne liczenie propozycji porcjami (Winogron przekraczał limit
  118 s); audyt PASS, P3 wdrożone. `v1.7.80` — komórka docelowa, która przy
  odświeżeniu dostaje flagę jakości z bieżącej geometrii (nieaktualny wiersz,
  np. `partial_visibility`), kończy planszę jako `stale` zamiast zatrzymać
  przebieg; cofanie nadal się zatrzymuje; audyt PASS po poprawce P2.
- Pozostałe P3 (osobne zadanie): przejście komórki do `outside` bez flagi,
  kontrola sumy pikseli po odświeżeniu, test pętli `apply` na atrapach,
  osobny plik częściowych wierszy już wdrożony. Dwie komórki pending/model z
  nieaktualną widocznością (`5bc8d6ad…`, `6d74416b…`) wymagają zwykłej
  synchronizacji — zapis do bazy tylko za zgodą operatora.
