# Audyt TASK-0950 - Przejęcie sekwencji przez zdjęcie zastępcze i sprzątanie starego zdjęcia

Werdykt: REVISE
Audytor: Codex, gpt-6-astra, high
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...a7f9fe27d9a726dc220117d274e4fa52aa8eb273 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawki zamykają trzy znaleziska poprzedniej rundy i mają odpowiadające im testy regresyjne. Wspólna reguła własności, migracja oraz raport API i Adminu realizują podstawowy scenariusz taska. Pozostaje błąd współbieżności: sprzątanie może zakleszczyć równoległe zapisy geometrii dwóch zdjęć.

## Znaleziska

### P0

- [P0-4] `services/api/src/game_predictor_api/storage/pending_sequence_ownership.py:377` — Przeliczanie bramek blokuje inne zdjęcia, gdy transakcja już trzyma blokadę własnego źródła. Sortowanie samych `candidates` nie zapewnia wspólnej kolejności wszystkich blokad.

  Przykład: zdjęcia A i B mają stan `geometry_incomplete` oraz zakres 100–108. Dwa równoległe żądania rozwiązują slot A/100 i B/101. Każde blokuje inną sekwencję i własne zdjęcie (`virtual_grid_geometry_repository.py:407`, `:417`). Następnie zapytanie kandydatów wskazuje drugie zdjęcie, ponieważ jego zakres obejmuje przejmowaną sekwencję. Transakcja A czeka na B, a B na A przy `FOR UPDATE` w `image_geometry_completeness_state_repository.py:172`. PostgreSQL przerywa jedno żądanie z powodu zakleszczenia.

  Należy zapewnić wspólny protokół blokowania całego zbioru źródeł objętych przejęciem, zanim transakcja zablokuje własne zdjęcie, albo zastosować wcześniejszą wspólną serializację tych operacji. Naprawa powinna obejmować API i workera oraz test dwóch równoległych transakcji.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| B przejmuje odrzucone S, zachowuje osiem dobrych plansz A i zapisuje alternatywy | spełnione | Scenariusz i asercje: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:153`; ocena statyczna. |
| Slot A przechodzi do `superseded`, bramka jest przeliczana, dobre plansze materializowane | niespełnione | Wariant sekwencyjny pokrywa `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:196`; współbieżne wykonanie może zostać przerwane — P0-4. |
| Ta sama checksuma zachowuje dotychczasową regułę | spełnione | Wariant `same-photo`: `services/api/tests/integration/test_image_batch_store.py:2961`; dotychczasowe asercje własności zachowane. |
| Raport importu pokazuje zastąpione i pominięte sekwencje | spełnione | HTTP: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:244`; UI: `apps/admin/src/features/imports/geometry-completeness-section.tsx:418`. |
| Przejęcie zachowuje komórki `outside` i historię zatwierdzeń | spełnione | Testy regresyjne: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:517` oraz `:570`; ocena statyczna. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1** — Chroniony właściciel innego zdjęcia przechodzi do ścieżki zapisującej pominięcie. Dowód: `services/worker/src/game_predictor_worker/images/pipeline_store.py:454`; test: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:435`.
- **P0-2** — Przejęcie dopuszcza niepełną historię cropów i przywraca dostępność nowych komórek. Dowód: `services/api/src/game_predictor_api/domain/image_symbol_reviews.py:853`, `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:3102`; test: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:517`.
- **P0-3** — Proweniencja zatwierdzenia jest wybierana według tożsamości cropa, zamiast numeru rewizji. Dowód: `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:2758`; test: `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:570`.

Otwarte: **P0-4**.

## Proponowane testy

W `services/api/tests/integration/test_replacement_photo_takeover_postgres.py` dodać test współbieżności:

- Dwa niekompletne zdjęcia z nakładającymi się zakresami, różne rozwiązywane sekwencje i dwie niezależne sesje PostgreSQL.
- Wymusić przeplot przed sprzątaniem bramek. Sprawdzić zakończenie obu operacji bez zakleszczenia, pojedynczego właściciela każdej sekwencji i poprawne stany bramek.
- Dodać wariant równoległego importu workera oraz ręcznego rozwiązania slotu.

Komenda w środowisku testowym opisanym w tasku:

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_replacement_photo_takeover_postgres.py services/api/tests/test_lateral_lock_order.py -q
```

## Zakres przeglądu i ograniczenia

Przeczytano brief, poprzedni raport, poprawki, odpowiednie fragmenty dokumentacji oraz implementację własności, ochrony lateral, synchronizacji komórek, bramki, migracji, kontraktu i UI. Prześledzono kolejność blokad w API i workerze. `git diff --check` zakończył się bez błędów; zgłosił ostrzeżenia LF/CRLF.

Nie uruchamiano testów, migracji ani usług. Wyniki testów zapisane w `Outcome` pozostają deklaracjami wykonawcy. P0-4 wynika z analizy kolejności blokad; nie odtwarzano go na bazie.