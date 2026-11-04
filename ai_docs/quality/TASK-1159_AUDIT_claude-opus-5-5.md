Werdykt: PASS

**Audytor:** claude-opus-5-5/high · **Runda:** 2 (focused) · **Baza:** `c7ed8afe1913292d3fe5f7f23cb133f077ac84e2` (v1.7.563), zamrożony kod niezacommitowany · **Zakres:** tylko TASK-1159 (T5). Sprawdziłem zamknięcie R1 P1-1 i P2-1..5, kontrakt koordynatora oraz skutki zmienionego kodu i testów. Akceptacja ujścia T6 i partial-A należy do T6.

To przegląd wyłącznie statyczny przez Read/Grep. Przeczytałem indeks R2 i wszystkie cztery części pakietu. Celowo sprawdziłem też w worktree `storage/grid_recognition_status.py:35-60`, wywołujących `routed_/read_game_recognition_status`, klasy błędów domeny, budowę `optionsKey` w panelu i producentów `actualRaster`. Niczego nie zmieniałem. Nie uruchamiałem testów, buildów, PG, usług ani sieci. Wyniki wykonawcy (PG 1 PASS/34.39s, Python 42, Admin 6, Reviewer 1, SDK 6) traktuję jako deklaracje.

## P0
Brak.

## P1
Brak otwartych. **P1-1 zamknięte.** Uzasadnienie:

- **Zależność w `main.py:2480-2498`:**
  - Sesja katalogu pozostaje zwykłą, niepowiązaną `Session(database_engine)`.
  - `status_reader` dostaje `session_factory`, czyli `GameStorageSession` na roli aplikacji, a nie sesję katalogu.
  - Innych wywołujących nie ma: jedynym produkcyjnym wywołaniem jest `main.py:2491`.
- **Projekcja w `storage/grid_recognition_status.py:39-43`:**
  - Ma osobną transakcję `game_storage_scope(game)`.
  - `SET TRANSACTION READ ONLY` idzie przez połączenie przed jakimkolwiek dostępem ORM.
  - Potem następuje `GameStorageRouter().bind(..., READ)`. Bind z READ wykonuje tylko SELECT i `set_config(..., true)`, bez FOR SHARE i blokady doradczej (część 3, `bind`, `_resolve`, `_set_transaction_scope`), więc nie koliduje z READ ONLY.
  - Wyjątek i rollback zostają w tej osobnej sesji, więc katalog commituje się niezależnie.
- **Degradacja (`:44-60`):**
  - Błędy domeny (`GridModelRegistryError`, `NeuralGridProposalError`, `NeuralOperationPinError`, `GameStorageRoutingError`) mają atrybut `code` i dają `unavailable` z `capabilities=null`.
  - Błędy połączenia i puli (`OperationalError`/`InterfaceError`/`PoolTimeout`) oraz `DataError` mapują się na typowane kody.
  - `DBAPIError` daje `unavailable` tylko dla SQLSTATE 42P01, 42703, 3F000 i 42501.
  - Błąd składni (42601), naruszenie READ ONLY (25006) oraz `TypeError`/`ValueError`/`RuntimeError` przechodzą dalej. Test `test_grid_recognition_status_projection.py` sprawdza to przez tożsamość wyjątku (`caught.value is error`).
- **Test PG `integration/test_grid_recognition_status_postgres.py`:**
  - Używa niezmienionego `create_app`, roli LOGIN aplikacji i gry `game_data_v2`/`active` (asercja `:620`).
  - Działa prawdziwy raport v5 z sidecarem i `load_frozen_assessment` (asercja `cohort_reads` niepusta, `automatic=evaluation=qualified`).
  - Obserwator kursora asertywnie sprawdza `transaction_read_only=on`, ustawienie gry i `current_schema()=game_data_v2`. `AssertionError` w zdarzeniu nie jest łapany przez projekcję, więc dałby 500 i test by padł. To prawdziwa bramka, a nie dekoracja.
  - Sesja katalogu jest sprawdzana jako niepowiązana zarówno przy instrukcji, jak i przy commicie.
  - Błąd SQL jest prawdziwym 42P01, tylko w zapytaniu projekcji. Wynik: 200, ta sama wersja, `unavailable` z `capabilities=null`. Globalny GET daje 200, a po wyłączeniu błędu odczyt wraca do `qualified`.
  - Brak konfiguracji V3 daje 200 z `GRID_MODEL_FORMAT_UNSUPPORTED`.
  - Nie podmieniono `status_reader`, `session.get` ani czytnika kohorty.
