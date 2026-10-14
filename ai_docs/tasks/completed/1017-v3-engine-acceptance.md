---
title: TASK-1017 — Akceptacja nowych wyników przez silnik V3
status: done
last_updated: 2026-10-14
---

# TASK-1017 — Akceptacja nowych wyników przez silnik V3

## Status

`done`

## Goal

Nowa poprawna rewizja otrzymuje właściwy stan akceptacji silnika.

## Context

Task jest częścią zaakceptowanej rewizji 6. Akceptacja silnika i pochodzenie danych. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1010 done, v1.7.368 / `02f38d6cb731dfc06001a1c6fc819ee4927acba1`; D-550 i D-552 accepted z wcześniejszych jawnych poleceń operatora. Historyczny backfill nadal nie jest zlecony.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. D-550/D-552 przyjęto przed tym zadaniem; pozostałe proponowane decyzje wymagają udokumentowanego przyjęcia przed ich zależnymi zmianami.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. zmiana kwalifikacji danych produkcyjnych.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [IMAGE_INGESTION](../../requirements/IMAGE_INGESTION.md).
- [VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP](../../architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md).
- Zakres odczytu uzupełniający z planu: IMAGE_INGESTION, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP, D-484/D-523/D-541.

- [D-484](../../process/decisions/DECISION_LOG_2026.md#d-484--kompletność-geometrii-zdjęcia-jest-bramką-przed-cięciem-na-symbole) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-523](../../process/decisions/DECISION_LOG_2026.md#d-523--operational-neural-crops-and-recoverable-symbol-verification) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-541](../../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

- [D-550](../../process/decisions/DECISION_LOG_2026.md#d-550--akceptacja-silnika-v3-i-statusowy-backfill) — przyjęta polityka, bez zgody na wykonanie historycznego backfillu.

## Scope

- Zastąpić bezwarunkowe `needs_review` oceną kompletu pozycji i pochodzenia.
- Zachować odrębność engine/human approval.
- Aktualizacja statusu i projekcji należy do transakcji istniejącego zapisu.

## Out of scope

- Bez historycznego backfillu i bez poluzowania bramki jakości.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Komplet zgodnych pozycji może zostać przyjęty; deferred, partial, konflikt lub błąd blokuje akceptację.
- [x] Żaden przypadek nie ustawia ręcznego zatwierdzenia.
- [x] Stare snapshoty pozostają czytelne.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Implementacja kwalifikuje wyłącznie pierwotną geometrię nowego importu (`geometry_revision=0`, owner tego samego joba). Nie jest ogólnym writerem reinferencji TASK-0999. Dowód w `globalInitialization.v3EngineAcceptance` powstaje wyłącznie przed pierwszym zapisem payloadu nowej polityki; jego konsumenci w source repository/manual correction przechowują obiekt jako metadane. Walidator stage zachowuje zgodność historycznej postaci. Worker nie dodaje nowego pinu podczas decode/resume. Retry przechowuje payload, checksumę i geometry engine crop version. Nieaktualna source rewizja nie jest przepisywana. `grid_issue` blokuje tylko aktualną komórkę pending z bieżącą geometry_revision/source_geometry_revision_id i virtual_source; historyczny zapis pozostaje zachowany.

`neural_pending_payload` zachowuje dziś `needs_review`; zapis geometrii i zapis rozpoznania są osobnymi transakcjami. `project_source_geometry` uznaje `ready` za accepted tylko w klasycznym rolloutMode. Nowej akceptacji nie wolno nadać przed kontrolą rzeczywiście zapisanych plansz i właścicieli. Wydzielić czystą, wersjonowaną kwalifikację V3. Finalizować po `project_recognition` w tej samej transakcji co bramka i projekcje. Sprawdzić komplet oczekiwanych slotów, source/model/checksum binding, jednoznaczne sekwencje, bieżącą rewizję i aktualne zgłoszenia. Konflikt/deferred/partial oznacza brak engine approval, bez poluzowania crop gate.

Politykę przypiąć przy tworzeniu nowego joba/fingerprintu. Historyczny job bez nowej wersji polityki zachowuje dotychczasowy wynik przy retry. Istniejące provenance `geometry_source=auto`, `engine_kind`, `engine_version`, `created_by` i status źródła muszą odróżniać engine approval; nie ustawiać `approved_geometry_revision` ani `geometry_approved_by`. Nie zmieniać hashy/payloadu zapisanej geometrii i decyzji człowieka. Zachować D-523 materializację pełnych neural slotów oraz diagnostykę uncalibrated — engine approval nie jest oceną pikseli. Przed kodowaniem wykonawca doprecyzowuje dokładne symbole i testy w tym miejscu; sprzeczność wymaga zgłoszenia, bez ukrytej zmiany modelu.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Potwierdzony zakres przed kodowaniem: nowe `domain/v3_engine_acceptance.py` (`pin_v3_engine_acceptance_policy`, `qualify_v3_engine_acceptance`) i `storage/v3_engine_acceptance_repository.py` (`finalize_v3_engine_acceptance`). Istniejące `application/jobs.py` przypina politykę przy obu nowych jobach importu; `images/production_workflow.py` i `neural_pending_geometry.py` przekazują immutable dowód proposal/binding w `globalInitialization`. `pipeline_store.py::project_recognition` finalizuje status po zapisie właścicieli, przed recompute i synchronizacją. Wstępna geometria pozostaje `needs_review`, ponieważ sama propozycja nie dowodzi poprawnego zapisu. Nowe joby oznaczają provenance przez `created_by=system:v3-engine-acceptance-v1`; stan `accepted` wraz z auto/neural engine odróżnia akceptację silnika, bez nowych kolumn i API. Nie zmienia się engine crop version ani diagnostyka uncalibrated.
- Doprecyzowanie po teście realnego startu: `schemas/jobs.py::_payload_from_domain` wyłącza wyłącznie wewnętrzny klucz polityki z odpowiedzi importów obrazów, zachowując strict validation wszystkich innych pól. Publiczne schematy pozostają bez zmian. Regresja `test_neural_page_geometry_api.py::test_all_unbound_neural_sources_start_and_replay_without_invented_boards` kontroluje201/replay, zapisany pin, brak pinu w odpowiedzi i odrzucenie innego extra pola.
- Testy: nowy czysty `test_v3_engine_acceptance.py` oraz nowy PostgreSQL `integration/test_v3_engine_acceptance_postgres.py` oparty na istniejącym izolowanym fixture; komplet, brak pozycji/deferred/partial, model/source/checksum/revision/owner drift, aktualny grid_issue, rollback, cold retry i historyczny job bez polityki. Regresje wymienione poniżej pozostają obowiązkowe. Dokumenty właścicielskie: IMAGE_INGESTION i VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP. Brak pytań produktowych blokujących; powyższe doprecyzowanie realizuje D-550.

- Istniejące: [neural_pending_geometry.py](../../../services/worker/src/game_predictor_worker/images/neural_pending_geometry.py) — `neural_pending_payload`; konsument: `services/worker/src/game_predictor_worker/images/production_workflow.py`.
- Istniejące: [image_geometry_completeness_state_repository.py](../../../services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py) — `recompute_source_image_geometry_completeness`.
- Ustalony przepływ: `services/worker/src/game_predictor_worker/images/pipeline_store.py::project_source_geometry`, `project_recognition`; `images/pipeline_execution.py` — granice transakcji; `services/api/src/game_predictor_api/storage/image_geometry_v2_repository.py::append`; `domain/neural_crop_policy.py::pin_neural_crop_policy`. Nowa czysta funkcja kwalifikacji i jej moduł zostaną nazwane po odczycie kodu.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_v3_engine_acceptance.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Komplet zgodnych pozycji może zostać przyjęty; deferred, partial, konflikt lub błąd blokuje akceptację.
- Żaden przypadek nie ustawia ręcznego zatwierdzenia.
- Stare snapshoty pozostają czytelne.

## Verification

Zakres: WORKER, API; regresje `test_neural_folder_correction_pipeline.py` i produkcyjnego importu.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_geometry_completeness_domain.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_neural_folder_correction_pipeline.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez historycznego backfillu i bez poluzowania bramki jakości.

## Outcome

### Execution phase

- Faza: implementacja i weryfikacja zakończone; próba niezależnego audytu przekroczyła limit, gotowe do commita zgodnie z wyjątkiem AGENTS.md. Current HEAD v1.7.368 / `02f38d6cb731dfc06001a1c6fc819ee4927acba1`. TASK-1010 zamknięty; D-550/D-552 accepted.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: uruchomiony `claude-fable-5-1`, reasoning `high`, Read/Glob/Grep; timeout480 s bez stdout/stderr i bez werdyktu. [Dowód i ograniczenie](../../quality/TASK-1017_AUDIT_TIMEOUT_CODEX.md). To nie jest PASS. Nie ponawiano; wyjątek AGENTS.md nie zatrzymuje taska z powodu braku odpowiedzi.
- Następny krok: lead tworzy osobny commit, zapisuje pełny hash po jego utworzeniu i uruchamia TASK-1008. Integracja pozostaje niezatwierdzona.

### Changed

- Nowe joby importu neuronowego przypinają `v3-engine-acceptance-v1` w payloadzie i fingerprintach obu istniejących ścieżek utworzenia importu. Stare joby/retry nie otrzymują domyślnej polityki.
- Projekcja odpowiedzi joba usuwa wyłącznie wewnętrzny pin przed dotychczasową walidacją importu obrazów. Zapisane wejście joba pozostaje pełne; inne nieznane pola nadal są odrzucane. Nie rozszerzono kontraktu API.
- Nowe source payloady przechowują immutable dowód proposal/binding/model w globalInitialization; checksumę oblicza się przed pierwszym zapisem. Aktor `system:v3-engine-acceptance-v1` z auto/neural provenance odróżnia wynik silnika. Wstępny status pozostaje `needs_review` aż do kontroli rzeczywiście zapisanych plansz.
- Czysta kwalifikacja rozlicza pełny zbiór pozycji, sekwencje, aktualność źródła i rewizji, identyczność modelu/checksum/binding/24 nodes, kompletność i aktualnych właścicieli. Deferred, partial, missing/duplicate slot, provenance drift, obcy owner oraz bieżący grid_issue blokują akceptację.
- Finalizacja jest wywołana przez rzeczywisty `project_recognition` po zapisie plansz, pod istniejącymi blokadami sequence/source i game WRITE, przed recompute/projekcjami w tej samej transakcji. Zmienia wyłącznie status source rewizji. Pola human approval, payloady, hashe, cropy, etykiety, decyzje i ownerzy pozostają nietknięte. Nowsza rewizja blokuje zapis statusu historycznej rewizji.
- D-523 oraz uncalibrated diagnostics pozostają zachowane; przy braku source acceptance pełne neural sloty nadal mają istniejącą dostępność operacyjną. Aktualny grid_issue przetrwa cold retry i cofa engine acceptance. Stare zgłoszenie innej source rewizji nie blokuje nowej kwalifikacji i nie jest usuwane.

### Verification results

- `pytest services/api/tests/test_v3_engine_acceptance.py services/api/tests/test_neural_crop_policy.py`: 33 passed. Nowy test obejmuje kwalifikację i blockers, legacy roundtrip/fingerprint, immutable payload i odmowę eksportu exact lattice bez aktualnego human approval (`NEURAL_GEOMETRY_HUMAN_APPROVAL_REQUIRED`). `production_geometry.classify_label_level` zwraca U dla nowego engine actor; eksporter pozostał bez zmian.
- Test istniejącego rzeczywistego startu HTTP `test_neural_page_geometry_api.py -k all_unbound_neural_sources_start_and_replay`: 1 passed/25 deselected po poprawce. Pierwsza próba wykryła Pydantic extra_forbidden na wewnętrznym pinie; poprawka projekcji objęła wyłącznie ten klucz. Test sprawdza201, idempotentny replay i identyczny pełny payload w repozytorium, pin w trwałym jobie, brak pinu w odpowiedzi oraz ValidationError dla innych nieznanych pól. Kontrola Ruff/format tych dwóch dodatkowych plików PASS.
- Regresje `test_neural_folder_correction_pipeline.py`, `test_production_image_workflow.py`, `test_image_geometry_completeness_domain.py`, `test_image_pipeline_execution.py`: 167 passed poza sandboxem. Pierwsza próba w sandboxie: 122 passed/45 błędów fixture tmp_path (ograniczenia uprawnień), nie traktowana jako zaliczenie.
- PostgreSQL `integration/test_v3_engine_acceptance_postgres.py`: pełny zestaw pierwotnych 9 przypadków 9 passed/69.19 s, w jednej losowej bazie *_test z `GAME_PREDICTOR_PG_TEST_ROLE=application` (NOBYPASSRLS). Test `test_failed_gate_rolls_back_engine_acceptance_and_recognition` wywołuje realny store, wymusza błąd recompute i dowodzi rollback statusu oraz plansz/komórek. Cold replay używa świeżych sesji.
- Po doprecyzowaniu bieżących zgłoszeń: `-k issue` 3 passed/8 deselected/48.19 s; obejmuje current issue, stale issue i realny cold retry. Po dodatkowej kontroli zgodności slotów i wymiarów: `-k complete_acceptance` 3 passed/8 deselected/51.06 s; komplet accepted/geometry_complete, historyczna polityka i deferred pozostają needs_review/geometry_incomplete. Pozostałe zaliczone przypadki nie były powtarzane.
- Pierwsze próby PG: sandbox odmówił localhost; potem test wykrył brak ORM game_id na RecognizedBoard i SourceImage (naprawiony join SourceImage→Job z zakresem gry i jawnym routerem WRITE). Próba 9 oddzielnych migracji przekroczyła120 s po 6 częściowych PASS; wynik nie jest zaliczeniem. Fixture zmieniono na module, z unikalnymi game/źródłami/file execution i receipt. Wyłącznie własny pozostawiony cel `game_predictor_task0760_50b9427fe38b_test` usunięto po potwierdzeniu jedynej gry task1017-345062eb, pustych jobów i0 połączeń; receipt w ignorowanym artifacts. Wcześniejsze i niewiadome bazy pozostały nietknięte. Wszystkie finalne fixture kończą cleanup.
- Mypy `--follow-imports=silent` sześciu zmienionych modułów PASS; po ostatnim doprecyzowaniu dwóch nowych modułów ponowiony PASS. Pierwsza sandboxowa próba przekroczyła120 s i raportowała dwa wcześniejsze błędy w niezmienionym schemas/source_lattice_geometry.py; poza sandboxem kontrola zmienionego zakresu jest zielona. Dwa lokalne błędy typów nowego repository poprawiono przed finalnym PASS.
- Dodatkowa projekcja `schemas/jobs.py`: mypy PASS. OpenAPI Admin i wygenerowany klient są aktualne; publiczny kontrakt pozostał bez zmian. Część VisionLab `openapi:check` napotkała sandboxowe EPERM podczas rename w TEMP; tylko tę niezaliczoną część powtórzono poza sandboxem (`vision-lab:openapi:check`) i uzyskano PASS. Nie regenerowano repozytoryjnych klientów ani artefaktów API.
- Ruff check oraz Ruff format --check: 8 początkowych plików Python PASS; dodatkowe schemas/jobs.py i test_neural_page_geometry_api.py także Ruff/format PASS. Mapę zregenerowano; `scripts/generate_code_map.py --check` PASS. Finalne `npm run docs:check` PASS (63 active/10 done/98289 bytes CURRENT_STATE); `git diff --check` PASS. Każdy proces kontroli miał twardy timeout120 s.

### Not completed

- Niezależny werdykt nie został otrzymany w limicie audytu480 s; brak PASS pozostaje ograniczeniem opisanym powyżej. Commit i integracja nie były wykonane przez wykonawcę. Bez merge i push.
- Nie uruchamiano/restartowano usług, treningu, aktywacji, produkcyjnej migracji ani historycznego backfillu. Nie zmieniano danych operatora i nie tworzono nowego backupu/snapshotu bazy.
- Pełne kontrole projektu i live odbiór na danych operatora nie były potrzebne do tego pionu i nie zostały wykonane. Ograniczenie: obecny writer świeżego importu nie zastępuje przyszłego ponownego rozpoznania/propozycji z planu.

### Documentation updates

- IMAGE_INGESTION opisuje akceptację i ochronę human truth; VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP opisuje pin, immutable evidence, zakres writer'a, transakcję i legacy decode. Task/CURRENT_STATE mają fazę i dowody kontroli; mapa kodu uwzględnia nowe moduły. README/plan/DecisionLog i historia TASK-1010 pozostają dokumentami prowadzonymi przez leada.

### Recommended next task

- TASK-1008
