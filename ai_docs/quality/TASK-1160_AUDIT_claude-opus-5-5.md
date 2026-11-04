# Audyt TASK-1160 (T6): odbiór pełnego przepływu wykrywania plansz

Werdykt: PASS

- **Audytor:** claude-opus-5-5/high
- **Runda:** 1
- **Baza:** `bc00e2a736a6f5a51a9d2bd590d96d280a95d23a` (v1.7.564), gałąź `codex/full-board-detection`. Do tego dochodzą niezacommitowane zmiany T6 z drzewa roboczego.
- **Zakres:**
  - `services/worker/tests/test_full_board_acceptance.py` (nowy),
  - `services/api/tests/integration/test_validation_purpose_migration_postgres.py` (rozszerzony),
  - `ai_docs/tasks/1160-full-board-acceptance.md`,
  - `ai_docs/quality/TASK-1160_VERIFICATION.md`,
  - sekcja T6 planu i §6 instrukcji operatora.
- **Kontekst produktu (tylko celowane fragmenty):**
  - `grid_model_evaluation_handler.py:369-540`,
  - `full_board_runtime_evidence.py`,
  - `full_board_calibration_run.py:252-305`,
  - `full_board_calibration_evidence.py:71-111`,
  - `0181_validation_purposes.py:62-80`.

**Charakter przeglądu:** wyłącznie statyczny (Read/Grep). Nic nie zmieniałem, nie uruchamiałem testów, usług, bazy ani sieci. Nie otwierałem zdjęć, prywatnych raportów HTML, sekretów ani modeli.

## P0
Brak.

## P1
Brak.

## P2 (5)

1. **Restart sprawdzany tylko od końcowego checkpointu.**
   - **Gdzie:** `services/worker/tests/test_full_board_acceptance.py:189`. Restart startuje z `context.states[-1]`, czyli stanu po zapisie raportu.
   - **Co to pokrywa:** utratę odpowiedzi po zakończeniu. Dzięki pętli w `grid_model_evaluation_handler.py:406-409` wszystkie jednostki są pomijane.
   - **Czego nie pokrywa:** restartu w trakcie przebiegu v4, na przykład po jednostce VALIDATION, a przed `calibration.finish()` (`grid_model_evaluation_handler.py:450-454`). Nie sprawdza też, że po restarcie nie zmieniają się bajty pliku detail.
   - **Skutek:** wymaganie planu „Restart/lost response” (T3,T6) dla ścieżki v4 i kalibracji opiera się tu na wcześniejszych dowodach T3/T4, a nie na tym teście.
   - **Minimalna poprawka:** dodać parametryzowany restart od checkpointu pośredniego, na przykład pierwszego stanu z `{game}:VALIDATION` w `units` i bez `automaticCalibration`. Asercje: brak dodatkowych wywołań silnika dla ukończonych jednostek, identyczne SHA raportu i identyczne bajty detail/final.

2. **Nieprzetestowana trzecia przesłanka blokady downgrade 0181.**
   - **Gdzie:** `services/api/tests/integration/test_validation_purpose_migration_postgres.py:136,156`. Test sprawdza blokadę po historii kohorty v4 i po `validation_purpose='B'`.
   - **Luka:** warunek `diagnostic_comparison` (`0181_validation_purposes.py:71-72`) nie jest sprawdzany osobno. Po `_diagnostic_registration` (`:188`) nie ma już próby downgrade, a wcześniejsze użycie B i tak blokowałoby downgrade.
   - **Skutek:** regresja w tej gałęzi przeszłaby niezauważona. Instrukcja (`V3_GRID_FINE_TUNING_OPERATOR.md:242`) obiecuje wszystkie trzy przesłanki.
   - **Minimalna poprawka:** w osobnym savepoincie bez użycia B, a tylko z rekordem `recording_evidence` (`kind='use'`, `purpose='diagnostic_comparison'`), sprawdzić `pytest.raises(RuntimeError, match="Purpose history prevents downgrade")`.

3. **Cold reader potwierdza ścieżkę tylko modułu API.**
   - **Gdzie:** `services/worker/tests/test_full_board_acceptance.py:234`. Asercja `__file__` dotyczy tylko `game_predictor_api...full_board_calibration`. `GridCohortSnapshot` z `game_predictor_worker` nie jest sprawdzany.
   - **Ryzyko:** dziś `PYTHONPATH` ma pierwszeństwo przed editable `.pth`, więc ryzyko jest niskie. Weryfikacja deklaruje jednak wymuszenie kodu tego worktree dla całego readera.
   - **Minimalna poprawka:** dodać analogiczną asercję dla `game_predictor_worker.images.grid_cohort_dataset.__file__`.

4. **Brak jawnych asercji braku claimów whole-photo i duplicate.**
   - **Gdzie:** `services/worker/tests/test_full_board_acceptance.py:173-175`. Test sprawdza `full_photos == 0` i `false_boards is None`. Kryterium akceptacji mówi jednak też o duplicate claims i `wholePhotoClaims` (tabela liczników w VERIFICATION).
   - **Skutek:** pole duplikatów lub zakresu `labelled_targets` mogłoby zacząć zgłaszać claim bez czerwonego testu.
   - **Minimalna poprawka:** asercje na pola duplicate/`assessmentScope`/`wholePhotoClaims` w raporcie i w `automaticCalibration` dla danych częściowych.

