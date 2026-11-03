Werdykt: PASS

Audytor: claude-opus-5-5/high. Runda 1 (jedyna ponowiona próba po timeout transportowym, bez wcześniejszego werdyktu).
Baza: worktree `codex/full-board-detection`, HEAD `887d8a3b` (v1.7.559) plus niezacommitowane zmiany T2. Pakiet adaptive R1: index i części 01–06, deklarowany SHA256 `11ce470a…ada8`. Sumy SHA części nie zostały przeze mnie przeliczone, bo nie miałem shella.
Zakres: tylko T2 / TASK-1156 oraz autoryzowana poprawka P1 koordynatora w `project_source_geometry`. T3/T4 nie były oceniane.
Przegląd był wyłącznie statyczny (Read/Grep). Niczego nie zmieniałem i nie uruchamiałem testów, usług, bazy ani modeli. Wyniki testów biorę z deklaracji wykonawcy i przy każdym to zaznaczam.

## P0 / P1

Brak.

Poprawka P1 koordynatora jest zweryfikowana w kodzie. `pipeline_store.py:680–689`: przy zaufanej polityce joba `v3-engine-acceptance-v3` każda nowa rewizja dostaje status `needs_review`, niezależnie od workerowego `ready`, `rolloutMode`, `engineKind=manual_v1` czy `geometrySource=manual`. Podrobienie `manual_v1` daje dodatkowo `created_by≠V3 actor`, więc finalizer zwraca `REVISION_PROVENANCE_INVALID` i nie promuje rewizji. Polityki v1/v2 i brak polityki działają jak wcześniej.

Test `test_v3_forged_ready_is_not_accepted_before_recognition` (neural/manual) rzeczywiście odtwarza regresję. Przed poprawką oba warianty zapisałyby `accepted` w pierwszej transakcji. Test czyta stan świeżą sesją i zawęża sprawdzenie do SHA nowego kandydata. Jest też test dodatni: promocja następuje tylko w finalizerze, a zapieczętowane SHA, payload i `globalInitialization` pozostają identyczne.

## P2 (5)

1. **`services/api/src/game_predictor_api/application/jobs.py:405` (`_pin_neural_operation`)**
   - Problem: ponowne użycie pinu opiera się na `list_jobs(..., limit=10_000)` i liniowym porównaniu payloadów, bez gwarancji kolejności i bez blokady.
   - Skutek: retry po utracie odpowiedzi może utworzyć nowy pin w trzech sytuacjach: gra ma więcej niż 10 tys. jobów danego typu, istnieją dwa dopasowania albo dwa współbieżne prepare przypadną na moment publikacji raportu. Nowy pin oznacza inny `input_key`, czyli duplikat joba z podniesioną kwalifikacją. Łamie to kryterium „retry nie podnosi” w przypadkach brzegowych. Dochodzi też koszt O(N) przy każdym prepare.
   - Minimalna poprawka: deterministyczny lookup po skrócie stabilnej tożsamości (albo zapytanie bez limitu) plus blokada per gra (`acquire_job_admission` / advisory lock) przed resolverem. Po osiągnięciu limitu system powinien odmówić (fail-closed), a nie mintować nowy pin.

2. **`services/api/src/game_predictor_api/storage/neural_grid_operation_qualification.py:97` (`recheck_operation_pin`) oraz test `services/api/tests/integration/test_v3_engine_acceptance_postgres.py:389`**
   - Problem: gałąź porównująca `evaluationId`, `evaluationSha256` i `publicationEvidenceSha256` z bieżącą publikacją nie ma testu. Test unieważnienia przechodzi przez wyjątek `_evidence`. Wariant PG `forged_game_evidence=True` przechodzi, bo snapshot jest historyczny (`for_game`, więc `historical_evidence` daje REQUIRED), a nie dzięki wykryciu niezgodnego ID/SHA.
   - Skutek: regresja w porównaniu, np. przy ponownej publikacji wersji z innym raportem, przeszłaby niezauważona.
   - Minimalna poprawka: test z opublikowanym raportem dla tej gry i pinem o obcym `evaluationId`/SHA, oczekujący `NEURAL_GRID_GAME_EVALUATION_STALE`. Drugi test: ponowna publikacja z nowym raportem, gdzie stary pin też daje STALE.