- **Pion kontraktu:**
  - Schemat ma `capabilities: ... | None` (`schemas/grid_recognition_status.py:413`).
  - Zgadzają się z nim delta OpenAPI `anyOf null`, `types.gen.ts`, test żądania SDK i fallback Admin (`grid-model-assignment-summary.tsx`, „Układ modelu nie został odczytany” i stan „chwilowo niedostępny”), z testem interakcji.

## P2 (otwarte, nieblokujące, maks. 5)

1. **Zduplikowany klucz opcji legacy.**
   - **Gdzie:** `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:258-265` wobec `:148-156`.
   - **Skutek:** literał `JSON.stringify({trainingMode:'grid-only',historicalCohorts:[]})` powiela budowę `optionsKey`. Jeśli dojdzie nowe pole, start legacy znów zablokuje się po odświeżeniu. Taka awaria jest bezpieczna (fail-closed), a obecny test `legacy refresh restores…` by ją wykrył.
   - **Poprawka:** wspólna funkcja `optionsKeyFor({trainingMode, historicalCohorts, purposeAware})` używana w obu miejscach.
2. **Kontrakt `sequenceNumber` w indeksie v2 istnieje tylko po stronie konsumenta.**
   - **Gdzie:** `services/worker/src/game_predictor_worker/images/comparison_input_diagnostics.py:103-107`. Grep: w `scripts/` i `services/worker` nie ma producenta wpisów z `actualRaster`.
   - **Skutek:** przyszły producent bez tego pola da wyłącznie `unavailable`. To bezpieczne, ale niejawne.
   - **Poprawka:** udokumentować wymagane pola wpisu indeksu v2 (`sourceId`, `positionIndex`, `sequenceNumber`, `modelVersionId`, `record`, `actualRaster`) przy rendererze lub w VISION_LAB. Bez zmiany logiki.

## Zamknięcie uwag R1

| ID | Stan | Dowód statyczny |
|---|---|---|
| P1-1 | **Zamknięte** | Patrz wyżej: osobna sesja READ ONLY routowana na grę, katalog niepowiązany, wąska degradacja, realny test PG przez `main` z obserwacją schematu i READ ONLY |
| P2-1 | **Zamknięte** | `board-geometry-correction-workspace.tsx:441-453`: zawsze neutralny tekst „Zapisana geometria nie potwierdza ludzkiej weryfikacji… zapisz ją ręcznie”. Test z `approvedGeometryRevision === geometryRevision === 3` sprawdza brak „ma zapisane zatwierdzenie” |
| P2-2 | **Zamknięte** | Dla `redetect`: `comparison_input_diagnostics.py:97-99` daje `stage_label="wejście ekranu"`, a `:123-129` daje `margin=None`. Szablon pokazuje „nie dotyczy”. Testy: Python `screen` (margines `None`), VM rendera bez `0.15`. v1 bez zmian |
| P2-3 | **Zamknięte** | Wymagany typ `int` i równość z bieżącą planszą. Brak pola lub zmiana sekwencji z 101 na 102 daje `DIAGNOSTIC_TARGET_SEQUENCE_MISMATCH` i nie zapisuje pliku PNG. Wartość 101 w indeksie jest literałem niezależnym od planszy, więc to nie jest tautologia |
| P2-4 | **Zamknięte** | Osobny `previewSequence`. `refresh()` unieważnia podgląd, a podgląd już nie unieważnia `readSequence`. Jest strażnik `refreshInFlight` i `disabled={…\|\|refreshing}` w obu przyciskach. Odświeżenie legacy przywraca klucz grid-only. Oba testy interakcji odtwarzają regresję (odroczona lista i przebieg, `FRESH_RUN`, 0 wywołań podglądu, start odblokowany po refresh) |
| P2-5 | **Zamknięte** | Polecenie sprzed T5 bez nowych kluczy jest zapisane jako job. Dwa prawdziwe HTTP `POST` przez router z `exclude` dają 200 i identyczne odpowiedzi. `_preview` jest podmienione na `pytest.fail`; `start()` zwraca istniejący job przed `_preview` (część 3, `start:1002-1009`), więc ta podmiana jest skuteczna. Bez zmian zostają `input_key`, SHA payloadu, `previewSha256` i budżet, a liczba jobów jest ta sama |
| R1 „checkpoint grid-only A” | **Zamknięte (statycznie)** | `_train` dla v4 wymusza `corrections`. Walidacja to `CohortPhotos(snapshot,"VALIDATION")` przez `GridBoardDataset` z `validation_purpose="A"`, który pomija B, a liczniki pochodzą z `purposeCounts["VALIDATION-A"]`. Strażnik `frame` odrzuca B przed odczytem bajtów. `correction_evaluator` dostaje tylko te części |

