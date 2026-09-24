---
title: TASK-0650 — Wspólny kalkulator payout w workerze (PreparedPayoutEvaluator)
status: done
---

# TASK-0650 — Wspólny kalkulator payout w workerze

## Status

`done`

**Uwaga o numeracji:** drugi task planu sesji `2026-09-24` „Przybliżona
wygrana” w „Wyszukaj plansze” ([TASK-0649](completed/0649-board-search-result-limit-input.md)
był pierwszy). Taski `0651`–`0654` z tego planu jeszcze nie istnieją jako
pliki.

## Goal

Wydzielić z istniejącego kalkulatora payout (`payout-v3-unknown-prefix-stop`)
wariant, który waliduje konfigurację reguł raz i pozwala tanio ocenić wiele
plansz, bez zmiany wyniku ani semantyki istniejących `evaluate_payout` /
`evaluate_payout_v2`. Wydzielić też ładowanie konfiguracji reguł niezależne
od datasetu, żeby przyszły kalkulator „Przybliżonej wygranej” (TASK-0651/0652)
mógł go użyć bez budowania `PayoutSource`.

## Context

TASK-0651 (czysty kalkulator domenowy zakresu) i TASK-0652 (pion API) będą
oceniać do 10 000 plansz dla jednej, już opublikowanej wersji reguł. Dzisiejszy
`evaluate_payout` re-waliduje pełną macierz payout (`validate_paylines` +
`validate_payout_configuration`) przy każdym wywołaniu — dla zakresu 10 000
plansz to 10 000 identycznych walidacji tej samej, niezmiennej konfiguracji.
`SqlAlchemyPayoutStore.load_source` dodatkowo wymaga `dataset_version_id`,
którego kalkulator Admina nie ma (czyta żywe dokumenty wyszukiwania plansz,
nie dataset).

## Dependencies / entry conditions

Brak zależności od TASK-0649 (niezależne zadania tej samej serii).

## Recommended execution

