# Raport audytu TASK-1128/B2a — runda 2

Werdykt: PASS
Runda: 2
**Model/reasoning:** claude-opus-5-5 / high (audytor). Wykonawca: gpt-6-astra/high.
**Zakres:** sprawdziłem tylko poprawkę aliasu reserved newSHA, `_replace_once` i rozliczenie P2-1…P2-5. Tylko Read/Glob/Grep: 10 odczytów, bez edycji, komend i testów. Liczby z testów (PG 8 PASS, unit 25 PASS) to deklaracje wykonawcy. Ich nie uruchamiałem; sprawdziłem tylko, co testy faktycznie sprawdzają.

## P0
Brak.

## P1
Brak.

## P2
Brak nowych.

## Rozliczenie

### closed — luka aliasu reserved newSHA
- **Zgodność zbiorów.** `source_replacement_source_current_v1` zwraca False w czterech przypadkach. Każdy ma teraz swoją gałąź w `affected_sources`:
  - retired po `source_id`: `0175_source_replacement_guards.py:24-25` → `:46`
  - retired po SHA: `:24-25` → `:47-49`
  - reserved po `new_source_id`: `:26-27` → `:50` (dowolny stan, więc obejmuje też predykat `current_v1` z `:32-37`)
  - reserved po `new_sha256`: `:26-27` → nowa gałąź `:51-53`, z JOIN `source_images` po `game_id` i `checksum_sha256=new_sha256`, tylko `state='reserved'`. To dokładnie odpowiada `:27`.
- **Predykaty sekwencji z `current_v1`.** `:38-41` jest pokryte przez `:58-65`, łącznie z wariantem `COALESCE(i.sequence_number, b.sequence_number)`.
- **Separacja gier.** Zachowana: `p.game_id=g` oraz `s.game_id=p.game_id` (`:52-53`).
- **Brak szerokiego skanu.** Nowa gałąź startuje od małej tabeli `slots`, nie od review/geometrii.
- **Ostateczny filtr.** `:67-72` nadal liczy `current_v1` per review, więc zwykły fallback accepted się nie zmienia.
- **Runtime.** `current_review_clause` używa `excluded_reviews_v1` (`storage/source_replacement_guards.py:34-39`). `require_current_review` najpierw sprawdza retired, potem stały kod `RESERVED` (`:65-84`).
- **Test regresji.**
  - `_reserved_sha_alias_is_not_current` (`test_source_replacement_guards_postgres.py:342-382`) jest wywoływany zaraz po INSERT slotów 101/102 w stanie reserved (`:176-183`).
  - Fixture: osobny job, ten sam `d*64`, seq 1200 poza slotami (`:344-368`).
  - Asercje:
    - `source_current is False` (`:370-377`)
    - `current_review_clause is False` (`:378`), czyli dokładnie dotychczasowa luka
    - `SOURCE_REPLACEMENT_RESERVED` (`:379-381`)
  - Fixture jest izolowany w `begin_nested` + rollback (`:343`, `:382`), więc nie zaburza dalszych asercji bootstrap/bind/retired (`:204-336`).

### closed — R1 P2-3 (anchory migracji)
- `_replace_once` wymaga `count == 1`, inaczej rzuca `RuntimeError` (`0175:14-17`).
- Użyty dla wszystkich anchorów:
  - wrapper scope: `:109`
  - photo CREATE: `:115`
  - photo scope: `:116`
  - population anchor: `:117-122`
  - downgrade CREATE: `:143`
- Testy unit: `missing` / `ambiguous` (`test_source_replacement_migration.py:18-21`) oraz `single` (`:24-27`). Fixture `"absent"` nie zawiera już słowa `anchor`.
- **Uwaga informacyjna (bez klasyfikacji).** Anchory photo nie są sprawdzane przed wykonaniem *całej* migracji. Sprawdzenie następuje po `op.execute` funkcji (`:21`) i wrappera (`:109`). Atomowość zapewnia jedna transakcja Alembica (`alembic/env.py:38`, `:59`) i transakcyjny DDL PostgreSQL. Brak ryzyka częściowego stanu. Sformułowanie „sprawdzane przed wykonaniem” jest więc ścisłe per wywołanie, nie per migracja.

### closed jako zaakceptowane ograniczenie / przeniesione do C2 (rozliczenie poprawne)
- **P2-1 i P2-2.** Obowiązkowe kryteria C2 są w planie przed udostępnieniem admission/restored (`777A2_READABILITY_REPLACEMENT_PLAN_20261102.md:71`):
  - korekta roboczej geometrii tego samego slotu bez konfliktu unikalności, prowadząca do whole-photo bind,
  - zamknięcie/wycofanie provisional PRZED zwolnieniem slotów,
  - test po restarcie: brak current/queue/count/search/canonical orphan.

  B2b ma tylko cancel planned (`:63`, `:71`). Task to odnotowuje (`1128-source-replacement-ownership.md:113`). Tekst planu nie twierdzi, że dwa pending na tym samym seq są utrwalane. Zgadza się to z ograniczeniem unikalności wskazanym przez koordynatora.
- **P2-4.** Ograniczenie dostępności puli (lock/sesja per gra) jest zapisane jako fail-closed bez usuwania, bez benchmarku (`1128-…md:113`).
- **P2-5.** Jedyny produkcyjny konstruktor `ManagedCleanupArtifactStore` (`main.py:979-984`) zawsze wstrzykuje `source_replacement_paths_gc_guard`. Grep po całym `services/` pokazuje pozostałe wywołania wyłącznie w testach: `test_cleanup_repository.py:479,619`, `test_grid_cohort_retention_edges_postgres.py:417,440`, `test_cleanup_domain.py:220,268,304,330,357,380`, `test_source_replacement_cleanup_recovery.py:39,62`. W workerze nie ma żadnego konstruktora.

### open
Brak.

## Uwaga poza zakresem
Bez klasyfikacji, nie blokuje. Po przejściu slotu w `pending_bound` alias z tym samym SHA (inny `source_id`) wraca do current. To spójne z istniejącą semantyką `source_current_v1`, która wyklucza SHA tylko dla `reserved` (`0175:27`), więc poprawka zachowuje zgodność, zamiast zmieniać kontrakt. Jeśli C2 dopuszcza zduplikowane SHA w jednej grze, warto to jawnie objąć testem D1.
