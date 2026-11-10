# Audyt TASK-1180 — Wydajny wybór próbki pilota jakości 777A2

Werdykt: PASS
Audytor: claude-opus-5-5, reasoning high
Wykonawca: gpt-6-astra, reasoning high
Zakres: HEAD...a9af003222c0dcf052c96977bb0109396590902e oraz zmiany niezacommitowane, data 2026-11-10
Runda: 2
SHA pakietu: 41d1ebb9d04ac6e3971838f62519b9094f669cc3984b6847cfa9e48cd3b2a6ba
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W rundzie 2 sprawdziłem poprawki po rundzie 1. Najważniejsze z nich to rozbudowany test PostgreSQL, wymóg blokady EXCLUSIVE w `has_replacement_fences` i zamrożone literały wzorca legacy. Ponownie przejrzałem też cały moduł `readability_inventory.py` i jego użycie w `readability_workflow.py`.

Znalezisko P1-1 jest zamknięte. Test pokazuje teraz, że każdy z trzech rodzajów historii wymiany osobno wyłącza szybką ścieżkę i faktycznie wyklucza źródło. Pokazuje też, że pełne listy legacy i nowe są równe dla pilota i audytu przy trzech seedach. Sprawdziłem, że w produkcji nowa asercja blokady jest spełniona, a heartbeat nie koliduje z blokadami transakcji inventory.

Pozostają ryzyka P2, opisane w Outcome. Główne to izolacja READ COMMITTED między przebiegami rang i niewielki zapas czasu zapytania prefiksu audytu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/symbols/readability_inventory.py:117-148` — Kolejne przebiegi rang i partie źródeł to osobne zapytania w READ COMMITTED. Zapis do `image_symbol_review_cells`, który omija blokadę własności sekwencji, może między nimi przesunąć rangi. Skutek: pominięte pole albo duplikat, który skończy się konfliktem `INSERT` w `readability_workflow.py:459-480`.
  - **Stan.** Wykonawca odnotował ryzyko w Outcome i wymaga, by odbiór pilota odbył się bez równoległego backfillu ani masowych zmian korpusu. Nie zweryfikował jednak wszystkich pisarzy, więc ryzyko pozostaje świadomie zaakceptowane.
  - **Proponowana poprawka na przyszłość.** Ustawić REPEATABLE READ dla transakcji inventory albo potwierdzić, że wszyscy pisarze projekcji biorą blokadę własności sekwencji.

- [P2-4] `services/worker/src/game_predictor_worker/symbols/readability_inventory.py:104-115` — Każdy prefiks audytu skanuje wszystkie pola gry. Zmierzone 18,204 s to około 61% limitu 30 s (`symbol_readability.py:75`).
  - **Skutek.** Wzrost korpusu, większa liczba oznaczonych pozycji albo obciążenie bazy mogą znowu dać SQLSTATE 57014.
  - **Stan.** Ryzyko i obowiązek pomiaru przy pierwszym pełnym pilocie są zapisane w Outcome, bez obietnicy czasu ukończenia. Akceptacja ryzyka jest właściwa w tym zakresie, ale samo ryzyko nadal istnieje.

- [P2-5] `services/worker/src/game_predictor_worker/symbols/readability_workflow.py:362-368` — Heartbeat nie ma testu. Sprawdziłem statycznie, jak działa:
  - `context.heartbeat()` używa osobnej sesji (`jobs/store.py:159-170`) i blokuje wiersz joba.
  - Transakcja inventory nie blokuje tego wiersza aż do `self.fence` w `readability_workflow.py:513`, czyli po ostatnim wywołaniu `progress`. Zakleszczenie jest więc wykluczone.
  - `progress` jest wołany dla każdej partii źródeł (`readability_inventory.py:130-131`), każdego prefiksu (`:105-106`) i każdego wiersza.
  - **Stan.** Wykonawca odnotował brak testu. Ryzyko jest akceptowalne do odbioru operatorskiego.
  - **Proponowana poprawka.** Test jednostkowy z fałszywym kontekstem i podmienionym `time.monotonic`.

- [P2-7] `services/api/tests/integration/test_readability_inventory_postgres.py:130-181` — Test asercjami potwierdza wykluczenie tylko dla źródła `rejected` i źródeł z historią wymiany (`excluded_sources`). Dla pola z rozjechaną geometrią (`stale`) i pozycji `ever_labelled` sprawdza wyłącznie równość z legacy.
  - **Skutek.** Jeśli `rendered_pixel_checksum_sha256` pola `labelled` jest w fixture `NULL`, warunek `NOT EXISTS` niczego nie wyklucza i scenariusz nie rozróżnia zapytań. Analogicznie test nie dowodzi, że pole `stale` przeszło przez tani nadzbiór audytu i zostało odrzucone dopiero przy hydratacji. Równość z zamrożonym literałem legacy nadal chroni poprawność, więc to tylko słabszy dowód rozróżnialności.
  - **Proponowana poprawka.** Dodać asercje, że `stale["cell_id"]` nie występuje w listach pilota i audytu. Dla audytu dodać asercję, że żaden wiersz nie ma RGB równego `labelled["rendered_pixel_checksum_sha256"]`, oraz że to RGB nie jest `None`.

- [P2-8] `ai_docs/process/CURRENT_STATE.md:96` — Wpis mówi o „49 testach”. Outcome po rundzie poprawek podaje „Łącznie 50 różnych testów PASS”. Skutkiem jest drobna niespójność stanu procesu.
  - **Proponowana poprawka.** Przy zamknięciu taska zaktualizować wpis w `CURRENT_STATE.md` do stanu po audycie.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Dokładna zgodność kolejności i snapshotów starego/nowego query dla pilota i audytu, kilka seedów, flagi current zachowane | spełnione (statycznie; wynik testu według deklaracji wykonawcy) | Równoważność kolejności: pilot w `readability_inventory.py:49-75` i `:117-148`, audyt w `:101-116`. Zakres `has_replacement_fences` (`:27-46`) obejmuje dokładnie tabele, od których zależy strażnik: `0175_source_replacement_guards.py:22-42` i `0176_source_replacement_closed.py:11-27,72-85`. Ten sam warunek skrótu jest już w `0179_empty_replacement_search.py:23-28`. Test `test_readability_inventory_postgres.py:182-235` obejmuje retired, reserved i restored osobno, po 3 seedy, pilota i audyt. |
| Brak hydratacji całego korpusu, paczki ≤250, close po wcześniejszym zakończeniu, brakujące lub stale cele odmawiają | spełnione | Paczki: `readability_inventory.py:20`, `:113`, `:142-143`, `:165-174`. Odmowa `READABILITY_CROP_STALE`: `:183-185`. Zamykanie kursorów w `finally`: `:114-115`, `:144-145`, `:187-188`, `readability_workflow.py:398-399`, `:452-453`. Testy: `services/worker/tests/test_readability_inventory.py` (6 przypadków). |
| Istniejące testy rodzin/izolacji i PG readability przechodzą; lint/types/docs/map i wymagany audyt rozliczone | niezweryfikowane | Deklaracja wykonawcy w Outcome: 50 testów PASS, ruff, mypy i mapa kodu PASS. Testów nie uruchamiałem. Ten raport rozlicza audyt krzyżowy. |
| Ograniczony odczyt READONLY potwierdza pierwszą partię bez timeout; brak deklaracji ukończonego pilota | niezweryfikowane | Outcome i `READABILITY_PILOT_TIMEOUT_20261110.md` podają 1,843 s i 18,204 s, ale artefakty pomiarowe są poza pakietem. Outcome, raport jakości i `CURRENT_STATE.md:96` nie deklarują ukończonego pilota. |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P2-2, P2-3, P2-6.

Dowody zamknięcia:

- **P1-1.** Rozbudowany test PostgreSQL:
  - `test_readability_inventory_postgres.py:104` sprawdza pustą historię, a `:182-235` każdy rodzaj historii osobno z `assert has_replacement_fences(...)`.
  - Asercja wykluczenia źródła jest w `:113`.
  - Pole `rejected`, rozjechana geometria i `ever_labelled` są w `:132-180`.
  - Wycofanie fixture przez savepoint jest w `:234-235`. Rejestr blokady jest wiązany z transakcją główną (`sequence_ownership_lock.py:83`), więc działa także w zagnieżdżonych transakcjach.
- **P2-2.** Akceptacja późnego filtrowania nadzbioru audytu i doprecyzowanie sekcji Risks zostały zapisane w Outcome.
- **P2-3.** `readability_inventory.py:29-35` odmawia bez blokady EXCLUSIVE, a test `test_readability_inventory.py` (`test_fence_fast_path_refuses_missing_ownership_lock`) to sprawdza. W produkcji blokada jest wcześniej pobrana przez `repo.acquire_write_lock` (`readability_workflow.py:352`, `symbol_readability.py:62-63`) w trybie domyślnym EXCLUSIVE, który zapisuje go w rejestrze (`sequence_ownership_lock.py:103`, `:156-157`).
- **P2-6.** Warunki legacy są zamrożonymi literałami w `test_readability_inventory_postgres.py:82-101` i nie zależą od `ELIGIBLE_SQL`.

Otwarte: P2-1, P2-4, P2-5, P2-7, P2-8.

## Proponowane testy

- `services/api/tests/integration/test_readability_inventory_postgres.py`: asercje rozróżnialności z P2-7. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_readability_inventory_postgres.py`. Asercje:
  - pole `stale` nie występuje w liście pilota ani audytu;
  - RGB pola `labelled` nie jest `None` i nie występuje w liście audytu.