Sonnet 5, reasoning `high`, z dodatkowym review: Opus 5.5 `high` — refaktor
kodu payoutu używanego przy wydaniach (batch precomputing dla wydań
mobilnych) wymaga ścisłej parytetowości z istniejącym zachowaniem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ALGORITHMS.md` (§B „Payout”, `payout-v3-unknown-prefix-stop`)
- `ai_docs/architecture/DATA_MODEL.md` (§`rules_versions`, §`payout_rules`, §`layout_payouts`)

## Scope

- `services/worker/src/game_predictor_worker/domain/payout.py`: nowy
  `PreparedPayoutEvaluator` (frozen dataclass) i `prepare_payout_evaluator(
  game, paylines, payout_symbols, payout_rules)`. Wewnętrzna pętla
  dopasowań (`_evaluate_matches`) jest teraz wspólnym prywatnym helperem
  używanym zarówno przez `PreparedPayoutEvaluator.evaluate`, jak i przez
  istniejący `_evaluate_payout_validated` (a więc przez `evaluate_payout` i
  `evaluate_payout_v2`).
- `services/worker/src/game_predictor_worker/payouts/contracts.py`: nowy
  `RulesPayoutConfiguration` (dataclass) — konfiguracja jednej wersji reguł
  niezależna od datasetu.
- `services/worker/src/game_predictor_worker/payouts/store.py`: nowa funkcja
  modułowa `load_rules_payout_configuration(session, rules_version_id)`.
  `SqlAlchemyPayoutStore.load_source` korzysta z niej zamiast duplikować
  zapytania.

## Out of scope

- `payouts/handler.py` (batch precomputing dla wydań) — nie zmieniany;
  nadal woła `evaluate_payout`/`evaluate_payout_v2` per layout tak jak dziś.
  Przepięcie handlera na `PreparedPayoutEvaluator` nie było proszone i
  wykraczałoby poza tę zmianę.
- Żadna zmiana reguł domenowych payout-v3 (kierunek, jokery, sumowanie,
  `payout-v2` zachowanie).
- API Admina, kalkulator zakresu, endpoint (TASK-0651/0652).

## Acceptance criteria

- [x] `PreparedPayoutEvaluator.evaluate(cells)` daje identyczny wynik jak
      `evaluate_payout(...)` dla każdego przypadku w
      `packages/domain-fixtures/payout-golden-cases.json`.
- [x] Nieprawidłowa konfiguracja (duplikat reguły, niekompletna macierz,
      niemonotoniczny payout) zgłasza błąd już w `prepare_payout_evaluator`,
      przed jakąkolwiek oceną planszy.
- [x] `evaluate_payout` i `evaluate_payout_v2` dają identyczne wyniki jak
      przed refaktorem dla wszystkich istniejących testów i golden cases
      (zero regresji, zero zmiany komunikatów błędów ani ich kolejności).
- [x] `SqlAlchemyPayoutStore.load_source` zwraca identyczny `PayoutSource`
      jak przed refaktorem, potwierdzone kodem (kolejność sprawdzeń i pola
      niezmienione). Właściwy integracyjny test tej ścieżki —
      `services/api/tests/integration/test_payout_store.py` (nie
      `services/worker/tests/test_payout_store.py`, który nie istnieje) —
      jest czerwony, ale **pre-existing**: ten sam test failuje identycznie
      na commicie `v0.10.418`, sprzed tego taska (zweryfikowane przez
      tymczasowy `git stash` moich zmian). Przyczyna: fikstura testu nie
      ustawia `expected_layout_count` przy tworzeniu `DatasetVersionModel`,
      a kolumna jest dziś `NOT NULL`. Nie naprawiono — poza zakresem.
- [x] `test_payout_batch.py` bez zmian i zielony (handler batch payout
      nietknięty).
- [x] `mypy --strict` i `ruff check` czyste dla zmienionych plików.

## Technical notes

**Dlaczego zero zmiany semantyki `evaluate_payout`/`evaluate_payout_v2`:**
`_evaluate_payout_validated` zachowuje dokładnie tę samą kolejność co przed
refaktorem: `validate_paylines` → `validate_payout_configuration` → budowa
`wildcard_codes`/`ordinary_symbols`/`rules_by_symbol`/`line_cell_indices_by_payline`
→ pętla dopasowań. Zmienia się wyłącznie to, że budowa struktur i pętla są
teraz w osobnych, nazwanych funkcjach (`_ordinary_symbols_by_display_order`,
`_rules_by_symbol`, `_line_cell_indices`, `_evaluate_matches`) zamiast inline
w jednej funkcji. `PreparedPayoutEvaluator` to nowa, dodatkowa ścieżka: jej
`evaluate()` waliduje planszę PO walidacji konfiguracji (bo konfiguracja jest
walidowana raz w `prepare_payout_evaluator`), co jest odwrotną kolejnością
niż w `evaluate_payout` (tam plansza jest walidowana przed konfiguracją).
To nie wpływa na żaden istniejący callsite — `evaluate_payout`/
`evaluate_payout_v2` nie są przepisane na wywołanie `prepare_payout_evaluator`
właśnie po to, żeby kolejność walidacji (a więc i to, który błąd wypada
pierwszy przy jednocześnie niepoprawnej planszy i konfiguracji) pozostała
identyczna jak dziś.

**Payout dla planszy częściowej jest dolnym ograniczeniem, nie przybliżeniem**
(przypomnienie dla testów lower-bound, pełny dowód w planie TASK-0651): dla
każdej pary `(payline, symbol)` prefiks zbudowany ze znanych komórek może
zostać tylko wydłużony albo zakończony przez nieznaną komórkę, nigdy
skrócony; `payout_by_length` jest ściśle rosnący, więc krótszy potwierdzony
prefiks nigdy nie daje wyższej wypłaty niż prawdziwa (dłuższa lub równa)
plansza. To już dzisiejsza własność `payout-v3-unknown-prefix-stop`
(D-247) — ten task jej nie zmienia, tylko dodaje testy, które to
udokumentują na `PreparedPayoutEvaluator`.

## Expected files

- Istniejące: `domain/payout.py`, `payouts/contracts.py`, `payouts/store.py`.
- Nowe: brak plików produkcyjnych.

## Test cases

W `services/worker/tests/test_payout.py`:
- `prepare_payout_evaluator(...).evaluate(cells)` == `evaluate_payout(...)`
  dla każdego golden case.
- Nieprawidłowa konfiguracja (np. brak reguły dla jednej długości) rzuca
  `DomainValidationError` już w `prepare_payout_evaluator`.
- Kompletna plansza z 5 wiśniami na jednej payline daje tylko wypłatę za
  długość 5 (nie sumuje 3+4+5).
- Prefiks `C C C ? ?` (3 wiśnie, potem nieznane) z `min_match_length(C)=3`
  daje wypłatę za 3, taką samą jak pełna plansza `C C C x y` gdzie `x,y` nie
  przedłużają ciągu.
- Prefiks `C C ? C C` (nieznane w środku) NIE przeskakuje do 4/5 — wynik
  ograniczony do prefiksu przed pierwszym `?` (długość 2; wypłaca tylko gdy
  `min_match_length(C) <= 2`, inaczej 0).
- Plansza zaczynająca się od `?` (`? C C C C`) daje 0 na tej linii — brak
  naliczania z samego środka.
- Ciąg złożony wyłącznie z jokerów (`W W ? ? ?` z `min_match_length=2`) nie
  wygrywa (0).
- `W C W ? ?` (joker + symbol + joker, potem nieznane) z
  `min_match_length(C)=3` daje wypłatę za 3.
- Dwie niezależne paylines tej samej (częściowej) planszy liczone osobno i
  sumowane.
- Dla golden case każda plansza częściowa (z podmienionymi na `0` losowymi
  komórkami) ma `total_payout <= total_payout` tej samej planszy kompletnej
  (dowód dolnego ograniczenia na przykładach, nie exhaustive proof).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_payout.py services/worker/tests/test_payout_batch.py services/worker/tests/test_payout_readiness.py -v
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_payout_store.py -v
npm run python:lint
npm run python:typecheck
```

