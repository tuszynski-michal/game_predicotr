# Audyt TASK-1177 — Wydajny zapis symboli i zamrażanie manifestu

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...f4d1672933487752e51f0e49b4e49513d6779a00 oraz zmiany niezacommitowane, data 2026-11-10
Runda: 2
SHA pakietu: 5f47b689134cbaff3f7375eff8ff771cb2d514424e1b75ca7ce6dfa4d15cd446
Otwarte P0: 0
Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W drugiej rundzie sprawdziłem poprawki do znalezisk z rundy 1. Na nowo przejrzałem też najważniejszy kod: ścieżkę freeze z poświadczeniem bez blokady i fence'em, nieblokującą próbę blokady własności, liczniki bulk oraz obsługę STALE, WRITE_BUSY i PROJECTION_NOT_READY w Adminie.

Obie blokady z rundy 1 usunięto:

- kontrakt API opisuje teraz nowe zachowanie i kody 409;
- predykat ciężkich jobów ma dokładny test jednostkowy i test PostgreSQL.

Poprawiono też P2-3 i P2-4. Logika backendu nadal wygląda poprawnie: kolejność blokad to własność → gra → stan katalogu, NOWAIT daje WRITE_BUSY, konflikt 40001 daje STALE, a idempotencja chroni replay.

Commit blokuje nowe znalezisko P1. Kod Admina dodany w poprawkach nie jest sformatowany przez Prettier, więc obowiązkowa kontrola formatu (`format:check` w `npm run quality`, DoD) nie przejdzie. Najważniejszym ryzykiem merytorycznym pozostaje świadomie zaakceptowane P2-1.

## Znaleziska

### P0

Brak.

### P1

- [P1-3] `apps/admin/test-interactions/model-quality-loading.test.mjs:157` — Cztery nowe testy interakcji (linie 153–261) nie są w formacie Prettier.
  - Przykłady:
    - jednowierszowe bloki `} finally { await unmount(root); }` (188, 212, 234, 260);
    - strzałki bez nawiasów `b => b.textContent` (175, 204, 227, 249) przy domyślnym `arrowParens: always`;
    - wiersze dłuższe niż 80 znaków (167, 196, 253, 255);
    - niezłamane `mount(client({`.
  - Istniejąca część pliku (np. 116–151) jest sformatowana Prettierem.
  - Podobnie `apps/admin/src/features/model-quality/model-quality-actions.ts:657`: ostatnia gałąź zagnieżdżonego ternary (`: apiErrorMessage(`) ma wcięcie 14 spacji zamiast 16. Prettier 3 przeformatuje ten fragment.
  - Obie ścieżki obejmuje `format:check` z `package.json:57`. Nie wyklucza ich `.prettierignore`, który pomija tylko `ai_docs/` i artefakty.
  - `ai_docs/quality/TASK-1177_VERIFICATION.md` wymienia dla Admina tylko ESLint, typecheck i build. Nie podaje wyniku Prettier.
  - Skutek: pełna bramka `npm run quality` nie przejdzie. Naruszony jest wymóg DoD „lint/format/typecheck przeszły dla zmienionych modułów” (`ai_docs/process/DEFINITION_OF_DONE.md:48`) oraz kryterium „kontrole zaliczone”.
  - Poprawka: uruchomić `prettier --write` na obu plikach, potem `npm run format:check`, i dopisać wynik do raportu weryfikacji.

### P2

