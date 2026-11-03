# Audyt TASK-1141, runda 2 (final, celowana): claude-opus-5-5 / high

## Werdykt: **PASS**

P1-1 z final R1 jest zamknięte. Poprawka nie dodała nowych P0 ani P1.

## Zakres
Sprawdziłem tylko poprawkę P1-1 w `services/api/src/game_predictor_api/storage/source_purge_retention.py`:
- `retained`: linie 62-136,
- `guard`: linie 138-158,
- `dispatch`: linie 42-60.

Porównałem ją z zarzutem z R1 (`TASK-1141_AUDIT_claude-opus-5-5_R1.md:30-40`). Upstream, UI i reszty taska nie audytowałem ponownie.

## P1-1: weryfikacja

**Zarzut z R1:** każdy kandydat był łączony z każdym konsumentem (N×M) warunkiem `regexp_replace(...)=regexp_replace(c.path) OR starts_with(...)`. Na dużych tabelach groził timeout 30 s i blokada importów.

**Stan po poprawce:**
- **Normalizacja raz, w Pythonie.** Ścieżki kandydatów są normalizowane raz w `source_purge_retention.py:71-74` (`removeprefix("data/")` i warianty `x` oraz `data/x`). Pasuje to do kierunku z R1:36-37.
- **Siedem gałęzi exact (78-109).** Każda filtruje własną tabelę przez `kolumna = ANY(CAST(:variants AS text[]))`. W SQL nie ma już `regexp_replace`, nie ma złączenia kandydatów z konsumentami i nie ma `starts_with`. Koszt jest liniowy względem tabeli, a nie N×M. Tablica wariantów to bind po stronie serwera, więc PG 18 może użyć hashowanego ScalarArrayOp albo indeksu.
- **Gałęzie root (110-119):** cohorts, exports, `symbol_model_iterations` (5 ścieżek) i `grid_model_versions` zwracają małe zbiory z `is_root=true`. Dopasowanie prefiksem odbywa się w Pythonie (124-136) tylko na tym małym zbiorze, zgodnie z R1:39.
- **Semantyka exact się nie zmieniła.** Warunek „konsument po zdjęciu `^data/` równa się kandydatowi po zdjęciu `^data/`” jest równoważny dopasowaniu do `{x, data/x}`. Jedyna różnica to możliwy nadzbiór, który działa fail-closed. Wynik zachowuje pisownię ścieżki od wywołującego (132-136).
- **Wyjątki gry i źródła są bez zmian.** Każda gałąź ma `NOT(game_id=:game AND id/source_image_id = ANY(:excluded))`, a `source_images` i `source_image_crops` dodatkowo `purged_at IS NULL`.
- **Preview i finalize używają tej samej funkcji.** Preview woła `retained` przez `source_replacement_purge.py:205-207` (`shared`). Finalize woła ją z `guard`, linia 156. Test PG `test_source_purge_frozen_postgres.py:299-301` wywołuje ją bezpośrednio.
- **Blokada i dowód są bez zmian.** `guard` nadal wykonuje kolejno:
  - blokadę `SHARED` wszystkich gier (143) z `lock_timeout` i `statement_timeout` (18-19);
  - odczyt receipt (144-151);
  - sprawdzenie, że `paths ⊆ fileProof` (152-154);
  - wyjątki z `sourceIds` z receipt (155).
- **Dispatch (42-60) jest bez zmian:** znany klucz idzie przez `guard`, nieznany przez fallback, a brak fallbacku kończy się fail-closed.

## Ryzyka resztkowe (nie blokują, bez nowej rundy)
- **Brak indeksów na kolumnach ścieżek (obserwacja).** W `models.py` nie znalazłem deklarowanych indeksów na `relative_path`, `board_relative_path` i `crop_relative_path`. Gałęzie exact będą więc prawdopodobnie robić seq scan. Ten koszt jest liniowy, a nie N×M jak w R1. Gałąź JSONB `crop_artifacts` (95-101) i `unnest` w `source_image_crops` (102-107) siłą rzeczy liczą wyrażenie po stronie tabeli, ale też liniowo. Bez EXPLAIN i bez pomiaru na realnych danych zapas względem 30 s jest oszacowaniem z kodu, nie liczbą. Zgodnie z ustaleniem nie robiliście benchmarku.
- **Granica katalogu dla roots (obserwacja).** Root ma teraz zawsze dopisany `/` (129), więc dopasowanie zatrzymuje się na granicy katalogu. Starej postaci `starts_with` nie czytałem, więc nie potwierdzam pełnej równoważności. Granica katalogu jest jednak poprawną semantyką. Same roots trafiają też do zbioru exact (127), co daje nadzbiór i działa fail-closed.

## Lista zamkniętych i otwartych
- **Zamknięte w R2:** P1-1 (final R1).
- **Rozliczone wcześniej i przyjęte przez prowadzącego, nie blokują:** P2-1 (zaakceptowane), P2-2 (komentarz, bez zmiany zachowania), P2-3 (zaakceptowane), P2-4 (dopasowane), P2-5 (odświeżanie w panelu). W R2 ich nie weryfikowałem.
- **Otwarte P0/P1:** brak.

## Ograniczenia
- Wykonałem 8 odczytów i wyszukiwań: R1 (P1-1), cały `source_purge_retention.py`, `grep` wywołań `retained`, `grep` testów PG/FS i indeksów oraz fragment testu frozen PG.
- Nie czytałem całego `application/source_purge.py::_preview`. Ścieżkę preview → `shared` → `retained` potwierdziłem przez `grep`.
- Testy nie zostały uruchomione. Wynik 4×PASS oraz ruff i mypy PASS przyjmuję z raportu wykonawcy.
- Raportu nie zapisałem do `ai_docs/quality/`, bo audyt był tylko do odczytu. Treść jest gotowa do wklejenia jako `TASK-1141_AUDIT_claude-opus-5-5_R2.md`.
- Brak przyszłego commita i hasha nie jest znaleziskiem.
