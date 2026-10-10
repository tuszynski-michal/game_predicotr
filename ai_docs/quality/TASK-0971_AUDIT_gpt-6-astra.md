# Audyt TASK-0971 — Przejęcie sekwencji przez zdjęcie zastępcze i sprzątanie starego zdjęcia

Werdykt: REVISE
Audytor: Codex, gpt-6-astra, high
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...a7f9fe27d9a726dc220117d274e4fa52aa8eb273 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 4

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Reguła przejęcia, sprzątanie odrzuconych slotów, zachowanie historii komórek i raport importu mają pokrycie w kodzie oraz testach. Poprawiono wcześniejsze odwrócenie kolejności blokady własności i blokady sekwencji przy decyzjach komórek. Pozostały jednak dwa cykle blokad: z dzierżawą joba oraz z cofnięciem odrzucenia planszy. Oba mogą przerwać transakcję importu lub decyzję użytkownika.

## Znaleziska

### P0

- **[P0-6] `services/api/src/game_predictor_api/storage/image_review_repository.py:1758` — Blokada własności jest pobierana przed pośrednią blokadą joba, przeciwnie do kolejności workera.**

  Po `ensure_sequence_ownership_lock` metoda `save_resolution` wywołuje `get_item(..., for_update=True)`. Zapytanie w `image_review_repository.py:709` stosuje nieograniczone `FOR UPDATE`, a `_base_query` dołącza `JobModel` (`:2055`). W rezultacie blokowany jest również wiersz joba. Ten sam problem występuje w `_supersede_pending_sequence_occurrences` (`:1401`, `:1409`).

  Worker najpierw blokuje job w `_require_candidate_lease` (`services/worker/src/game_predictor_worker/images/pipeline_store.py:1297`), następnie czeka na własność gry (`:413`). Możliwy przeplot: decyzja użytkownika trzyma blokadę własności; worker tego samego importu blokuje job i czeka na własność; decyzja przez `get_item` czeka na job. Wystarczy przetwarzanie kolejnego zdjęcia tego importu, nawet z innymi sekwencjami. PostgreSQL przerwie jedną transakcję.

  Należy ograniczyć `FOR UPDATE OF` do rzeczywiście zmienianych tabel, wyłączając job z zapytań wykonywanych po pobraniu blokady własności. Dodać regresję z decyzją planszy i projekcją kolejnego zdjęcia **tego samego joba**; obecny test współbieżności używa różnych jobów.

- **[P0-7] `services/api/src/game_predictor_api/storage/pending_sequence_ownership.py:377` — Przeliczanie wielu zdjęć nadal może zakleszczyć się z cofnięciem odrzucenia planszy.**

  Pętla przelicza i materializuje kolejnych kandydatów w jednej transakcji. Materializacja pierwszego zdjęcia pobiera blokadę `ImageSymbolReviewStateModel` przez `_synchronize` (`services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:2505`, `:3214`), a następna iteracja blokuje kolejne źródło.

  Tymczasem `_revert_item` w `services/api/src/game_predictor_api/storage/geometry_rejection_revert.py:514` pomija blokadę własności: blokuje sekwencję, źródło (`:517`), a następnie stan liczników przez `restore_cells_of_reopened_board` (`:583`).

  Przykładowy przeplot: zdjęcia C i A mają odrzuconą pozycję S; A ma dodatkowo odrzuconą planszę T. Import B przejmuje S i materializuje C, blokując stan liczników. Równoległe cofnięcie odrzucenia T blokuje źródło A i czeka na ten stan. Import przechodzi następnie do A i czeka na jego źródło. Operacje dotyczą różnych sekwencji, więc blokady sekwencji nie zapobiegają cyklowi.

  Należy objąć `_revert_item` protokołem własności przed blokadami sekwencji i źródła. Analogicznie sprawdzić `_revert_board_revision`, które również zaczyna bez tej blokady (`services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:1109`). Dodać test przejęcia z materializacją kilku kandydatów równolegle z cofnięciem odrzucenia.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| B przejmuje odrzucone S, zachowuje osiem dobrych plansz A i zapisuje alternatywy | spełnione | Scenariusz i asercje w `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:173`; ocena statyczna. |
| Slot A przechodzi do `superseded`, bramka jest przeliczana i dobre plansze materializowane | spełnione | `services/api/src/game_predictor_api/storage/pending_sequence_ownership.py:370`; ocena wariantu sekwencyjnego. |
| Ta sama checksuma zachowuje dotychczasową regułę | spełnione | Wariant `same-photo` w `services/api/tests/integration/test_image_batch_store.py:2961`. |
| Raport importu pokazuje zastąpione i pominięte sekwencje | spełnione | HTTP i liczniki w `services/api/tests/integration/test_replacement_photo_takeover_postgres.py:245`; UI w `apps/admin/src/features/imports/geometry-completeness-section.tsx:418`. |
| Przejęcia i istniejące decyzje zachowują poprawność przy współbieżności | niespełnione | Cykle blokad opisane w P0-6 i P0-7. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1** — Chroniony właściciel innego zdjęcia zachowuje własność, a import zapisuje pominięcie. Dowód: `services/worker/src/game_predictor_worker/images/pipeline_store.py:461`.
- **P0-2** — Przejęcie dopuszcza niepełną historię cropów i przywraca dostępność komórek. Dowód: `services/api/src/game_predictor_api/domain/image_symbol_reviews.py:853`, `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:3133`.
- **P0-3** — Proweniencja zatwierdzenia jest rozpoznawana po tożsamości cropa. Dowód: `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:2789`.
- **P0-4** — Dwa przejęcia pobierają wspólną blokadę przed blokadami źródeł. Dowód: `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py:411`.
- **P0-5** — Decyzja komórki pobiera blokadę własności przed sekwencją, a wywołania zagnieżdżone zachowują jej tryb. Dowód: `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py:1226`, `services/api/src/game_predictor_api/storage/sequence_ownership_lock.py:108`. Zamknięcie dotyczy poprzednio opisanego cyklu; pozostałe cykle opisano osobno.

Otwarte: **P0-6, P0-7**.

## Proponowane testy

W `services/api/tests/integration/test_replacement_photo_takeover_postgres.py` dodać scenariusze z niezależnymi sesjami i kontrolowanymi barierami:

- Decyzja planszy podczas projekcji kolejnego zdjęcia tego samego joba: worker trzyma dzierżawę, decyzja trzyma własność gry.
- Przejęcie S z materializacją pierwszego zdjęcia i późniejszym przeliczeniem drugiego, równolegle z cofnięciem odrzucenia innej planszy drugiego zdjęcia.
- Analogiczny przeplot dla cofnięcia korekty istniejącej planszy.

Sprawdzić zakończenie obu transakcji bez zakleszczenia oraz spójność właścicieli, historii i liczników.

Komenda w środowisku testowym opisanym w tasku:

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_replacement_photo_takeover_postgres.py services/api/tests/test_sequence_ownership_lock.py services/api/tests/test_lateral_lock_order.py -q
```

## Zakres przeglądu i ograniczenia

Sprawdzono brief, historię uwag, odpowiednie fragmenty dokumentacji, regułę własności, sprzątanie bramek, synchronizację komórek, migrację, raport API, klienta, UI oraz testy. Prześledzono blokady importu, decyzji komórek, rozstrzygnięć i cofnięć.

`git diff --check` nie zgłosił błędów. Nie uruchamiano testów, migracji ani usług. Wyniki testów w `Outcome` są deklaracjami wykonawcy; opisane przeploty wynikają z analizy statycznej i nie były odtwarzane na bazie.