3. **`services/worker/src/game_predictor_worker/images/production_workflow.py:653`**
   - Problem: ścieżka workera, w której recheck odbywa się przed `ProductionImageStageAdapterSuite`, nie jest wykonywana przez żaden test. Testy PG wstrzykują `qualification_blockers` bezpośrednio do suite.
   - Skutek: bezpieczeństwo trzyma finalizer, ale błąd w tej ścieżce (np. `None`, czyli `UNCHECKED`) po cichu zablokowałby automat dla każdej kwalifikowanej gry w produkcji.
   - Minimalna poprawka: test workflow (choćby na repozytorium w pamięci) sprawdzający, że kwalifikowany pin daje `()`, a niekwalifikowany `GAME_EVALUATION_REQUIRED`, przekazane do `neural_pending_payload`.

4. **`jobs.py:405` w połączeniu z wywołaniami ok. `jobs.py:960` (świeży import) i `:2260` (preflight)**
   - Problem: tożsamość pomija pochodny `pipeline_fingerprint`. Dla tej samej selekcji i manifestu kwalifikacja jest więc zamrożona na zawsze: po publikacji raportu gry ponowny import lub reprocess tej samej selekcji dostaje stary pin `unqualified` (albo dedupe zwraca stary job). Jeśli świeży import nie ma osobnego klucza wersji kodu, nowy job po deployu też odziedziczy stary pin.
   - Skutek: to nie jest problem bezpieczeństwa, tylko żywotności i UX. Jedyną drogą do automatu dla istniejących danych pozostaje grid reinference (nowy pin przy każdym prepare).
   - Minimalna poprawka: udokumentować to w D-585/VISION_LAB i w komunikacie Admin albo dodać jawny klucz żądania. Plus test potwierdzający zamierzone zachowanie.

5. **`services/worker/src/game_predictor_worker/images/pipeline_store.py:680` (kod istniejący, poza zakresem T2)**
   - Problem: `project_recognition` nadaje `approved_geometry_revision=0` z aktorem `system:import-qualified-manual-geometry` na podstawie workerowego `cropped.geometryQualification`. Gate liczy `geometry_approved` niezależnie od statusu rewizji i pinu v3. Finalizer blokuje status rewizji (`approved_geometry_revision is None`), ale gate może dać OK.
   - Skutek: przy modelu zagrożeń „worker nie jest zaufany” to potencjalna furtka obejścia kwalifikacji gry. Ze statycznego pakietu nie da się stwierdzić, czy ścieżka neural v3 w ogóle emituje to pole.
   - Minimalna poprawka: test PG, w którym job v3 z podrobionym `geometryQualification` nie kończy się `geometry_complete`, albo ograniczenie tej gałęzi do jobów spoza acceptance-v3. Można to zrobić w osobnym tasku.

## Pokrycie kryteriów

