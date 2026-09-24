---
title: TASK-0651 — Czysty kalkulator domenowy „Przybliżonej wygranej”
status: done
---

# TASK-0651 — Czysty kalkulator domenowy „Przybliżonej wygranej”

## Status

`done`

**Uwaga o numeracji:** trzeci task planu sesji `2026-09-24` „Przybliżona
wygrana” w „Wyszukaj plansze”. [TASK-0649](completed/0649-board-search-result-limit-input.md)
i [TASK-0650](completed/0650-shared-payout-evaluator-worker.md) ukończone.
Taski `0652`–`0654` jeszcze nie istnieją jako pliki.

**Przyjęte założenia (decyzje D1–D6 z planu sesji, zaakceptowane przez
użytkownika poleceniem „przejdź do kolejnego zadania” bez uwag do treści
planu):** zapisane w sekcji Technical notes poniżej i w `CURRENT_STATE.md`.
Jeżeli którekolwiek okaże się błędne, wymaga korekty planu i tego pliku
przed kontynuacją TASK-0652.

## Goal

Czysta, deterministyczna funkcja domenowa licząca „Przybliżoną wygraną” dla
zakresu `S+1…S+N` — planowanie pozycji, kategoryzację plansz (kompletna /
częściowa / brakująca), naliczanie payoutu przez wstrzykniętą funkcję oceny
i wynikowe podsumowanie/wiersze — bez żadnego I/O, bez zależności od
SQLAlchemy, FastAPI ani `game_predictor_worker`.

## Context

TASK-0652 (pion API) potrzebuje gotowego, w pełni przetestowanego rdzenia
domenowego, zanim dołoży repozytorium (odczyt `image_board_search_fast_documents`/
`legacy_board_search_archive_documents`), serwis aplikacyjny (ładowanie
`RulesPayoutConfiguration` z TASK-0650, budowa `PreparedPayoutEvaluator`) i
endpoint HTTP. Rozdzielenie pozwala przetestować całą logikę zakresu, braków
i bilansu bez PostgreSQL.

## Dependencies / entry conditions

- TASK-0650 ukończony (dostarcza `PreparedPayoutEvaluator`/
  `prepare_payout_evaluator`, których ten task **nie importuje** — moduł
  domenowy przyjmuje `evaluate: Callable[[Sequence[int]], int]` jako
  wstrzykniętą zależność, żeby zostać czystym i niezależnym od pakietu
  workera; realne podłączenie `PreparedPayoutEvaluator.evaluate` nastąpi w
  TASK-0652).
- Decyzje D1–D6 przyjęte jako założenia (patrz Technical notes).

## Recommended execution

