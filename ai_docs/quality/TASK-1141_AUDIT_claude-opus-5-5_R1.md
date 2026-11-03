# Audyt TASK-1141 — Fizyczne usuwanie zastępowanego zdjęcia

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high (pomocnicy: ten sam model, UI/test frozen)
Zakres: d78eaf1c oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1 (audyt końcowy po PLAN R2 PASS)

Przegląd statyczny. Nie zmieniałem żadnych plików i nie uruchamiałem poleceń ani testów.

## Streszczenie

Sprawdziłem kod pionu purge, nie samą deklarację: adapter source-only, wspólny predykat retencji, orkiestrację quarantine/COMMIT/finalize/recovery, zależność produkcyjną w `main.py`, migrację 0177, modele frozen, compact digest, endpointy i guard zasobów. Zakres DELETE jest dokładny i ogranicza się do źródła:
- modele, kohorty i aktywacje nie trafiają do kandydatów (`cohort_ids=()` itd.);
- frozen FK są odpięte, a nowe INSERT pilnuje trigger;
- exact replay sprawdza klucz i body przed innymi strażnikami;
- `fileProof` i `quarantineKey` są maskowane;
- `recovery_required` nie nadpisuje plików.

Jedno P1 dotyczy kształtu zapytania we wspólnym predykacie retencji. Na realnej skali bazy podgląd i finalize najpewniej przekroczą własny limit 30 s albo będą długo trzymać blokady EXCLUSIVE wszystkich gier. Wtedy pliki nie zostaną faktycznie odzyskane, a to jest główny cel taska.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/storage/source_purge_retention.py:69-115` (wywołania: `storage/source_replacement_purge.py:204-206` z `application/source_purge.py:31` oraz `guard` w `source_purge_retention.py:123,136`, używany przez `application/cleanup.py:237-253`).
  - **Problem:** Predykat `retained` łączy kandydatów z całą tabelą konsumentów warunkiem `regexp_replace(requested)=regexp_replace(c.path) OR (c.is_root AND starts_with(...))`. Taki warunek nie pozwala na hash join ani na użycie indeksu. Konsumentami są wszystkie `recognized_boards`, `image_symbol_review_cells` (komentarz w `image_geometry_completeness_repository.py:914` mówi o milionach wierszy) i rozwinięte `crop_artifacts` wszystkich rewizji geometrii, we wszystkich grach. Każdy z około 300–500 kandydatów jednego zdjęcia (oryginał, 9 plansz, 135 cel, wycinki geometrii, rejestr, atlasy) jest porównywany z każdym konsumentem: setki milionów wywołań regexp.
  - **Skutek:**
    - W `guard` działa `SET LOCAL statement_timeout='30s'` (`source_purge_retention.py:19`). Finalize po COMMIT dostaje wtedy `CleanupConflictError` / HTTP 500, kwarantanna zostaje `pending`, a każde ponowienie (exact replay, `recover()`) trafia w ten sam timeout. Bajty nigdy nie zostają odzyskane, więc kryterium „faktycznie usuwane” nie jest spełnione na realnych danych.
    - W preview i execute to samo zapytanie biegnie, gdy sesja główna trzyma EXCLUSIVE fence wszystkich gier, co wstrzymuje importy w każdej grze.
    - Przy sprzecznych danych zachowanie pozostaje fail-closed, więc nie ma utraty danych. Testy PG na małej bazie nie mogą tego ujawnić.
  - **Poprawka (wąska, bez nowego frameworka):**
    - W Pythonie wyznaczyć znormalizowane warianty ścieżek (`x` i `data/x`).
    - W gałęziach konsumentów dokładnych użyć `path = ANY(CAST(:variants AS text[]))` per gałąź: semi-join albo hash, bez wyrażeń po stronie tabeli.
    - Dopasowanie prefiksem `starts_with` zostawić tylko dla pięciu gałęzi root (cohorts, exports, model iterations, grid versions), które mają mało wierszy.
    - Semantyka i jedna wspólna funkcja dla preview i finalize zostają bez zmian. Istniejące testy PG/FS potwierdzają semantykę po zmianie.

### P2

- [P2-1] `services/api/src/game_predictor_api/main.py:1005-1020` i `application/cleanup.py:356-360`. Dla żądań purge (mode `replace_delete_source`) `replacement_request` ma wartość False, więc na starcie każdego takiego żądania i każdego generic cleanup działa `recover()` bez żadnego fence. `recover()` przywraca każdą kwarantannę, której klucza nie ma w zatwierdzonych receiptach. Drugie równoległe żądanie mogłoby więc przywrócić pliki purge, który jest w trakcie i jeszcze nie ma COMMIT. Skutek jest wykrywalny (`recovery_pending`, `cleanup.py:320-321`) i naprawialny exact replayem. Mechanizm istniał wcześniej dla legacy. Proponuję akceptację ryzyka (pojedynczy lokalny operator) albo pominięcie `recover()` dla żądań purge.
- [P2-2] `storage/source_replacement_purge.py:25-57,387-406`. Listy nie zgadzają się z kolejnością DELETE:
  - `image_board_search_fast_documents` jest usuwane, ale nie ma go w `DELETE_TABLES`;
  - `image_review_queue_items` jest w `DELETE_TABLES`, ale nie ma jawnego DELETE (zależy od cascade lub triggera).

  Klasyfikacja FK sprawdza tylko dzieci sześciu efemerycznych rodziców i działa na poziomie tabeli, nie kolumny. Zgadza się to z zaakceptowanym P1-3 (RESTRICT kończy się rollbackiem, czyli fail-closed). Proponuję tylko ujednolicić listy z komentarzem o queue triggerze.
- [P2-3] `services/api/alembic/versions/0177_source_replacement_purge.py:104-109`. Downgrade odtwarza FK z automatycznymi nazwami i `ON DELETE RESTRICT`, a nie z oryginalnymi nazwami i akcjami usuniętymi w `upgrade` (pętla `DROP CONSTRAINT` w liniach 14-25). Cykl downgrade/upgrade może dać dryf nazw względem baseline. Proponuję zapisać w downgrade oryginalne nazwy constraintów albo przyjąć ryzyko, bo downgrade po purge i tak odmawia.
- [P2-4] `storage/image_geometry_completeness_repository.py:892`. Kod błędu to `SOURCE_PURGED`, a projekt (pkt 7) mówi o `SOURCE_REPLACEMENT_SOURCE_PURGED`. `purged_at` sprawdza tylko ten jeden punkt dostępu do zasobu źródła; worker nie zna `purged_at` i polega na `status='rejected'` oraz istniejących guardach retired/current. Proponuję ujednolicić kod w dokumentacji (API_CONTRACT) albo w kodzie. Nie rozszerzać zakresu.
- [P2-5] `application/source_purge.py:96`. Odpowiedź execute zawsze zwraca `fileStatus: "pending"` i `deletedBytes: 0`, bo finalize działa dopiero po COMMIT w zależności (`main.py:1024`). Raport jest uczciwy i zgodny z zasadą „pending nie udaje deletedBytes”, ale UI musi pobrać manifest ponownie, żeby pokazać `finalized`. Proponuję akceptację, jeśli panel odświeża manifest po sukcesie (nie zweryfikowałem tego).

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| Manifest/request po fizycznym usunięciu, mały tombstone | spełnione | `domain/source_purge.py:11-50` (puste tablice grafu, frozen digest), `domain/source_replacement_retirement.py:18-21`, `source_replacement_purge.py:425-428` (`purged_at`, `rejected`), raporty PG pg10 |
| Dedykowane pliki faktycznie usuwane, współdzielone i modele zostają | **niezweryfikowane na skali (P1-1)** | Zakres: `source_replacement_purge.py:125-147` (bez kohort i modeli), `source_purge_retention.py:71-107` (konsumenci exact i root), `cleanup.py:283-311` (tylko własne pary atlasów) |
| Numery zostają lukami z rezerwacją, zwykły import działa | spełnione | `source_replacement_purge.py:285-319` (slots reserved, retired `prior.sequence_numbers`), 323-334 `gap_open`, PG admission po DELETE |
| Stare ID/SHA nie wracają do current | spełnione | retired rows (303-319), trigger `0177:50-61` (`source_replacement_current_v1`) |
| Fresh preview/confirm, atomowość, replay, restart, recovery | spełnione (poza P1-1 dla finalize) | `application/source_purge.py:66-96`, `source_replacement_purge.py:70-104`, `main.py:1017-1029`, `cleanup.py:313-342`, `cleanup_repository.py:250-265` |
| API/OpenAPI/generated/wrapper/request test, UI | spełnione wg dowodów wykonawcy; statycznie sprawdzono tylko `api/cleanup.py:130-212` i symbole panelu | Grep panelu: `previewSourcePurge`, `executeSourcePurge`, `fileStatus`, potwierdzenie i token |
| Audyt bez otwartych P0/P1, task-close/commit/hash | niespełnione | P1-1 otwarte |

## Listy zamknięte i otwarte

Zamknięte w audycie projektu (R1 → R2), potwierdzone w kodzie:
- P1-1 PLAN (wspólny predykat): ta sama funkcja `retained` dla preview i dla `guard`;
- P1-2 PLAN: `_busy`, `IMPORT_UNFINISHED`;
- P1-3 PLAN: `_classified_fks` oraz lista detach;
- P1-4 PLAN: `MODEL_BUSY`, `GRID_BUSY`, `REVIEW_BUSY`;
- P2-2 PLAN: `fileProof`, `recover_purge`.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- Bez nowych scenariuszy. Po poprawce P1-1 wystarczy ponowić istniejące `test_source_replacement_purge_postgres.py` oraz `test_source_purge.py` (semantyka shared/finalize bez zmian). Opcjonalnie, bez benchmarku: jedno `EXPLAIN` (bez `ANALYZE`) na bazie testowej, które pokaże semi-join/hash zamiast Nested Loop z join filter po regexp.

## Zakres przeglądu i ograniczenia

Przeczytane (23 celowane odczyty i wyszukiwania):
- task 1141, plan dostawy, szablon audytu;
- `storage/source_replacement_purge.py` w całości (2 fragmenty);
- `storage/source_purge_retention.py` i `application/source_purge.py` w całości;
- `application/cleanup.py:195-394` i `525-684`;
- `main.py:955-1054`;
- `cleanup_repository.py:250-290` i `849-944`;
- migracja 0177 w całości;
- `models.py:4140-4274`;
- `domain/source_purge.py` i `domain/source_replacement_retirement.py:1-45`;
- `api/cleanup.py:120-229`;
- `image_geometry_completeness_repository.py:865-919`;
- wyszukiwania symboli w panelu i w usługach.

Czego nie sprawdziłem:
- `storage/source_replacement.py` (preview/create w trybie compact), `SourceRetirement._invalidate`/`_derive_jobs`, `acquire_sequence_ownership_lock`: zgodność hasha z triggerem przyjąłem z dowodów wykonawcy;
- `_cross_game_reader` (ewentualny timeout);
- schematy Pydantic, wrapper klienta, pełny panel UI, generated diff;
- rzeczywiste liczności tabel produkcyjnych. P1-1 to ocena złożoności zapytania z kodu, niepotwierdzona pomiarem.

Testów nie uruchamiałem. Ich wyniki pochodzą z raportu wykonawcy. Raportu nie zapisałem do `ai_docs/quality/`, bo audyt był tylko do odczytu; treść jest gotowa do wklejenia jako `TASK-1141_AUDIT_claude-opus-5-5.md`.
