Werdykt: PASS

**Audytor:** claude-opus-5-5/high, Runda2 (focused R2, po jednej rundzie poprawek).

**Baza:** worktree `codex/full-board-detection`, HEAD `887d8a3b` (v1.7.559) plus niezacommitowane zmiany T2 i delta R1→R2 z pakietu `TASK1156-focused-r2-index.md`, części 01–02. Sum SHA pakietu nie przeliczałem, bo nie miałem shella.

**Zakres:** tylko zamknięcie uwag R1 P2-1…P2-5 i dwóch luk P1 koordynatora (retry, ludzkie zatwierdzenie) oraz skutki zmienionego kodu i testów. T3/T4 nie były oceniane.

To przegląd wyłącznie statyczny (Read/Grep). Niczego nie zmieniałem, nie uruchamiałem testów, usług, bazy, modeli ani subagentów. Wyniki PASS i czasy pochodzą z deklaracji wykonawcy.

## P0 / P1

Brak.

**Luka P1 koordynatora: retry (dawniej R1 P2-1). Zamknięta.**
- `job_repository.py` (`find_neural_operation_pin`) najpierw bierze blokadę gry `acquire_job_admission(require_idle=False)`, czyli `pg_advisory_xact_lock`. Dopiero potem robi dokładne porównanie JSONB: `input_payload - derived_keys = identity`.
- W API repozytorium, resolver i zapis joba używają tej samej sesji (`main.py:1177`). Blokada jest więc trzymana przez lookup, resolver i `_persist_job` aż do commit.
- Nie ma już `list_jobs` ani okna 10 000 dla pinu. Przy dwóch trafieniach operacja kończy się błędem (fail-closed).
- Kolejność w kodzie jest poprawna: pin powstaje przed wyliczeniem `pipeline_fingerprint` i `base_page_geometry_manifest` (`jobs.py:948`, `:1572`, `:2188`). Oba te pola są poprawnie wyłączone z tożsamości żądania.
- Test PG na współbieżność rzeczywiście odtwarza regresję. Bez blokady drugi wątek wywołałby resolver (`calls != [False]`) albo dostałby pin `qualified` po publikacji (asercja `unqualified` w resolverze).
- Retry po restarcie lub utracie odpowiedzi jest bezpieczny: blokada jest transakcyjna, a pin trwały w payloadzie joba.

**Luka P1 koordynatora: ludzkie zatwierdzenie (dawniej R1 P2-5). Zamknięta.**
- Pieczątkę ludzkiego zatwierdzenia z importu blokuje `is_game_scoped_neural_acceptance(job.input_payload…)` (`pipeline_store.py:~686`). To samo dotyczy wczesnego statusu źródła (`:~372`).
- Decyzję podejmuje zaufana polityka joba, a nie deklaracje workera.
- Sprawdziłem czytniki `geometry_qualification` (`image_symbol_review_repository.py:2618`, `image_geometry_completeness_state_repository.py:531`, `board_search_projection_repository.py:908`). Traktują te metadane jako informację o dostępności komórek. Zatwierdzenie wymaga `approved`, więc nie ma obejścia.
- Test PG: v3 kończy się bez rewizji, aktora i czasu zatwierdzenia, z poziomem U i `geometry_incomplete`; v2 bez zmian. Przed poprawką asercje by nie przeszły (rewizja 0, `geometry_complete`), więc test odtwarza regresję.

## P2 (4)

1. **Fałszywa „niejednoznaczność” przy duplikatach z tym samym pinem**
   - Miejsce: `services/api/src/game_predictor_api/storage/job_repository.py:~603` (`len(rows) > 1`) w połączeniu z `jobs.py:2195–2208`.
   - Problem: `_equivalent_page_geometry_preflight` pomija joby FAILED/CANCELLED, a kod jawnie pozwala je zastąpić, gdy zmieni się baza (`jobs.py:2750–2752`). Taki zastępczy job ma tę samą tożsamość i ten sam zamrożony pin, ale inną bazę, więc inny `input_key`.
   - Skutek: kolejne ponowienie tej samej selekcji trwale kończy się `NEURAL_GRID_OPERATION_IDENTITY_AMBIGUOUS`, choć oba wiersze mają identyczny pin. To przeczy D-585/VISION_LAB („identyczne parametry to retry”). Bezpieczeństwo jest zachowane (fail-closed), cierpi żywotność. Test PG utrwala ten fałszywy alarm: zakłada duplikat z identycznym pinem (`left[1]`).
   - Minimalna poprawka: `SELECT DISTINCT input_payload -> :pin_key … LIMIT 2` (albo porównanie wierszy) i błąd tylko przy różnych pinach. W teście sprawdzić osobno: ten sam pin daje ten pin, różne piny dają AMBIGUOUS.

2. **Blokada odrzuca też ludzkie decyzje kwalifikacji zapisane w imporcie**
   - Miejsce: `services/worker/src/game_predictor_worker/images/pipeline_store.py:~686`.
   - Problem: dla jobów v3 blokada działa bez wyjątków. `geometryQualification` może jednak pochodzić z zapisanej po stronie serwera decyzji operatora w `geometry_guard_resolution_manifest` (`production_workflow.py:322–324`), a nie tylko z metadanych workera.
   - Skutek: decyzje operatora o częściowych planszach przy imporcie v3 nie dają zatwierdzenia, a plansze zostają `geometry_incomplete`. Operator musi powtórzyć pracę ręcznie. Kierunek jest bezpieczny i opisany w D-585, ale to regresja UX/żywotności.
   - Minimalna poprawka: nadawać pieczątkę tylko wtedy, gdy kwalifikacja dokładnie odpowiada decyzji z zaufanego manifestu w payloadzie joba (checksum decyzji). Albo jawnie zapisać to ograniczenie dla T5 i dodać test PG.

