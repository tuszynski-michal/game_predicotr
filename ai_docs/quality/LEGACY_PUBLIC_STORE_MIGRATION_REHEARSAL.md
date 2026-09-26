---
title: Rehearsal migracji legacy public store
status: accepted
last_updated: 2026-09-26
---

# TASK-0685 — rehearsal `0125_remove_legacy_public_game_store`

## Wynik

**Ready dla STOP B.** Rehearsal wykonał pełną ścieżkę wyłącznie na świeżej,
losowo nazwanej bazie testowej PostgreSQL: read-only preflight → Alembic `0125`
→ zamknięcie puli → postflight z nowej sesji. Nie połączono się z bazą
użytkownika i nie wykonano na niej DDL ani DML.

| Krok | Wynik |
|---|---|
| Preflight | `ready`; 65 zwykłych relacji legacy, wszystkie puste; brak blockerów, aktywnych jobów i migracji |
| Rewizja przed apply | `0124_game_data_v2_partial_visibility_constraints` |
| Apply | `0125_remove_legacy_public_game_store`, 1 312 ms na izolowanej bazie |
| Postflight nowej sesji | 0/65 relacji legacy w `public`; 65 parentów `game_data_v2`; pozostają `games`, `symbols`, `jobs`, `game_storage_locations` |
| PostgreSQL | `18.4` |
| Preflight SHA-256 | `271e76900c13f22b0aa976a0c80059fb57575930e4bc5ffbb4d52e68204b0bb8` |
| Postflight SHA-256 | `b64dadd6ff6e920f50ac628a30649a5668b1b9c8262f10dd3d691cb06e213ec` |

Checksumy dotyczą znormalizowanych raportów izolowanego przebiegu; preflight
zawiera czas i nazwę efemerycznej bazy, więc są dowodem konkretnej próby, a nie
wartością oczekiwaną dla T09.

## Negatywne ścieżki

| Warunek | Reakcja | Dowód |
|---|---|---|
| Wiersz w relacji legacy | `LEGACY_PUBLIC_STORE_TABLE_NOT_EMPTY` przed pierwszym `DROP`; wszystkie 65 relacji pozostają. | Izolowany test PostgreSQL. |
| Zewnętrzny FK albo widok | Fail-closed przed DDL. | Scenariusze T05, nadal w tym samym teście migracji. |
| Inny rodzaj relacji | Fail-closed przed DDL. | Scenariusz T05 dla zastąpionej relacji widokiem. |
| Blokada `ACCESS SHARE` na `public.source_images` | PostgreSQL zwraca `lock timeout` po limicie migracji 2 s; rewizja i 65 relacji pozostają niezmienione. | Nowy test T06. |
| `CASCADE` | Niedozwolone; test statyczny wymaga `DROP TABLE … RESTRICT` i odrzuca wystąpienie `CASCADE` w źródle migracji. | Nowy test T06. |

Limity `lock_timeout = 2s` i `statement_timeout = 30s` są częścią `0125`.
Wynik 1 312 ms nie jest benchmarkiem 85 GB bazy: dowodzi jedynie ścieżki
kontrolnej na pustych, małych relacjach testowych.

## Warunki przekazane do T09

T09 może rozpocząć się wyłącznie po świeżym raporcie read-only z
`scripts/audit_legacy_public_game_store.py`, który jest `ready`, ma własną
checksumę i potwierdza: dokładnie 65 zwykłych, pustych relacji, aktywne V2
location dla każdej gry, brak aktywnych migracji, jobów i obcych locków oraz
brak zewnętrznych FK/zależności. Następnie operator musi przedstawić ten raport
użytkownikowi i uzyskać osobne, dokładne potwierdzenie apply `0125`.

Niepustość, drift relacji, blocker preflightu, lock, timeout albo błąd
migracji oznacza stop. Nie wykonuje się ręcznego `DROP`, `CASCADE`, downgrade
ani automatycznego retry; należy zachować raport i odczytać katalog przed
następną decyzją.

## Weryfikacja

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest `
  services/api/tests/integration/test_legacy_public_store_removal_migration.py `
  -k "snapshot_is_exact_frozen_manifest or rehearsal_preflight_apply_and_new_session_postflight"
# 2 passed

.\.venv\Scripts\python.exe -m pytest `
  services/api/tests/integration/test_legacy_public_store_removal_migration.py `
  -k "lock_timeout_happens_before_any_drop or nonempty_guard_happens_before_any_drop"
# 2 passed, uruchomione osobno dla limitu pojedynczego kroku

.\.venv\Scripts\python.exe -m ruff check `
  services/api/tests/integration/test_legacy_public_store_removal_migration.py
```

W trakcie jednego przekroczonego, połączonego przebiegu zakończono dwa
osierocone procesy testowe i usunięto wyłącznie zweryfikowaną, losową bazę
`game_predictor_task0684_c57483a32c77`. Kolejne krótkie przebiegi podały
wyniki powyżej.
