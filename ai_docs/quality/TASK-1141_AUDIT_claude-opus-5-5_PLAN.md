# Audyt TASK-1141: fizyczne usuwanie zastępowanego zdjęcia (PLAN)

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: d78eaf1c oraz niezacommitowane dokumenty planu/taska/decyzji. Oceniam tylko sekcję „Jedyna korekta projektu po audycie PLAN R1” (`ai_docs/delivery/777A2_PHYSICAL_SOURCE_PURGE_PLAN_20261103.md:61-75`). Data: 2026-11-03.
Runda: 2

Przegląd statyczny. Audytor nie zmieniał plików, nie uruchamiał testów ani usług.

## Streszczenie

Korekta zamyka wszystkie cztery P1 z rundy 1 i wymagane P2-2. Pozostałe P2 (P2-1, P2-3, P2-4, P2-5) mają jawne rozstrzygnięcie. Zakresu nie rozszerzono.

Sprawdziłem w kodzie trzy rzeczy:
- Lista DELETE/DETACH z P1-3 obejmuje każdy FK zadeklarowany w `models.py` do sześciu usuwanych rodziców.
- Klucz `prior.sequence_numbers` z P2-1 jest dokładnie tym kluczem, który czyta fence mobile (`mobile_source_proof.py:19`).
- Ścieżka `finalize`/`recover` pozwala na purge-specific dispatcher.

Zostały dwie drobne nieścisłości do domknięcia przy implementacji (P2 niżej). Nie blokują przejścia do kodu.

## Znaleziska

### P0

Brak.

### P1

Brak otwartych.

Rozliczenie P1 z rundy 1:

- **[P1-1] zamknięte.** Jeden predykat `SourcePurgeRetention` liczy exact paths i prefiksy konsumentów. Podgląd i purge-specific finalize/recovery używają tej samej listy. Heurystyka UUID/SHA zostaje wyłączona dla purge.
  - Do kwarantanny trafiają tylko pliki bez zewnętrznego konsumenta. Dlatego whole-receipt fence w `finalize` (`application/cleanup.py:232-248`) przestaje być blanket retention. „Pending” oznacza teraz wyłącznie nową, rzeczywistą referencję, co jest poprawne.
  - Test z drugim zdjęciem tego samego joba i legacy entry odpowiada propozycji z R1.
- **[P1-2] zamknięte.** Wybrano wariant kodowanego blokera `SOURCE_REPLACEMENT_PURGE_IMPORT_UNFINISHED` przed przeniesieniem plików. Manifest i resume importera zostają bez zmian, co było jedną z dwóch opcji R1. Test obejmuje brak mutacji, potem settled i fresh preview.
- **[P1-3] zamknięte.** Każdy FK do `recognized_boards`, `image_review_items`, `image_symbol_review_cells`, `image_source_geometry_revisions` i `image_symbol_prediction_revisions` w `models.py` trafia do klasyfikacji.
  - DELETE: `models.py:1930`, `2485/2495`, `2645`, `2691`, `3145-3217`, `3372-3380`, `3433`, `3488-3504`, `3557/3560`, `3793/3796`, `4806/4810`, `5559/5562`, `5622/5625`, `5695/5704`.
  - Relacje wewnętrzne: `2413`, `2552`, `2959-3010`, w tym zerowanie wskaźnika prediction revision w `2994`.
  - DETACH: `325/328` (`symbol_reference_images`), `4186/4190` i `4266-4284` (frozen cohort).
  - `image_board_geometry_revisions` nie ma w modelach FK przychodzących. Ewentualne FK spoza modeli wyłapie zaplanowany test `pg_constraint`.
  - `symbol_reference_images` zostaje odpięte z guardem insertu, a plik pozostaje exact shared. Katalog symboli nie jest kasowany, zgodnie z R1.
- **[P1-4] zamknięte, z korektą listy statusów w R2-P2-1.** Zamknięta lista trzech kodowanych blokerów jest sprawdzana pod ownership przed side effects. Historia nie blokuje. Pokrywa to wszystkie trzy kategorie konsumentów z R1.

### P2

- **[R2-P2-1] Lista statusów aktywnej iteracji pomija `trained`.**
  - Plan `:71` wymienia `created/dataset_build/training/evaluating`.
  - Constraint `models.py:4306-4307` ma też nieterminalny `trained`, czyli stan między treningiem a ewaluacją. Iteracja w `trained` przeszłaby przez bloker, a ewaluacja ruszyłaby już po purge.
  - Poprawka: zdefiniować „aktywny” jako dopełnienie stanów terminalnych `candidate_ready/rejected/failed/cancelled`, a nie jako listę dodatnią. Do testu P1-4 dodać przypadek `trained`.