Timeout: 120 s na komendę.

## Risks / open questions

- Brak. Refaktor jest wewnętrzny i addytywny; publiczne funkcje
  `evaluate_payout`/`evaluate_payout_v2`/`SqlAlchemyPayoutStore.load_source`
  zachowują dotychczasowe sygnatury i zachowanie.

## Outcome

### Changed

- [domain/payout.py](../../services/worker/src/game_predictor_worker/domain/payout.py):
  wydzielono `_line_cell_indices`, `_ordinary_symbols_by_display_order`,
  `_rules_by_symbol` i wspólny `_evaluate_matches` (dawna pętla dopasowań
  z `_evaluate_payout_validated`, bez zmiany kolejności ani logiki). Nowe
  `PreparedPayoutEvaluator` (frozen dataclass) i `prepare_payout_evaluator(
  game, paylines, payout_symbols, payout_rules)`. `evaluate_payout` i
  `evaluate_payout_v2` zachowują dokładnie swoją poprzednią kolejność
  walidacji (plansza → paylines → konfiguracja payout) i wywołują tę samą
  `_evaluate_matches`.
- [domain/__init__.py](../../services/worker/src/game_predictor_worker/domain/__init__.py):
  eksport `PreparedPayoutEvaluator`/`prepare_payout_evaluator` na poziomie
  pakietu, spójnie z istniejącym `evaluate_payout`/`evaluate_payout_v2`.
- [payouts/contracts.py](../../services/worker/src/game_predictor_worker/payouts/contracts.py):
  nowy `RulesPayoutConfiguration` (wymiary, koszt spinu, symbole, paylines,
  payout_symbols, payout_rules jednej wersji reguł — niezależny od datasetu).