| Kryterium | Ocena statyczna |
|---|---|
| Układ 3×5 i strona 3×3 sprawdzane przed inferencją; źródło zachowane | **Zamknięte.** Topologia gry jest sprawdzana w `_pin_neural_operation` i `grid_reinference.prepare`. Topologia modelu: `validate_manifest` (`domain/grid_model_registry.py:192–198`) wymusza screen 3×3, board 5/3 (nazwy osi catalogue-v1) i capabilities. Adapter odwraca nazwy osi bez zmiany SHA. Worker v14 odrzuca brakujący lub niezgodny pin przed runnerem (test: `runner.calls == 0`). Błąd na API następuje przed utworzeniem joba. |
| Nowa gra bez exact PASS dostaje wyłącznie propozycje | **Zamknięte.** Pin `unqualified` daje `GAME_EVALUATION_REQUIRED` w workerze, w `qualify` i w writerach. Historyczne dopuszczenie modelu jest traktowane jako REQUIRED, a raport innej gry daje „outside scope”. Są testy jednostkowe i PG. |
| v3 przypina raport albo `unqualified`; restart i retry nie podnoszą kwalifikacji | **Zamknięte, z zastrzeżeniem P2-1.** Pin jest częścią payloadu i fingerprintu. Cold retry odzyskuje pin przed resolverem (test z resolverem, który przy powtórzeniu rzuca błąd). Pin `unqualified` nigdy nie przechodzi rechecku. |
| API recheckuje dowód przed automatycznym zapisem; currentness nie jest zastępowane innym raportem | **Zamknięte, z luką testową P2-2.** Finalizer działa w tej samej transakcji recognition (commit przy wyjściu z `session.begin()`). Writer reinference robi recheck przed zapisem i w kwalifikacji. Porównywane są dokładne ID/SHA raportu i publikacji, a D-559 jest sprawdzane przez `_require_current`. Błędy infrastruktury są propagowane. |
| Historyczne v1/v2 bez zmian; nieznane lub brakujące nowe piny blokowane | **Zamknięte.** `crop_policy_for_acceptance` mapuje v3 na crop-v2, a v1/v2 bez zmian. Pole `operationPin` jest dodawane tylko dla v3. Legacy preflight z pinem jest odrzucany. Pin jest usuwany z odpowiedzi JSON. Deklarowane testy PG v1/v2 i cold replay: 6 PASS. |
| Testy, lint/typecheck, docs PASS, audyt przed commitem | **Otwarte formalnie.** Według deklaracji wykonawcy standardowy Admin typecheck nie przechodzi (stary klient przez junction); PASS jest tylko w izolowanym worktree. W mypy zostają błędy z bazy HEAD559. Pełne `npm run quality` nie było uruchamiane. |

## Listy

**Zamknięte:**
- P1 koordynatora (wcześniejsze `accepted`).
- Granice transakcji: geometria i recognition to osobne transakcje, finalizer działa bez własnego commitu.
- Wiązanie pinu z grą, modelem, manifestem, regułami i SHA.
- Pin usuwany z publicznego JSON-u.
- OpenAPI i wygenerowany klient zaktualizowane razem ze schematem.
- Parser Admin rozpoznaje v13 i v14.

**Otwarte (P2, nieblokujące):** P2-1 do P2-5 powyżej, standardowy Admin typecheck oraz zamknięcie taska/commit.

## Proponowane testy

1. Pin z obcym `evaluationId`/SHA przy opublikowanym raporcie gry daje STALE (P2-2).
2. Ponowna publikacja wersji z nowym raportem: stary pin daje STALE, nowy prepare daje `qualified`.
3. `ProductionImageImportWorkflow` przekazuje wynik rechecku do suite (P2-3).
4. `_pin_neural_operation`: więcej dopasowań niż limit, dwa dopasowania i współbieżne prepare (P2-1).
5. PG: job v3 z podrobionym `geometryQualification` nie daje `geometry_complete` (P2-5).
6. Restart po zapisanych etapach, gdy kwalifikacja zmieniła się między uruchomieniami: zapieczętowany payload zostaje, a status ustala tylko finalizer.

## Ograniczenia

- Przegląd statyczny, bez wykonania testów. Liczby PASS i czasy pochodzą z deklaracji wykonawcy.
- Nie sprawdzałem SHA części pakietu.
- Spoza pakietu przeczytałem tylko dwa wycinki: `validate_manifest` (topologia), żeby potwierdzić kryterium 3×3/3×5, oraz `grid_engine_acceptance_repository.py:575–642`. Ten drugi writer używa jawnie polityki v1 dla historycznych projekcji i nie oceniałem go jako części T2.
- Nie da się stąd ustalić, czy produkcyjny etap cropów v3 emituje `geometryQualification` (P2-5).
- Testy działają na syntetycznych rekordach serwera i nie dowodzą rzeczywistej kwalifikacji modelu dla żadnej gry. Silniejsza kalibracja T4 jest poza zakresem.