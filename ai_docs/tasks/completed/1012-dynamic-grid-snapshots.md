---
title: TASK-1012 — Dynamiczne snapshoty i spójny routing V3
status: done
last_updated: 2026-10-15
---

# TASK-1012 — Dynamiczne snapshoty i spójny routing V3

## Status

`done`

## Goal

Nowe wersje z katalogu działają bez dopisywania do statycznego rejestru.

## Context

Task jest częścią zaakceptowanej rewizji 6. Snapshoty i zgodność całego importu. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0994 done, v1.7.373 / `c06b7432e76e6e3d24b1cd78757d9f900bc9cac7`; rzeczywiste scoped kontrole PASS, audyt Claude high timeout bez werdyktu, jawny wyjątek AGENTS zapisany w tasku0994. Rejestr i assignments dostępne w kodzie; brak migracji operatora.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. zgodność rozpoczętych zadań i wielu konsumentów.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [IMAGE_INGESTION](../../requirements/IMAGE_INGESTION.md).
- [API_CONTRACT](../../architecture/API_CONTRACT.md).
- Zakres odczytu uzupełniający z planu: IMAGE_INGESTION, API_CONTRACT, D-544, kontrakt snapshotu tego planu.

- [D-544](../../process/decisions/DECISION_LOG_2026.md#d-544--nowe-gry-777-importują-przez-v3-z-profilem-grid_profile_777_v2) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Nowa wersja snapshotu oraz czytnik starej.
- Jeden resolver możliwości dla preflightu, importu, ponownego użycia, workera i własności sekwencji.

## Out of scope

- Bez przepisywania historycznych payloadów i ukrytych aliasów starego profilu.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Trzecia rodzina działa; stary job wznawia się po zmianie aktywacji; stary preflight nie uruchamia innej wersji; brak lub zmiana hashy nie powoduje fallbacku.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

- Nowe zadania używają `neural-grid-proposal-snapshot-v2`: gameId, konfiguracja gry, expectedLayoutCount, pełny descriptor katalogu i jego SHA-256. Descriptor przypina versionId/familyId, managedDirectory, inferenceManifest, pliki, preprocessingVersion, decodingPolicyVersion, topology i capabilities. W pamięci przechowujemy kanoniczny JSON, aby zewnętrzna mutacja słownika nie zmieniła przypiętego modelu.
- Czytnik v1 nadal porównuje dokładny historyczny manifest ze statycznym rejestrem. Nie przepisujemy payloadów, nie dodajemy aliasów i nie zmieniamy znaczenia dawnych profili. Adapter wersji v2 zachowuje interfejs potrzebny workerowi, ale pobiera ścieżkę i manifest wyłącznie z descriptora snapshotu.
- Jedna domenowa polityka rozpoznaje neutralny V3 oraz dwa istniejące formaty V3. Nowy snapshot wymaga dodatkowo istniejącego assignment gry z publicznego katalogu. Kolejność: zgodność scope/game → format → assignment → wersja → descriptor/SHA/identity → topology/capabilities/kontrakty → dostępność i hashe plików → zapis snapshotu w jobie. Brak assignment albo niezgodność blokuje import; bez classical/current/default fallbacku. Historyczna gra kod7 pozostaje klasyczna.
- Interpretacja uzgodniona z leadem: TASK-1012 konsumuje istniejący jawny assignment. Nie tworzy ani nie przełącza przypisań; publikacja/aktywacja/default i ich bramki należą do TASK-0998. Dostępność artefaktów nie oznacza PASS oceny.
- Reuse i start z ukończonego preflightu parsują jego snapshot, sprawdzają właściciela gry, format i artefakty tego snapshotu. Nie odczytują aktualnej wersji assignment, więc późniejsza aktywacja nie zmieni wersji. Worker po restarcie odtwarza wyłącznie pin z payloadu. Istniejący snapshot z brakującym lub zmienionym plikiem kończy się błędem, bez wybrania innej wersji.
- Własność sekwencji stosuje wspólną politykę V3 i sprawdzenie assignment/capabilities dla nowych żądań. Numeracja, kanon, ręczne decyzje i per-game symbol snapshot pozostają zachowane. Brak nowych tabel/migracji; istniejący manifestv9/0156 wystarcza.
- Publiczne payloady propozycji i jobów otrzymują addytywną unię v1/v2. Backend/OpenAPI/generowany klient/wrapper i test żądania muszą zachować zgodność. Shadow zachowuje osobny historyczny kontrakt D-544 i nie jest przełączany w tym tasku.
- Kontrole: snapshot roundtrip/immutability, trzecia rodzina, neutralny bez assignment, obcy gameId, zmieniony descriptor/hash, stare snapshoty, wznowienie/start po zmianie assignment, brak/mutacja pliku, worker preflight i import, kanoniczne zakresy. Testy używają fixture lub izolowanych danych; nie wykonują rzeczywistej inferencji, publikacji, aktywacji ani migracji operatora.

### Jedna runda poprawek audytu — plan przed kodem (2026-10-15)

- Raport rundy 1 `TASK-1012_AUDIT_claude-fable-5-1.md` ma REVISE, P1-1 i P2-1–4. Raport pozostaje bez zmian.
- P1-1: test workera usunie zależności od katalogu testów API. Lokalna mała fabryka utworzy wyłącznie niezmienny descriptor oraz fikcyjne artefakty inference; repozytorium użyje wąskiego mocka `get_job`, ponieważ badany replay/start wymaga tylko tego odczytu. Nie kopiujemy całej klasy MemoryJobRepository, nie zmieniamy helperów ani domyślnego zachowania istniejących testów API, nie dodajemy sys.path.
- Samodzielny nowy proces pytest otrzyma wyłącznie oficjalne ścieżki `services/api/src`, `services/worker/src`, `services/test_support`; osobno uruchomimy udokumentowany `Suite Worker` z twardym limitem 120 s i kontrolą własnego drzewa procesów po timeout. Cała suite nie otrzyma PASS z samego zebrania testu.
- P2-1: usuwamy wyłącznie starszy drugi stub TASK-1012 z CURRENT_STATE, pozostawiając sekcję wyników i wszystkie cudze sekcje. P2-2: aktualizujemy obie daty frontmatter do 2026-10-15. P2-4: dodajemy regresję gry kod7 błędnie ustawionej na każdy format V3; klasyfikator/JobService mają pozostać klasyczne bez odczytu assignment. Zachowanie produktu nie jest zmieniane.
- P2-3 (doprecyzowanie D-549) prowadzi lead; wykonawca nie edytuje Decision Log. Po kontroli zapiszemy osobny zestaw plików i diffów korekty względem zamrożonego zakresu rundy 1, wyniki, ograniczenia i wymagany przegląd P1.

## Expected files

- Istniejące: [neural_grid_proposal.py](../../../services/api/src/game_predictor_api/domain/neural_grid_proposal.py) — `NeuralGridSnapshot`.
- Istniejące: [grid_profile_snapshot_resolver.py](../../../services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py) — `resolve_neural_grid_proposal`, routing profilu.
- Istniejące: [grid_engine_model_store.py](../../../services/api/src/game_predictor_api/storage/grid_engine_model_store.py) — `ManagedGridEngineModelStore`; [instalator](../../../scripts/install_grid_engine_models.py) — `install_version`.
- Istniejące: [jobs.py](../../../services/api/src/game_predictor_api/application/jobs.py) — preflight, snapshoty, admission i start zadań.
- Pozostały zakres wskazany w zaakceptowanym planie: `services/api/src/game_predictor_api/storage/image_sequence_canonical_repository.py::uses_neural_grid_pilot`; konsumenci snapshotów w workerze.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_dynamic_grid_snapshots.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Trzecia rodzina działa; stary job wznawia się po zmianie aktywacji; stary preflight nie uruchamia innej wersji; brak lub zmiana hashy nie powoduje fallbacku.

## Verification

Zakres: API, WORKER, testy snapshotów/resolvera/importu, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_grid_proposal.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_neural_folder_correction_pipeline.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez przepisywania historycznych payloadów i ukrytych aliasów starego profilu.

## Outcome

### Execution phase

- Faza bieżąca: done, jedna runda poprawek zakończona formalnym Claude high PASS w rundzie2; przygotowanie osobnego commita, później oczekiwanie na integrację całego planu.
- Baza: v1.7.373 / `c06b7432e76e6e3d24b1cd78757d9f900bc9cac7`; worktree `D:/game_predicotr/worktrees/v3-grid-fine-tuning`, branch `codex/v3-grid-fine-tuning`.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`; zatwierdzony upstream main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d`.
- Commit/stage: nie wykonywano; lead ustala następny wolny patch po audycie.
- Audit: `claude-fable-5-1/high`, runda1 REVISE zachowana jako `_round1.md`; runda2 PASS w canonical report. P1-1 i P2-1..P2-4 zamknięte; P2-5 wcześniejszy błąd launchera przyjęty poza zakresem. Obie rundy statyczne, limit do20min na jawne polecenie operatora.
- Dokładny zakres i hashe: `artifacts/audits/TASK-1012_SCOPE.json`. `CURRENT_STATE.md` jest współdzielony: wykonawca zmienił wyłącznie sekcję TASK-1012. README, plan oraz metadane ukończonego TASK-0994 należą do leada i nie są zakresem tego taska.

### Changed

- Snapshot `neural-grid-proposal-snapshot-v2` przypina właściciela, format gry i kanoniczny immutable descriptor katalogu z SHA-256. Descriptor obejmuje rodzinę/versionId, manifest, pliki, preprocessing, decoder, topology/capabilities i managedDirectory. Adapter wersji zachowuje interfejs istniejącego workera. V1 nadal odczytuje dokładny historyczny rejestr bez zmiany payloadu.
- Nowe preflighty wszystkich trzech formatów V3 rozwiązują istniejący assignment z publicznego repozytorium katalogu. Resolver sprawdza scope, brak przypisania, record/version/family identity, kanoniczny descriptor, hash i zgodność kontraktów. Brak przypisania daje `GRID_MODEL_ASSIGNMENT_REQUIRED`; brak lub drift plików nie wybiera innej wersji.
- Start importu i reuse zachowują snapshot preflightu po zmianie aktualnego assignment. Worker w nowej instancji odtwarza pin bez odczytu aktualnej aktywacji; sprawdza artefakty także przy replay ukończonego manifestu. Manifest źródła nie może zawierać snapshotu innej gry.
- Canonical preflight korzysta ze wspólnego resolvera możliwości i przypisania. Historyczna gra kod7 pozostaje klasyczna; kolejność/sekwencje, kanon, decyzje człowieka oraz game-scoped symbol snapshots są zachowane.
- Publiczne modele jobów/propozycji mają dyskryminowaną unię v1/v2; zaktualizowano OpenAPI, wygenerowane typy/index klienta, eksport wrappera i test żądania GET istniejącego endpointu jobs. Admin rozpoznaje dynamiczny snapshot i pokazuje exportId z właściwego manifestu.
- Istniejący test resolvera zmienił oczekiwanie statycznego `current` na jawny historyczny assignment zgodnie z nowym kontraktem; zachował kontrolę obu profili i klasycznej gry. Dodano testy trzeciej rodziny, braków/driftu, cudzej gry, nowego procesu oraz worker replay/start/reuse po zmianie assignment.
- Nie potrzeba migracji: istniejący katalog i assignment z 0156/manifest v9 wystarczają. Shadow zachowuje osobny historyczny kontrakt D-544.

### Verification results

- Finalne skoncentrowane pytest: **90 PASS**, API snapshoty/propozycje/resolver/HTTP oraz worker preflight, replay i folder correction pipeline. Czas 12,19 s; limit procesu 120 s. Receipt: `artifacts/audits/TASK-1012_final_tests.json`, pełny log obok. Fixture inference używa testowego runnera, bez rzeczywistego model runu.
- Nowy proces odczytuje zapisany snapshot v2 i weryfikuje jego pliki. Test workerowy rekonstruuje handler, nie ponawia inferencji po checkpointcie, zachowuje preflight pin podczas startu/reuse po zmianie assignment i odmawia replay/startu po utracie starego pliku.
- Read-only adapter snapshotu v2 zweryfikował obie rzeczywiste bazy w `D:/game_predicotr/artifacts/models/grid-engine/.../v1`: AVAILABLE, bez inferencji. Receipt: `artifacts/audits/TASK-1012_BASELINE_INTEGRITY.json`.
- Ruff check wszystkich 10 zmienionych modułów Python i trzech testów: PASS. Formatowanie Ruff: wykonane. Receipty: `TASK-1012_ruff_close.json`, `TASK-1012_format_close.json`.
- Mypy `--follow-imports=silent`: PASS dla 10 modułów; po końcowej walidacji identity/owner ponownie PASS dla dwóch dotkniętych modułów. Receipty: `TASK-1012_mypy_fixed.json`, `TASK-1012_mypy_close.json`. Zakres świadomie nie włącza istniejących błędów `source_lattice_geometry.py:36/38` z importów.
- Typecheck klienta Admin: PASS. Typecheck Admin (`next typegen`, `tsc --noEmit`): PASS po poprawce prezentacji exportId w snapshotach v2. Receipty: `TASK-1012_client_typecheck.json`, `TASK-1012_admin_typecheck_fixed.json`.
- Skoncentrowane testy TS Admina, starej gotowości importu i wrappera klienta: **21 PASS**, w tym odczyt dynamicznej trzeciej rodziny i zachowanie pinu GET job. Receipt: `TASK-1012_ts_tests.json`.
- Scoped ESLint dwóch zmienionych modułów Admin: 0 errors, 1 istniejące ostrzeżenie `no-img-element` poza zmianą. Wywołanie z root podało także informację o braku katalogu Pages; nie jest błędem. Receipt: `TASK-1012_admin_lint.json`. Prettier zmienionych TS/MJS: wykonany.
- OpenAPI Admin export check i generated-client check: PASS w prefiksie umbrella `openapi:check`. Umbrella zakończyła się błędem EPERM rename w TEMP niezwiązanego VisionLab; sama umbrella nie jest raportowana jako PASS. Wyłącznie `vision-lab:openapi:check` ponowiono z eskalacją: PASS. Receipty: `TASK-1012_openapi_check.json`, `TASK-1012_vision_openapi_check.json`.
- Mapy kodu zregenerowano po nowych symbolach. `code-map:check`: PASS. `docs:check`: PASS (58 aktywnych tasków, 10 done). `git diff --check`: PASS. Receipty: `TASK-1012_map_check.json`, `TASK-1012_docs_check.json`, `TASK-1012_diff_check.json`.
- Wcześniejsze próby są zachowane w receiptach: pierwsza kontrola 24 PASS i cztery błędy TEMP pytest w sandboxie; eskalowana próba wykryła maskowanie `JobConflictError` przez `ValueError` (naprawione); kolejna 84 PASS i jeden test starego kontraktu statycznego resolvera (zaktualizowany do jawnego assignment); pierwszy mypy wykrył `str | None` dla konfiguracji (jawna walidacja naprawiła typ); pierwsza kontrola typu Admin wykryła odczyt pola `model` tylko dla v1 (naprawiony helper z dyskryminacją). Żadna niezaliczona próba nie jest PASS.

### Not completed

- Niezależny audyt, rozliczenie jego uwag, commit i końcowe zamknięcie taska należą do leada. Nie wykonano stage, commita, merge ani push.
- Bez migracji lub backfillu bazy operatora, backupu, startu/stopu usług, rzeczywistej inferencji/GPU/treningu, publikacji, aktywacji ani ustawienia default. Nie wykonywano szerokiego builda, całej quality, benchmarków ani masowego przetwarzania.
- Brak nowej bazy/roli/procesu PostgreSQL; kontrola nowego resolvera i workera korzysta z istniejących repozytoriów oraz izolowanych fixture. Testy nie potwierdzają produkcyjnego rollout ani jakości inferencji.

### Documentation updates

- Task: szczegółowe Technical notes zapisane przed kodem, aktualne wyniki i ograniczenia.
- IMAGE_INGESTION oraz API_CONTRACT opisują assignment, unię v1/v2, kompatybilność i granice TASK-0998; CODE_MAP i CODE_MAP_SYMBOLS zregenerowane.
- CURRENT_STATE: zaktualizowano wyłącznie aktywną sekcję TASK-1012; bez zamykania taska przed audytem.

### Jedna runda poprawek audytu — wynik

- P1-1: usunięto oba importy testów API z testu workera. Lokalna fabryka tworzy mały descriptor i fikcyjne pliki inference; wąski mock repozytorium udostępnia tylko wymagany odczyt `get_job`. Nie zmieniono współdzielonych helperów, istniejących konsumentów API, kodu produkcyjnego ani konfiguracji importów.
- P1-1 weryfikacja: nowy samodzielny proces `pytest services/worker/tests/test_dynamic_grid_snapshot_replay.py` z oficjalnym PYTHONPATH zawierającym wyłącznie `services/api/src`, `services/worker/src`, `services/test_support`: **1 PASS** (1,39 s testu; 3,41 s procesu). Katalog testów API nie został dodany do sys.path ani PYTHONPATH. Receipt: `TASK-1012_CORRECTION_worker_standalone.json`.
- Wymagany udokumentowany `npm run python:test -- -Suite Worker`: wykonany, exit4 po 8,48 s, zero zebranych testów, błąd launchera przed kolekcją `ERROR: file or directory not found: s` i rootdir `D:/`. Skrypt repozytorium nie został zmieniony w tym tasku. Wynik nie jest PASS; receipt `TASK-1012_CORRECTION_worker_suite.json` oraz pełny log obok.
- Dodatkowy bezpośredni `pytest services/worker/tests` z tymi samymi oficjalnymi ścieżkami skutecznie zebrał testy i rozpoczął ich wykonywanie, lecz został zakończony po twardym limicie 120 s (120,44 s ze sprzątaniem, exit124). Pełna suite nie ma końcowego wyniku ani PASS. Własne drzewo procesu PID 38576 zakończono; późniejszy odczyt nie znalazł PID, jego dzieci ani pasującego procesu pytest. Receipty: `TASK-1012_CORRECTION_worker_directory.json`, `TASK-1012_CORRECTION_CLEANUP.json`. Nie ponawiamy szerokiej suite ani nie rozszerzamy zakresu o launcher.
- P2-1: usunięto wyłącznie starszy drugi stub TASK-1012; właściwa sekcja wyników i obce sekcje CURRENT_STATE zachowane. Dwa pierwsze podejścia zatrzymała asercja granic przed zapisem tego pliku; ostateczna selekcja użyła pełnych linii nagłówków. Nie usunięto cudzej sekcji.
- P2-2: obie daty frontmatter API_CONTRACT i IMAGE_INGESTION ustawiono na 2026-10-15.
- P2-3: lead doprecyzował accepted D-549 w pełnym wpisie, kopii i indeksie; nowy preflight wszystkich formatów V3 wybiera assignment, a D-544 zachowuje znaczenie snapshotów v1. Wykonawca nie edytował Decision Log. Lead potwierdził `check_decision_links` PASS 581/550/550.
- P2-4: trzy regresje konfiguracji `neural_grid_v3`, `grid_profile_mumie_v1`, `grid_profile_777_v2` dla gry kod7 potwierdzają klasyczny routing JobService i brak odczytu assignment. Nie zmieniono zachowania historycznej gry ani kodu aplikacji.
- Dodatkowe tanie regresje audytu: GET istniejącego joba zachowuje oba kontrakty v1/v2 z dyskryminacją `contractVersion`; canonical preflight propaguje `GRID_MODEL_ASSIGNMENT_REQUIRED`. Finalna kontrola API: **28 PASS**, 11,23 s; receipt `TASK-1012_CORRECTION_api_final.json`.
- Ruff obu dotkniętych testów: pierwszy końcowy odczyt wykrył wyłącznie kolejność lokalnych importów; `ruff check --fix` naprawił 1 uwagę, pozostało 0. Formatowanie wykonane. Receipt: `TASK-1012_CORRECTION_ruff_fix.json`. Nie powtarzano mypy/typów/OpenAPI aplikacji, ponieważ poprawki nie zmieniły jej źródeł ani kontraktu.
- Docs check po usunięciu stuba i zmianach dat: PASS (59 aktywnych tasków, 10 done; liczba 59 obejmuje ponownie otwarty przez leada TASK-0994). Późniejsze rozbudowanie własnej sekcji przekroczyło limit CURRENT_STATE o369 bajtów; skrócono wyłącznie sekcję TASK-1012, pozostawiając pełne dowody w Outcome. Końcowy `docs:check` po skróceniu: PASS, CURRENT_STATE99572 bajty; receipt `TASK-1012_CORRECTION_docs_after_compact.json`. Receipty: `TASK-1012_CORRECTION_docs.json`, `TASK-1012_CORRECTION_docs_final.json`.
- Zestaw oryginalnych 27 plików i receiptów zachowano jako `TASK-1012_SCOPE_ORIGINAL.json`. Korekta obejmuje dokładnie 6 plików; osobne diffy i hashe są w `TASK-1012_CORRECTION_SCOPE.json` oraz `TASK-1012_CORRECTION.patch`. Brak automatycznej następnej rundy poprawek. P1 czeka na ograniczony ponowny przegląd; pozostałych otwartych P2 wykonawcy nie ma. Ograniczenia launchera i pełnej suite są opisane, nie ukryte.

### Definition of Done / zgodność z planem

- Funkcjonalność: kryterium trzeciej rodziny, starego joba, pinu preflight→start i fail-closed ma testy i PASS. Dodatkowy review pozostaje wymagany; dlatego task nie ma jeszcze statusu done.
- Kod i trwałość: wspólna domenowa polityka, adapter immutable descriptora i istniejący worker; brak HTTP/UI w logice domenowej. Nowy proces oraz rekonstruowany handler potwierdzają odczyt trwałego pinu. Nie dodano obejścia środowiskowego ani produkcyjnej ścieżki tymczasowej.
- Dane: bez zmiany schematu, seedów lub zapisów operatora. Chroniona numeracja/kanon i brak wymiany symbol modelu są objęte zachowanymi regresjami. Brak zmiany algorytmu signature.
- Kontrakt: backend i OpenAPI opisują addytywną unię; klient jest wygenerowany, wrapper eksportuje nowy typ i ma test rzeczywistego wywołania GET. Nowe snapshoty wymagają assignment zamiast statycznego current, co opisano jawnie w wymaganiach i API_CONTRACT.
- Narzędzia: właściwe testy, format, lint i typy zaliczone; ostrzeżenie ESLint i niezaliczone próby odnotowane powyżej. Nie deklaruje się PASS całej quality.
- UX: zmiana dotyczy odczytu i etykiety istniejącego importu; regresje zachowują loading/empty/error i jawny click startu. Nie wprowadzono nowego formularza ani gestu; fizycznego Androida nie testowano.
- Dokumentacja i przekazanie: Outcome/CURRENT_STATE/wymagania/kontrakt/mapy aktualne. Nie potrzeba dodatkowej decyzji architektonicznej ponad zaakceptowane D-549 i plan R6. Audyt, commit i przeniesienie do completed pozostają zadaniem leada.

### Recommended next task

- Lead: audyt Claude high TASK-1012 po rozstrzygnięciu oczekującego audytu bazowego TASK-0994; jedna runda poprawek według zasad planu. Następnie osobny commit, zapis pełnej wersji/hash i zamknięcie dokumentacji. Kolejny task planu: TASK-0998.

### Zamknięcie przez leada po rundzie 2

- [Raport R1 REVISE](../../quality/TASK-1012_AUDIT_claude-fable-5-1_round1.md) i [R2 PASS](../../quality/TASK-1012_AUDIT_claude-fable-5-1.md) zachowane bez zmiany werdyktów. Brak otwartych P0/P1. Jedna runda poprawek; brak automatycznej kolejnej pętli.
- P1-1 zamknięte lokalnym helperem workera i wąskim mockiem, bez współdzielonych fixture API. Standalone worker działa wyłącznie na oficjalnym PYTHONPATH. P2-1 jeden nagłówek stanu, P2-2 poprawione daty, P2-3 doprecyzowanie accepted D-549 w pełnym logu/kopii/indeksie przez leada, P2-4 trzy testy błędnych konfiguracjiV3 starej gry7 — zachowanie produktu bez zmiany.
- P2-5 z R2 świadomie pozostaje poza zadaniem: wcześniejszy PowerShell launcher pojedynczej Suite rozbija ścieżkę na znaki i kończy się przed kolekcją. Nie zmieniano go. Testy uruchamiano bezpośrednio przez pytest z jawnymi ścieżkami i limitami; timeout pełnego Worker120s nie jest PASS. Ograniczenie zapisano w CURRENT_STATE; oddzielna poprawka wymaga własnego zakresu.
- Po niezależnym zamknięciu korekty0994 (v1.7.374 / `27ff986a873559330cd75aad3ee47081a41758d5`) lead sprawdził połączenie source:45 testów schema+registry+dynamic+worker PASS15,48s oraz kolejny samodzielny worker1 PASS1,43s. Te kontrole uzasadniała nowa centralna rejestracja ORM; nie powtarzano całego quality ani zielonych frontendów.
- W audycieR2 dispatch wskazywał bazę373 i zamrożony diff. W czasie przeglądu zapisano wyłącznie parent0994 jako374, poza zakresem1012; treść plików1012 nie była zmieniana. Raport pozostaje zgodny z briefem i zachowanymi hashami.
- Odbiór DoD: additive v2/v1, pin trzeciej rodziny i brak fallbacku, scope gry, start/replay/resume, backend/OpenAPI/klient/UI, testy/checki, decyzja i dokumentacja spełnione. Brak nowej migracji, operator DB, usług, rzeczywistej inferencji, GPU/treningu, publikacji, aktywacji, default, push, wdrożenia i scalenia.
- Następny krok: osobny commit1012 po świeżym skanie numeracji oraz staged check/list/stat; pełny hash dopisać po utworzeniu bez amend. Następny funkcjonalny task0998, publikacja i aktywacja.

- Końcowe po zamknięciu: docs:check PASS (57 aktywnych tasków,10 done,96437B), code-map:check i git diff --check PASS. Oryginalne i korekcyjne receipty zachowane. Wybrany kolejny wolny patch po skanie wszystkich refs/worktree HEADs: v1.7.375; ponownie potwierdzić przed commitem.
