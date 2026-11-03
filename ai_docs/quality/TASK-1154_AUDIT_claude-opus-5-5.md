# Audyt statyczny TASK-1154 / T0

- **Audytor:** claude-opus-5-5 / high
- **Wykonawca:** gpt-6-astra / high
- **Runda:** 1, druga próba transportowa (pierwsza przekroczyła limit czasu bez werdyktu)
- **Baza:** `448f75e7`, kod zamrożony

## Zakres i ograniczenia

- Przeczytałem cały `artifacts/audits/TASK1154-scoped-review.md`. Zawiera task, kryteria T0, wyniki wykonawcy, D-584 i pełny diff z nowym testem i fixture.
- Kontekst bieżących plików czytałem tylko punktowo:
  - `grid_reinference_handler.py`: wywołanie `recognize`, budowa checkpointu, `load_checkpoint`, wywołanie zapisu automatic;
  - `storage/grid_reinference.py`: `prepare` i `view`;
  - `v3_engine_acceptance.py`: pin i `qualify`;
  - `neural_pending_geometry.py`;
  - `production_workflow.py`: przekazanie pinów;
  - `pipeline_store.py:715-764`;
  - `geometry_core/inference.py:232-253`.
- **Nie uruchamiałem żadnych testów, lintu, mypy ani usług** i nie korzystałem z bazy. Wyniki 84 + 13 + 4 PASS, ruff, docs i code-map pochodzą od wykonawcy. Uznaję je za deklarowane dowody; nie potwierdzałem ich.
- Nie oceniałem T1–T6, capabilities (T2), kalibracji ani kompletności kraty (T4). Statusowego backfillu v1 też nie, zgodnie z poleceniem.

## Podsumowanie

Kod domyka cel T0:
- Wspólna czysta funkcja `neural_auto_crop_blockers` jest używana przez workera (`neural_pending_payload`, reinferencję) i przez API (`qualify_v3_engine_acceptance`, `full_neural_prediction_geometry`, guard zapisu automatic).
- Gałąź v1 odtwarza dawną decyzję 1:1.
- Checkpoint v1 jest bajtowo niezmieniony: nie ma klucza `executionPolicy`, więc ma ten sam sha.
- v2 blokuje kody FIT. Fallback po FIT_FAILED zawsze niesie kod `NEURAL_GRID_FIT_FAILED` (`geometry_core/inference.py:249`), więc blokada nie zależy od kształtu geometrii.

Nie znalazłem otwartych P0/P1.

## P0 / P1

Brak.

## P2 (najwyżej 5)

1. **`services/api/src/game_predictor_api/domain/neural_crop_policy.py:~196-209` oraz konsument `storage/image_geometry_completeness_state_repository.py:504`**
   - **Problem:** w v2 `full_neural_prediction_geometry` sprawdza tylko spójność dowodu zapisanego w samej geometrii (`neuralAcceptanceEvidence` plus własne węzły). Nie porównuje go z przypiętą propozycją. Takie porównanie robią tylko `qualify_v3_engine_acceptance` i guard w `virtual_grid_geometry_repository.py:173-232`.
   - **Skutek:** projekcja kompletności może uznać za „pełną” geometrię ze sfałszowanym czystym dowodem. Status akceptacji i zapis automatic nadal zostaną zablokowane.
   - **Minimalna poprawka:** udokumentować, że ta funkcja daje tylko kwalifikację spójności, albo przekazać tam wykrycie z propozycji, gdy jest dostępne. Do tego test negatywny.

2. **`neural_crop_policy.py:~88` (`1 <= end - start + 1 <= 9`)**
   - **Problem:** limit 9 pozycji jest zaszyty w kodzie, równolegle do inwariantów `validate_neural_source_binding`.
   - **Skutek:** wynik jest fail-closed, ale przy zmianie limitu w domenie v2 po cichu przełączy się na review. Nie mylę tego z `expectedLayoutCount`, który kod słusznie pomija.
   - **Minimalna poprawka:** użyć wspólnej stałej z `neural_grid_proposal` albo zostawić komentarz z odwołaniem.