Sonnet 5, reasoning `high`, z dodatkowym review: Opus 5.5 `high` — rdzeń
reguł domenowych (kategorie plansz, koniec sekwencji, bilans) jest
bezpośrednio testowany przez wymagania użytkownika z `ai_docs/delivery/`
sesji `2026-09-24` i błąd tutaj propaguje się do każdej liczby pokazywanej
operatorowi.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ALGORITHMS.md` (§C „Target forecast” — analogiczna,
  już zaakceptowana definicja pełnego cyklu i zawijania, D-116)
- `ai_docs/architecture/DATA_MODEL.md` (§„Projekcja wyszukiwania plansz
  częściowym układem”, §`image_symbol_review_states...` dla rozróżnienia
  kompletności rozpoznania od zatwierdzenia)

## Scope

- Nowy plik `services/api/src/game_predictor_api/domain/board_search_approximate_win.py`:
  - `ApproximateWinDocument` (dataclass): jedna logiczna plansza z projekcji
    wyszukiwania — `sequence_number`, `status`, `board_checksum_sha256`,
    `mobile_codes: tuple[int | None, ...]` (15 pozycji, `None` = `?`/brak
    dowodu, nigdy zgadywana wartość).
  - `plan_approximate_win_positions(start_sequence_number, requested_spin_count,
    sequence_length) -> tuple[int, ...]` — zakres `S+1…S+N` z zawijaniem
    cyklicznym (D1).
  - `calculate_approximate_win(...) -> ApproximateWinResult` — kategoryzacja,
    naliczanie payoutu przez wstrzykniętą `evaluate`, podsumowanie, wiersze,
    fingerprint danych.
  - `ApproximateWinResult`, `ApproximateWinSummary`, `ApproximateWinCompleteness`,
    `ApproximateWinRow` (dataclasses, wynik czysto do odczytu).

## Out of scope

- Repozytorium PostgreSQL, serwis aplikacyjny, endpoint HTTP, OpenAPI,
  klient TS (TASK-0652).
- Podsekcja UI Admina (TASK-0653).
- Podłączenie prawdziwego `PreparedPayoutEvaluator` — ten task przyjmuje
  `evaluate` jako parametr; testy używają albo prostego fake'a, albo
  (dla testu parytetu z payout-v3) bezpośrednio importują
  `game_predictor_worker.domain.payout.prepare_payout_evaluator`, co jest
  dopuszczalne w teście, mimo że plik produkcyjny tego nie importuje.
- Zmiana `evaluate_payout`/`PreparedPayoutEvaluator` z TASK-0650.

## Acceptance criteria

- [x] `plan_approximate_win_positions` zwraca dokładnie zakres `S+1…S+N` z
      zawijaniem cyklicznym zgodnym z `ALGORITHMS.md` §C (ta sama formuła co
      mobilna prognoza celu), `evaluated_spin_count = min(N, L−1)`.
- [x] Plansza startowa `S` nigdy nie wchodzi do zakresu ani do wyniku.
- [x] Brakujący dokument dla pozycji w zakresie: koszt spinu doliczony,
      payout 0, kategoria „brakująca”, `evaluate` NIE jest wywoływane.
- [x] Plansza z ≥1 `None` w `mobile_codes`: kategoria „częściowa” zawsze,
      również gdy naliczono dla niej potwierdzoną wypłatę > 0.
- [x] Plansza z 15 znanymi kodami: kategoria „kompletna”, `payout_kind =
      "exact"` w wierszu (jeśli payout > 0).
- [x] Suma `complete_board_count + partial_board_count + missing_board_count
      == evaluated_spin_count` dla każdego scenariusza testowego.
- [x] Koszt narastający (`cumulative_cost_credits`) w każdym wierszu
      uwzględnia WSZYSTKIE wcześniejsze spiny zakresu (w tym pominięte w
      `rows` i brakujące), nie tylko wiersze z payoutem > 0.
- [x] `rows` zawiera wyłącznie spiny z `payout_credits > 0`, w tym te
      występujące, gdy bilans narastający nadal jest ujemny.
- [x] Pusty zakres wyników (brak jakiejkolwiek dodatniej wypłaty) daje pustą
      krotkę `rows`, ale poprawne `summary`/`completeness`.
- [x] Duplikat `sequence_number` w `documents` podnosi błąd przed
      jakimkolwiek naliczeniem.
- [x] Nieprawidłowy `start_sequence_number` (poza `1..sequence_length`) albo
      `requested_spin_count < 1` podnosi `BoardSearchError` z jawnym kodem.
- [x] `wrapped_at_sequence_end` poprawnie odróżnia zakres kończący się przed
      końcem sekwencji od zakresu przechodzącego przez granicę `L → 1`.
- [x] `data_fingerprint_sha256` zmienia się, gdy zmienia się dowolny kod
      symbolu, status albo checksuma dowolnej ocenianej planszy.
- [x] Zero I/O, zero importu SQLAlchemy/FastAPI/`game_predictor_worker` w
      pliku produkcyjnym (weryfikowalne przez `grep import` w Verification).
- [x] `mypy --strict` i `ruff check`/`format` czyste.

## Technical notes

**Przyjęte decyzje (D1–D6, jako założenia robocze — patrz uwaga o
numeracji):**

- **D1 (koniec sekwencji):** wariant A — zawijanie cykliczne, ta sama
  formuła co ALGORITHMS.md §C: `sequence_number = ((S − 1 + n) mod L) + 1`
  dla `n = 1..evaluated_spin_count`, `evaluated_spin_count = min(N, L − 1)`.
  `wrapped_at_sequence_end = (S + evaluated_spin_count) > L`.
- **D2 (źródło symboli):** ten task jest agnostyczny — `ApproximateWinDocument`
  dostaje gotowe `mobile_codes` od wywołującego (TASK-0652 wypełni je z
  `image_board_search_fast_documents`, tym samym źródłem co wyszukiwanie).
- **D3 (niezatwierdzony numer planszy startowej):** poza zakresem tego
  modułu — `S` nie jest częścią `documents`/wyniku; ostrzeżenie UI
  (TASK-0652/0653) będzie osobnym polem `startBoardStatus`, wyliczanym przez
  serwis aplikacyjny z odrębnego zapytania o planszę `S`.
- **D4 (reguły):** poza zakresem — serwis aplikacyjny (TASK-0652) wybiera
  najnowszą `published` wersję reguł przed wywołaniem tego kalkulatora.
- **D5 (limity):** `requested_spin_count` nie jest tu górnie ograniczane
  liczbą stałą (np. 10 000) — to walidacja warstwy API/serwisu (TASK-0652,
  `Query(le=APPROXIMATE_WIN_SPIN_COUNT_MAX)`). Ten moduł tylko odrzuca
  `< 1` i klamruje do `L − 1` (część definicji D1, nie osobny limit).
- **D6 (symbol spoza aktywnych symboli reguł):** ten moduł nie zna katalogu
  symboli — `evaluate(cells)` (docelowo `PreparedPayoutEvaluator.evaluate`)
  sama zgłasza błąd dla nieznanego kodu; ten moduł **nie łapie** wyjątków z
  `evaluate` i pozwala im propagować, żeby cała kalkulacja zakresu
  zatrzymała się fail-closed zamiast po cichu pominąć jedną planszę.
  Mapowanie na `409 APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES` należy do
  TASK-0652.

**Refinement techniczny względem opisu w planie (Sonnet, w ramach
„rozstrzygnij szczegóły techniczne”):** plan nazwał pole `symbol_codes`;
ostatecznie `mobile_codes: tuple[int | None, ...]`, bo `image_board_search_fast_documents`
przechowuje właśnie kody mobilne (`primary_symbol_mobile_codes`), a
`PreparedPayoutEvaluator.evaluate` (TASK-0650) oczekuje `Sequence[int]` z
`0` jako sentinelem unknown (D-247) — `None → 0` jest konwertowane wewnątrz
`calculate_approximate_win` tuż przed wywołaniem `evaluate`, więc warstwa
repozytorium (TASK-0652) nie musi znać tego szczegółu kodeka.

**Błędy:** reużyto istniejącego `BoardSearchError` z
`game_predictor_api.domain.board_search` (ten sam typ wyjątku co
wyszukiwanie plansz, ta sama konwencja `{code, message}`) zamiast tworzyć
równoległą klasę błędu. Nowe kody: `APPROXIMATE_WIN_START_OUT_OF_RANGE`,
`APPROXIMATE_WIN_SPIN_COUNT_INVALID`. Duplikat dokumentu i zła długość
`mobile_codes` to błędy integralności wywołującego (bug repozytorium, nie
błąd użytkownika) — `ValueError`, nie `BoardSearchError`.

**Przykład kontrolny z planu (zweryfikowany testem):** zakres 1000 spinów,
koszt spinu 20, rozpoznane wypłaty 18 000 → koszt spinów 20 000, bilans
−2000.

## Expected files

- Nowy: `services/api/src/game_predictor_api/domain/board_search_approximate_win.py`.
- Nowy: `services/api/tests/test_board_search_approximate_win_domain.py`.

## Test cases

- `plan_approximate_win_positions`: `S` nie wchodzi do zakresu; dokładnie
  `N` pozycji gdy `N ≤ L−1`; klamrowanie do `L−1` gdy `N > L−1`; zawijanie
  `L → 1`; `S = L` (ostatnia pozycja) daje pierwszą pozycję zakresu `= 1`.
- `calculate_approximate_win`: brakująca pozycja (koszt + 0, kategoria
  „brakująca”, `evaluate` niewywołane); plansza kompletna z payoutem
  (`exact`); plansza częściowa z potwierdzonym minimum (`confirmed_minimum`)
  — z naliczonym payoutem mimo pozostania „częściową”; plansza częściowa
  bez żadnego naliczenia (payout 0, nie trafia do `rows`, ale liczy się do
  `partial_board_count`); rozłączność i suma kategorii dla mieszanego
  zakresu; koszt narastający uwzględnia spiny pominięte w `rows` oraz spiny
  po ostatniej wypłacie; ujemny bilans mimo występujących wypłat (przykład
  kontrolny 1000/20/18000/−2000); pusty zakres bez żadnej wypłaty (poprawne
  `summary`/`completeness`, `rows == ()`); duplikat `sequence_number` w
  `documents` → `ValueError`; nieprawidłowy `start_sequence_number` →
  `BoardSearchError(APPROXIMATE_WIN_START_OUT_OF_RANGE)`;
  `requested_spin_count < 1` → `BoardSearchError(APPROXIMATE_WIN_SPIN_COUNT_INVALID)`;
  wyjątek z `evaluate` (symulujący D6) propaguje się niezłapany;
  `wrapped_at_sequence_end` True/False dla obu wariantów;
  `data_fingerprint_sha256` różni się dla różnych kodów/statusu/checksum,
  identyczny dla identycznych danych wejściowych (determinizm).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_approximate_win_domain.py -v
npm run python:lint
npm run python:typecheck
Select-String -Path services/api/src/game_predictor_api/domain/board_search_approximate_win.py -Pattern "^import|^from" | Select-String -NotMatch "from __future__|from collections.abc|from dataclasses|from enum|from hashlib|from game_predictor_api.domain.board_search"
```

