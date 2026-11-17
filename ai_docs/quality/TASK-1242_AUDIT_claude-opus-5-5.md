# Audyt TASK-1242 — Resume-compatible grid preparation throughput

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...8c1d2f00b06dbc4de474cc87e85e4a8bef99acb9 oraz zmiany niezacommitowane, data 2026-11-17
Runda: 2
SHA pakietu: c5aa481aff6c02984bd454bc3256e9ace5a2c5d32ad40e124232d2242d2818bc
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W rundzie 2 sprawdziłem poprawki do znalezisk z rundy 1. Przejrzałem nową blokadę `lock_materialization` (`FOR NO KEY UPDATE`), skrócony do 2 s plaster czasu grupy, poprawiony opis wydajności, niezerowe liczniki w teście PostgreSQL i test dispatchu rodzica.

Blokada nagłówka nie koliduje już z `FOR KEY SHARE` przy sprawdzaniu FK zdarzeń `currentness_notice`. Nagłówek kohorty ma unikalny tylko klucz główny `(game_id,id)`. Trigger niezmienności zabrania zmiany `document` i kluczy, więc także końcowy `UPDATE` nagłówka bierze blokadę NO KEY UPDATE. Zapisy nagłówka pozostają serializowane względem innych blokad `FOR UPDATE` (np. `cancel`). CAS sprawdza rewizję w bazie i w pamięci.

Zostaje ryzyko rezydualne, które wykonawca jawnie opisał. Współdzielone ogrodzenia zapisu i ogrodzenie zasobów kohorty są trzymane do około 2 s dłużej niż czas jednej strony. Dodaję jedno nowe znalezisko P2 dotyczące odporności na brak klucza `roles`.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-4] `services/api/src/game_predictor_api/storage/grid_training_cohort_repository.py:267` w powiązaniu z `services/api/src/game_predictor_api/storage/grid_cohort_materialization_progress.py:12`
  - **Problem:** awaryjna ścieżka `summary_view` wywołuje `empty_counts(row.summary)`, która czyta `summary["roles"]` bez wartości domyślnej. Ta sama funkcja w `:260` zakłada brak `roles` i podstawia `[]`. Poprzedni kod budował liczniki z `result["roles"]`, więc dla `summary` bez `roles` zwracał puste liczniki zamiast wyjątku.
  - **Skutek:** nagłówek z `summary = {}` (domyślna wartość kolumny w `0163_grid_training_cohorts.py:250`) skończyłby się teraz `KeyError` w `view`, czyli błędem 500 przy odczycie kohorty. Ryzyko jest niskie. Jedyna ścieżka tworzenia w `grid_training_cohort_commands.py:201` zapisuje `{"roles": [], "reasonCounts": {}}`, a `refresh_summary` zawsze ustawia role.
  - **Poprawka:** w `empty_counts` użyć `summary.get("roles", [])`. Można też zaakceptować ryzyko i odnotować, że każde istniejące `summary` zawiera `roles`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Stare strony i receipty oraz ich bajty pozostają ważne; zwykłe żądania bez zmian | spełnione (statycznie) | `grid_training_cohort_commands.py:577-580` (domyślnie 1 strona), `grid_training_cohorts.py:85-91`, `test_grid_preparation_throughput.py:163`, `:208`; integracja `:248` i porównanie `old_path.read_bytes()` |
| Ta sama kohorta kontynuuje od zapisanego kursora po świeżym procesie; brak duplikatów | spełnione (statycznie, testu nie uruchamiano) | `test_grid_preparation_throughput_postgres.py:208-248`; kursor z `grid_training_cohort_repository.py:232-245`; klucz idempotencji rodzica z rewizji `grid_correction_learning.py:1000` |
| Grupowanie redukuje pełne odczyty nagłówka i przygotowania oraz receipty na źródło | spełnione (statycznie) | `grid_training_cohort_repository.py:168-182` (projekcja samej rewizji, bez `document`), `grid_training_cohort_commands.py:590`, `:597-606`, `:618-620`; `test_grid_preparation_throughput.py:402` |
| Liczniki pochodne równe pełnej agregacji stron, także dla starych kohort i po restarcie | spełnione (statycznie) | `grid_cohort_materialization_progress.py:24-66`, `grid_training_cohort_repository.py:265-269`, `:286-311`; integracja `:57`, `:195` i porównanie bez `materializationProgressV1`; testy jednostkowe `:55`, `:80`, `:110`, `:118` |
| Rollback, nieaktualne rewizje, utrata odpowiedzi i zmienione lub usunięte wejście zachowują istniejące zabezpieczenia | spełnione (statycznie) | `grid_training_cohort_commands.py:403-427`, `:531-532`, `:588-589`; równoległe zdarzenie z FK przy `lock_timeout='5s'`: integracja `:156-173` |
| Testy celowane, lint i typecheck w zakresie, mapy, dokumentacja i niezależny review przechodzą | spełnione w części review (ten raport: PASS); wyniki testów, lintu i typów niezweryfikowane | ten raport; deklaracje w `ai_docs/tasks/1242-grid-preparation-throughput.md` |
| Naprawa gotowa do przeglądu; wdrożenie i weryfikacja tego samego rodzica raportowane osobno | niezweryfikowane (poza zakresem audytu statycznego) | sekcja „Not completed” w pliku taska |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P2-1, P2-2, P2-3.