3. **Brak testu PG dla ścieżki IMPORT**
   - Miejsce: `job_repository.py:~584` (gałąź `:job_type='import'`).
   - Problem: test PG obejmuje tylko VALIDATE. Ścieżka IMPORT (filtr `v3_engine_acceptance_policy_version`, rzutowanie enum `job_type`, payload z `pipeline_fingerprint` dodawanym po pinie) ma tylko unit test na mocku sesji i test na repozytorium w pamięci (porównanie dictów w Pythonie, nie JSONB).
   - Skutek: błąd SQL lub różnica w porównaniu ujawni się dopiero w produkcji.
   - Minimalna poprawka: test PG cold retry dla `create_image_import` lub reprocessu przez `SqlAlchemyJobRepository`: ten sam pin, resolver nie wywołany.

4. **Test współbieżności nie dowodzi, że drugi prepare czekał na blokadzie**
   - Miejsce: `test_v3_engine_acceptance_postgres.py` (`test_exact_prepare_is_serialized…`).
   - Problem: `second_started` jest ustawiane przed `factory.begin()`.
   - Skutek: przy skrajnym przeplocie wątków test może przejść bez blokady. W praktyce jest to mało prawdopodobne.
   - Minimalna poprawka: przed `allow_commit` sprawdzić w `pg_locks` / `pg_stat_activity`, że drugi backend czeka na advisory lock.

Uwaga kosmetyczna: `_new_stage_adapters` (`production_workflow.py:~648`) porównuje politykę bezpośrednio, zamiast użyć nowego `is_game_scoped_neural_acceptance`.

## Zamknięcie uwag R1

| R1 | Stan | Dowód statyczny |
|---|---|---|
| P2-1 / P1 retry | **Zamknięte** | Dokładny lookup pod blokadą transakcyjną, bez okna historii. Unit test na mocku sesji dowodzi braku `list_jobs` i resolvera oraz kolejności: blokada przed zapytaniem. Test PG z publikacją pomiędzy dwoma prepare daje ten sam job i zamrożony `unqualified`. Pozostaje fałszywy alarm z P2-1 nowej listy. |
| P2-2 | **Zamknięte** | Każde z pól `evaluationId`, `evaluationSha256` i `publicationEvidenceSha256` jest psute osobno, z przeliczonym `pinSha256`, i daje STALE. Usunięcie dowolnej z trzech porównań w `recheck_operation_pin:826–831` zostałoby wykryte. Ponowna publikacja daje REVISION_CONFLICT, a symulowana podmiana read-modelu daje STALE. |
| P2-3 | **Zamknięte** | `__call__` używa `_new_stage_adapters` (delta `:614`). Test PG wywołuje tę prawdziwą metodę: `()` lub REQUIRED trafia do suite, wynik to `accepted` lub `needs_review`, bez UNCHECKED. |
| P2-4 | **Zamknięte** (dokumentacja) | D-585 i oba VISION_LAB opisują idempotencję i przyszłą wskazówkę T5. |
| P2-5 / P1 ludzkie zatwierdzenie | **Zamknięte** | Wspólny helper w obu gałęziach plus test PG v3/v2. Pozostaje ograniczenie z P2-2 nowej listy. |

**Zgodność historyczna:** v1/v2 zachowują pieczątkę, `crop_policy` i status. Pin nadal jest tylko dla v3. Nie ma migracji ani zmian API/OpenAPI w R2.

## Pokrycie kryteriów (tylko skutki R2)

- „Retry i restart nie podnoszą kwalifikacji”: spełnione, ze zastrzeżeniem żywotności z P2-1.
- „Worker nie tworzy ludzkiego zatwierdzenia ani GT”: spełnione.
- „Ponowne sprawdzenie dowodu przed automatycznym zapisem”: pokrycie testowe uzupełnione.
- Testy, lint, typecheck: formalnie nadal otwarte. Według deklaracji wykonawcy standardowy Admin tsc ma znany blocker z R1, a mypy zostaje z 5 błędami bazowymi (0 nowych).

## Listy

**Zamknięte:** R1 P2-1, P2-2, P2-3, P2-4, P2-5 oraz obie luki P1 koordynatora.

**Otwarte, nieblokujące:**
- nowe P2-1…P2-4,
- standardowy Admin typecheck (znany z R1),
- zamknięcie taska i commit.

## Proponowane testy

1. Preflight FAILED → zastąpienie z nową bazą → kolejne ponowienie: zwraca ten sam pin, nie AMBIGUOUS. Duplikat z innym pinem daje AMBIGUOUS.
2. PG cold retry IMPORT (świeży import i reprocess) przez prawdziwe repozytorium: resolver nie wywołany, ten sam pin.
3. Test współbieżności z asercją oczekiwania na advisory lock w `pg_locks`.
4. Strict v3 z `geometry_guard_resolution_manifest` zawierającym ludzką kwalifikację: zachowanie zgodne z decyzją z P2-2 nowej listy.

## Ograniczenia

- Przegląd statyczny, bez wykonania testów. Liczby PASS pochodzą z deklaracji wykonawcy.
- Spoza pakietu przeczytałem tylko celowane wycinki: `jobs.py:840–958`, `1480–1590`, `2150–2213` i `2745–2767`, `_bind_geometry_guard_policy`, `pin_v3_engine_acceptance_policy` oraz czytniki `geometry_qualification` (3 pliki). Dodatkowo `production_workflow.py:300–354`.
- Nie ustaliłem, czy w produkcji importy neural v3 faktycznie niosą ludzkie kwalifikacje z manifestu decyzji (to warunek P2-2 nowej listy).
