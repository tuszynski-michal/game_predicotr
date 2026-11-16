# Audyt TASK-1235 — Naprawa timeoutu rejestracji kohorty siatek

Werdykt: PASS
Audytor: claude-opus-5-5, przegląd statyczny
Wykonawca: Codex (inna rodzina modeli), reasoning nieznany
Zakres: HEAD...656a966b5342d47254865849980c407f71c014aa oraz zmiany niezacommitowane, data 2026-11-16
Runda: 1
SHA pakietu: 960675034f23080ba28146b971ad14a7f87b287e55356aca8f536532551be255
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem migrację 0191 i moduł, który przepisuje dwie funkcje SQL: `recording_photo_context_data_v3` oraz `recording_photo_cohort_v4`. Porównałem je z pierwotnymi definicjami złożonymi z szablonów v1, v4 i v6–v10 oraz z wcześniejszymi przepisaniami 0188 i 0189. Przeczytałem też nowe testy, zmianę `schema_readiness` i dokumentację. Gałąź „pustego domknięcia” daje dokładnie ten sam wynik co oryginał dla źródła bez powiązań. Odtworzyłem to krok po kroku: `recording_closure_v1('{}')` zwraca `'{}'`, pętla zbiega w pierwszej iteracji, a `recording_proof_v1('{}')` nie zależy od danych. Cache stron w kohorcie v4 jest spójny z kolejnością planu. Każda iteracja pętli dochodzi do wywołania kontekstu, bo przed nim są tylko instrukcje `RAISE`, bez `CONTINUE`. W pętli nic nie jest zapisywane, więc odczyt stronami nie zmienia widoczności własnych zapisów transakcji. Główne ryzyko: istniejący zestaw regresji kohorty v4 nie został wykonany na nowych definicjach, a czas pełnej rejestracji nie ma jeszcze prognozy.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/tests/integration/test_recording_closure_performance_postgres.py:330` (zob. `ai_docs/tasks/1235-grid-cohort-closure-timeout.md:126`, `services/api/tests/integration/test_effective_grid_material_postgres.py:49`). Istniejący test materiału efektywnego przerywa się na wcześniejszej, historycznej asercji tekstu funkcji. Przez to jego dalsze przypadki dla kohorty v4 nie zostały uruchomione na definicjach po 0191. Chodzi o `GRID_COHORT_FULL_PHOTO_REQUIRED` (l. 278, 342), negatywną ścieżkę `newUseExcluded` z `GRID_CORRECTION_REGISTRY_CHANGED` (l. 295, 398) i `RECORDING_BINDING_INVALID` (l. 333). Nowy test sprawdza konflikt ról, nieaktualny dowód i ekspozycję diagnostyczną. Nie sprawdza natomiast negatywnego przypadku `newUseExcluded` ani `GRID_VALIDATION_SELECTION_EXPOSED` dla walidacji B na poziomie kohorty. Nie ma też asercji na wiersze `recording_photo_reservation_releases` po rejestracji, a `releaseUses` pochodzi teraz z kontekstów pobranych stronami w trybie preview=true. Statycznie te kontrole są nienaruszone: test jednostkowy porównuje wszystkie kody `RAISE`, a zgodność kontekstów sprawdzono dla obu trybów preview. Pomyłka w kluczu cache dałaby kontekst NULL i błąd dowodu przy udanej rejestracji 205 źródeł. Dlatego oceniam to jako P2. Proponowana poprawka: osobny commit naprawiający historyczną asercję (uwzględniający przepisania 0188/0189), a potem uruchomienie całego pliku na 0191. Alternatywnie: dopisać do nowego testu powyższe trzy przypadki oraz liczbę zwolnień rezerwacji dla źródeł 23 i 24.
- [P2-2] `services/api/src/game_predictor_api/storage/source_recording_closure_performance.py:100`. Brak wpisu w `closure_page` daje cicho `context = NULL`. W ścieżce `validate_cohort_use`, gdy `member.role = desired`, warunek `NOT (context->'allowedRoles' ? desired)` daje NULL i kontrola `RECORDING_ROLE_CONFLICT` jest pomijana. Dziś ten przypadek jest nieosiągalny: tablice id i flag mają ten sam porządek co pętla, a istnienie źródła sprawdza krok tożsamości. Proponowana poprawka: jawne `IF context IS NULL THEN RAISE 'GRID_CORRECTION_REGISTRY_CHANGED'` (z symetrycznym fragmentem do downgrade). Można też zaakceptować ryzyko i opisać je w `Outcome`. Druga drobna zmiana zachowania: konteksty całej strony liczą się przy pierwszej pozycji, czyli przed kontrolami tożsamości pozycji 2–200. Wyjątek z kontekstu późniejszej pozycji (np. `RECORDING_CLOSURE_UNRESOLVED`) może więc wyprzedzić wcześniejszy błąd 40001. Nie wpływa to na decyzję o dopuszczeniu i można to zaakceptować.
- [P2-3] `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md:16` (zob. `ai_docs/tasks/1235-grid-cohort-closure-timeout.md:70`). Na ścieżce `register_cohort_use` kontekst jest nadal liczony osobno dla każdego źródła w dwóch miejscach:
  - `recording_training_scope_v1` (`services/api/src/game_predictor_api/storage/source_recording_sql_v8.py:209`), dla około 469 użytych członków TRAIN/VALIDATION;
  - wyzwalacz `recording_validation_fence_v1` (`source_recording_sql_v8.py:185`), dla każdej z około 884 wstawianych pozycji.

  Oba korzystają z tańszej gałęzi v3 tylko dla źródeł bez powiązań. Źródła z historią użyć nadal przechodzą pełne domknięcie. Pomiar obejmuje wyłącznie odczyt 200 źródeł, więc zmieszczenie się w 300 s nie jest prognozowane. Uczciwie to odnotowano w `ai_docs/tasks/1235-grid-cohort-closure-timeout.md:140`. Proponowana poprawka: przed ponowieniem na żywych danych wykonać ograniczony pomiar tylko do odczytu `recording_training_scope_v1` dla tej kohorty i dopisać do dokumentacji architektury, że te dwa wywołania zostają per źródło. Można też zaakceptować ryzyko i zapisać wynik ponowienia jako bloker zgodnie z kryterium 5.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zmierzone wąskie gardło i poprawka są udokumentowane | spełnione | `ai_docs/tasks/1235-grid-cohort-closure-timeout.md:70`, `:126`; `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md:9`; zastrzeżenie w P2-3 |
| Kontrole źródła, aktualności, chronionych ról i celu walidacji działają nadal | spełnione | Statycznie: gałąź pustego domknięcia (`source_recording_closure_performance.py:48–63`) jest równoważna oryginałowi (`source_recording_sql_v6.py:40–133`, `source_recording_sql_v8.py:83–97`); wszystkie `RAISE` zachowane (`services/api/tests/test_recording_closure_performance.py`); testy PG: `test_recording_closure_performance_postgres.py:319–330`; luki w P2-1 |
| Docelowe regresje jednostkowe i PostgreSQL, jakość w zakresie i audyt wykonane | niezweryfikowane | Wyniki są deklaracją wykonawcy (`ai_docs/tasks/1235-grid-cohort-closure-timeout.md:113–131`); audytor nie uruchamiał testów; ten audyt jest rundą 1 |
| Upgrade/downgrade bazy i bezpieczeństwo funkcji sprawdzone | niezweryfikowane | Statycznie: `CREATE OR REPLACE` z `pg_get_functiondef` zachowuje OID, właściciela, ACL, `SECURITY DEFINER` i `search_path` (`source_recording_closure_performance.py:150–163`); kontrola wstępna obu definicji przed zapisem (`:137–147`, test jednostkowy); asercje metadanych i downgrade w `test_recording_closure_performance_postgres.py`; wykonania nie sprawdziłem |
| Ten sam rodzic przechodzi rejestrację albo zapisano konkretny bloker | niezweryfikowane | Etap po wdrożeniu; w `ai_docs/tasks/1235-grid-cohort-closure-timeout.md:138–141` zapisany jako niewykonany |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P2-1, P2-2, P2-3.

## Proponowane testy

- W `services/api/tests/integration/test_recording_closure_performance_postgres.py`: po udanej rejestracji `ready` sprawdzić `recording_photo_reservation_releases` dla tej kohorty. Oczekiwane są dokładnie zwolnienia źródeł 23 i 24, czyli niechronione użycia walidacyjne wcześniejszych kohort. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_recording_closure_performance_postgres.py`.
- W tym samym teście dodać trzy negatywne przypadki:
  - źródło z `newUseExcluded` i niezgodnym dowodem lub `used=true` na drugiej stronie, oczekiwany `GRID_CORRECTION_REGISTRY_CHANGED`;
  - VALIDATION z celem B na źródle z `selectionExposed` (indeks 23), oczekiwany `GRID_VALIDATION_SELECTION_EXPOSED`;
  - brak użyć po `bad_diagnostic`.
