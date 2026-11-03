# Audyt TASK-1129 / B2b — wycofanie źródła z zachowaniem historii

Werdykt: PASS

Audytor: claude-opus-5-5
Reasoning: high
Runda: 1

## Streszczenie

Nie znalazłem błędów P0 ani P1. Wycofanie przebiega w jednej transakcji, w ustalonej kolejności:
- blokada EXCLUSIVE na grę;
- replay receipt przed jakimkolwiek CAS (`storage/source_replacement_retirement.py:153-167`);
- sprawdzenie fazy i rewizji wpisu;
- blokady sekwencji, a potem blokady wierszy rosnąco po id: sources, potem review, board i deferred (`:168-199`);
- ponowne wywołanie istniejącego buildera B2a i porównanie `scope_digest` z niezmiennym planem (`:51-86`);
- token wiążący action/game/batch/entry/revision/snapshot (`:87-96`, `:200-205`).

Każdy błąd przerywa żądanie, a zależność cleanup cofa całą transakcję (`main.py:1010-1022`), więc faza się nie zmienia. Wyjątek D-580 jest wąski. Proof wiąże dokładny wiersz joba (id/game/type/input_key/payload) i powstaje tylko dla jobów nowych po `_invalidate`. Job istniejący wcześniej albo scalony nie dostaje proof. Helper scala bez zmiany payloadu (`super_game_input_version.py:240-251`), więc kolejne wpisy tego samego batcha mogą kontynuować.

Mobile: SHARED fence obejmuje publish, record_snapshot i mark_ready (`releases/handler.py:125-149`, `:190-196`). Używa jednego połączenia tylko do blokady i jednego routowanego czytnika naraz (`releases/store.py:57-86`).

## P0

Brak.

## P1

Brak.

## P2

1. **`NOT IN (SELECT public.source_replacement_excluded_reviews_v1(...))` nie jest odporne na NULL** (`storage/super_game_series_repository.py:98, 111, 134, 141, 152`).
   - **Skutek:** jeśli funkcja z B2a zwróci kiedykolwiek wiersz NULL (np. przez LEFT JOIN board bez review), każdy z pięciu odczytów supergame zwróci pusty wynik dla całej gry. Wyglądałoby to jak brak danych, a nie jak błąd.
   - Nie czytałem treści funkcji (migracja 0175 jest poza zakresem), więc nie jest to potwierdzony błąd.
   - **Zalecenie:** potwierdzić, że funkcja zwraca tylko NOT NULL, albo przejść na `NOT EXISTS`.

2. **Kolejność blokad review → board różni się od opisanej w dokumentacji** (`storage/source_replacement_retirement.py:180-193` wobec `sequence_ownership_lock.py:27`, który opisuje „board, review item, …”).
   - Pod EXCLUSIVE zderzyć się mogą tylko uczestnicy bez blokady ownership.
   - **Skutek:** w najgorszym razie PG wykryje deadlock i cofnie transakcję (fail-closed). To ryzyko dostępności, nie integralności.

3. **SHARED fence trwa przez cały fizyczny publish snapshotu** (`releases/handler.py:125-149`). Połączenie fence pozostaje w tym czasie bezczynne w otwartej transakcji (`releases/store.py:60-86`).
   - **Skutek:** oczekujący na EXCLUSIVE retirement ustawia się w kolejce blokad PG. Nowe SHARED (decyzje symbol-cell) mogą wtedy czekać za nim przez cały publish.
   - Jeśli kiedyś zostanie skonfigurowany `idle_in_transaction_session_timeout`, fence zniknie po cichu w trakcie publikacji. Wtedy `record_snapshot` się zapisze, a dopiero wyjście z kontekstu zgłosi błąd.

4. **Fence i test startowy sprawdzają istnienie dowolnego wiersza `source_replacement_slots` bez filtra `state='reserved'`** (`releases/store.py:74-78`).
   - W B2b to poprawne, bo istnieje tylko stan reserved.
   - **Skutek dla C2:** jeśli zwolnienie slotu zostawi wiersz w innym stanie, mobile zostanie zablokowany na stałe. C2 musi świadomie zmienić to zapytanie albo usuwać wiersze.

5. **Szczegóły błędu podglądu są zaszumione** (`storage/source_replacement_retirement.py:58-65`).
   - `resolutionUrls` budowane jest ze wszystkich canonical i pending, także własnych, nawet gdy jedynym blockerem jest np. `ACTIVE_JOB`.
   - Dla obcego deferred geometry nie ma URL (jest tylko `pendingGeometry`).
   - **Skutek:** to tylko UX, operator może kliknąć w niewłaściwy element.

## Pokrycie kryteriów