Ostatnie polecenie musi zwrócić pusty wynik (żaden import SQLAlchemy,
FastAPI ani `game_predictor_worker` w pliku produkcyjnym). Timeout: 120 s na
komendę.

## Risks / open questions

- Założenia D1–D6 nie zostały jawnie potwierdzone przez użytkownika treścią
  (tylko poleceniem kontynuacji). Jeśli TASK-0652 albo odbiór ujawni, że
  któreś założenie jest błędne, ten plik i `CURRENT_STATE.md` wymagają
  korekty przed dalszą pracą — kontrakt `ApproximateWinResult` może się
  wtedy zmienić (np. dodanie `truncated_at_sequence_end` dla wariantu B
  zamiast zawijania).

## Outcome

### Changed

- [domain/board_search_approximate_win.py](../../services/api/src/game_predictor_api/domain/board_search_approximate_win.py)
  (nowy): `ApproximateWinDocument`, `ApproximateWinRow`, `ApproximateWinSummary`,
  `ApproximateWinCompleteness`, `ApproximateWinResult`,
  `plan_approximate_win_positions`, `calculate_approximate_win`. Zero
  importów SQLAlchemy/FastAPI/`game_predictor_worker` — zweryfikowane
  grepem. Reużywa `BOARD_SEARCH_CELL_COUNT` i `BoardSearchError` z
  `domain/board_search.py` zamiast dublować stałą i typ błędu.
