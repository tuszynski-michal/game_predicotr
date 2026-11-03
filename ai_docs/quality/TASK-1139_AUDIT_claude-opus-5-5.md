# Audyt TASK-1139 — Przyrostowy podział i prawdziwe liczniki

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: drzewo R1 6ef0ee05702b6704a902de03aabd17cc57205aa4...drzewo R2 761c58d627008d00edf80150612b9566ffd134a4 (poprawki po R1, niezacommitowane na HEAD 3562ab1a868ae26cb2c36bf453197c1790561015), data 2026-11-03
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem wyłącznie poprawki do uwag R1 na podstawie dokładnego diffu i wyników wykonawcy w `artifacts/audits/TASK-1139_R2_FOCUSED.md`.

- Oba P1 są zamknięte. Downgrade 0172 odmawia teraz tylko przy istniejącej historii i odtwarza funkcje z 0171. Zewnętrzne ochrony SQL (holdout, ancestor, use, role head, sesja, konflikt, ochrona bez roli) mają test na prawdziwym capability.
- Wszystkie pięć P2 z R1 poprawiono albo jawnie udokumentowano.
- W samych poprawkach nie znalazłem nowych P0 ani P1.
- Ryzyko szczątkowe: dwa pliki testów reinference nie mają dowodu pełnego przejścia. Jeden test kończy się FAIL, który wykonawca uznaje za zastany, bez dowodu bazowego. Drugi plik przerwał limit czasu. Prowadzący powinien to rozstrzygnąć przed commitem.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-6] `services/api/tests/integration/test_grid_reinference_postgres.py:43` — wykonawca raportuje 6 PASS, a potem FAIL `cleanup_reset` (FK RESTRICT przy usuwaniu review items). `test_grid_reinference_stats_postgres.py` przerwał limit 120 s i nie ma wyniku.
  - Fixture modułu, czyli zejście z head do 0158 i ponowny upgrade (`grid_reinference_schema_support.py:72`), przeszedł, skoro sześć testów wykonało się po nim. Przyczyna z R1 (P1-1) jest więc usunięta.
  - Poprawki nie dotykają `reset_game` ani review items. Twierdzenie, że FAIL jest zastany, nie ma jednak dowodu porównawczego na HEAD v1.7.536.
  - Proponuję, aby prowadzący przed commitem uruchomił `cleanup_reset` na bazowym HEAD albo zapisał to ryzyko w `Outcome`.

- [P2-7] `services/api/src/game_predictor_api/storage/source_recording_sql_v6.py:83` — nowe `unspecified_protection` (linie 83–85) i gałąź `allowed` (linia 94) działają także w `recording_photo_context_v1`, bo ta funkcja korzysta z `context_data_v2(preview=false)`.
  - Skutek: użyty członek historycznej kohorty v1, którego grupa ma dowód holdout/ancestor/use bez roli, przestaje przechodzić `validate_cohort_use`. Przed 0172 role-less evidence było ignorowane, bo v4 filtrował `payload ? 'role'`. Test `_grid_correction_growth_protections.py:228` potwierdza to zachowanie celowo, ale dla członka nieużytego.
  - Na danych operatora wpływ jest zerowy: preflight nie znalazł `recording_occurrences`, więc brak grup. Zapis w `API_CONTRACT.md` („Zamrożone kohorty pozostają weryfikowalne”) jest jednak ogólniejszy niż faktyczne zachowanie.
  - Proponuję dopisać ten wyjątek fail-closed do API_CONTRACT lub D-582 albo zaakceptować ryzyko w `Outcome`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Stare metadane bez użycia mogą bezpiecznie zwiększyć TRAIN | spełnione | jak w R1; `test_grid_correction_registry_postgres.py:289`; symulacja: TRAIN 146 plansz = 77 + 69 |
| Rzeczywiste kontrole i historia pozostają chronione i weryfikowalne | spełnione (z zastrzeżeniem P2-7) | `source_recording_sql_v6.py:83-94`; `_grid_correction_growth_protections.py:84-240` (siedem konfiguracji, brak zwolnień, proof bez zmian); historyczny wyjątek tylko po zapisanym release: `source_recording_sql_v6.py:182-185` |
| Freeze atomowo zapisuje zwolnienia i przydziały; preview niczego nie zmienia | spełnione | bez zmian względem R1; registry lifecycle 1 PASS (45,83 s, deklaracja wykonawcy) |
| Rezerwa nieopisanych kontroli najwyżej pięć zdjęć na rolę | spełnione | `grid_correction_incremental_split.py:93-119`; `test_grid_correction_incremental_split.py:148` (1255 źródeł, budżet 10 000, dokładnie 5 rezerw, deterministyczność) |
| Minima, atesty, nierozdzielne grupy i bufory dziesięciu zdjęć obowiązują | spełnione | bez zmian względem R1 |
| Jednostki liczników, deduplikacja i powody wyłączeń są jawne | spełnione | `grid_correction_progress.py:40-48`; `test_grid_correction_incremental_split.py:127`; `API_CONTRACT.md` (blok TASK-1139: `usedTrain`, reprezentant kopii, `GRID_CORRECTION_CONTROL_NOT_PENDING`) |
| Testy domenowe, PostgreSQL, kontrakt i wymagane kontrole przechodzą | niezweryfikowane (częściowo) | Deklaracje wykonawcy: domena/adapter/readiness 54 PASS, guarded migration 1 PASS, recording migration lifecycle 5 PASS, source crop runs 4 PASS, evaluation bridge 1 PASS. Reinference: `cleanup_reset` FAIL bez dowodu bazowego, stats przerwany limitem czasu (P2-6). Zastany FAIL `test_shared_candidate_rejects_correction_policy_before_creating_plan` udokumentowany. Wyników nie uruchamiałem. |