| Kryterium | Ocena | Dowód |
|---|---|---|
| Niezmienny plan, drift odmawia bez rebase | OK | `:81-86`; plan nie jest nadpisywany; GET nakłada fazę i rewizję (`storage/source_replacement.py:516-531`) |
| Jedna transakcja, replay przed CAS, wszystkie sloty i markery | OK | `:156-167`, `:274-311`; marker dla każdego aliasu ze starym SHA |
| Obcy pending blokuje; własne review i deferred superseded z pełnym prior | OK | builder `:226-231`; review: event `superseded` plus `previous` z całym wierszem (`domain/source_replacement_retirement.py:22-34`); deferred: `superseded_at` plus pełne `pending_slots` w `prior` markera; test `test_source_retirement_postgres.py:457-467` potwierdza brak eventów pending; board→`rejected` to istniejący wzorzec (`image_review_repository.py:1468`) |
| Current search/supergame bez wycofanego zdjęcia, historia zostaje | OK (z P2-1) | `:361-392`, `_invalidate` `:407-421`; test rebuild `:533-542`, `_POSITION_BOARDS_SQL` `:444-448` |
| Mobile: kontrola na starcie oraz fence przed publish i markready | OK | `releases/store.py:36-38`, `handler.py:125`, `:190`; test PG `:544-548`; worker parametryzowany `snapshot`/`ready` (`test_release_workflow.py:195-222`) |
| Cancel tylko z planned; request-v1 tylko gap_open; postęp innego wpisu nie psuje scope | OK | `_planned` `:142-150`; eksport `:435-439`; brak rewizji batcha w payloadzie; test `:511-521` |
| Typowany eksport, UI reload i utracona odpowiedź | OK | schemat `Literal`/`confirmed: Literal[True]` (`schemas/source_replacement.py:90-98`); UI utrwala dokładne polecenie przed wysłaniem i usuwa je tylko przy 2xx lub 4xx (`source-retirement-actions.tsx:176-196`); uszkodzony zapis blokuje nowe operacje (`:80-91`) |
| D-580 proof | OK | `:115-139`, `:393-405`; testy: zmiana payloadu `:474-484`, obcy derive `:489-506` |

## Zamknięte

- Wiele własnych pending w jednym zdjęciu nie łamie unikalności: `uq_..._item_idempotency` i `uq_..._item_revision` są per review item (`alembic/versions/0018_image_failure_retry.py:213-222`). Akcja `superseded` jest dozwolona od 0050.
- Współbieżny replay tego samego klucza czeka na EXCLUSIVE, a potem odczytuje receipt.
- Status joba nie wchodzi do digestu proof, więc przejście created→processing nie unieważnia proof. Taki job jest odfiltrowany przed liczeniem tokenu.
- DELETE i preview w trybie `replace_preserve_history` omijają recover artefaktów cleanup (`main.py:993-1013`).

## Otwarte (poza B2b / C2)

- Admission, restored i expiry; zamknięcie orphans przed zwolnieniem slotów; zapobieganie duplikatom provisional; preflight newSHA.
- Po zwolnieniu slotów w C2 trzeba rozstrzygnąć, czy dataset_version zbudowany przed wycofaniem może jeszcze trafić do wydania. Fence patrzy tylko na sloty, nie na markery retired.
- Nie zweryfikowałem, czy `count_projection_status='unavailable'` (`:415-419`) jest automatycznie odbudowywany z wykluczeniem wycofanych review.

## Proponowane testy

1. Prawdziwa współbieżność PG: SHARED fence jest trzymany, a retirement w drugiej sesji czeka albo kończy się lock_timeout i nie mutuje niczego. Następnie retirement po zwolnieniu fence oraz mark_ready, które je wykrywa.
2. Trzy wpisy w jednym batchu: derive z wpisu 1 przechodzi w `processing`, wpis 2 tworzy nowy proven job, wpis 3 nadal przechodzi.
3. Supergame po wycofaniu zdjęcia z boardem bez review item (ryzyko NULL z P2-1): wyniki innych sekwencji nie mogą znikać.
4. Wycofanie zdjęcia z co najmniej dwoma własnymi pending review: liczniki `image_review_queue_states` się zgadzają.
5. UI: odpowiedź 5xx lub zerwana sieć, potem przeładowanie; ponowione polecenie ma ten sam `idempotencyKey`, a serwer zwraca replay.

## Ograniczenia

- Przegląd statyczny. Nie uruchamiałem testów ani usług. Wyniki weryfikacji (PG 2 PASS, unit 93 PASS z 1 odznaczonym, UI/wrapper 6 PASS) przyjmuję z Outcome.
- Odznaczony test APK opisany jest uczciwie jako niewyjaśniona zależność kolejności lub środowiska. Nie dotyczy publication gate, nie oceniam go.
- Przekroczyłem limit: użyłem 26 wywołań narzędzi zamiast 24.
- Nie czytałem:
  - `schemas/source_replacement.py` w całości (tylko Grep), `test_source_retirement.py`, testów wrappera klienta i interakcji UI;
  - pierwszej części testu PG (`:1-286`);
  - treści funkcji `source_replacement_excluded_reviews_v1` ani `start_rebuild`.
- Treść planu i D-580 przyjąłem z zakresu podanego przez operatora.