- [P2-1] `services/api/src/game_predictor_api/application/verified_training_cohorts.py:321` — Ryzyko z rundy 1 pozostaje otwarte jako jawnie zaakceptowane. Poprawność fence'u zależy od tego, że każdy pisarz wejść manifestu podbija `catalog_revision` albo unieważnia gotowość projekcji. Architektura D-600 (`ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`, sekcja „Przygotowanie poza blokadą i fence zapisu”) zawiera teraz ten inwariant i listę kontrolną. Testy pokrywają tylko bulk i ręczną geometrię. Proponuję utrzymać akceptację ryzyka w task-close i w razie potrzeby dodać testy dla pozostałych pisarzy w osobnym tasku.
- [P2-2] `services/api/src/game_predictor_api/storage/image_review_repository.py:713-721` — Zawieszony job CREATED/PROCESSING typu IMPORT lub IMAGE_GRID_REINFERENCE nadal bezterminowo blokuje przygotowanie, a panel nie wskazuje, który to job. Ryzyko jest ograniczone: według raportu weryfikacji odczyt `task1177-active-heavy.json` nie znalazł na danych operatora żadnego takiego joba. Wskazanie blokującego joba odroczono jawnie. Akceptacja ryzyka jest właściwa, jeśli trafi do task-close.
- [P2-5] `ai_docs/tasks/1177-symbol-review-performance-freeze.md:73-76` — Outcome taska jest nieaktualny wobec raportu weryfikacji. Podaje „PASS:54 Python, 13 PostgreSQL, 11 interakcji” i „Audyt Opus oczekuje”. Raport podaje 56 testów Python, 8+5+1 PostgreSQL i 12 interakcji (`ai_docs/quality/TASK-1177_VERIFICATION.md:30-35`) oraz opisuje rundę poprawek. Dodatkowo nagłówek `## Boundaries and remaining work` (`TASK-1177_VERIFICATION.md:67`) jest pusty, bo treść znalazła się pod kolejnym nagłówkiem. Skutek: niespójny zapis dowodów w momencie zamknięcia. Poprawka: przy task-close ujednolicić liczby i stan audytu w Outcome oraz przenieść treść granic pod właściwy nagłówek.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zmierzona przyczyna i ograniczone porównanie przed/po | spełnione (według raportu, bez ponownego pomiaru) | `ai_docs/quality/TASK-1177_VERIFICATION.md:49-66`: 413→376 SQL, 1.229→1.180 s, inwentarz: stara wersja przekroczyła limit 12 s, nowa 3.292 s, plus EXPLAIN odcięcia partycji |
| Mniej zbędnych SQL, krótsze sekcje blokad, zgodny wynik zapisów | spełnione | `image_symbol_review_bulk_operation_repository.py:403-417,529-574,608-625`; `symbol_training_board_owners.py`; `verified_training_cohorts.py:320-331`; test PG `test_real_bulk_recounts_once_per_boundary_and_replay_creates_no_events` |
| Aktualne potwierdzenie manifestu, realne stale nadal blokuje | spełnione, z ryzykiem P2-1 | `verified_training_cohorts.py:324-339`; `symbol_cell_training_source_repository.py:113-156`; `test_verified_training_freeze_fence.py`; test PG `test_other_writer_can_commit_during_attestation_and_fence_rejects_its_drift` (RC i RR); `test_full_cell_correction_postgres.py:174-179` |
| Czytelny konflikt/oczekiwanie i bezpieczny retry w Adminie | spełnione | `model-quality-actions.ts:640-662`; `model-quality-workspace.tsx:232-262,804-809`; `model-quality-loading.test.mjs:153-261` |
| Restart/utrata odpowiedzi/własność/holdouty/human approvals chronione | spełnione statycznie | `verified_training_cohorts.py:288-303,345-354`; `sequence_ownership_lock.py:122-158`; odcisk ochrony `symbol_cell_training_source_repository.py:100-110`; `test_sequence_ownership_lock.py` (nieudana próba nie jest zapisana jako posiadana blokada) |
| API/OpenAPI/SDK zgodne, właściwe testy PG/UI i kontrole zaliczone | niespełnione | Kontrakt poprawiony (`API_CONTRACT.md:4728-4747`), test predykatu dodany (`test_image_review_repository_job_lock.py:11-35`, PG `test_queued_bulk_blocks_freeze_before_any_attestation_or_artifact_write`). Kontrola formatu Admina nie przejdzie (P1-3). Wyniki testów są tylko deklarowane przez wykonawcę |
| Opus i task-close przed commitem, P2 jawnie zapisane | niezweryfikowane | Runda 2 kończy się werdyktem REVISE. P2-1 i P2-2 zapisano w raporcie weryfikacji, task-close jeszcze nie nastąpił (P2-5) |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P1-2, P2-3, P2-4

