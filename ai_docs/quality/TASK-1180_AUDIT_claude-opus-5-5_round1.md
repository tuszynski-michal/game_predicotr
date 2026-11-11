# Audyt TASK-1180 — Wydajny wybór próbki pilota jakości 777A2

Werdykt: REVISE
Audytor: claude-opus-5-5, reasoning high
Wykonawca: gpt-6-astra, reasoning high
Zakres: HEAD...a9af003222c0dcf052c96977bb0109396590902e oraz zmiany niezacommitowane, data 2026-11-10
Runda: 1
SHA pakietu: 57521c21377c102233cd06e37424ae362f6d371df130439f590fac1cfaa0407d
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadałem podział `SNAPSHOT_SQL` na fragmenty, nowy moduł `readability_inventory.py`, jego użycie w `readability_workflow.py`, testy jednostkowe i nowy test PostgreSQL. Sprawdziłem też definicje `source_replacement_current_v1` (migracje 0175/0176), protokół blokady `sequence_ownership_lock` i to, czy zapisy historii wymiany źródeł biorą tę blokadę.

Algorytm wygląda poprawnie:
- Pilot dzieli pracę na przebiegi po rangach i partie źródeł bez rozdzielania remisów hashy. Partycja `row_number` zawiera `s.id`, więc ograniczenie do partii źródeł nie zmienia rang.
- Audyt przegląda prefiksy `00`–`ff`. Ich konkatenacja daje dokładnie globalną kolejność `md5, id`.
- Pominięcie strażnika `current` przy pustej historii jest semantycznie uzasadnione. Funkcja zależy wyłącznie od `retired`, `slots` i `entries` w fazie `restored`, a wszystkie znalezione zapisy do tych tabel biorą blokadę EXCLUSIVE.

Główne ryzyko: test równoważności działa tylko na danych, w których żaden filtr nie rozróżnia starego i nowego zapytania. Gałąź z niepustą historią wymiany i filtrowanie nadzbioru audytu na prawdziwym SQL pozostają bez testu.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/tests/integration/test_readability_inventory_postgres.py:100` — Test równoważności sprawdza tylko przypadek pustej historii wymiany (`assert not has_replacement_fences`). Wszystkie 60 pól ma też status `pending`, zgodną geometrię, `source_available` i brak oznaczonych pozycji w `symbol_readability_items`.
  - **Gałąź z niepustą historią nie jest sprawdzona.** Gdy jest niepusta historia, `has_replacement_fences` musi zwrócić `True`, a strażnik musi faktycznie odfiltrować pola. Ta gałąź nie jest wykonywana w żadnym teście. Wywołanie z `fences=True` na pustej historii dowodzi tylko składni, bo strażnik zwraca wtedy zawsze prawdę.
  - **Nadzbiór audytu nie jest sprawdzony na prawdziwym SQL.** Tania lista ID audytu (`readability_inventory.py:42-51`) pomija warunki `r.status<>'rejected'`, zgodność geometrii i strażnik `current`. Nie ma jednak w danych pola, które ta lista zwraca, a hydratacja musi odrzucić.
  - **Skutek.** Kryterium „flagi current zachowane” i „dokładna podsekwencja” nie ma dowodu w gałęzi, której błąd wpuściłby wycofane albo zastąpione źródła do pilota lub audytu. Funkcja `has_replacement_fences` decyduje o pominięciu zabezpieczenia, a nie ma pozytywnego testu.
  - **Poprawka.** Rozszerzyć fixture o:
    - jedno źródło z wpisem w `source_replacement_retired` albo slotem `reserved`, osobno także wpis `entries` z `phase='restored'`;
    - jedną recenzję `rejected`;
    - jedno pole z rozjechaną geometrią;
    - jedną pozycję `ever_labelled` o tym samym `rendered_pixel_checksum_sha256`.
  - Następnie sprawdzić, że `has_replacement_fences` zwraca `True` i że `candidate_snapshots` z `replacement_fences=True` daje listę równą legacy dla pilota i audytu przy kilku seedach.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/symbols/readability_inventory.py:105-136` — **Pilot nie widzi jednego spójnego stanu danych.** Każdy przebieg rangi (`position`) i każda partia to osobne zapytanie w transakcji READ COMMITTED. Legacy liczyło `row_number` na jednym snapshocie.
  - **Skutek.** Jeżeli między przebiegami pole zostanie dodane do warstwy lub z niej usunięte przez zapis niebiorący blokady własności sekwencji, rangi się przesuną. Pole może zostać wtedy po cichu pominięte albo zwrócone drugi raz. Duplikat skończyłby się konfliktem przy `INSERT` w `readability_workflow.py:459-480`, a nie typowanym `READABILITY_CROP_STALE`.
  - **Poprawka.** Uruchomić transakcję inventory w REPEATABLE READ: ustawić to na początku transakcji w `readability_workflow.py:350`, przed blokadą. Alternatywnie odnotować w tasku, że wszyscy pisarze `image_symbol_review_cells` biorą blokadę własności.

