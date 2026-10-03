---
title: TASK-0828 — B4 — zapis biblioteki wzorców dla oczekujących komórek Winogron z pewnością ≥ 99%
status: done
last_updated: 2026-10-03
---

# TASK-0828 — B4 — zapis biblioteki wzorców dla oczekujących komórek Winogron z pewnością ≥ 99%

## Status

`done`

## Goal

Czwarty przebieg D-466: pewne propozycje biblioteki wzorców zapisane jako nowa
wersja predykcji dla oczekujących komórek z predykcją modelu Winogron i
pewnością modelu ≥ 99% (łącznie z 100%) w grze `777`.

## Context

Polecenie operatora 2026-10-02: przepuścić przez nowy algorytm symbole, które
nie były jeszcze przepuszczone (pasmo ≥ 99%, pominięte w TASK-0750), po jednej
grupie, zaczynając od Winogronu; potem Śliwka i Arbuz osobnymi zadaniami.
Polecenie jest zgodą na zapis wymaganą przez D-466.

Pomiar przed startem (oczekujące, `virtual_source`, bez flagi jakości, pełna
widoczność): 806 442 komórki Winogron ≥ 99% bez predykcji biblioteki
(636 740 w paśmie 99–<100%, 169 702 równe 100%) na 314 426 planszach.
Szacunek z tempa B3: podgląd ~4,6 h, zapis ~17,5 h (14–23 h).

## Dependencies / entry conditions

- TASK-0750 done; narzędzie po zmianach TASK-0792/0794/0795 (manifest renderu,
  digest v2, rola aplikacji).

## Recommended execution

`claude-opus-5-5`, reasoning `high`; kontrola po zapisie odczytem bazy.

## Relevant docs

- `ai_docs/process/DECISION_LOG.md` (D-466)
- `ai_docs/tasks/completed/0750-symbol-reference-library-eight-symbols-80-99.md`

## Scope

- Zakres dzielony na dziesięć porcji pewności, bo narzędzie przy każdym
  wznowieniu wczytuje i zapisuje cały cache wycinków (całość ~10 GB nie
  mieści się w pamięci). Granice to kwantyle rozkładu (wartości zaokrąglone do
  8 miejsc); pierwsza porcja zaczyna się od 0,99000001, żeby pominąć komórki
  już przepisane przez bibliotekę (0,99):

  | Porcja | `--min-confidence` | `--max-confidence` | Komórki |
  | --- | --- | --- | --- |
  | 01 | 0.99000001 | 0.99985906 | 63 672 |
  | 02 | 0.99985906 | 0.99999253 | 63 661 |
  | 03 | 0.99999253 | 0.99999917 | 63 324 |
  | 04 | 0.99999917 | 0.99999979 | 62 237 |
  | 05 | 0.99999979 | 0.99999992 | 64 278 |
  | 06 | 0.99999992 | 0.99999996 | 59 172 |
  | 07 | 0.99999996 | 0.99999998 | 65 067 |
  | 08 | 0.99999998 | 0.99999999 | 60 850 |
  | 09 | 0.99999999 | 1.0 | 134 479 |
  | 10 | 1.0 | 1.0001 | 169 702 |

- Każda porcja kolejno: `apply-preview` do końca, `apply` porcjami, `apply-verify`.
  Manifest następnej porcji powstaje dopiero po zapisie poprzedniej, bo jedna
  plansza może mieć komórki z kilku porcji.
- Pierwsza porcja zaczyna od kanarka (`apply --limit-boards 5`) i odczytu bazy.

## Out of scope

- Inne symbole (Śliwka, Arbuz — osobne zadania), zatwierdzanie komórek,
  zmiany kodu narzędzia.

## Acceptance criteria

- [x] Dziesięć manifestów z sumami kontrolnymi; zapis tylko dla tych sum.
- [x] Zapis bez błędów (plansze `stale` dopuszczalne i opisane).
- [x] `apply-verify` każdej porcji zgodny z manifestem.

## Technical notes

- Sterownik w tle z głównego checkoutu (`artifacts/data/originals`), manifesty
  w worktree `artifacts/symbol-reference-library/apply-winogron-ge99-<NN>/`
  (poza Gitem). Kod wyjścia 3 = powtórz; każdy inny kod zatrzymuje przebieg.
- Nie uruchamiać równolegle weryfikacji Winogronu w Adminie (zakleszczenie w B3).
- Budżet rundy podglądu 300 s (twardy limit procesu 600 s), zapisu 240 s:
  od TASK-0792 `_with_render_specs` czyta specyfikacje z manifestów plansz i
  sam odczyt migawki trwa ~75 s na 64 tys. komórek (48 s same specyfikacje),
  więc budżet 55–70 s z B3 kończył się przed renderem. Wyjątek od limitu
  120 s dotyczy tylko procesu sterownika w tle.

## Test cases

- Kanarek: odczyt pięciu plansz po zapisie (wersja `symbol-reference-library-v1`,
  komórki `pending`).