## Pokrycie kryteriów

| Kryterium | Ocena |
|---|---|
| Current vs frozen vs człowiek; brak kalibracji nie blokuje | Tak. P1-1 zamknięte, a `unavailable` nie zmienia przypisania ani wersji |
| Compact/loading/error/retry, GET-only, odrzucanie nieaktualnych odpowiedzi | Tak. Wyścig z P2-4 zamknięty |
| Ręczny zapis/CAS/retry; legacy exact retry | Tak. Retry przez HTTP potwierdzone testem |
| API → OpenAPI → SDK → wrapper → test | Tak, z nullowalnym `capabilities` |
| Diagnostyka v1 bez zmian; v2 strict | Tak. Dodane wiązanie sekwencji i etap ekranu |
| HTML: pięć widoków, viewport ≠ input, margines | Tak. Dla ekranu margines „nie dotyczy” |
| Scoped kontrole, dokumentacja i niezależny audyt | Audyt: ten PASS. Task-close i commit nadal czekają na roota |

## Listy identyfikatorów
- **Zamknięte:**
  - z R1: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5, pytanie o checkpoint grid-only A;
  - zamknięte już w R1 i bez regresji: niepodnoszenie frozen pinu, alias `foreign_scope`, `geometry_saved` przez właściciela/CAS/czytnik, pełne zdjęcie 9/9, v2 bez pożyczania wejścia innego slotu, historia v4.
- **Otwarte (nieblokujące):** R2-P2-1 (klucz opcji legacy), R2-P2-2 (dokumentacja indeksu v2).

## Proponowane testy (opcjonalne)
1. Wspólny helper klucza opcji i asercja równości klucza legacy z `optionsKey` dla grid-only.
2. Test jednostkowy, w którym wyjątek pada wewnątrz `bind`/odczytu, a nie z fabryki sesji: 25006 i 42601 przechodzą dalej, 42501 daje `unavailable`. Obecnie PG pokrywa tylko 42P01 i brak konfiguracji.

## Ograniczenia
- Przegląd wyłącznie statyczny, bez moich zmian i bez uruchamiania jakichkolwiek testów, buildów, PG czy usług. Czasy i wyniki PASS pochodzą z deklaracji wykonawcy.
- Nie oglądałem HTML, zdjęć, danych operatora ani artefaktów spoza pakietu.
- Izolowane buildy Admin i Reviewer nie są standardowym PASS workspace, co wykonawca sam zastrzega.
- Ponowna zaplanowana weryfikacja T6 (ujście obserwacji, partial-A) jest poza zakresem.
