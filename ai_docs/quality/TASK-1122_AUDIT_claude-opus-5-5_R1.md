# Audyt TASK-1122 — Uproszczony panel i zastosowanie modelu

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high (według tabeli planu i taska)
Zakres: HEAD...7801ea4711f92f04eeeb58bfed124f9f850e01e0 oraz zmiany niezacommitowane (indeks i drzewo robocze, 35 ścieżek z briefu), data 2026-11-02
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano pion zastosowania kandydata. Obejmuje on serwis `GridCorrectionApplyService`, router HTTP, zamknięte schematy, payload joba z osobnym dyskryminatorem, dyspozytor i handler workera, OpenAPI, wygenerowany klient z wrapperem i testem żądania, panel uczenia i panel zastosowania w Adminie oraz dokumentację. Konstrukcja jest staranna. Wejście do panelu wykonuje wyłącznie GET. Polecenie startu jest idempotentne. Kroki rejestru mają deterministyczne klucze i receipts, a każdy krok ponownie sprawdza CAS defaultu i przypisania. Porównania z faktycznie przypisaną wersją wykonują się przed jakąkolwiek mutacją, a GET uzgadnia lukę między commitem a checkpointem. Główne ryzyko: krok `publish` każdego nowego apply zakłada, że kandydat nie jest opublikowany. Dlatego ścieżka „świeży podgląd → nowe zastosowanie”, wprost przewidziana przez leada, trwale się blokuje, gdy wcześniejszy przebieg albo ręczne działanie operatora już opublikowały kandydata.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/application/grid_correction_apply.py:559` — dla kroku `publish` kod zawsze ustawia `expected = 0`, a `_steps` (`grid_correction_apply.py:228-231`) zawsze dodaje `publish` do nowego przebiegu. Rzeczywisty `GridModelPublicationService.execute` (`services/api/src/game_predictor_api/application/grid_model_publication.py:270-280`) odrzuca wtedy już opublikowaną wersję kodem `GRID_MODEL_REVISION_CONFLICT`. Podgląd (`grid_correction_apply.py:123-185`) nie sprawdza stanu publikacji, więc pokazuje `canApply=true`.

  **Scenariusz:** pierwszy apply commituje `publish`. Zanim wykona `set_default`, ktoś ustawia nową rewizję tej samej bazy. Stary przebieg nie wznowi się, bo `_require_default` odrzuca obcą rewizję. Świeży podgląd jest poprawny, zgodnie z interpretacją leada w Technical notes. Nowy apply po porównaniach zawsze kończy się błędem na `publish`. Tak samo dzieje się po ręcznej publikacji kandydata w sekcji Zaawansowane.

  **Skutek:** kandydat zostaje opublikowany, ale nie jest defaultem. Zalecanej w UI i w `ADMIN_APP.md` ścieżki „odśwież podgląd” nie da się dokończyć. Narusza to wymaganie planu T3 „Concurrent default => nowy preview” oraz „resume po partial success”. Fake `Catalogue.execute` w `services/api/tests/test_grid_correction_apply.py:124-149` nie modeluje konfliktu publikacji, więc testy tego nie wykrywają.

  **Poprawka:** przy istniejącej publikacji tej samej wersji z tym samym `evaluationId` i dowodem zgodnym z pinami (`publication.evidence_json` zawiera `evaluationId`, `evaluationSha256` i `manifestSha256`) oznaczyć krok jako spełniony receiptem typu „already-published”, bez mutacji. Jeśli publikacja ma inny dowód, podgląd powinien zwrócić jawny blocker. Dodać test jednostkowy z fake'iem odrzucającym ponowną publikację oraz scenariusz w Postgres.

### P2

- [P2-1] `services/api/tests/test_grid_correction_apply.py:97-193` — wszystkie testy serwisu apply używają fake'ów: `ReadSession`, `Catalogue` oraz podmienionych `_evidence` i `_registry`. Nie ma testu PostgreSQL dla zapytań JSONB po `learning_kind` i `learning_id`, advisory locków `start` i `resume`, rzeczywistych komend rejestru ani claimu rodzica z `waitingForJobId`.

  Dodatkowo zdanie z Outcome „Parent PostgreSQL replay/CAS/cancel/resume: 1/1 PASS” (`ai_docs/tasks/1122-grid-correction-learning-panel.md:114`) dotyczy rodzica uczenia z T2 (`integration/test_grid_correction_learning_postgres.py`), a nie rodzica apply. Łatwo je odczytać jako pokrycie apply.

  **Poprawka:** doprecyzować to zdanie w Outcome. Test Postgres apply (replay startu, CAS, partial, resume, ponowna publikacja) dodać najpóźniej w T4, zgodnie z planem. Szkic leada (`artifacts/task1123-apply-draft.log`) nie jest testem w repozytorium.

- [P2-2] `services/api/src/game_predictor_api/application/grid_correction_apply.py:130-134` — po własnym, udanym apply podgląd tego samego learningu zawsze zwraca `GRID_APPLY_DEFAULT_CHANGED`, bo head jest już kandydatem, a nie bazą. Etykieta w `apps/admin/src/features/model-quality/grid-model-state.ts:31-32` mówi wtedy „Inna baza wymaga nowego przebiegu uczenia”, co po sukcesie wprowadza w błąd. Panel nadal pokazuje opt-in „Zastosuj także w innych ocenionych grach” (`apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx:346-370`), choć dla tego kandydata nigdy się nie powiedzie.

  **Poprawka:** gdy head jest już kandydatem z własnym receiptem `set_default`, zwrócić osobny kod, np. „kandydat już zastosowany”, i ukryć opt-in. Można też jawnie zaakceptować ograniczenie i opisać je w `ADMIN_APP.md`.

- [P2-3] `services/api/src/game_predictor_api/application/grid_correction_apply.py:238-295` — nic nie blokuje utworzenia drugiego apply dla tego samego learningu, gdy pierwszy jest aktywny albo częściowo wykonany. Inna karta albo drugi klucz po utracie stanu UI może tak zrobić, bo UI blokuje to tylko lokalnie (`grid-correction-apply-panel.tsx:408`). Drugi przebieg wykona porównania i zakończy się konfliktem CAS lub publikacji. Rejestr pozostaje spójny, ale historia rośnie o mylące porażki.

  **Poprawka:** w `start`, pod blokadą rejestru, odrzucać nowy apply, gdy dla `learning_id` istnieje aktywny albo wznawialny przebieg, i kierować do resume.

- [P2-4] `services/api/src/game_predictor_api/application/grid_correction_apply.py:317-349` — `resume` nie ma klucza idempotencji. Klucz zapisany przez UI (`grid-correction-apply-panel.tsx:471-475`) nie jest wysyłany. Ponowienie po utraconej odpowiedzi na udany resume dostaje 409 `GRID_APPLY_NOT_RESUMABLE`, a UI pokazuje „Polecenie odrzucone”, choć wznowienie zadziałało. Duplikatów nie ma, więc ryzyko dotyczy tylko komunikatu.

  **Poprawka:** traktować resume już wznowionego przebiegu (status `created` lub `processing`) jako odpowiedź idempotentną, zwracając widok. Można też jawnie zaakceptować ryzyko, bo T2 ma ten sam wzorzec.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| GET-only otwarcie | spełnione | `services/api/src/game_predictor_api/api/grid_correction_apply.py:39-52,68-83`; `apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx:165-196`; `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs:168-186,249` |
| Prowadzony workflow (panel podstawowy, Zaawansowane, osobne narzędzia) | spełnione | `apps/admin/src/features/model-quality/grid-model-workspace.tsx:40-87`; `apps/admin/test-interactions/grid-model-workspace.test.mjs:244-266` |
| Pełny pion API (backend/OpenAPI/generated/wrapper/request test) | spełnione | `services/api/src/game_predictor_api/main.py:2488-2498`; `packages/admin-api-client/src/index.ts:1550-1592`; `packages/admin-api-client/test/grid-correction-apply-request.test.mjs:5-56` |
| Utracona odpowiedź / restart bez duplikatów | spełnione (tylko testy z fake'ami) | `services/api/src/game_predictor_api/application/grid_correction_apply.py:248-263,543-574`; `services/api/tests/test_grid_correction_apply.py:196-298`; `apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx:209-261` |
| Apply osobne i jawne, potwierdzenie photo-only | spełnione | `services/api/src/game_predictor_api/application/grid_correction_apply.py:241-246,272-277`; `services/api/src/game_predictor_api/schemas/grid_correction_apply.py:141-152` |
| Baseline faktycznie przypisanej wersji | spełnione | `services/api/src/game_predictor_api/application/grid_correction_apply.py:163-169,220-227,439-480,547-558` |
| Partial success widoczny i wznawialny | spełnione przy braku obcych zmian | `services/api/src/game_predictor_api/application/grid_correction_apply.py:351-380`; `services/api/tests/test_grid_correction_apply.py:318-356` |
| Concurrent default => świeży preview (interpretacja leada) | niespełnione po commicie `publish` | P1-1; `services/api/src/game_predictor_api/application/grid_correction_apply.py:559-560`; `services/api/src/game_predictor_api/application/grid_model_publication.py:270-280` |
| Historia i rollback bez recropu | spełnione | `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:297-325,692-737` (istniejąca trasa rollback) |
| Właściwe testy, lint/typecheck, dokumentacja | niezweryfikowane (testów nie uruchamiano), dokumentacja obecna | `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/architecture/VISION_LAB.md`, `ai_docs/quality/TASK-1122_VERIFICATION.md`; zob. P2-1 |
| Audyt Opus 5.5/high bez otwartych P0/P1 | niespełnione | ten raport: P1-1 otwarte |
| Outcome, task-close, commit, record-hash | niespełnione (poza zakresem audytu) | `ai_docs/tasks/1122-grid-correction-learning-panel.md`, sekcja Not completed |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- `services/api/tests/test_grid_correction_apply.py`: fake rejestru odrzucający `publish` przy istniejącej publikacji. Scenariusz: pierwszy apply commituje `publish`, obca rewizja tej samej bazy, świeży preview, nowy apply kończy się sukcesem bez drugiej publikacji. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_apply.py -k published`.
- Ten sam plik: ręczna publikacja kandydata przed apply. Podgląd albo pomija krok, albo zwraca jawny blocker; nie wolno uruchamiać porównań, które skończą się konfliktem.
- `services/api/tests/integration/` (T4, `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`): rodzic apply na prawdziwym PostgreSQL. Zakres: replay startu tym samym kluczem, drugi klucz przy aktywnym przebiegu, zwolnienie slotu podczas porównania, crash między commitem a checkpointem, resume po partial success, konflikt ponownej publikacji.
- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`: po udanym apply podgląd nie sugeruje nowego przebiegu uczenia i nie oferuje opt-in innych gier (P2-2).

## Zakres przeglądu i ograniczenia

Przeczytano w całości: brief, sekcję T3 planu, `application/grid_correction_apply.py`, `api/grid_correction_apply.py`, `schemas/grid_correction_apply.py`, handler i dyspozytor workera, `grid-correction-apply-panel.tsx`, `grid-correction-learning-state.ts`, większość `grid-correction-learning-panel.tsx` oraz raport weryfikacji. Przeczytano też diffy `grid_correction_learning.py`, `schemas/jobs.py`, `cli.py`, `main.py` i wrappera klienta.

Dla kontekstu sprawdzono istniejące `grid_model_publication.py` (`execute`, `_evidence`) i `create_assigned_comparison`/`_report` w `grid_model_evaluation.py`. Sprawdzono także claim i deferral rodzica w `services/worker/.../jobs/store.py` i `domain/jobs.py` oraz przejrzano testy jednostkowe, interakcyjne i request test.

Nie analizowano wiersz po wierszu wygenerowanych `openapi.json`, `sdk.gen.ts` i `types.gen.ts`; ich zgodność wykonawca deklaruje przez drift check. Pominięto CSS. Nie uruchamiano testów, lintów, typechecku, buildu ani PostgreSQL, więc wyniki z Outcome przyjęto jako deklarację wykonawcy. Nie sprawdzano zachowania RLS/storage scope sesji apply w rzeczywistej bazie.
