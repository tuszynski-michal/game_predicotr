# Audyt TASK-1122 — Uproszczony panel i zastosowanie modelu

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high (według tabeli planu i taska); regresja PostgreSQL APPLY: lead
Zakres: 7801ea4711f92f04eeeb58bfed124f9f850e01e0...7801ea4711f92f04eeeb58bfed124f9f850e01e0 (pusty diff commitów) oraz zmiany niezacommitowane z focused listy R2 (12 ścieżek z briefu), data 2026-11-02
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Runda 2 sprawdziła poprawki znalezisk R1. Najważniejsza była P1-1, czyli trwałe zablokowanie nowego apply po wcześniejszej publikacji kandydata. Zbadano serwis `grid_correction_apply.py`, rzeczywisty kontrakt dowodu w `grid_model_publication.py`, panel zastosowania, etykiety, testy jednostkowe, nowy test PostgreSQL APPLY oraz dokumentację. P1-1 jest usunięte. Istniejąca publikacja jest przyjmowana bez mutacji tylko przy identycznym, kanonicznym dowodzie z tą samą sumą kontrolną. Format `expected` dokładnie odpowiada temu, co zapisuje `GridModelPublicationService._evidence`. Inny dowód blokuje podgląd, porównanie i wykonanie. Pozostały wyłącznie drobne ryzyka P2: ścieżka GET może stać się nieczytelna przy publikacji z innym dowodem, a odczyt może pokazać krok publikacji jako wykonany wcześniej, niż przebieg do niego doszedł.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-3] `services/api/src/game_predictor_api/application/grid_correction_apply.py:394` — część startowa poprawki R1 jest skuteczna: `start` pod blokadą rejestru odrzuca drugi aktywny apply (`grid_correction_apply.py:330-332`), co potwierdza test PostgreSQL (`services/api/tests/integration/test_grid_correction_apply_postgres.py:373-375`). `resume` nie sprawdza jednak `_active`. Przebieg FAILED z przyczyny innej niż CAS, na przykład przejściowej porażki porównania, można więc wznowić, gdy nowy przebieg tego samego learningu jest już aktywny. Skutek: dwa aktywne przebiegi, zdublowane porównania (koszt GPU) i jawny konflikt CAS w historii. Danych to nie narusza. Ryzyko jest zaakceptowane w `ai_docs/tasks/1122-grid-correction-learning-panel.md:77`. Zdanie `ai_docs/requirements/ADMIN_APP.md:43` („Drugi aktywny apply jest blokowany po stronie serwera”) nie wspomina o tym wyjątku. **Propozycja:** w `resume`, po `registry.repository.lock()`, odrzucać wznowienie kodem `GRID_APPLY_BUSY`, gdy `_active` zwraca inny identyfikator. To jedna linia i znosi zaakceptowane ryzyko. Alternatywnie dopisać wyjątek dla resume w `ADMIN_APP.md`.

- [P2-5] `services/api/src/game_predictor_api/application/grid_correction_apply.py:449` — `_view` wywołuje `_publication_receipt` dla każdego nieukończonego kroku `publish`. Ta funkcja rzuca `GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT`, gdy kandydat ma publikację z innym dowodem. `_view` obsługuje `list` (`grid_correction_apply.py:378`), `get`, odtworzenie `start` i odpowiedź `resume`. **Scenariusz:** apply A kończy się FAILED przed publikacją, na przykład na porównaniu. Operator publikuje potem kandydata ręcznie w sekcji Zaawansowane z innym raportem. Od tej chwili GET listy dla tego learningu zwraca 409 dla całej historii, a panel pokazuje tylko „Nie udało się odczytać historii zastosowania.” (`apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx:150-151`) i gubi kod przyczyny. Danych to nie narusza, a podgląd nadal poprawnie pokazuje blokadę. Jednak historia i częściowy sukces innych przebiegów przestają być widoczne. Test PostgreSQL `different_evidence` sprawdza tylko pustą listę (`test_grid_correction_apply_postgres.py:360`). **Propozycja:** w `_view` przechwytywać ten konflikt i zostawiać krok `pending`, ewentualnie z polem informacyjnym. Blokada pozostaje wtedy w preview i advance, a odczyt nie zawodzi. Do tego test jednostkowy: istniejący przebieg z oczekującym `publish` plus obca publikacja z innym dowodem, po czym `list` zwraca widok.