3. **Parametr `valid_pixel_box` (`neural_crop_policy.py`)**
   - **Problem:** w produkcji parametr nie jest nigdzie przekazywany. Ustawia go tylko test `pixels`. Kontrola retained crop zależy od `require_inside_valid_box` w workerze (`grid_reinference_handler.py:532-549`) i od renderera. Guard API sprawdza wyłącznie granice obrazu.
   - **Skutek:** to zgodne z planem („crop musi przejść obecny renderer”), ale nazwa sugeruje wspólną kontrolę pikseli API/worker, której nie ma.
   - **Minimalna poprawka:** przekazać pole z `frame.crop` albo dopisać w docstringu, że kontrolę egzekwuje renderer i worker.

4. **Regresja 462205 (`services/api/tests/test_neural_auto_crop_v2.py`, `test_recorded_462205_...`)**
   - **Problem:** test ręcznie mapuje `reasons` na `reasonCodes`. Test PostgreSQL wstrzykuje kod FIT bezpośrednio do `reasonCodes`. Nie zweryfikowałem statycznie, w zadanym budżecie, że produkcyjna serializacja `detection.reasons` do `reasonCodes` w propozycji zachowuje kody FIT.
   - **Skutek:** gdyby to mapowanie gubiło kody, v2 przepuściłoby FIT_OUTLIERS mimo zielonych testów.
   - **Minimalna poprawka:** test jednostkowy od obiektu wykrycia z `reasons=["NEURAL_GRID_FIT_OUTLIERS"]` przez `raw_inference` / `build_neural_source_proposal` do `neural_auto_crop_blockers`.

5. **`virtual_grid_geometry_repository.py:206-232` w połączeniu z `grid_reinference_handler.py:373`**
   - **Problem:** guard rzuca `ImageGridReviewError` dla całego źródła. Nie widzę testu, że w handlerze kończy się to deterministycznym wynikiem z rollbackiem, a nie samym błędem joba. Normalnie nie powinno się to zdarzyć, bo `automatic_blockers` wcześniej wyklucza pozycje z `good`.
   - **Skutek:** zachowanie jest fail-closed, ale niespójny stan może zostać zgłoszony jako awaria joba zamiast `needs_manual_review`.
   - **Minimalna poprawka:** test integracyjny z checkpointem, którego dowód różni się od propozycji. Oczekiwane: brak zapisu i jawny outcome.

## Pokrycie kryteriów T0 (statycznie)