- [test_board_search_approximate_win_domain.py](../../services/api/tests/test_board_search_approximate_win_domain.py)
  (nowy): 32 testy — planowanie pozycji i zawijanie, kategoryzacja,
  narastające sumy (w tym przykład kontrolny 1000/20/18000/−2000 z planu),
  `wrapped_at_sequence_end`, duplikat dokumentu, propagacja wyjątku z
  `evaluate` (D6), walidacja `ApproximateWinDocument`, determinizm/czułość
  fingerprintu.

### Verification results

```
.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_approximate_win_domain.py -q
  → 32/32 passed

.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_domain.py services/api/tests/test_board_search_api.py -q
  → 17/17 passed (regresja wspólnych zależności BoardSearchError/BOARD_SEARCH_CELL_COUNT: brak)

ruff check + ruff format --check (oba nowe pliki) → czyste (po poprawce
  jednej linii >100 znaków w teście)

npm run python:typecheck → zero błędów w board_search_approximate_win.py
  (po zmianie nazwy zmiennej pętli `document`→`candidate` w deduplikacji,
  która myliła mypy co do typu `ApproximateWinDocument` vs
  `ApproximateWinDocument | None` przy reużyciu nazwy w dwóch pętlach)
```

### Not completed

- Nic w zakresie tego taska.

### Documentation updates

- Brak — nowy, wewnętrzny moduł domenowy bez zmiany API ani zachowania
  istniejących funkcji.

### Recommended next task

- TASK-0652 — pion API: repozytorium (odczyt zakresu z
  `image_board_search_fast_documents`/`legacy_board_search_archive_documents`
  z `GameStorageRouter().bind()`), serwis aplikacyjny (ładowanie
  `RulesPayoutConfiguration`, `prepare_payout_evaluator`, mapowanie
  `DomainValidationError` na `APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES`),
  endpoint HTTP, OpenAPI, klient TS.