- [P2-2] `services/worker/src/game_predictor_worker/symbols/readability_inventory.py:166-170` — **Audyt nie odróżnia filtrowania od zmiany danych.** W trybie audytu brak wiersza przy hydratacji zawsze oznacza ciche pominięcie. Nie da się odróżnić odfiltrowania nadzbioru od zmiany pola między listą ID a hydratacją. Sekcja „Risks” wymaga typowanego `stale` zamiast cichej utraty pól.
  - **Ocena.** Pod blokadą EXCLUSIVE okno jest małe, a pominięte pole jest wtedy faktycznie nieuprawnione. Ryzyko jest akceptowalne.
  - **Poprawka.** Zapisać tę akceptację w Outcome taska.

- [P2-3] `services/worker/src/game_predictor_worker/symbols/readability_inventory.py:24-25` — **Wymóg blokady jest tylko w docstringu.** To, że wołający trzyma blokadę własności sekwencji, opisuje jedynie docstring. Inne miejsce wywołania bez blokady pominęłoby strażnik `current` bez gwarancji, że historia pozostanie pusta.
  - **Poprawka.** W `has_replacement_fences` dodać trwałą asercję `held_sequence_ownership_lock(session, game_id=game) is SequenceOwnershipLockMode.EXCLUSIVE` (`sequence_ownership_lock.py:92`). Przy jej braku zgłaszać błąd.

- [P2-4] `services/worker/src/game_predictor_worker/symbols/readability_inventory.py:95-99` — **Zapas czasu jest mały.** Zapytanie jednego prefiksu audytu skanuje całą tabelę pól gry: liczy `md5` i warunek `NOT EXISTS` po wyrażeniu JSON. Zmierzone 18,204 s to około 61% limitu 30 s (`symbol_readability.py:75`).
  - **Skutek.** Wzrost korpusu, większa liczba oznaczonych pozycji albo obciążenie bazy mogą ponownie dać SQLSTATE 57014.
  - **Czas całego pilota nie jest zmierzony.** Dotyczy to wielu przebiegów rang razy trzy części TEST/VAL/TRAIN, przez cały czas pod blokadą EXCLUSIVE gry.
  - **Poprawka lub akceptacja.** Odnotować ryzyko w tasku i w odbiorze operatorskim. Mierzyć czas wykonania pełnego pilota przy pierwszym rzeczywistym uruchomieniu.

- [P2-5] `services/worker/src/game_predictor_worker/symbols/readability_workflow.py:364-368` — **Heartbeat nie ma testu.** Zakres wymaga odnawiania dzierżawy co 10 s między partiami i polami. Żaden test nie sprawdza, że `progress` wywołuje `context.heartbeat()` ani że `candidate_id_pages` woła `progress` przy partiach i prefiksach.
  - **Poprawka.** Dodać test jednostkowy z fałszywym kontekstem i podmienionym `time.monotonic`.

