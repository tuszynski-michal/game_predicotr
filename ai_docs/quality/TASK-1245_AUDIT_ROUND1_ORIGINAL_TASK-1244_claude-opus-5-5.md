Werdykt: REVISE

# Audyt TASK-1244 — Nadzór postępu istniejącego treningu korekt

Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...041002571fc029eb66c82bae19bcad66ec4bfd63 oraz zmiany niezacommitowane, data 2026-11-17
Runda: 1
SHA pakietu: 1f5e751bb2a15538905d8e9c456bd189fc9bf7d1e25ccc7d4567d50a2da345cc
Otwarte P0: 0
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzano nową politykę `operator-progress-supervised-v1` w `RunBudget`, narzędzie owner do podglądu i zastosowania zgody (`prepare_supervision`/`verify_supervision` oraz `extend_grid_training_run.py`), obserwator i publikator aktywności, sposób użycia ich w supervisorze, w `ChildControl` i w `Watchdog`, zmiany indeksowania manifestu oraz ścieżkę API, klienta i panelu z wartością null. Rdzeń jest poprawny: null przetrwa serializację, starsze budżety zachowują swoją tożsamość, zgoda działa pod CAS i jest idempotentna, a obserwator odrzuca powtórki, poprzednie próby i uszkodzone pliki. Główne ryzyko polega na tym, że jedna kosztowna faza przed treningiem, czyli przygotowanie wycinków walidacyjnych, nie publikuje żadnej aktywności. Przy większym zbiorze VALIDATION nadzór może więc zatrzymać trening, który naprawdę pracuje. Brakuje też testów samego zatrzymania przez watchdog dziecka oraz odnawiania okna przez pomiary walidacyjne.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/worker/src/game_predictor_worker/images/grid_training_child.py:473` (oraz `services/worker/src/game_predictor_worker/images/grid_training_data.py:531-539`) — Po zindeksowaniu ról dziecko wywołuje `validation_crops(validation, recipe)`. Ta funkcja dla każdego zdjęcia VALIDATION wykonuje `photos.rgb(index)`, czyli `snapshot.frame`: odczyt bajtów, SHA, dekodowanie i sumę kontrolną pikseli, a potem wycina wszystkie plansze. Ani ta pętla, ani `CohortPhotos.rgb` nie wywołują `activity`. Następna aktywność pojawia się dopiero przy pomiarze bazowym w `train()` albo przy pierwszym kroku optymalizatora. Jeśli przygotowanie wycinków potrwa co najmniej 300 s, i supervisor (`grid_training_handler.py:870`), i watchdog dziecka (`grid_training_child.py:295`) zakończą rzeczywiście pracujący przebieg kodem `RUN_PROGRESS_STALLED`. To łamie kryterium „Genuine page/validation/step progress keeps supervision alive” i powtarza problem z kontekstu taska, czyli długie przygotowanie danych przed pierwszym krokiem GPU. Proponowana poprawka: przekazać callback aktywności do `validation_crops`, na przykład `activity(f"validation-crops-{n}", index + 1)` po każdym zdjęciu, i podobnie zabezpieczyć inne pętle po klatkach przed pierwszym krokiem. Należy dodać test, w którym przy nadzorowanym specu fazy wycinków publikują rosnące jednostki.

- [P1-2] `services/worker/tests/test_grid_progress_supervision.py:195` — Test `test_watchdog_keeps_supervisor_loss_and_stall_protection` nie sprawdza ochrony przed zastojem. Asertuje tylko brak wygaśnięcia przy postępie i kod `RUN_SUPERVISOR_LOST`. Żaden test nie potwierdza, że `Watchdog.expired()` zwraca `RUN_PROGRESS_STALLED` (`grid_training_child.py:295-296`) ani że `check()` zapisuje wtedy wynik `watchdog: True` i kończy proces. A to nowa, niezależna ścieżka zabicia procesu dziecka. Brakuje też testu, że zakończone pomiary walidacyjne (`grid_correction_consistency.py:155-157`) odnawiają okno. Kryterium akceptacji wprost wymienia odnawianie przez walidację i widoczne zakończenie przy zastoju. Proponowana poprawka: dopisać przypadek watchdoga z publikacją zatrzymaną na co najmniej 300 s i asercją kodu oraz zapisanego wyniku. Dopisać też test `CorrectionEvaluator.measure` z callbackiem, który sprawdza fazy `validation-N` z licznikami 1..n i to, że kolejne pomiary dostają nową fazę.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/training_core/run_activity.py:60-69` — Publikacja ma stałą nazwę pliku tymczasowego, nie robi fsync i ponawia tylko 3 razy po 10 ms. Istniejący `write_json_atomic` (`grid_training_child.py:92-113`) ma 6 rosnących opóźnień do około 0,47 s i filtruje kody WinError 5, 32 i 33. Plik czytają dwa obserwatory (supervisor i watchdog), a skaner antywirusowy może dłużej trzymać uchwyt. Wtedy `PermissionError` z kanału pomocniczego przerwie trening błędem `GRID_TRAINING_UNEXPECTED_ERROR`, choć nie jest to błąd treningu. Propozycja: przyjąć ten sam profil ponowień i nie przerywać pracy, gdy nie uda się zapisać jednego rekordu aktywności. Sam brak publikacji i tak wykryje okno 300 s.
- [P2-2] `services/worker/src/game_predictor_worker/images/grid_correction_consistency.py:160` — W zmienionej pętli `measure` dla każdego zdjęcia nadal jest `part.snapshot.manifest["gameId"]`, a to głęboka kopia całego manifestu. To samo dzieje się w `grid_training_data.py:125` przy każdym elemencie batcha z kontraktem wyjścia. Propozycja: wyliczyć `gameId` raz przed pętlą, tak jak zrobiono w `GridBoardDataset._sources`.
- [P2-3] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:932` — Gdy zastój zostanie wykryty, każdy wynik inny niż `exported` zostaje zastąpiony kodem `RUN_PROGRESS_STALLED`. Dotyczy to także `no_improvement` albo prawdziwego wyjątku treningu, który dziecko zapisało tuż przed wykryciem. Operator zobaczy wtedy błąd zastoju zamiast rzeczywistej przyczyny. Propozycja: nadpisywać kod tylko wtedy, gdy wyniku brak albo gdy wynik pochodzi z przerwania (`RUN_CANCELLED` lub watchdog).
- [P2-4] `services/worker/src/game_predictor_worker/training_core/grid_training_admission.py:557-558` oraz `grid_training_handler.py:276-278` — Ujemny upływ czasu ściennego przy odzyskiwaniu próby kończy się dla nowej polityki wyjątkiem `GRID_RUN_CLOCK_INVALID`. W starszych politykach wyczerpywał budżet. Kod nie ma etykiety w `REASON_LABELS`, a ponowienie trafi na ten sam błąd, dopóki zegar nie dogoni `charged_at`. Propozycja: dodać etykietę i test albo jawnie zaakceptować ryzyko.
- [P2-5] `services/worker/src/game_predictor_worker/images/grid_training_child.py:641` — Zakres przewidywał publikowanie aktywności po etapach eksportu, a `export_graphs`, `raw_parity` i kopiowanie checkpointu nic nie publikują. Dziś to krótkie operacje, a pomiar spójności w eksporcie publikuje przez ewaluator, więc ryzyko jest małe. Propozycja: dodać jeden znacznik `export` albo poprawić opis w zakresie i w D-617.
- [P2-6] `packages/admin-api-client/src/generated/sdk.gen.ts:1` — Według `git status` worktree ma zmienione także inne wygenerowane pliki klienta (`client.gen.ts`, `client/*.gen.ts`, `core/*.gen.ts`, `index.ts`, `sdk.gen.ts`), których nie ma w zamrożonym pakiecie. Propozycja: przed commitem upewnić się, że to tylko artefakt regeneracji, na przykład końce linii, i że nie trafi do commitu poza zakresem, albo dołączyć te pliki do audytu.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Polityka przetrwa serializację i nowy proces; ponad 7200 s nie wyczerpuje budżetu ani nie odnawia kroków | spełnione | `grid_training_admission.py:528-531,560-564,594-596`; `test_grid_progress_supervision.py:69` |
| Starsze budżety i tożsamości wire bez zmian | spełnione | `grid_training_handler.py:579-589` (pole `timePolicy` tylko dla nowej polityki); `grid_training_admission.py:567-571,503-516` |
| Rzeczywisty postęp stron, walidacji i kroków podtrzymuje nadzór; heartbeat, poprzednia próba, uszkodzone dane i powtórki nie; widoczne zatrzymanie przy zastoju, anulowaniu i utracie supervisora | niespełnione | P1-1 (`grid_training_child.py:473` bez aktywności), P1-2 (brak testu zastoju w watchdogu i walidacji); obserwator: `run_activity.py:88-113`, testy `:152,:177` |
| Podgląd i zastosowanie zgody zachowują tożsamość i stan, sprawdzają wiązania, odrzucają aktywne i zmienione joby, są idempotentne (także PostgreSQL) | spełnione statycznie | `run_progress_supervision.py:18-143`; `extend_grid_training_run.py:159-167,170-202`; `test_grid_run_budget_extension_postgres.py:26` (testu nie uruchamiano) |
| Indeksowanie bajtowo, etykietami i rolami równoważne, bez wielokrotnych kopii manifestu; bieżący przebieg monitorowany | częściowo spełnione | `grid_cohort_dataset.py:541-561`, `test_grid_cohort_dataset.py:171`; P2-2; monitorowania operacyjnego nie da się sprawdzić statycznie |
| Backend, OpenAPI, klient, wrapper i panel zgodne co do null | spełnione | `grid_training_cohorts.py:334`; `openapi.json:23022-23031`; `types.gen.ts:12744`; `grid-correction-learning-panel.tsx:1339-1345`; testy klienta i API |
| Zakresowe testy, lint, typy, dokumentacja, mapy i audyt Claude przed commitem | niezweryfikowane | Wyniki tylko z Outcome taska; audyt w tej rundzie: REVISE |
| Wynik i bezpieczne przekazanie przedstawione do akceptacji; bez aktywacji i nowego przebiegu | niezweryfikowane | Outcome taska opisuje zakończony przebieg bez zgody i bez aktywacji; status `in_progress` |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P1-2, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- `services/worker/tests/test_grid_progress_supervision.py`: `Watchdog` z nadzorowanym specem, bez nowej aktywności przez co najmniej 300 s, sprawdza `expired() == "RUN_PROGRESS_STALLED"` oraz to, że `check()` zapisuje wynik `{"status": "interrupted", "code": "RUN_PROGRESS_STALLED", "watchdog": true}` i wywołuje `exit_process(4)`. Uruchomienie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_progress_supervision.py`.
- Test `CorrectionEvaluator.measure` z callbackiem `activity`: fazy `validation-1`, `validation-2` i rosnące liczniki dla każdego zdjęcia.
- Test `validation_crops` (po poprawce P1-1): przy nadzorowanym przebiegu każde zdjęcie VALIDATION publikuje jednostkę, a obserwator nie zgłasza zastoju mimo upływu ponad 300 s przy ciągłym postępie.
- Test, że trwały `PermissionError` przy publikacji aktywności nie kończy treningu (P2-1).
- Test supervisora: anulowanie przy polityce postępu nadal daje `cancelled`, a wynik `no_improvement` zakończony tuż przed wykryciem zastoju zachowuje swój kod (P2-3).

## Zakres przeglądu i ograniczenia

Przeczytano pakiet (diff, nowe pliki `run_activity.py`, `run_progress_supervision.py`, `test_grid_progress_supervision.py`, plik taska) oraz kod potrzebny do oceny: `grid_training_admission.py` (`RunBudget`, `evaluate_admission`), `grid_training_handler.py` (`_set_budget`, `_recover_previous_attempt`, `_admit`, `_train`, `_supervise`), `grid_training_child.py` (`write_json_atomic`, `ChildControl`, `Watchdog`, `run`, `_train`, `_export`), `grid_cohort_dataset.py` (`sources`, `_frame`, `GridBoardDataset`), `grid_training_data.py` (`CohortPhotos`, `validation_crops`), `grid_correction_consistency.py`, skrypt `extend_grid_training_run.py` oraz panel Admin. Nie uruchamiano testów, lintu, mypy ani PostgreSQL. Wyniki „PASS” w Outcome są deklaracją wykonawcy i nie zostały tu potwierdzone. Nie sprawdzono, ile trwa przygotowanie wycinków walidacyjnych dla rzeczywistej kohorty `8d571c98-…`, więc P1-1 ocenia ryzyko na podstawie kodu, a nie pomiaru. Plików wygenerowanego klienta spoza pakietu (P2-6) nie porównywano bajtowo, bo przegląd był wyłącznie statyczny i nie korzystał z powłoki.