## Listy zamknięte i otwarte

Zamknięte:
- **P1-1:** `services/api/alembic/versions/0172_grid_correction_growth.py:54-86`.
  - Odmowa następuje tylko przy wierszach w `recording_photo_reservation_releases` albo `reservation_policy='incremental-v2'`, pod tymi samymi blokadami doradczymi co register.
  - Downgrade odtwarza `recording_photo_context_v1` i `recording_photo_cohort_v1` z v4 oraz wrapper v5, czyli dokładny stan 0171. Potem usuwa SAFE/INTERNAL, tabelę zwolnień i kolumnę.
  - Test `test_grid_correction_growth_migration_postgres.py:21` sprawdza pustą ścieżkę 0172 → 0171 → head, odtworzoną definicję v1 i obie blokady historii (linia 59).
  - Istniejące testy migracji schodzące z head przechodzą według deklaracji wykonawcy.
  - `schema_readiness.py:18` wymaga 0172, więc API nie wystartuje cicho na bazie 0171.
- **P1-2:** `services/api/tests/integration/_grid_correction_growth_protections.py:84`, wywołane z `test_grid_correction_registry_postgres.py:302`.
  - Pokryte są holdout, ancestor, use, role head, sesja z użyciem innego zdjęcia, sprzeczne role i ochrona bez roli.
  - Register daje `RECORDING_ROLE_CONFLICT`, kontekst po odmowie jest identyczny, a zwolnień jest 0 (linie 228–240).
  - Poziom adaptera pokrywa `test_grid_correction_split_adapter.py:252` (`GRID_CORRECTION_PROTECTION_CONFLICT`).
- **P2-1:** `storage/grid_correction_split.py:281` — adapter v1 nie dołącza `aliasComponentIds`, a `recording_photo_context_v1` je usuwa. `API_CONTRACT.md` opisuje konieczność nowego preview dla niezamrożonych draftów v1 sprzed 0172. Szczątkowa zmiana semantyki v1 jest opisana w P2-7.
- **P2-2:**
  - `domain/grid_correction_progress.py:40-48` — rezerwa obejmuje tylko `pendingCorrection`. Pozostałe kontrole bez etykiet trafiają do wykluczeń z powodem `GRID_CORRECTION_CONTROL_NOT_PENDING`.
  - `storage/grid_correction_split.py:26` (`previously_used_train_boards`) — zmieniony reprezentant identycznej pikselowo kopii zachowuje użycie po pikselach, pozycji i węzłach. Rewizja własnego źródła nadal musi się zgadzać dokładnie.
  - Testy: `test_grid_correction_split_adapter.py:287` i `_grid_correction_growth_protections.py:13`.
- **P2-3:** `source_recording_sql_v6.py` (`aliasComponentIds`) — zwracane są skróty `recording_digest_v1` z rodzajem aliasu, bez surowych sum. Test `_grid_correction_growth_protections.py` sprawdza brak `byte:`/`pixel:` i surowych hashy sesji.
- **P2-4:** `grid_correction_incremental_split.py:93-119` — odległości liczone są liniowo, dwoma przebiegami na import i rolę. Semantyka jest zachowana, bo kandydaci powstają przed przydziałem, jak w R1. Test 1255 źródeł mieści się w 10 000 kroków.
- **P2-5:** `source_recording_sql_v6.py:182-185` — pominięcie kontroli roli nieużytego członka v1 wymaga wpisu release z kluczem `(wanted, cohort, source.id)`. Bez zwolnienia konflikt nadal odmawia (`_grid_correction_growth_protections.py:228`).

Otwarte: P2-6, P2-7.

## Proponowane testy

- `cleanup_reset` z `services/api/tests/integration/test_grid_reinference_postgres.py` na bazowym HEAD v1.7.536 (disposable DB, `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`, timeout ≤120 s na komendę) jako dowód, że FAIL jest zastany. Ponadto `test_grid_reinference_stats_postgres.py` w pojedynczych scenariuszach (`-k accepted` itd.), aby zmieścić się w limicie.
- W `test_grid_correction_registry_postgres.py`: użyty członek historycznej kohorty v1 w grupie z dowodem bez roli. Test ma jawnie przypiąć oczekiwany wynik `validate_cohort_use` (P2-7).

## Zakres przeglądu i ograniczenia

To runda 2, przegląd ukierunkowany wyłącznie na poprawki uwag R1 (`ai_docs/quality/TASK-1139_AUDIT_claude-opus-5-5_R1.md`) i ewentualne regresje wprowadzone przez te poprawki. Runda 1 była wznowiona po limicie czasu w tej samej sesji.

Przeczytałem cały `artifacts/audits/TASK-1139_R2_FOCUSED.md`: dokładny diff R1 → R2 oraz rozliczenie testów wykonawcy. Odtworzenie stanu 0171 w downgrade oceniłem na podstawie znanych z R1 plików `source_recording_sql_v4.py`, `source_recording_sql_v5.py` i `0170_grid_correction_photo_roles.py`.

Nie uruchamiałem testów, lintu, typecheck, PostgreSQL ani docs:check. Wszystkie wyniki testów to deklaracje wykonawcy z logów `artifacts/task1139-r1-*.log`, których nie czytałem. Numery linii w nowych plikach testowych i hunkach wyliczyłem z diffu.

Zgodnie z poleceniem nie oceniałem braku commita, mapy kodu, docs:check ani zamknięcia taska; należą do prowadzącego. Przypominam, że `EXPECTED_ALEMBIC_HEAD` = 0172 wymaga migracji operatora przed uruchomieniem nowego API. Według AGENTS.md niewykonana wymagana migracja blokuje merge.