- `apply-verify` po każdej porcji; liczniki po całości.

## Outcome

- Porcja 01, podgląd 2026-10-02 19:36–19:57 UTC (render ~80–105 komórek/s):
  63 672 komórki; propozycje WINOGRON 52 568, Siedem 1 792, Wiśnia 1 437,
  Śliwka 896, Pomarańcz 402, Gwiazda 337, Arbuz 314, Cytryna 1, do przeglądu
  5 925. Manifest `c7edd87f…`: 42 950 plansz, 57 708 celów (wykluczone 14
  `assignment_not_model`, 25 `revision_not_current`).
- Kanarek 19:57 UTC: 5 plansz `applied`; odczyt bazy — cele WINOGRON 0,99,
  `pending`, wersja `symbol-reference-library-v1` (`cc3ec834…`), pozostałe
  komórki plansz z dotychczasowymi predykcjami. Pełny przebieg porcji 01–10
  uruchomiony po kanarku (porcja 01 z nowym manifestem, bo zmienił się odcisk
  stanu komórek).

  | Porcja | Komórki | Cele | Plansze | Manifest | Zapis (UTC) | `apply-verify` |
  | --- | --- | --- | --- | --- | --- | --- |
  | 01 | 63 663 | 57 699 | 42 945 | `072387b1…` | 20:02–21:36 | 57 699 `library_prediction`, 0 błędów |
  | 02 | 63 661 | 56 283 | 44 092 | `66564334…` | 21:57–23:35 | 56 283 `library_prediction`, 0 błędów |
  | 03 | 63 324 | 50 390 | 41 497 | `1e9fda93…` | 00:00–01:24 (3.10) | 50 390 `library_prediction`, 0 błędów |
  | 04 | 62 237 | 41 475 | 35 821 | `1ab616a0…` | 01:48–03:01 | 41 475 `library_prediction`, 0 błędów |
  | 05 | 64 278 | 42 087 | 36 148 | `3b1e4623…` | 03:28–04:41 | 42 087 `library_prediction`, 0 błędów |
  | 06 | 59 172 | 41 685 | 35 367 | `229d9bba…` | 05:05–06:17 | 41 685 `library_prediction`, 0 błędów |
  | 07 | 65 067 | 48 638 | 40 345 | `f349cf13…` | 06:44–08:25 | 48 638 `library_prediction`, 0 błędów |
  | 08 | 60 850 | 47 995 | 40 107 | `724d87c7…` | 08:47–10:12 | 47 995 `library_prediction`, 0 błędów |
  | 09 | 134 479 | 117 212 | 78 042 | `5144ee82…` | 10:54–13:44 | 117 212 `library_prediction`, 0 błędów |
  | 10 | 169 702 | 154 152 | 80 327 | `4451aaf2…` | 14:28–17:22 | 154 152 `library_prediction`, 0 błędów |

  Propozycje (zmiany symbolu / do przeglądu): 01 — 5 179 / 5 925; 02 — 2 096 /
  7 353; 03 — 1 191 / 12 911; 04 — 524 / 20 740; 05 — 246 / 22 174; 06 — 176 /
  17 476; 07 — 104 / 16 414; 08 — 62 / 12 830; 09 — 99 / 17 224; 10 — 66 / 15 455.
- Kontrola wzrokowa (po porcji 06, 9 368 zmian w manifestach; próbki po 10 na
  grupę): Siedem, Wiśnia, Arbuz, Gwiazda, Pomarańcz, Cytryna zgodne z
  propozycją; w grupie Śliwka część wycinków to fragment śliwki przesunięty
  względem pola (podejrzenie przesuniętej siatki, nie symbolu).
- Razem 2026-10-02 19:36 – 2026-10-03 17:22 UTC (~21,8 h): 806 433 komórki w
  zakresie, 657 616 komórek z predykcją biblioteki (+9 celów kanarka) na
  474 691 zapisach plansz (+5 kanarka); 0 błędów, 0 plansz `stale`; każda porcja
  `apply-verify` zgodna z manifestem. Zmiany symbolu 9 699 (Siedem 3 993,
  Wiśnia 2 393, Śliwka 1 744, Arbuz 558, Gwiazda 527, Pomarańcz 483, Cytryna 1);
  do przeglądu (bez pewnej propozycji, zostały przy modelu) 148 502. Odczyt
  bazy po przebiegu: 148 817 oczekujących komórek Winogron z predykcją modelu
  > 99% (do przeglądu + wykluczone `assignment_not_model`/`revision_not_current`
  i poza zakresem).
- Podgląd zmian: `artifacts/symbol-reference-library/winogron-ge99-changes/index.html`
  w worktree (poza Gitem), wycinek + kontekst, grupy według nowego symbolu.
- Tempo: render ~80–105 komórek/s, zapis ~380–490 plansz/min; porcje ~60 tys.
  komórek ~1,5–2 h, porcje 09/10 ~3 h.