Dowody zamknięcia:

- **P1-1:** `ai_docs/architecture/API_CONTRACT.md:4728-4747` opisuje poświadczenie bez blokady i fence pod krótką blokadą. Wymienia WRITE_BUSY, PROJECTION_NOT_READY, typy i statusy ciężkich jobów oraz mapowanie konfliktu RR na STALE. D-600 w `DECISION_LOG_2026.md` uzupełniono o te kody.
- **P1-2:** `services/api/tests/test_image_review_repository_job_lock.py:11-35` sprawdza dokładny zbiór czterech typów, statusy CREATED/PROCESSING, `game_id` i brak stanów końcowych oraz WAITING_FOR_REVIEW. Nowy test PG `test_queued_bulk_blocks_freeze_before_any_attestation_or_artifact_write` potwierdza HEAVY_JOB_ACTIVE przed poświadczeniem i zapisem artefaktu.
- **P2-3:** `model-quality-workspace.tsx:244-248` pokazuje informację o odrzuceniu niezależnie od wyniku `prepareCohort`. Pokrywa to test `model-quality-loading.test.mjs:215-235`.
- **P2-4:** `model-quality-actions.ts:655-656` ma dedykowany komunikat PROJECTION_NOT_READY. Podgląd nadal nie sprawdza gotowości katalogu, ale operator dostaje teraz czytelne instrukcje.

Otwarte: P1-3, P2-1, P2-2, P2-5.

## Proponowane testy

- `npm run format:check` po sformatowaniu `apps/admin/test-interactions/model-quality-loading.test.mjs` i `apps/admin/src/features/model-quality/model-quality-actions.ts`, a następnie pełne `npm run quality`.
- `services/api/tests/integration/test_symbol_review_performance_freeze_postgres.py`: pełny `VerifiedTrainingCohortService.freeze` z prawdziwym repozytorium symbol-cell. Zmiana `recognized_boards.geometry_revision` albo właściciela fast document między poświadczeniem a fence'em powinna dać STALE. To wzmacnia P2-1. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_symbol_review_performance_freeze_postgres.py`.
- Ten sam plik: freeze przy jobie IMPORT lub IMAGE_GRID_REINFERENCE w stanie PROCESSING daje HEAVY_JOB_ACTIVE, a w stanie WAITING_FOR_REVIEW nie blokuje.

## Zakres przeglądu i ograniczenia

Przeczytałem cały zamrożony pakiet: task, wycinek planu, diff zmian śledzonych, nowe pliki, raport rundy 1 i raport weryfikacji. W repozytorium przejrzałem:

- `verified_training_cohorts.py` (konstruktor, preview, freeze);
- `symbol_cell_training_source_repository.py` (fence);
- `sequence_ownership_lock.py`;
- `image_review_repository.py` (`has_active_heavy_job`) wraz z wyszukaniem jego wywołań;
- `image_symbol_review_bulk_operation_repository.py` (`process_next_batch`, `_apply_board_targets`, `_record_board_error`, `_locked_targets`);
- `model-quality-workspace.tsx`, `model-quality-actions.ts` i nowe testy interakcji;
- `package.json` (format:check), `.prettierrc.json`, `.prettierignore`, `API_CONTRACT.md` i `DEFINITION_OF_DONE.md`.

Nie uruchamiałem testów, Prettier, lintu, typechecku, OpenAPI ani pomiarów. P1-3 oceniam statycznie na podstawie konfiguracji Prettier i porównania z istniejącym formatowaniem pliku. Wyniki PASS i pomiary pochodzą wyłącznie z raportu wykonawcy. Nie sprawdzałem wszystkich pisarzy biorących blokadę własności pod kątem `catalog_revision` (P2-1). Nie widziałem artefaktów `artifacts/task1177-*`.