- [P2-6] `services/api/tests/integration/test_readability_inventory_postgres.py:82-97` — **Wzorzec legacy zależy od nowej stałej.** Zapytania „legacy” w teście są złożone z nowej stałej `ELIGIBLE_SQL`, a nie z zamrożonego literału starego kodu. Zmiana `ELIGIBLE_SQL` zmieni obie strony porównania jednocześnie i test tego nie wykryje.
  - **Poprawka.** Wkleić w teście dokładne literały usunięte z `readability_workflow.py`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Dokładna zgodność kolejności i snapshotów starego/nowego query dla pilota i audytu, kilka seedów, flagi current zachowane | niezweryfikowane | Analiza statyczna potwierdza równoważność: `readability_inventory.py:38-77`, `:89-136`; definicja strażnika w `0176_source_replacement_closed.py:12-27` i `0175_source_replacement_guards.py:22-28`. Test `test_readability_inventory_postgres.py:98-113` obejmuje tylko pustą historię i dane bez filtrów rozróżniających (P1-1). |
| Brak hydratacji całego korpusu, paczki ≤250, close po wcześniejszym zakończeniu, brakujące lub stale cele odmawiają | spełnione | Paczki: `readability_inventory.py:130-131`, `:101`, `:154-162`. Odmowa `READABILITY_CROP_STALE`: `:171-173`. `finally/close`: `:176-177`, `readability_workflow.py:398-399`, `:452-453`. Testy: `test_readability_inventory.py` (5 przypadków). |
| Istniejące testy rodzin/izolacji i PG readability przechodzą; lint/types/docs/map i wymagany audyt rozliczone | niezweryfikowane | Deklaracja wykonawcy w Outcome. Testów nie uruchamiano. Audyt krzyżowy trwa (ten raport). |
| Ograniczony odczyt READONLY potwierdza pierwszą partię bez timeout; brak deklaracji ukończonego pilota | niezweryfikowane | Outcome podaje 1,843 s i 18,204 s, ale artefakty dowodowe są poza zakresem pakietu. Outcome i `CURRENT_STATE.md` nie deklarują ukończonego pilota. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- `services/api/tests/integration/test_readability_inventory_postgres.py`: nowy przypadek z niepustą historią wymiany i polami rozróżniającymi, opisanymi w P1-1. Asercje: `has_replacement_fences(...) is True` oraz równość z legacy dla pilota i audytu przy trzech seedach. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_readability_inventory_postgres.py`.
- `services/worker/tests/test_readability_inventory.py`: test, że `progress` jest wołany dla każdej partii źródeł i każdego prefiksu audytu. Plus test w `readability_workflow` z fałszywym kontekstem i podmienionym zegarem, sprawdzający `heartbeat()` po 10 s. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_readability_inventory.py`.
- Test jednostkowy asercji blokady w `has_replacement_fences`, jeżeli zostanie dodana według P2-3.

## Zakres przeglądu i ograniczenia

Przeczytano:
- pełny pakiet audytowy (task, diff, nowe pliki);
- `readability_workflow.py:140-528`, `readability_inventory.py:80-177`, `readability_selection.py:33-89`;
- `sequence_ownership_lock.py` oraz `acquire_write_lock`/`bind` w `symbol_readability.py`;
- migracje `0175_source_replacement_guards.py` i `0176_source_replacement_closed.py`;
- zapisy do tabel wymiany w `source_replacement_purge.py` i `source_purge_retention.py`, a także wykaz miejsc biorących blokadę w modułach `source_replacement*`;
- fixture `test_symbol_readability_postgres.py:1-104` i nagłówki pomocników z `test_image_batch_store.py`.

Ograniczenia:
- Nie uruchamiano testów, lintera, mypy ani zapytań. Wyniki z Outcome przyjęto jako deklarację wykonawcy, bez potwierdzenia.
- Nie czytano artefaktów pomiarowych z `artifacts/readability-pilot-20261110/`.
- Nie przeglądano zmian w `CODE_MAP*.md`, bo są poza zadanym pathspec.
- Nie zweryfikowano wszystkich pisarzy `image_symbol_review_cells` pod kątem blokady (dotyczy P2-1).