5. **Pozytywne evidence sprawdzone tylko dla slotu 4.**
   - **Gdzie:** `services/worker/tests/test_full_board_acceptance.py:543`. `calibrated_result_blockers` jest sprawdzane wyłącznie dla `evidence["4"]`.
   - **Skutek:** nie widać, że sloty bez ratunku dostają `rescue_completed=False` i nie przejmują `boardGeometry` (`full_board_runtime_evidence.py:77-78`). Rozjazd w tym miejscu nie zostałby wykryty.
   - **Minimalna poprawka:** dla jednego slotu bez ratunku (na przykład `"0"`) sprawdzić, że w `features` nie ma oznaczenia ukończonego ratunku i że wynik jest stabilny.

## Pokrycie kryteriów akceptacji

| Kryterium | Ocena statyczna |
|---|---|
| AC1: handler zapisuje frozen A, `require_targets(A)`, B nie trafia do A, raw PASS ≠ auto PASS | **Spełnione.** Prawdziwy `GridModelEvaluationJobHandler`. Detail ma 15 celów na grę, a zbiór źródeł równa się źródłom A z `GridBoardDataset`. Przypadek negatywny `observed[:-1]` zwraca `FROZEN_TARGET_SET_CHANGED:A`. Werdykt raportu to PASS, a auto to `unqualified`/`CALIBRATION_MINIMUM:baselineBadSources`, z B liczonym osobno (1/3). |
| AC2: rzeczywisty sink `run_with_rescue` → runtime evidence, drift routing/preset odrzucany | **Spełnione.** Drift `selectedPath`, routingu i marginesu presetu (z nowym, poprawnym SHA bundla) daje `{}` przez porównanie `routing_sha` (`full_board_runtime_evidence.py:61-63`), a nie przez przypadkowy wyjątek. Replay i alias nie wywołują nowych calls. Walidatory i store nie są mockowane. |
| AC3: restart zachowuje tożsamości i budżet, dane częściowe bez claimów | **Częściowo** (P2-1, P2-4). Utrata odpowiedzi po zakończeniu jest pokryta: identyczny raport i SHA, 0 nowych calls. Cold reader w osobnym procesie sprawdza frozen A i plik evidence, który `finish()` zawsze zapisuje (`full_board_calibration_run.py:296`), więc `require_calibration_evidence` faktycznie weryfikuje seal B/REG. |
| AC4: instrukcja wdrożenia, downgrade, rejestracja i rollback | **Spełnione.** Kolejność 0180→0181, opis blokady downgrade, rollback przez `rollbackGameGridModel` oraz PowerShell z `timeout=120`. |
| AC5: mapa wymagań i DoD, reuse T0–T5 | **Spełnione.** Rzeczy niewykonane (prawdziwy NN, B/REG, browser/Android review) są opisane jawnie. |
| AC6: zamknięcie (Opus, task-close, commit, końcowy hash) | Otwarte zgodnie z procesem. Ten audyt nie jest wykonaniem tych kroków. |

Zgodność historyczna: test PG porównuje bajty `recording_photo_context_v1/v2` przed migracją i po cyklu downgrade/reupgrade, sprawdza uprawnienia przez `recording_permission_errors == ()`, a także fence'y `GRID_VALIDATION_PURPOSE_CONFLICT`, `B_SELECTION_FORBIDDEN` i `DIAGNOSTIC_EXPOSED`. Rejestracja diagnostyki jest wykonywana na roli aplikacji (`app_engine`), a weryfikacja na roli właściciela, więc nie widzę przecieku ról. Rejestracja jest idempotentna, a podrobiony wpis zwraca `RECORD_INVALID`.

## Otwarte i zamknięte

- **Otwarte:** P2-1 … P2-5 oraz AC6 (proces zamknięcia).
- **Zamknięte:** AC1, AC2, AC4, AC5. Kod produkcyjny, API i schemat są niezmienione względem T5, co potwierdza zakres pakietu i brak zmian produkcji w statusie git.

## Proponowane testy
1. Restart handlera v4 od checkpointu pośredniego z porównaniem bajtów detail/final (P2-1).
2. Blokada downgrade 0181 wyłącznie z historią `diagnostic_comparison` (P2-2).
3. Asercja `__file__` modułu workera w cold readerze (P2-3).
4. Asercje braku claimów duplicate/whole-photo dla danych częściowych (P2-4).
5. Evidence dla slotu bez ratunku (P2-5).

## Ograniczenia
- Przegląd był statyczny, bez wykonania. Wyniki 2 PASS/14.43s, PG 1 PASS/21.01s i cleanup 0/0/0 to deklaracje wykonawcy. Nie mogłem ich zweryfikować, sprawdziłem jedynie spójność kodu testów z tymi deklaracjami.
- Nie czytałem w całości dziewięciu części snapshotu ani logów `artifacts/task1160/`. Numery linii pochodzą z oryginalnych plików w worktree.
- Nie oceniałem jakości NN, parity ONNX (T3 przyjęte przez odwołanie) ani UI w przeglądarce/Androidzie.
