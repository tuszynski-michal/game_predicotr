---
title: Historical offline migration baseline repair
status: accepted
last_updated: 2026-09-08
---

# Naprawa zakresu historycznych testów migracji offline

## Przyczyna i zakres

16 historycznych testów generowało SQL od początku aż do `head`, mimo że ich
asercje dotyczą konkretnych wcześniejszych migracji. Po dodaniu 0104 testy
dochodziły do celowej bramki `0104 requires online catalog validation; no offline SQL`.
Nie był to błąd PostgreSQL ani dowód braku DDL historycznych funkcji.

Naprawa przypina wyłącznie cel upgrade każdego testu do najwyższej rewizji
potrzebnej jego asercjom. Pozostawia wszystkie asercje i downgrade bez zmian.
Nie zmienia 0104 ani jej wymogu kontroli katalogu w trybie online.

| Testowany obszar | Cel upgrade |
|---|---|
| Games/symbols | `CATALOG_REVISION` |
| Rules | `RULES_REVISION` |
| Paylines | `PAYLINES_REVISION` |
| Symbol payouts | `PAYOUTS_REVISION` |
| Dataset staging | `DATASETS_REVISION` |
| Jobs | `JOBS_REVISION` |
| Job leases | `JOB_LEASES_REVISION` |
| Layout payouts | `LAYOUT_PAYOUTS_REVISION` |
| Mobile releases | `MOBILE_RELEASES_REVISION` |
| Layout import staging | `LAYOUT_IMPORT_STAGING_REVISION` |
| Layout normalization | `LAYOUT_IMPORT_NORMALIZATION_REVISION` |
| Layout publication | `LAYOUT_IMPORT_PUBLICATION_REVISION` |
| Review batches | `REVIEW_BATCHES_REVISION` |
| Review feedback | `REVIEW_FEEDBACK_REVISION` |
| Cohort cells | `VERIFIED_TRAINING_COHORT_CELLS_REVISION` |
| Legacy cleanup receipt | `LEGACY_GAME_OPERATIONAL_CLEANUP_REVISION` |

## Weryfikacja

- Przed naprawą: historyczny baseline 49 passed / 16 failed.
- Po naprawie: baseline 65 passed; razem z 8 testami TASK-0518 **73 passed w 49,04 s**.
- Ruff format/check oraz mypy `--follow-imports=silent`: passed dla pięciu plików
  Python obejmujących oba zestawy testów oraz nowy schemat/manifest.
- Każda komenda używała `.venv/Scripts/python.exe` i subprocess timeout 120 s.
- PostgreSQL był używany tylko przez izolowane testy TASK-0518, w osobnych,
  losowo nazwanych bazach usuwanych po sprawdzeniu braku połączeń.

## Rozdzielenie commitów

Ta naprawa jest osobnym commitem przed TASK-0518: 16 zmian targetów upgrade
w `test_migration_baseline.py` i niniejszy raport. Historyczna asercja head
musi odpowiadać 0104 w tym punkcie toru; przejście do 0105 oraz sprawdzenie
jej rodzica należą do kolejnego commita TASK-0518.
