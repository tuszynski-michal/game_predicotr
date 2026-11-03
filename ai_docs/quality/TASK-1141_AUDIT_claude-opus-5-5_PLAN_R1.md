# Audyt TASK-1141 — Fizyczne usuwanie zastępowanego zdjęcia (PLAN)

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: d78eaf1c oraz zmiany niezacommitowane (plan/task/decision docs), data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano projekt D-583 (plan, task, D-583/D-579/D-580) i porównano go z kodem: CleanupService (kwarantanna, finalize, recovery), generic delete graph, guardy wymiany, retention guard GC, detach grid, mobile fence, FK z models.py i triggery 0174. Kierunek jest właściwy. Projekt nie używa generic graph, zostawia mały tombstone, korzysta z istniejącej kwarantanny i odpina grid. Główne ryzyko: projekt nie uzgadnia, które pliki chroni podgląd, a które `finalize`. `finalize` zatrzymuje całą kwarantannę, jeśli chroniony jest choć jeden plik. Do tego dochodzą nierozstrzygnięte realne zależności: niezakończony import starego zdjęcia, `symbol_reference_images` i aktywni konsumenci. W obecnym kształcie purge może skończyć się trwałym „pending”, czyli blanket retention, którego koordynator zabronił, albo zepsuć cudzy job.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `ai_docs/delivery/777A2_PHYSICAL_SOURCE_PURGE_PLAN_20261103.md:47,49` przeciw `services/api/src/game_predictor_api/storage/source_replacement_guards.py:157-187`, `storage/storage_gc_repository.py:110-113`, `application/cleanup.py:241-248`.
  - Problem 1: `finalize` sprawdza retencję całego receiptu naraz. Jeden chroniony plik zatrzymuje całą kwarantannę.
  - Problem 2: `referenced_artifact` dopasowuje każdy segment ścieżki wyglądający jak UUID do `document::text` wszystkich entries. Dopasowuje też `file_execution_key` i `source_selection_id` źródeł z `source_replacement_sources`.
  - Projekt wyłącza z tego tylko „compact purge refs i purged sources”. Legacy entries tej samej gry (777 A2 już je ma z TASK-1130/1131) i inne źródła z tego samego joba lub execution nadal dopasują ID joba lub execution w ścieżkach wycinków.
  - Podgląd liczy „shared” innym predykatem (`cleanup_repository.py:644-706`).
  - Skutek: podgląd obiecuje bajty, a `finalize` po cichu zostaje wiecznie pending z `SOURCE_REPLACEMENT_REFERENCED`.
  - Poprawka: jeden predykat retencji dla purge. Podgląd i `finalize` wywołują ten sam predykat dla tych samych ścieżek. Do kwarantanny trafiają wyłącznie ścieżki plikowe, które przeszły predykat. Dla kluczy purge `finalize` używa exact-path i prefiksu katalogu konsumenta. Pomija dopasowania po tożsamości, które należą wyłącznie do usuwanego źródła lub jego niewspółdzielonego execution.
  - Test: PG/FS z legacy entry tej samej gry i drugim zdjęciem tego samego joba. `finalize` ma zwrócić `True`, a liczba plików shared w podglądzie ma się zgadzać z tym, co zostaje na dysku.
- [P1-2] Plan `:43,47` przeciw `storage/cleanup_repository.py:690-706`. Oryginały joba w stanie `created/processing/waiting_for_review` (albo `managed_source_job_id`) są zachowywane, bo wznowiony job weryfikuje cały manifest oryginałów (TASK-1042). Job starego zdjęcia z innymi zdjęciami w review jest typowo `waiting_for_review`.
  - Projekt nie mówi, co wtedy. Z helperem oryginał nigdy nie zniknie. Bez helpera wznowienie cudzego joba padnie na brakującym pliku.
  - Poprawka: jawna reguła. Purge usuwa rekord pliku starego zdjęcia z manifestu/`image_import_job_files` tego joba, tak aby wznowienie go nie wymagało, z testem resume. Alternatywnie kodowany bloker `SOURCE_REPLACEMENT_PURGE_IMPORT_UNFINISHED` przed kwarantanną.
- [P1-3] Plan `:43`. Lista DELETE jest opisowa, a w `models.py` jest kilkanaście FK RESTRICT/CASCADE do sześciu efemerycznych rodziców (recognized_boards, image_review_items, image_symbol_review_cells, image_source_geometry_revisions, image_board_geometry_revisions, image_symbol_prediction_revisions).
  - Nienazwane w planie: `symbol_reference_images` (`models.py:324-334`, dane katalogu symboli gry z własnym `image_relative_path`), `image_symbol_review_bulk_targets` (`:3371-3380`), `image_board_search_candidates` (`:5694-5704`).
  - Generic graph usuwa `symbol_reference_images` (`cleanup_repository.py:945-948`). Tu oznaczałoby to usunięcie danych katalogu, a zachowanie bez decyzji daje FK fail już po kwarantannie.
  - Poprawka: jawna klasyfikacja delete/detach/blocker. Dla `symbol_reference_images` kodowany bloker przed kwarantanną albo odpięcie FK z zachowaniem pliku jako shared.
  - Test: tani test PG, który z `pg_constraint` wylicza wszystkie FK do tych tabel i sprawdza, że każdy jest sklasyfikowany w adapterze.