- [payouts/store.py](../../services/worker/src/game_predictor_worker/payouts/store.py):
  nowa funkcja modułowa `load_rules_payout_configuration(session,
  rules_version_id)`. `SqlAlchemyPayoutStore.load_source` korzysta z niej
  zamiast duplikować zapytania; zwraca identyczny `PayoutSource` co przed
  refaktorem (te same pola, ta sama kolejność sprawdzeń `dataset is None` /
  konfiguracja brak / `game is None`).
- Testy: 13 nowych w `services/worker/tests/test_payout.py` (parytet
  golden cases, błąd niekompletnej konfiguracji w `prepare`, brak sumowania
  3+4+5, potwierdzony minimalny prefiks, brak przeskakiwania `?` w środku,
  brak naliczania z uciętej lewej strony, sam joker nie wygrywa, joker
  otaczający potwierdzony prefiks, dwie niezależne paylines, 6 wariantów
  monotoniczności dolnego ograniczenia).

### Verification results

```
.venv\Scripts\python.exe -m pytest services/worker/tests/test_payout.py services/worker/tests/test_payout_batch.py services/worker/tests/test_payout_readiness.py -q
  → 60/60 passed (42 w test_payout.py, w tym 13 nowych)

GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 .venv\Scripts\python.exe -m pytest services/api/tests/integration/test_payout_store.py -q
  → 1 failed: test_payout_store_loads_versioned_source_and_upserts_without_duplicates
    (NotNullViolation na dataset_versions.expected_layout_count — fikstura
    testu nie ustawia tej kolumny, która stała się NOT NULL w migracji
    0122/wcześniejszej po D-437; POTWIERDZONE jako pre-existing: ten sam
    test failuje identycznie na commicie v0.10.418, przed jakąkolwiek
    zmianą tego taska — zweryfikowane przez `git stash` moich plików i
    ponowne uruchomienie. Nie naprawiono — poza zakresem tego taska,
    zgłoszone jako osobny problem poniżej.)

npm run python:lint  → 1 pre-existing błąd w niezwiązanym, nietkniętym pliku
  services/worker/tests/test_page_geometry_preflight.py:345 (E501, linia >100
  znaków). Ruff scoped tylko do zmienionych plików: "All checks passed!".
  ruff format --check na zmienionych plikach: "5 files already formatted".

npm run python:typecheck → 69 pre-existing błędów w 13 niezwiązanych,
  nietkniętych plikach (m.in. shape_geometry_v2/core.py, page_geometry_preflight.py,
  v7_label_geometry_calibration.py — potwierdzone grepem, że żaden dotyczy
  domain/payout.py, domain/__init__.py, payouts/contracts.py ani
  payouts/store.py). Zero błędów w plikach zmienionych tym taskiem.
```

### Not completed

- Nic w zakresie tego taska. Dwa napotkane, niezwiązane, pre-existing
  problemy (integracyjny test `test_payout_store.py` i mypy/ruff w innych
  plikach) zostały zidentyfikowane, potwierdzone jako sprzed tej zmiany i
  świadomie pozostawione poza commitem zgodnie z AGENTS.md.

### Documentation updates

- Brak — zmiana wewnętrzna, bez zmiany zachowania domenowego ani API.

### Recommended next task

- TASK-0651 — czysty kalkulator domenowy „przybliżonej wygranej” (plik
  taska jeszcze nie istnieje, wymaga rozstrzygnięcia decyzji D1–D6 z planu
  sesji `2026-09-24` przed startem).
- Osobno, poza kolejnością planu: `services/api/tests/integration/test_payout_store.py`
  ma niepoprawną fikstywę (brak `expected_layout_count` przy tworzeniu
  `DatasetVersionModel`) — czerwony niezależnie od tego taska. Do naprawy w
  osobnym, jawnie zleconym tasku.