| Kryterium | Ocena | Dowód |
|---|---|---|
| FIT_FAILED (fallback) i FIT_OUTLIERS nie dają automatic w v2 | Zamknięte | `NEURAL_AUTO_CROP_BLOCKING_REASONS`; `neural_pending_geometry.py:115-131`; `automatic_blockers` (handler 577-589, 329-335, 768); `qualify_v3` 650-662; kod fallbacku `inference.py:249` |
| API ponownie kwalifikuje i nie ufa deklaracji automatic | Zamknięte (uwaga P2-1) | Guard `virtual_grid_geometry_repository.py:173-232` działa przed `acquire_sequence_ownership_lock`. Porównuje propozycję, snapshot, grę, checksum, binding, węzły i dowód. `qualify_v3` porównuje dowód z wykryciem propozycji z immutable payloadu importu. `structuredDisposition` nie jest wejściem kwalifikacji. |
| Niepełne przypisanie, zła geometria, brak pikseli, nieobsługiwany układ blokują | Zamknięte | Gałąź v2 `neural_auto_crop_blockers`: binding (missing, duplikaty, zakres, para pozycja–detekcja), `lattice_cell_quads`/`lattice_visibility` liczone od nowa, `(rows, columns) != (3, 5)`. Topologia jest przekazywana z workflow i z guarda. |
| v1 zachowuje decyzję, payload, fingerprint i checkpoint; nieznana wersja blokuje | Zamknięte | Gałąź legacy jest identyczna z dawnym warunkiem. Checkpoint v1 nie dostaje `executionPolicy`, więc ten sam sha. Geometria v1 jest bez `neuralAcceptanceEvidence`. Pin i fingerprint obu polityk są ustawiane razem tylko przy nowym imporcie (`application/jobs.py:876-881`, `1506-1511`); `prepare` reinferencji przypina v2 w payloadzie, dokumencie i `scopeSignature`, a replay `prepare` zwraca starą operację (`storage/grid_reinference.py:243-246`). Nieznana wersja jest odrzucana w każdej warstwie: schema `Literal`, `storage/grid_reinference.py:456`, `require_checkpoint_policy(None)`, `production_workflow.py:1526-1549` (także niespójna para), `finalize` 867-869, `crop_policy_for_acceptance` w guardzie. |
| Blokady sekwencji, pochodzenie rewizji i ochrona ręcznych decyzji | Zamknięte | `lateral_reprocess_protection.py` obejmuje teraz v1 i v2, więc nowe joby v2 nie omijają locka. `finalize` dodatkowo wiąże `engine_version` z oboma pinami. `target_protection` i ścieżka `grid_issue` → `proposal_ready` są bez zmian. Guard jest addytywny i nie zastępuje kontroli właściciela, rewizji ani checksumu. |
| 462205 z zapisanymi przyczynami, bez nowej inferencji | Zamknięte (uwaga P2-4) | Fixture zawiera zapisane węzły i `NEURAL_GRID_FIT_OUTLIERS`: v1 daje `()`, v2 blokuje. To zachowany wynik FIT_OUTLIERS, nie niezależny GT. |
| Testy, lint, typecheck, pion kontraktu, docs, mapa | Deklarowane przez wykonawcę, ja nie uruchamiałem | Pion kontraktu jest spójny statycznie: schema `Literal` v1/v2 → `openapi.json` (enum) → `types.gen.ts` → test wrappera SDK. Nie ma nowych tras ani pól. |

## Otwarte / zamknięte

- **Otwarte:** P2-1 do P2-5, wszystkie niewymagające. Rozliczenie audytu przed commitem leży po stronie roota.
- **Zamknięte:**
  - współdzielona kwalifikacja API/worker;
  - FIT_FAILED/FIT_OUTLIERS w v2;
  - recheck przed zapisem automatic;
  - piny v1/v2 przy restart/retry i lost reply;
  - odrzucanie nieznanej wersji i niespójnej pary;
  - blokady sekwencji i właściciela;
  - zachowanie human corrections;
  - historyczny backfill v1 bez zmian (`grid_engine_acceptance_repository.py:510-513`, `613`);
  - `expectedLayoutCount` nieużywany jako liczba plansz.

## Proponowane testy

1. Ścieżka od `detection.reasons` (FIT_OUTLIERS i FIT_FAILED z fallbackiem `grid_from_quad`) do propozycji i do blockers v2 (P2-4).
2. `full_neural_prediction_geometry` v2 z czystym dowodem w geometrii przy propozycji z kodem FIT. Należy udokumentować oczekiwany wynik projekcji kompletności (P2-1).
3. Handler reinferencji z rozbieżnym `neuralAcceptanceEvidence`: wynik, rollback, zero zapisów (P2-5).
4. Operacja v1 przygotowana przed zmianą i wznowiona po niej, z zapisem automatic: ta sama geometria i ten sam sha zapisu.

## Ograniczenia raportu

To wyłącznie analiza statyczna wskazanego diffu i kontekstu. Wyniki testów są deklaracją wykonawcy. Raport nie twierdzi niczego o jakości modelu ani o wykrywaniu poprawnych, ale niepełnych krat (T4). Nie stanowi niezależnego GT dla 462205.

Werdykt: PASS