Dowody zamknięcia:

- **P1-1:** `grid_training_cohort_repository.py:171-175` używa `with_for_update(key_share=True)`, czyli `FOR NO KEY UPDATE`. Ta blokada nie koliduje z `FOR KEY SHARE` przy sprawdzaniu FK z `0163_grid_training_cohorts.py:278`. Trigger nagłówka (`0163_grid_training_cohorts.py:144-148`) zabrania zmiany kluczy i `document`, więc `UPDATE` nie podnosi blokady do `FOR UPDATE`. Trigger `grid_cohort_notice_mark` (`0166_grid_model_evaluation.py:30-35`) nie dotyka nagłówka. Plaster czasu skrócono do 2 s (`grid_training_cohort_commands.py:601`). Test PostgreSQL w `test_grid_preparation_throughput_postgres.py:156-173` dowodzi wstawienia zdarzenia w trakcie grupy.
- **P2-1:** blokada strony nie przeładowuje już dokumentu (`grid_training_cohort_repository.py:172`). Opis poprawiono w `ai_docs/tasks/1242-grid-preparation-throughput.md:145` i `:189`.
- **P2-2:** niezerowe limity i liczniki w `test_grid_preparation_throughput_postgres.py:57` i `:195`.
- **P2-3:** test dispatchu w `test_grid_preparation_throughput.py:364`.

Otwarte: P2-4.

## Proponowane testy

- `services/api/tests/test_grid_preparation_throughput.py`: przypadek, w którym `summary_view` dostaje `row.summary = {}` i oczekuje pustej listy ról bez wyjątku (zabezpiecza P2-4). Komenda: `.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_preparation_throughput.py`.
- Opcjonalnie `services/api/tests/integration/test_grid_preparation_throughput_postgres.py`: druga sesja z `pg_advisory_xact_lock` (ekskluzywne ogrodzenie zasobów kohorty) i `lock_timeout='5s'` w trakcie grupy z 4 stronami. Test zmierzyłby rzeczywisty czas oczekiwania jako dowód dla zaakceptowanego ryzyka rezydualnego. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_preparation_throughput_postgres.py`.

## Zakres przeglądu i ograniczenia

**Przeczytane pliki i fragmenty:**

- zamrożony pakiet rundy 2 (task, diff, nowe pliki, testy, raport i receipt rundy 1);
- `grid_training_cohort_commands.py:380-621`;
- `grid_training_cohort_repository.py:1-313`;
- dispatch rodzica w `grid_correction_learning.py:960-1030`;
- triggery niezmienności, powiadomień i definicje FK w `0163_grid_training_cohorts.py:100-339`;
- trigger znaczników w `0166_grid_model_evaluation.py`;
- `0192_grid_cohort_header_cache.py`;
- `acquire_cohort_asset_guard` w `grid_cohort_asset_retention.py`;
- stałe `COMMAND_SECONDS=300` i `MATERIALIZATION_PAGE_SIZE=5`.

Grepem sprawdziłem też, że w kodzie i SQL żadna inna ścieżka nie blokuje nagłówka kohorty jawnym `FOR SHARE` ani `FOR UPDATE`.

**Ograniczenia:**

- Nie uruchamiałem testów, lintu, mypy, PostgreSQL ani skryptów parytetu. Deklarowane wyniki (85 PASS, parytet na 2057 stronach, czasy) przyjmuję jako niezweryfikowane.
- Nie widziałem operatorskiego checkoutu z TASK-1230, więc nie sprawdziłem tam kompatybilności poprawki ani odczytów przygotowanego artefaktu.
- Wydłużenie trzymania ogrodzeń zapisu i zasobów o co najwyżej około 2 s ponad czas jednej strony oceniam statycznie jako akceptowalne ryzyko rezydualne, opisane przez wykonawcę. Nie zmierzyłem go.