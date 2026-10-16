---
title: TASK-1006 — Kandydat wspólnej geometrii Mumii i 777a2
status: done
last_updated: 2026-10-16
---

# TASK-1006 — Kandydat wspólnej geometrii Mumii i 777a2

## Status

`done`

## Goal

Udostępnić kontrolowany trening geometrii obu gier.

## Context

Task jest częścią zaakceptowanej rewizji 6. Wspólna kohorta i regresje między grami. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-0997; kohorty obu gier; osobne zlecenie i budżet rzeczywistego runu.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-opus-5-5`, reasoning `high` (zamiennik `claude-fable-5-1`/`high`; wybór wykonawcy po sugestii operatora 2026-10-16, uzasadnienie w sekcji 8 planu). wspólne dane i ryzyko regresji.
- Dodatkowy review: `gpt-6-astra` (przy braku dostępności `gpt-6.1-sol`), reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../../architecture/VISION_LAB.md).
- [VISION_LAB](../../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: rozszerzenie D-527, VISION_LAB, reguły wspólnej kohorty.

- [D-527](../../process/decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Wybór jednej bazy na VALIDATION, równoważenie gier/nagrań, dziedziczenie wyłączeń obu linii danych.
- Jeden jawny eksperyment, bez automatycznej pętli.

## Out of scope

- Brak dobrego wspólnego kandydata nie blokuje panelu i pracy na dotychczasowych wersjach.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Duża gra nie dominuje.
- [x] Alias kontrolny nie trafia do treningu drugiej gry.
- [x] Regresja blokuje publikację.
- [x] Wynik nie przełącza gier automatycznie.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Wybór jednej bazy na VALIDATION, równoważenie gier/nagrań, dziedziczenie wyłączeń obu linii danych. Jeden jawny eksperyment, bez automatycznej pętli.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

### Kontrakt przed kodem (2026-10-16, Claude Code, D-560)

Stan zastany: run TASK-0996 pinuje jedną kohortę jednej gry; ocena D-559 jest per gra z jedną grą treningową; rejestr nagrań na poziomie rodziny łączy aliasy, bajty i piksele w domknięcie i blokuje TRAIN z kontrolą (`RECORDING_PROTECTED`, `RECORDING_ROLE_CONFLICT`), co sprawdza kwalifikacja kohorty.

- **Zakres runu:** `grid-shared-training-run-v1` = kohorta główna (gra trasy, `cohortId` kandydata) + po jednej frozen i `eligible` kohorcie każdej innej gry (2–8 gier), ta sama rodzina, baza i tryb. Opcjonalne `sharedCohorts` w `createGridTrainingRun`; idempotencja obejmuje zbiór kohort.
- **Polityka `grid-shared-candidate-v1`** (`domain/shared_grid_model_candidate.py`, czysta): TRAIN i VALIDATION w każdej kohorcie; grupa nagrania o różnych rolach → `GRID_SHARED_ROLE_CONFLICT`; zdjęcie TRAIN dowolnej gry o tych samych bajtach, pikselach albo grupie co zdjęcie kontrolne dowolnej gry → `GRID_SHARED_CONTROL_ALIAS` (dziedziczenie wyłączeń obu linii danych ponad kwalifikacją rejestru); deterministyczny plan z SHA (gra główna, kohorty, liczby zdjęć i nagrań TRAIN, wagi). API liczy plan przed kolejką, nadzorca przy każdym claim; różnica → `GRID_SHARED_PLAN_DRIFT`.
- **Trening:** jedna baza (D-549), `BalancedSampler` — runda odwiedza każdą grę raz, nagrania w permutacjach, zdjęcie z nagrania; czysta funkcja `(seed, step)`, wznowienie identyczne. VALIDATION: średnia wyników gier z równą wagą; REGRESSION nie jest czytany. Liczniki i plan kroków z sumy kohort. `snapshotId` kandydata = SHA planu.
- **Ocena/publikacja:** ocena kandydata wspólnego musi objąć dokładnie wszystkie kohorty treningu; gra główna ścisła poprawa, każda gra brak regresji (D-559). Brak automatycznej publikacji, aktywacji i przełączenia gier.
- **Bez migracji i nowych tabel.** Rzeczywisty eksperyment na danych operatora wymaga osobnego polecenia po integracji; mechanizm i wynik rozdzielone.

## Expected files

- Pozostały zakres wskazany w zaakceptowanym planie: rejestr, kohorty, trener i ocena poprzednich tasków; nowy proponowany `services/api/src/game_predictor_api/application/shared_grid_model_candidate.py` i wersjonowana joint policy.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/worker/tests/test_shared_grid_training.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Duża gra nie dominuje.
- Alias kontrolny nie trafia do treningu drugiej gry.
- Regresja blokuje publikację.
- Wynik nie przełącza gier automatycznie.

## Verification

Zakres: API, WORKER; rzeczywisty run tylko po zgodzie i spełnieniu warunków.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_cohorts.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_neural_grid_finetune.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Brak dobrego wspólnego kandydata nie blokuje panelu i pracy na dotychczasowych wersjach.

## Outcome

### Execution phase

- Wykonano 2026-10-16: Claude Code `claude-opus-5-5`/`high`, baza v1.7.389 `88b2ab823d466ad5f43f27c2653fc04bb2f6d0b9`, branch `codex/v3-grid-fine-tuning`, worktree `D:\game_predicotr\worktrees\v3-grid-fine-tuning`.
- Kontrakt przed kodem: D-560 (Technical notes). Bez migracji i nowych tabel.
- Commit: v1.7.390 / `9bf3a4b9315fecdd7a55e71a857d376e769bf70c` (poprzedni wersjonowany commit gałęzi v1.7.389); hash zapisany w v1.7.392.
- Audyt R1: [PASS](../../quality/TASK-1006_AUDIT_gpt-6-astra_R1.md) (Codex `gpt-6-astra`/`high`), bez P0/P1. Oba P2 domknięto przed commitem bez kolejnej rundy: plan przypina skrót przypisania źródło → rola → grupa każdej kohorty (`recordingsSha256`), więc zamiana grup przy tych samych liczbach daje `GRID_SHARED_PLAN_DRIFT` (P2-1); test `create` oceny odrzuca pominiętą i podmienioną kohortę treningu i przepuszcza pełny zakres (P2-2).

### Changed

- Polityka `grid-shared-candidate-v1`: `domain/shared_grid_model_candidate.py` (czysty `joint_plan`: zakres 2–8 gier, jedna rodzina/baza/tryb, TRAIN i VALIDATION w każdej kohorcie, konflikt ról grupy, alias kontrolny po bajtach, pikselach i grupie, deterministyczny plan z SHA); `images/grid_shared_candidate.py` stosuje go do metadanych przypiętych snapshotów (bez pikseli).
- Run: rodzaj `grid-shared-training-run-v1` w domenie jobów i schemacie; `application/shared_grid_model_candidate.py` (kohorty innych gier w ich własnych transakcjach, kwalifikacja, plan, sumaryczne liczniki); `GridTrainingRunService.create` z opcjonalnym `sharedCohorts` (idempotencja po zbiorze kohort, plan kroków z sumy), widok `sharedCohorts`/`jointSha256`; wstrzyknięcie w `main.py`.
- Nadzorca: przy każdym claim sprawdza kohorty współdzielone (frozen, manifest, tryb, baza, rodzina, kwalifikacja), przelicza plan (`GRID_SHARED_PLAN_DRIFT` przy różnicy), dopuszcza na sumie liczników i przekazuje trenerowi plan z grupami nagrań; odczyty kohort zawsze w zakresie właściwej gry; `counts_from_header`/`summed_counts` przeniesione do neutralnego modułu dopuszczenia.
- Trener: `BalancedSampler` (neutralny rdzeń), `JointPhotos` i `macro_evaluator`; wariant wspólny w `grid_training_child.py` (TRAIN wszystkich gier, VALIDATION średnio z równą wagą gier, wiązanie checkpointu i `snapshotId` z SHA planu); REGRESSION nadal nie jest czytany.
- Ocena D-559: kandydat wspólny musi być oceniony na wszystkich kohortach treningu (`GRID_EVALUATION_GAME_COHORT_REQUIRED`).
- OpenAPI, wygenerowany klient i test żądania `sharedCohorts`; D-560, sekcje VISION_LAB; strażnik ról w `test_grid_model_evaluation.py` obejmuje teraz dwa wywołania TRAIN/VALIDATION trenera wspólnego.

### Verification results

- Po P2: API 10 PASS i worker 7 PASS (20 z parametryzacją); test workera nazwany `test_shared_grid_training.py`, bo ta sama nazwa modułu w API i workerze koliduje przy wspólnym uruchomieniu pytest.
- Przed P2: API polityka i run wspólny 9 PASS (`test_shared_grid_model_candidate.py`), razem z runami 0996 17 PASS. Worker: 6 PASS ( równowaga gier i nagrań, wznowienie samplera, `JointPhotos` z `GridOnlyBatches`, pełny przebieg nadzorcy z fałszywym trenerem na dwóch snapshotach, drift planu i utrata kwalifikacji bez startu, alias kontrolny, brak ścieżki publikacji/aktywacji). Regresje treningu, oceny, dopuszczenia i API: 164 PASS po aktualizacji strażnika ról.
- E2E GPU na kodzie końcowym: PASS 100,5 s (run 69,6 s, plan `40af94c8…` z przypisaniem nagrań, 40 kroków, eksport z parity, jedna rejestracja); dowód nadpisany w `artifacts/audits/TASK-1006_GPU_E2E.json`.
- E2E GPU przed P2 (izolowany PostgreSQL, prawdziwy worker lane i trener CUDA RTX 4050, dwie syntetyczne gry 3 i 9 zdjęć TRAIN): PASS 114,0 s (run 81,5 s): claim w lane, admission na sumie kohort, trener na TRAIN obu gier z planem `716fb4fd…` (gry 9 i 3 zdjęć TRAIN, po 3 nagrania), 40 kroków, eksport z parity, instalacja i jedna rejestracja `not_evaluated` z `cohortId` gry głównej i `snapshotId` = SHA planu; dowód `artifacts/audits/TASK-1006_GPU_E2E.json`. Pierwsza próba z identycznymi JPEG obu fixture została poprawnie odrzucona jako `GRID_SHARED_CONTROL_ALIAS`.
- `openapi:check`, `docs:check`, `code-map:check`, Ruff i mypy zmienionych modułów PASS (mypy: jedynie 2 stare błędy w nietkniętym `source_lattice_geometry.py`); klient 1 nowy test PASS.

### Not completed

- Rzeczywisty eksperyment wspólnego kandydata Mumii i 777a2 na danych operatora: wymaga integracji (baza operatora na `0155`) oraz osobnego polecenia i budżetu; mechanizm i wynik są rozdzielone, brak pomiaru nie jest PASS.
- Interfejs uruchamiania runu wspólnego należy do TASK-1000.

### Documentation updates

- D-560 (pełny wpis i indeks), sekcje D-560 w architekturze i wymaganiach VISION_LAB, kontrakt w tym pliku, CURRENT_STATE, CODE_MAP.

### Recommended next task

- TASK-1000