- `services/worker/tests/test_readability_inventory.py`: test, że `progress` jest wołany przy każdej partii źródeł i każdym prefiksie audytu. Dodatkowo test `inventory` z fałszywym kontekstem i podmienionym `time.monotonic`, sprawdzający `heartbeat()` po 10 s. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_readability_inventory.py`.

## Zakres przeglądu i ograniczenia

Przeczytano:
- pełny pakiet audytowy: task, diff, nowe pliki i raport rundy 1;
- `readability_workflow.py:320-519` oraz `_repo` i `fence` (`:168-198`);
- `sequence_ownership_lock.py:60-220`;
- `symbol_readability.py:58-97`;
- migracje `0175_source_replacement_guards.py`, `0176_source_replacement_closed.py` i `0179_empty_replacement_search.py`, a także użycie strażnika w `0177_source_replacement_purge.py`;
- wartości dozwolonych statusów w `0174_source_replacement.py`;
- `ReadabilityWorkflowError` i `ReadabilityError`;
- implementację `heartbeat` w `jobs/runtime.py` i `jobs/store.py`;
- fragment ścieżki `outside` w `image_symbol_review_repository.py`.

Ograniczenia:
- Nie uruchamiano testów, lintera, mypy ani zapytań. Wyniki z Outcome przyjęto jako deklarację wykonawcy.
- Nie czytano artefaktów pomiarowych z `artifacts/readability-pilot-20261110/`.
- Nie przeglądano zmian w `CODE_MAP*.md` (poza pathspec).
- Nie zweryfikowano wszystkich pisarzy `image_symbol_review_cells` (dotyczy P2-1).
- Nie sprawdzono, czy fixture nadaje polom `virtual_source` niepusty `rendered_pixel_checksum_sha256` (dotyczy P2-7).