- [P2-6] `services/api/src/game_predictor_api/application/grid_correction_apply.py:448-453` — adopcja w GET nie sprawdza, czy przebieg w ogóle doszedł do kroku `publish`. Jeśli inny przebieg albo ręczne działanie opublikowało kandydata z identycznym dowodem, każdy wcześniejszy przebieg tego learningu jest odczytywany z krokiem „Potwierdzono istniejącą publikację”. Dotyczy to też przebiegu FAILED na porównaniu albo czekającego na porównanie, czyli przed krokiem, który według kolejności nie mógł jeszcze nastąpić. Panel dopisuje wtedy „Wykonane kroki są zachowane” (`grid-correction-apply-panel.tsx:472-478`). Rejestru to nie narusza, bo `advance` i tak przyjąłby tę publikację. Opis częściowego sukcesu może jednak wprowadzać w błąd. **Propozycja:** w GET adoptować publikację tylko wtedy, gdy wszystkie kroki `comparison` przed `publish` są ukończone. To dokładnie odpowiada luce commit/checkpoint, którą ta logika ma odtwarzać. Alternatywnie jawnie zaakceptować ryzyko w dokumentacji.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| GET-only otwarcie | spełnione | `apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx:165-196`; `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs:168` |
| Prowadzony workflow, osobne i jawne zastosowanie, potwierdzenie photo-only | spełnione | `services/api/src/game_predictor_api/application/grid_correction_apply.py:306-311,339-344`; `grid-correction-apply-panel.tsx:403-435` |
| Pełny pion API | spełnione (bez zmian kontraktu w R2; `receipt` to `dict`) | `services/api/src/game_predictor_api/schemas/grid_correction_apply.py:54-58` |
| Utracona odpowiedź / restart bez duplikatów | spełnione | `grid_correction_apply.py:319-328,620-654`; `services/api/tests/test_grid_correction_apply.py:228,267`; `services/api/tests/integration/test_grid_correction_apply_postgres.py:367,387,421` |
| Baseline faktycznie przypisanej wersji | spełnione | `grid_correction_apply.py:176-177,514-555,624-635` |
| Partial success i resume | spełnione (zob. P2-3, P2-6) | `grid_correction_apply.py:384-418`; `test_grid_correction_apply_postgres.py:415-443` |
| Concurrent default ⇒ świeży preview (R1 P1-1) | spełnione | `grid_correction_apply.py:246-282,643-644`; `services/api/src/game_predictor_api/application/grid_model_publication.py:137-142`; `test_grid_correction_apply.py:394-412`; `test_grid_correction_apply_postgres.py:382-414` |
| Inny dowód publikacji blokuje preview i wykonanie | spełnione (GET zob. P2-5) | `grid_correction_apply.py:190,578,623`; `test_grid_correction_apply.py:415-439`; `test_grid_correction_apply_postgres.py:354-363` |
| Własny default: osobny komunikat, bez opt-in i startu | spełnione | `grid_correction_apply.py:134-138`; `apps/admin/src/features/model-quality/grid-model-state.ts:12-13`; `grid-correction-apply-panel.tsx:263-264,348,403`; `grid-correction-learning-panel.test.mjs:550-617` |
| Idempotentny resume created/processing/completed | spełnione | `grid_correction_apply.py:388-389`; `test_grid_correction_apply.py:351-355`; `test_grid_correction_apply_postgres.py:436,443` |
| Historia i rollback bez recropu | spełnione | `test_grid_correction_apply_postgres.py:462-463,484-486` |
| Właściwe testy, lint/typecheck, dokumentacja | niezweryfikowane (polecenia nie były uruchamiane), dokumentacja zgodna poza P2-3 | `ai_docs/architecture/VISION_LAB.md:9-44`; `ai_docs/requirements/ADMIN_APP.md:16-47`; `ai_docs/quality/TASK-1122_VERIFICATION.md`; liczba 25 testów jednostkowych zgadza się z plikiem testów |
| Audyt Opus 5.5/high bez otwartych P0/P1 | spełnione (ten raport) | brak otwartych P0/P1 |
| Outcome, task-close, commit, record-hash | niespełnione (poza zakresem audytu, czeka na leada) | `ai_docs/tasks/1122-grid-correction-learning-panel.md`, sekcja Not completed |

