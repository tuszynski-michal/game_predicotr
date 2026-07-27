---
title: Payout completeness, restart and version safety
status: done
last_updated: 2026-07-27
---

# TASK-0033 — Payout completeness, restart and version safety

## Status

`done`

## Goal

Domknąć M3.2 wielokrotnie używalną bramką gotowości payoutów, która przed
snapshotem potwierdza dokładną kompletność konkretnej kombinacji
`dataset/rules/algorithm`, oraz dowodami, że awaria, retry i historyczne wyniki
innych wersji nie zmieniają rezultatu.

## Context

TASK-0032 dodał batch handler `payout-v2`, trwałe `layout_payouts`,
idempotentny upsert i JSONL audytu. TASK-0033 nie generuje jeszcze SQLite, lecz
dostarcza kontrakt, z którego skorzysta M3.3.

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

- czysty raport gotowości dla dokładnych wersji dataset/rules/algorithm,
- stabilne issues dla statusu, gry, wymiarów, braków i audytu,
- dokładne liczniki oraz bounded, deterministyczne próbki brakujących sekwencji,
- adapter PostgreSQL używający FK/PK i zapytań agregujących bez ładowania
  pełnego datasetu,
- jawna bramka `require`, która odrzuca niegotowy zestaw przed snapshotem,
- version safety: payout innego rules/dataset/algorithm nie liczy się do
  bieżącego zestawu,
- walidator JSONL potwierdzający nagłówek, kolejność, totals, matches i
  interpretacje,
- test awarii po upsercie przed checkpointem,
- test wznowienia od checkpointu bez duplikatów,
- test utrwalonych wyników zgodnych z golden `payout-v2`,
- testy jednostkowe, migracyjne i fizycznego PostgreSQL.

## Out of scope

- publiczny endpoint lub ekran raportu kompletności,
- generator i walidator SQLite,
- mobile release, APK i panel builda,
- automatyczne kasowanie historycznych payoutów,
- benchmark 500 000 layoutów,
- nowe tabele albo zmiana schematu z TASK-0032.

## Acceptance criteria

- [x] Raport jest gotowy wyłącznie dla opublikowanego datasetu i reguł tej
  samej gry oraz wymiarów.
- [x] Raport liczy wyłącznie dokładny `algorithm_version`.
- [x] Każdy layout `1..layout_count` ma dokładnie jeden wynik.
- [x] Brakujące payouty mają dokładny licznik i próbkę maksymalnie 100 numerów.
- [x] Brak `audit_path` blokuje gotowość.
- [x] Historyczne wyniki innego rules lub algorytmu nie maskują braków.
- [x] Bramka `require` zwraca stabilny błąd i pełny raport.
- [x] JSONL pozwala odtworzyć payout, matches, komórki, jokery i interpretacje.
- [x] Awaria po upsercie przed checkpointem może powtórzyć partię bez duplikatu.
- [x] Restart od checkpointu nie pomija ani nie przelicza wcześniejszych partii.
- [x] Utrwalone total payout są zgodne z golden cases M1.
- [x] Testy standardowe i fizyczny PostgreSQL przechodzą.

## Assumptions

- Gotowość administracyjna wymaga niepustego `audit_path` dla każdego wyniku,
  mimo że kolumna pozostaje nullable dla diagnostyki i kontrolowanych testów.
- Poprawność istnienia i zawartości plików audytu jest osobną weryfikacją
  artefaktów; raport PostgreSQL sprawdza ich przypisanie do rekordów.
- Bounded sample ma limit 100 jak istniejące raporty datasetu.
- Duplikat dokładnego klucza jest niemożliwy dzięki primary key; raport
  potwierdza zgodność liczby wyników i brakujących sekwencji.
- Zestaw archiwalny nie jest gotowym wejściem nowego snapshotu, nawet jeśli
  wyniki historyczne pozostają w bazie.

## Expected files

- `services/worker/src/game_predictor_worker/payouts/readiness.py`
- `services/worker/src/game_predictor_worker/payouts/store.py`
- `services/worker/src/game_predictor_worker/payouts/audit.py`
- testy payout batch/readiness/PostgreSQL
- dokumentacja stanu, modelu i testów

## Verification

```powershell
pytest services/worker/tests/test_payout_readiness.py -q
pytest services/worker/tests/test_payout_batch.py -q
pytest services/api/tests/integration/test_payout_store.py -q
npm run quality
```

## Risks / open questions

- Brak pytań blokujących. Pełna weryfikacja wszystkich plików audytu może być
  kosztowna dla 500 000 rekordów i zostanie zmierzona w M3.5.

## Outcome

- Dodano czysty raport i bramkę gotowości payoutów dla dokładnej kombinacji
  dataset/rules/algorithm wraz ze stabilnymi problemami i bounded próbką 100
  brakujących sekwencji.
- PostgreSQL wyznacza dokładne liczniki agregatami i lewym złączeniem bez
  materializowania pełnego datasetu; wyniki innych wersji nie maskują braków.
- Strumieniowy walidator JSONL potwierdza nagłówek, kolejność, totals, matches,
  komórki, jokery i ich interpretacje.
- Testy dowodzą bezpiecznego retry po upsercie przed checkpointem, wznowienia od
  checkpointu i zgodności wszystkich utrwalonych payoutów z golden cases M1.
- Pełna bramka przeszła: 170 standardowych testów Python, 63 mobile, 51 panelu,
  23 wspólnej domeny i 8 klienta API; dodatkowo przeszło 5 fizycznych testów
  PostgreSQL.