- [P1-4] Plan `:43,45`. Fence „nowe użycie purged odmawia” chroni tylko nowe użycie. Nie ma kodowanych blokerów dla zależności w toku:
  - `symbol_model_iterations` w `created/dataset_build/training/evaluating` z kohortą zawierającą źródło;
  - aktywne joby grid reinference/training lub kohorty z `live_source_image_id` źródła (`grid_reinference_retention.py:40-61` odpina linki, ale nie sprawdza aktywnych jobów);
  - `reviewer_work_assignments` na review źródła.
  - Wymóg z planu `:24` („Zależności wymagające rzeczywistego źródła mają jawny bloker”) jest więc niespełniony. Skutek: przerwany trening lub reinference czytający usunięte piksele.
  - Poprawka: zamknięta lista aktywnych konsumentów jako blokery przed kwarantanną, z kodami. Test jednego aktywnego iteration i jednego aktywnego joba grid.

### P2

- [P2-1] Plan `:41` przeciw `storage/mobile_source_proof.py:20,74-89`. Fence mobile/dataset czyta numery sekwencji z `source_replacement_retired`. Compact retired musi zachować ten sam klucz JSON. Po purge `LEFT JOIN recognized_boards` daje NULL, więc stary dataset odpada wyłącznie przez `affected`. Test: stary dataset z purged seq zostaje odrzucony.
- [P2-2] Plan `:49` przeciw `application/cleanup.py:259-276`. Przy niejednoznacznym commicie (zerwane połączenie po COMMIT) proces przywraca pliki, a baza ma stan purged. GET pokaże „finalized”, bo kwarantanna nie istnieje. Poprawka: finalized = brak kwarantanny i brak plików z receiptu w miejscu oryginalnym; w przeciwnym razie jawny stan i ponowna kwarantanna.
- [P2-3] Plan `:41` przeciw `alembic/versions/0174_source_replacement.py:136,221-229`. Dla źródła już wycofanego trybem legacy compact purge trafi na niezmienny PK retired, a pełny legacy document nadal chroni ścieżki. Wystarczy kodowana odmowa (np. `SOURCE_REPLACEMENT_LEGACY_RETIRED`) w preview/create i test; wsparcie to osobna decyzja operatora.
- [P2-4] `storage/cleanup_repository.py:1090-1096` usuwa stany review/projekcji całej gry. Adapter source-only nie może tego kopiować przy jednoczesnym imporcie nowych 9. Ma tylko inwalidować projekcję i polegać na triggerze liczników. Warto test z równoległym niezakończonym importem tej samej gry.
- [P2-5] `0174_source_replacement.py:157-168`. Rekordy `symbol_readability_decisions` są niezmienne i odwołują się do `cell_id` bez FK, więc po purge zostają z martwym `cell_id`. Policzyć je jako zachowane metadane z powodem w podglądzie i receipcie; manifest seq/cellIndex wystarcza do „Uzupełnij luki”.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| Manifest/request po fizycznym usunięciu, tombstone | niezweryfikowane (projekt OK) | plan:39-41 |
| Dedykowane pliki usunięte, shared/modele zostają | niespełnione w projekcie | P1-1, P1-2; plan:47 |
| Luki z rezerwacją, zwykły import | niezweryfikowane (projekt OK) | plan:39,51; P2-4 |
| Stare ID/SHA nie wraca do current | niezweryfikowane (projekt OK) | guards.py:42-62; plan:51 |
| Fresh preview/confirm, atomowość, replay, recovery | częściowo | plan:49; P2-2 |
| API/OpenAPI/client/UI zgodne | niezweryfikowane | plan:51,55 |
| Realne blokery zamiast blanket | niespełnione w projekcie | P1-3, P1-4 |
| Audyt bez P0/P1, outcome/close | niespełnione | ten raport |

## Listy zamknięte i otwarte

Zamknięte: brak (runda 1).

Otwarte: P1-1, P1-2, P1-3, P1-4, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `services/api/tests/integration/test_source_replacement_purge_postgres.py`:
  - legacy entry i sąsiednie zdjęcie tego samego joba, `finalize` zwraca True, a shared w podglądzie zgadza się ze stanem dysku (P1-1);
  - job starego zdjęcia w `waiting_for_review`, potem resume lub kodowany bloker (P1-2);
  - FK catalog z `pg_constraint` i `symbol_reference_images` (P1-3);
  - aktywny iteration lub job grid daje kodowany bloker przed kwarantanną (P1-4);
  - stary dataset odrzucony przez fence mobile (P2-1).
- `services/api/tests/test_source_replacement_cleanup_recovery.py`: niejednoznaczny commit pokazuje stan GET (P2-2).
- Komendy jak w planie `:59`. Planowane testy nie są dowodem PASS.

## Zakres przeglądu i ograniczenia

Przeczytano plan, task, D-583/D-580/D-579 i szablon. W kodzie: models.py 299-340 i 4143-4310 oraz grep FK i tabel; cleanup_repository.py 640-714 i 944-1105; source_replacement_guards.py 1-191; application/cleanup.py 110-305; grid_reinference_retention.py 1-62; mobile_source_proof.py 20-94; source_replacement_retirement.py 1-105; storage_gc_repository.py 85-119; 0174 96-255.

Nieprzeczytane z powodu limitu: main.py 969-1022, admission/binding, domena scope_digest, api/cleanup.py, schemas, panel UI, fixture PG. Nie zweryfikowano faktycznego układu katalogów wycinków, więc skala P1-1 jest wnioskiem z heurystyki, a nie z danych. Bez uruchamiania testów, komend i usług.
