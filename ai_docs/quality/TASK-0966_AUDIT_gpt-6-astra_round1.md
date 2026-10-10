# Audyt TASK-0966 — Migracja 0154, status `reverted` i cofnięcie korekty slotu odroczonego

Werdykt: REVISE
Audytor: Codex (`gpt-6-astra`, `high` — oznaczenie briefu)
Wykonawca: `claude-opus-5-5`, `high`
Zakres: HEAD...3879af42cc96fca5f8526e99d030700945ff801d oraz zmiany niezacommitowane, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani migracji.

## Streszczenie

Zbadano migrację, cofnięcie slotu, blokady, historię, filtrowanie rewizji `reverted` oraz testy. Implementacja obejmuje podstawowy scenariusz odtworzenia stanu, lecz lista korekt nie obsługuje historycznych rewizji bez geometrii źródła i jest podatna na równoległe usunięcie korekty. Współbieżne powtórzenie cofnięcia może również zwrócić konflikt zamiast zapisanego wyniku; brakuje części wymaganych testów odmowy na poziomie repozytorium.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:441` — **Historyczna korekta może przerwać odczyt całej listy.** `_LIST_SQL` obejmuje zdarzenia `geometry_saved` także dla historycznych rewizji `legacy_file`. Takie rewizje pozostają po migracji `0135` i mogą mieć `source_geometry_revision_id = NULL`. `list_recent` przekazuje je bezpośrednio do `_evaluate`, które zgłasza `GEOMETRY_CORRECTION_NOT_FOUND`, gdy nie znajduje rewizji źródła. Obsługa `NOT_SUPPORTED` w `_require_correction` nie chroni tej ścieżki. Należy zwracać wpis z odpowiednim powodem blokady, zachowując pozostałe korekty na liście. Dodać test importu zawierającego historyczną korektę i poprawny zapis slotu.

- [P0-2] `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:491` — **Idempotencja ma lukę między pierwszym odczytem audytu a odczytem korekty.** Drugie żądanie może odczytać brak audytu w linii 480, po czym pierwsze żądanie zatwierdzi cofnięcie i usunie rewizję planszy. `_require_correction` znajdzie wtedy audyt po rewizji i zwróci `GEOMETRY_REVERT_NOT_LATEST`, mimo identycznego klucza idempotencji. Ponowna kontrola w linii 543 nie zostanie osiągnięta. Należy ponownie sprawdzić audyt po kluczu przed odmową wynikającą ze zniknięcia korekty albo serializować żądania przed tymi odczytami. Dodać test dwóch transakcji z kontrolowanym momentem zatwierdzenia.

- [P0-3] `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:440` — **Równoległe cofnięcie może zakończyć listowanie przez `AssertionError`.** W domyślnej izolacji `READ COMMITTED` korekta może zostać usunięta po pobraniu `revision_ids`, lecz przed `_correction`. Kod zakłada, że nadal istnieje, chociaż metoda nie zapewnia wspólnej migawki odczytów. Należy zapewnić spójny snapshot albo obsłużyć zniknięcie wpisu bez przerwania listy. Dodać test listowania równolegle z cofnięciem.

### P1

- [P1-1] `services/api/tests/test_geometry_correction_reverts.py:73` — **Test każdego kodu blokady nie sprawdza odmowy operacji bez zapisu.** Test parametryczny ustawia gotowe wartości logiczne w `RevertEligibilityFacts`; nie weryfikuje pozyskania faktów przez SQL ani zachowania transakcji. Brak integracyjnego pokrycia `RESOLVED`, `SEQUENCE_OWNERSHIP`, `PINNED`, `REOPENED_RESOLUTION` i `NOT_SUPPORTED` potwierdza `ai_docs/tasks/0966-geometry-correction-revert-pending-slot.md:267`. Szczególnie wymagane przypadki zastąpienia pozycji, przejęcia komórek i kohorty pozostają niesprawdzone. Należy uzupełnić testy repozytorium z porównaniem stanu przed odmową i po niej; dla przypadku A sprawdzić obecny kontrakt odmowy, bez implementowania TASK-0967.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Upgrade/downgrade 0154 i odmowa utraty historii | niezweryfikowane | Strażnik: `services/api/alembic/versions/0154_geometry_correction_revert.py:322`. Test cyklu: `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py:508`. Wyniki wykonawcy nie były odtwarzane. |
| Odtworzenie slotu, grafu danych, sąsiadów, liczników, wyszukiwarki, joba i bramki | spełnione | Statycznie pokryte implementacją i porównaniem migawek: `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py:260`, asercja w linii 342. |
| Powrót slotu do `correction` z poprzednią propozycją | spełnione | Odczyt kolejki i kontrola poprzedniej rewizji: `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py:364`. |
| Każdy kod blokady ma test odmowy bez zapisu | niespełnione | P1-1; `ai_docs/tasks/0966-geometry-correction-revert-pending-slot.md:267`. |
| Ponowny zapis identycznej geometrii tworzy nową rewizję | spełnione | Filtr deduplikacji: `services/api/src/game_predictor_api/storage/image_geometry_v2_repository.py:143`; scenariusz ponownego zapisu w teście integracyjnym. |
| Powtórzenie cofnięcia zwraca zapisany wynik; stary zapis jest odrzucany | niespełnione | Sekwencyjne powtórzenia mają pokrycie; współbieżny przypadek narusza kontrakt — P0-2. |
| Dotychczasowe testy kompletności i korekty przechodzą bez zmian asercji | niezweryfikowane | Diff zachowuje asercje; wykonawca deklaruje 42 passed w `ai_docs/tasks/0966-geometry-correction-revert-pending-slot.md:236`. Audyt nie uruchamiał testów. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3, P1-1.

## Proponowane testy

W `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py` uzupełnić:

- Listę zawierającą historyczną korektę `legacy_file` oraz bieżącą korektę slotu.
- Powtórzenie tego samego cofnięcia, gdy pierwsza transakcja zatwierdza zmiany między odczytem klucza a odczytem rewizji.
- Cofnięcie zatwierdzone między pobraniem identyfikatorów listy a odczytem szczegółów.
- Brakujące odmowy wskazane w P1-1, z porównaniem stanu bazy.

Po uzupełnieniu uruchomić na bazie `*_test`, z limitem 120 sekund:

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py -q
```

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, właściwe fragmenty planu i dokumentacji, migrację 0154, nowe moduły domeny, aplikacji i repozytorium, modele, manifest v7, zmiany zapytań oraz testy. Sprawdzono także zachowanie historycznych rewizji i domyślne granice sesji potrzebne do oceny znalezisk.

Wyniki testów, lint i typecheck pochodzą z deklaracji wykonawcy w `Outcome`; audyt nie potwierdza ich niezależnym uruchomieniem. Nie wykonywano zmian plików, operacji na bazie ani czynności poza zakresem statycznego przeglądu.