- **[R2-P2-2] P2-2 nie wskazuje, co wyzwala recovery stanu `recovery_pending`.**
  - Startowe `recover()` (`application/cleanup.py:259-276`) przechodzi tylko po istniejących katalogach kwarantanny. Po przywróceniu plików katalogu już nie ma, więc tego przypadku samo nie znajdzie.
  - Sformułowanie „recovery tej samej komendy” oznacza, że gałąź „exact receipt/key-body sprawdzany pierwszy” (plan `:49`) nie może zwrócić zapisanego wyniku. Musi przejść do ponownej kwarantanny.
  - Implementacja musi zapewnić dwie rzeczy:
    1. GET entry w stanie `recovery_pending` zwraca tożsamość komendy potrzebną do replay, również w nowej sesji UI bez zapamiętanego klucza.
    2. Stan GET porównuje pliki na dysku z zapisanym proof (path + size + SHA), a nie z samym istnieniem ścieżki. Plik o innej treści pod tą samą ścieżką ma dać jawny `RECOVERY_REQUIRED`, a nie fałszywe pending.
  - Test z planu (`pending → recovery → realny brak plików`) wystarczy, jeśli przechodzi przez tę gałąź replay.

Uwagi implementacyjne bez rangi:

- **Dispatcher predykatu.** `_retention_guard(paths)` dostaje dziś tylko ścieżki (`cleanup.py:232-234`). Dispatcher według `operationType` potrzebuje klucza operacji. Zmiana sygnatury nie może zmienić zachowania generic GC/recovery, a ich istniejące testy mają przejść bez zmian.
- **Praktyczny skutek P1-2.** Job starego zdjęcia jest często w `waiting_for_review` z powodu jego własnych, nierozstrzygniętych review. Komunikat UI powinien wskazać istniejącą ścieżkę domknięcia tego importu. To kwestia czytelności, nie nowa akcja.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| Manifest/request po fizycznym usunięciu, tombstone | niezweryfikowane (projekt OK) | plan:39-41, 75 (P2-1 zgodne z `mobile_source_proof.py:19`) |
| Dedykowane pliki usunięte, shared/modele zostają | projekt spełnia | plan:65, 67, 69 |
| Luki z rezerwacją, zwykły import | niezweryfikowane (projekt OK) | plan:39, 75 (P2-4) |
| Stare ID/SHA nie wraca do current | niezweryfikowane (projekt OK) | plan:51, 75 (P2-3) |
| Fresh preview/confirm, atomowość, replay, recovery | projekt spełnia, z R2-P2-2 | plan:49, 73 |
| API/OpenAPI/client/UI zgodne | niezweryfikowane | plan:51, 55 |
| Realne blokery zamiast blanket | projekt spełnia, z R2-P2-1 | plan:67, 69, 71 |
| Audyt bez P0/P1, outcome/close | projekt: brak P0/P1; finał wymaga osobnego audytu | ten raport |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P1-2, P1-3, P1-4, P2-1, P2-2 (z R2-P2-2 jako wymogiem implementacyjnym), P2-3, P2-4, P2-5.

Otwarte: R2-P2-1, R2-P2-2.

## Proponowane testy

Testy z planu `:65-73` uzupełnione o dwa przypadki:

- `services/api/tests/integration/test_source_replacement_purge_postgres.py`: iteracja w statusie `trained` daje `SOURCE_REPLACEMENT_PURGE_MODEL_BUSY` bez mutacji (R2-P2-1).
- `services/api/tests/test_source_replacement_cleanup_recovery.py`: nowy store/sesja, GET `recovery_pending` z tożsamością komendy, replay przez gałąź exact receipt, ponowna kwarantanna, `finalized`. Osobno plik o innym SHA pod ścieżką z proof daje `RECOVERY_REQUIRED` bez usuwania (R2-P2-2).

Planowane testy nie są dowodem PASS. Żaden nie został wykonany.

## Zakres przeglądu i ograniczenia

Przeczytano:
- raport R1;
- plan `:30-82`;
- grep FK w `models.py` do sześciu rodziców wraz z mapą `__tablename__`;
- constraint statusów `symbol_model_iterations` (`models.py:4300-4339`);
- grep statusów i lease w `models.py`;
- `application/cleanup.py:200-309`;
- grep klucza w `mobile_source_proof.py`.

Wykonano 10 odczytów z limitu 12. Taska 1141 i D-583 nie czytałem ponownie, bo koordynator potwierdził ich aktualność.

Nie czytałem: worker resume, `cleanup_repository.py` (retention helpers), `main.py` (recovery zależności), modelu grid jobs i `reviewer_work_assignments` poza lease. Pokrycie FK zadeklarowanych tylko w migracjach Alembic nie jest zweryfikowane i zależy od zaplanowanego testu `pg_constraint`.