## Listy zamknięte i otwarte

Zamknięte:

- **P1-1:** `_publication_receipt` przyjmuje dokładnie zgodną publikację bez mutacji (`grid_correction_apply.py:246-282,643-644`). Kontrakt `expected` jest identyczny z `grid_model_publication.py:137-142`. Pokrywają to testy `test_grid_correction_apply.py:367-412` oraz warianty `first_apply` i `manual` w `test_grid_correction_apply_postgres.py:212-486`.
- **P2-1:** jest test PostgreSQL rodzica APPLY (`services/api/tests/integration/test_grid_correction_apply_postgres.py`), a Outcome rozróżnia dowód LEARNING od APPLY.
- **P2-2:** wprowadzono `GRID_APPLY_ALREADY_DEFAULT` (`grid_correction_apply.py:134-138`), panel ukrywa opt-in i start (`grid-correction-apply-panel.tsx:348,403`), a etykieta nie sugeruje nowego przebiegu (`grid-model-state.ts:12-13`).
- **P2-4:** resume dla created/processing/completed zwraca bieżący widok (`grid_correction_apply.py:388-389`).

Otwarte: P2-3 (częściowo: dotyczy już tylko resume, ryzyko zaakceptowane przez leada), P2-5, P2-6.

## Proponowane testy

- `services/api/tests/test_grid_correction_apply.py`: przebieg FAILED z oczekującym `publish`, potem obca publikacja z innym dowodem. `service.list`/`_view` nie rzuca, a krok pozostaje `pending` (P2-5). Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_apply.py -k view`.
- Ten sam plik: przebieg z nieukończonym `comparison` plus identyczna obca publikacja. GET nie oznacza `publish` jako ukończonego przed porównaniem (P2-6).
- Ten sam plik: `resume` przebiegu FAILED przy innym aktywnym apply tego learningu kończy się `GRID_APPLY_BUSY`, o ile P2-3 zostanie poprawione.
- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`: błąd listy zastosowań z kodem `GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT` pokazuje czytelną przyczynę zamiast ogólnego komunikatu. Komenda: `npm run test:interactions --workspace @game-predictor/admin` albo bezpośrednie wywołanie `tsx --test` z raportu weryfikacji.

## Zakres przeglądu i ograniczenia

Przeczytano w całości:

- brief, task i raport audytu R1
- `ai_docs/quality/TASK-1122_VERIFICATION.md`
- `services/api/src/game_predictor_api/application/grid_correction_apply.py`
- `services/api/src/game_predictor_api/api/grid_correction_apply.py`
- `apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx`
- `services/worker/src/game_predictor_worker/images/grid_correction_apply_handler.py`
- testy jednostkowe apply od fake'ów do linii ~480 oraz listę wszystkich przypadków
- główny test `services/api/tests/integration/test_grid_correction_apply_postgres.py:200-488`
- przypadek „own default” w interakcjach
- diff etykiet i ich testu
- dokumentację `ADMIN_APP.md` i `VISION_LAB.md`

Dla kontekstu sprawdzono:

- `GridModelPublicationService._evidence`, `_eligible_inspected` i `execute` (`grid_model_publication.py:64-309`)
- `JobStatus`
- warunek `waitingForJobId` w claimie workera, który potwierdza, że oczekujący rodzic ma status CREATED i jest objęty przez `_active`
- mapowanie `GridCohortError` na status HTTP w `main.py:2323-2328`

Nie uruchamiano testów, lintów, typechecku, buildu ani PostgreSQL. Wyniki z Outcome i raportu weryfikacji, w tym 25/25 unit apply, warianty PostgreSQL 1/1 i 2/2 oraz build 17.52 s, przyjęto jako deklarację wykonawcy i leada. Liczba przypadków jednostkowych zgadza się z plikiem. Nie sprawdzano wygenerowanego klienta, bo w R2 kontrakt HTTP się nie zmienił. Nie analizowano metadanych T2, `CODE_MAP*` ani CSS.
