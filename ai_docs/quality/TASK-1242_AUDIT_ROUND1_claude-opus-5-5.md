# Audyt TASK-1242 — Resume-compatible grid preparation throughput

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...8c1d2f00b06dbc4de474cc87e85e4a8bef99acb9 oraz zmiany niezacommitowane, data 2026-11-17
Runda: 1
SHA pakietu: 9fc801759f1da37c9d200a2feb73eddf196a831d745e68a76a66985d85679679
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem wewnętrzne grupowanie materializacji w `execute`, liczniki pochodne w `summary.materializationProgressV1` i dispatch w procesie nadrzędnym. Przejrzałem też nowe testy jednostkowe i test PostgreSQL. Bajty stron, kursory, CAS rewizji, odtwarzanie receiptów i fallback liczników do pełnego skanu wyglądają poprawnie. Pomaga w tym trigger niezmienności nagłówka: każde zapisanie wymusza `revision=OLD.revision+1`, a autoflush przed kolejną stroną to zapewnia. Główne ryzyko to wydłużenie czasu trzymania jawnej blokady `FOR UPDATE` na nagłówku kohorty i ogrodzeń transakcyjnych z czasu jednej strony do około 8 s plus jednej strony. Ten czas przekracza 5-sekundowe `lock_timeout` używane przez równoległe zapisy. Tej interakcji nie przeanalizowano i nie przetestowano.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/application/grid_training_cohort_commands.py:597` (pętla grupy do linii 606) w powiązaniu z `grid_training_cohort_commands.py:531` i `services/api/src/game_predictor_api/application/grid_correction_learning.py:1015`.
  - **Mechanizm:** pierwsza strona grupy wykonuje `repo.cohort(game, row.id, lock=True)`, czyli `SELECT … FOR UPDATE`. Ta blokada wiersza nagłówka trwa do COMMIT całej grupy, więc obejmuje kopiowanie i publikację stron 2..N, łącznie do około 8 s plus czas jednej strony. Wcześniej blokada obejmowała tylko krótki końcowy etap jednej strony.
  - **Konflikt z triggerem:** trigger `grid_cohort_notice_v1` (`services/api/alembic/versions/0163_grid_training_cohorts.py:208`) wstawia `currentness_notice` do `grid_training_cohort_events`. Ta tabela ma FK do nagłówka kohorty (`0163_grid_training_cohorts.py:238`, `:278`), a sprawdzenie FK bierze `FOR KEY SHARE`, które koliduje z `FOR UPDATE`. W efekcie każda edycja geometrii, boardów lub review dotykająca członka aktywnej kohorty (tabele z `0163_grid_training_cohorts.py:31`) czeka na koniec grupy.
  - **Ogrodzenia:** grupa dłużej trzyma też współdzielone ogrodzenia (`game_storage_routing.py:292`, `grid_cohort_asset_retention.py:76`). Ścieżki ekskluzywne z `lock_timeout` 5 s (np. `storage/grid_cohort_asset_retention.py:72`, `storage/source_purge_retention.py:18`, `storage/grid_cell_content.py:101`) czekają wtedy dłużej niż ich limit.
  - **Skutek:** rodzic uruchamia grupy jedna po drugiej, więc nagłówek jest zablokowany przez większość czasu przygotowania. Zapisy operatora i retencja mogą wtedy stale kończyć się `55P03` albo mieć wielosekundowe opóźnienia. Takie zachowanie nie występowało przy pojedynczych stronach, a pakiet nie zawiera ani analizy, ani testu tej interakcji.
  - **Poprawka:** jedna z opcji:
    - brać blokadę jako `FOR NO KEY UPDATE` (`with_for_update(key_share=True)`), które nie koliduje z FK `KEY SHARE`, i uzasadnić, że nadal serializuje zapisy nagłówka;
    - albo skrócić plaster czasu znacznie poniżej najkrótszego kolidującego `lock_timeout` (np. 2–3 s).

    W obu przypadkach trzeba dodać test PostgreSQL. Test powinien sprawdzić, że wstawienie zdarzenia z FK do kohorty z `lock_timeout='5s'` w drugiej sesji kończy się sukcesem w trakcie wielostronicowej grupy, albo jawnie udokumentować i zaakceptować nowe okno blokady.

### P2

- [P2-1] `ai_docs/tasks/1242-grid-preparation-throughput.md:144` — Outcome twierdzi, że pełne odczyty nagłówka występują raz na grupę.
  - **Stan faktyczny:** `_materialize` w `grid_training_cohort_commands.py:531` przy każdej stronie odczytuje nagłówek z `populate_existing=True`. Kolumna `document` (około 20 MB) nie jest odroczona (`grid_training_cohort_models.py:38`), więc dokument jest ponownie dekodowany na każdej stronie.
  - **Skutek:** redukcja odczytów nagłówka wynosi mniej więcej od 4 na stronę do 1 + 3/N na stronę, a nie do 1/N. Kryterium „reduces” pozostaje spełnione, ale deklaracja „up to 20x fewer” jest prawdziwa tylko dla receiptów i zdarzeń.
  - **Poprawka:** skorygować opis. Opcjonalnie pomijać ponowny odczyt z blokadą, gdy wiersz jest już zablokowany w tej transakcji, przy zachowaniu CAS po stronie pamięci.
- [P2-2] `services/api/tests/integration/test_grid_preparation_throughput_postgres.py:51` — w teście PostgreSQL wszystkie źródła są `used: False`, a limity mają wartość 0.
  - **Skutek:** porównanie liczników z pełnym skanem (`:159`) zachodzi dla samych zer, więc nie dowodzi parytetu na niezerowych danych w prawdziwej bazie. Parytet niezerowy pokrywają tylko testy jednostkowe na atrapach i niezałączony odczyt operatorski (2057 stron).
  - **Poprawka:** w teście PostgreSQL dodać kilku członków `used: True` z niezerowymi limitami, albo dołączyć skrypt parytetu jako dowód.
- [P2-3] `services/api/src/game_predictor_api/application/grid_correction_learning.py:1014` — żaden test w pakiecie nie potwierdza, że rodzic przekazuje `materialization_pages=20` tylko dla `materialize-page`, a pozostałe rodzaje poleceń wywołuje bez tego argumentu.
  - **Skutek:** regresja dispatchu, np. utrata grupowania albo błędne przekazanie argumentu do `prepare-page`, przeszłaby niezauważona. Deklarowane 38 regresji rodzica nie wskazuje takiego przypadku.
  - **Poprawka:** dodać asercję na argumentach wywołania `service.command` w istniejącym teście handlera rodzica.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Stare strony i receipty oraz ich bajty pozostają ważne; zwykłe żądania bez zmian | spełnione (statycznie) | `grid_training_cohort_commands.py:577-580` (domyślnie 1), `grid_training_cohorts.py:85-91`, `test_grid_preparation_throughput.py` `test_ordinary_command_keeps_one_physical_page`, integracja `:166` |
| Ta sama kohorta kontynuuje od zapisanego kursora po świeżym procesie; brak duplikatów | spełnione (statycznie, testu nie uruchamiano) | `test_grid_preparation_throughput_postgres.py:139-147`, `:175-212`; kursor z `grid_training_cohort_repository.py:216-229` |
| Grupowanie redukuje pełne odczyty nagłówka i przygotowania oraz receipty na źródło | spełnione częściowo (receipty i zdarzenia 1 na grupę; odczyty nagłówka nadal 1 na stronę, P2-1) | `grid_training_cohort_commands.py:597-620`, `:531` |
| Liczniki pochodne równe pełnej agregacji stron, także dla starych kohort i po restarcie | spełnione (statycznie; parytet w PostgreSQL trywialny, P2-2) | `grid_cohort_materialization_progress.py:24-66`, `grid_training_cohort_repository.py:249-253`, `:270-295`, testy `test_legacy_counts_bootstrap_once…`, `test_invalid_or_stale…`, `test_bootstrap_excludes…` |
| Rollback, nieaktualne rewizje, utrata odpowiedzi i zmienione lub usunięte wejście zachowują istniejące zabezpieczenia | spełnione co do semantyki; dostępność zapisów równoległych zagrożona (P1-1) | `grid_training_cohort_commands.py:403-420`, `:532`, `:588-589`; integracja `:118-138`, `:148-151` |
| Testy celowane, lint i typecheck w zakresie, mapy, dokumentacja i niezależny review przechodzą | niespełnione (review: REVISE) | ten raport; wyników testów nie weryfikowano |
| Naprawa gotowa do przeglądu; wdrożenie i weryfikacja tego samego rodzica raportowane osobno | niezweryfikowane (poza zakresem audytu statycznego) | `ai_docs/tasks/1242-grid-preparation-throughput.md`, sekcja „Not completed” |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P2-1, P2-2, P2-3.

## Proponowane testy

- `services/api/tests/integration/test_grid_preparation_throughput_postgres.py`:
  - **Scenariusz:** w trakcie grupy z `materialization_pages=4`, spowolnionej atrapą `copy_source` lub `publish_json`, druga sesja z `SET LOCAL lock_timeout='5s'` wstawia `GridTrainingCohortEventModel` dla tej kohorty. Wstawienie wyzwala FK `KEY SHARE`.
  - **Oczekiwanie:** wstawienie się powiedzie, albo test jawnie udokumentuje maksymalne opóźnienie.
  - **Komenda:** `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_preparation_throughput_postgres.py`.
- Ten sam plik: dodać członków `used: True` z niezerowymi `eligible*` i porównać `summary_view` z licznikami i bez nich w prawdziwej bazie.
- Istniejący test handlera rodzica dla `grid_correction_learning.py`: asercja, że dla `materialize-page` wywołanie zawiera `materialization_pages=20`, a dla `prepare-page` i `freeze` nie zawiera tego argumentu.

## Zakres przeglądu i ograniczenia

**Przeczytane pliki i fragmenty:**
- zamrożony pakiet (task, diff, nowe pliki i testy);
- `grid_training_cohort_commands.py` (`_materialize`, `execute`, importy);
- cały `grid_training_cohort_repository.py`;
- dispatch rodzica w `grid_correction_learning.py:930-1040`;
- kolumny modelu kohorty;
- triggery niezmienności i powiadomień oraz FK w `0163_grid_training_cohorts.py`, a także trigger znaczników w `0166_grid_model_evaluation.py`;
- `acquire_cohort_asset_guard` i ogrodzenie zapisu w `game_storage_routing.py`;
- przegląd grep ustawień `lock_timeout` w `services/api/src`.

**Ograniczenia:**
- Nie uruchamiałem testów, lintu, mypy ani PostgreSQL. Deklarowane wyniki (80 PASS, parytet na 2057 stronach, czasy) przyjmuję jako niezweryfikowane.
- Nie sprawdzałem, które konkretne ścieżki zapisu recenzenta ustawiają `lock_timeout`, ani rzeczywistych czasów pojedynczej strony u operatora. Skala P1-1 wymaga więc potwierdzenia pomiarem albo testem.
- Nie widziałem kodu operatorskiego checkoutu z TASK-1230.