---
title: Batch payout precomputation and audit
status: done
last_updated: 2026-07-27
---

# TASK-0032 — Batch payout precomputation and audit

## Status

`done`

## Goal

Podłączyć istniejący `payout-v2` do trwałego joba workera tak, aby opublikowany
dataset był oceniany partiami dla konkretnej opublikowanej wersji reguł, wyniki
były zapisywane idempotentnie w PostgreSQL, a strukturalny audyt pozostawał
dostępny poza aplikacją mobilną.

## Context

M3.1 dostarczył trwałe jobs, singletonowy lease, checkpoint, retry i ekran
obserwacji. M1 dostarczył czysty silnik `payout-v2` i golden cases. TASK-0032
łączy te elementy dla rzeczywistych danych administracyjnych, ale nie definiuje
jeszcze bramki kompletności snapshotu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- migracja Alembic i ORM dla `layout_payouts`,
- klucz logiczny dataset/rules/sequence/algorithm i nieujemny payout,
- odczyt opublikowanego datasetu oraz opublikowanych reguł tej samej gry i
  wymiarów,
- jawna obsługa wyłącznie `payout-v2`,
- deterministyczna konwersja rekordów administracyjnych do kontraktu engine,
- odczyt layoutów w bounded batchach bez ładowania pełnego datasetu,
- idempotentny zapis batcha i checkpoint po bezpiecznej granicy,
- strukturalny audyt JSONL w deterministycznych plikach partii,
- wznowienie od ostatniego checkpointu i ponowne przetworzenie bez duplikatów,
- rejestracja handlera payout w lokalnym workerze,
- testy domenowe, handlera, migracji i adaptera PostgreSQL.

## Out of scope

- endpoint lub UI tworzenia payout joba,
- kontrola kompletności payoutów przed snapshotem,
- invalidacja albo porównywanie historycznych wyników,
- generowanie SQLite, release i APK,
- benchmark 500 000 layoutów,
- Redis/Celery lub wykonywanie równoległe.

## Acceptance criteria

- [x] Worker odrzuca job innego typu, payload innej wersji i algorytm inny niż
  `payout-v2`.
- [x] Dataset i reguły muszą być opublikowane, należeć do `gameId` joba i mieć
  identyczne wymiary.
- [x] Aktywne paylines, symbole, minima i payout rules tworzą deterministyczne
  wejście istniejącego engine.
- [x] Każdy layout jest oceniany dokładnie według `sequence_number`.
- [x] Wynik ma nieujemny `total_payout` i unikalny klucz logiczny.
- [x] Audyt zachowuje matches, komórki, jokery i interpretacje.
- [x] Partia wyników i odpowiadający jej plik audytu są odtwarzalne.
- [x] Checkpoint wskazuje ostatni bezpiecznie zapisany numer sekwencji.
- [x] Retry/wznowienie nie tworzy duplikatów i może bezpiecznie powtórzyć partię.
- [x] Postęp i success count odpowiadają liczbie zapisanych layoutów.
- [x] Migracja ma upgrade/downgrade, a testy i pełna bramka jakości przechodzą.

## Assumptions

- Rozmiar partii wynosi domyślnie 1000 rekordów.
- Jeden plik JSONL opisuje jedną partię; wszystkie payouty partii wskazują ten
  sam względny `audit_path`, a rekord w pliku jest identyfikowany przez
  `sequenceNumber`.
- Plik partii powstaje przez atomową podmianę i ma deterministyczną nazwę
  zależną od wersji oraz zakresu sekwencji.
- Powtórny zapis tego samego klucza logicznego jest idempotentnym upsertem.
- Domyślny katalog lokalnych artefaktów to `artifacts/`, konfigurowalny dla CLI.
- TASK-0033 będzie właścicielem pełnego raportu kompletności, wykrywania
  historycznych braków oraz blokady snapshotu.

## Expected files

- `services/api/alembic/versions/0009_layout_payouts.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/worker/src/game_predictor_worker/payouts/`
- `services/worker/src/game_predictor_worker/cli.py`
- testy migracji, handlera i PostgreSQL
- dokumentacja modelu, decyzji i stanu

## Verification

```powershell
pytest services/worker/tests/test_payout_batch.py -q
pytest services/api/tests/test_migration_baseline.py -q
npm run lint
npm run typecheck
npm run quality
```

## Risks / open questions

- Brak pytań blokujących. Rozmiar i czas plików audytu dla 500 000 rekordów
  zostaną zmierzone w M3.5; format JSONL pozwala je czytać strumieniowo.

## Outcome

Migracja `0009_layout_payouts` dodała trwały wynik z kluczem
`(dataset_version_id, rules_version_id, sequence_number, algorithm_version)`,
FK do konkretnego layoutu i rules version, nieujemnym payoutem `bigint`,
względnym `audit_path` oraz czasem obliczenia.

Worker `worker-v2` rejestruje handler `payout-v2`. Handler wymaga opublikowanego
datasetu i reguł tej samej gry oraz wymiarów, mapuje aktywne symbole, minima,
paylines i reguły do istniejącego czystego engine, a layouty czyta keysetowo w
partiach po 1000. Stabilne błędy handlera trafiają do joba bez ujawniania
wyjątku technicznego.

Każda partia tworzy deterministyczny JSONL przez atomową podmianę, wykonuje
idempotentny PostgreSQL upsert, a dopiero potem zapisuje checkpoint z ostatnim
numerem sekwencji i licznikami. Retry może powtórzyć ostatnią partię bez
duplikatu. Audyt zawiera matches, komórki, jokery, payout i strukturalne
interpretacje.

Weryfikacja:

- pełne `npm run quality` przeszło: 162 testy Python i 5 jawnie pominiętych
  fizycznych testów, 51 testów panelu, 63 mobile, 23 shared i 8 klienta API,
- osobny pełny zestaw fizycznych testów PostgreSQL przeszedł: 5/5, w tym
  migracja upgrade/downgrade/upgrade, adapter payoutów i idempotentny upsert,
- ukierunkowane testy handlera/runtime/migracji przeszły: 27/27,
- format, OpenAPI drift, lint, mypy/TypeScript oraz walidatory snapshotu i
  fixture przeszły.