- Po osobnej naprawie historycznej asercji uruchomić cały `services/api/tests/integration/test_effective_grid_material_postgres.py` na głowie 0191.
- Ograniczony pomiar tylko do odczytu `SELECT public.recording_training_scope_v1(:game,:cohort)` dla kohorty `19a52a6c-…` przed ponowieniem na żywych danych (P2-3).

## Zakres przeglądu i ograniczenia

Przeczytałem: pakiet audytu (plik taska, diff, nowe pliki), `services/api/src/game_predictor_api/storage/source_recording_closure_performance.py`, migrację `0191_grid_cohort_linear_closure.py` oraz migracje 0186 i 0188–0190 z modułami `source_recording_source_limit.py` i `source_recording_unlimited_sources.py`. Sprawdziłem też szablony SQL `source_recording_sql_v1.py` (`recording_closure_v1`, `recording_proof_v1`), `_v4.py`, `_v6.py`, `_v7.py`, `_v8.py`, `_v9.py`, `_v10.py`, `_v11.py`, `_v12.py` i `_v13.py`, a także `source_recording_replacement_sql.py`. Poza tym przejrzałem fragmenty `test_effective_grid_material_postgres.py`, `_application_role_database.py`, `.agents/skills/task-close/SKILL.md` i reguły z `AGENTS.md` (sekcje 100–234).

Nie uruchamiałem żadnych testów, migracji ani zapytań. Nie sprawdziłem dosłownego tekstu `pg_get_functiondef` na żywej bazie, planów zapytań, czasów wykonania ani pliku `.runtime/task1235-baseline/read-parity.json`. Wyniki weryfikacji z `Outcome` traktuję jako deklarację wykonawcy. Zmian w `CODE_MAP*.md` nie oceniałem, bo są poza listą ścieżek pakietu. Skrócenie reguły utrzymania w `CURRENT_STATE.md` sprawdziłem pod kątem równoważności z procedurą `task-close` i nie znalazłem utraty wymagań.