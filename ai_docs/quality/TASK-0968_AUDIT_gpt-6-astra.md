# Audyt TASK-0968 - API listy, podglądu i cofnięcia korekt geometrii

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, medium
Zakres: HEAD...3aa7d04525c9df391a9f82d5839e5ecca4d32e2b oraz zmiany niezacommitowane, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano router, schematy, podłączenie serwisu, autoryzację, allowlisty, OpenAPI, klienta oraz testy wskazane w briefie. Implementacja zachowuje zakres zadania i deleguje cofanie do istniejącego serwisu. Brakuje jednego przypadku wymaganego przez kryterium pokrycia każdego kodu 409.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/tests/test_geometry_correction_revert_api.py:384` — test dodatkowych kodów 409 pomija `GEOMETRY_REVERT_RENDER_FAILED`. Kod ten nie należy do `RevertBlockingReason`, więc nie obejmuje go również test parametryzowany z linii 356. Jest częścią opublikowanego kontraktu i może zostać zgłoszony przez rzeczywisty weryfikator renderu. Kryterium „każdy 409 mapowany na kod” pozostaje niepełne. Należy dodać przypadek `GEOMETRY_REVERT_RENDER_FAILED` i sprawdzić status 409 oraz zachowanie pól `code` i `message`.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Trzy trasy w OpenAPI i kliencie | spełnione | `services/api/tests/test_openapi_contract.py:780`; `packages/admin-api-client/src/generated/sdk.gen.ts:2233`; `packages/admin-api-client/src/index.ts:3428` |
| Zielona kontrola aktualności OpenAPI | niezweryfikowane | Outcome deklaruje poprawny eksport i kontrolę wygenerowanego klienta; audyt nie uruchamiał poleceń weryfikacyjnych. |
| Testy listy: kolejność, limit, możliwość cofnięcia i powód blokady | spełnione | `services/api/tests/test_geometry_correction_revert_api.py:231`, `services/api/tests/test_geometry_correction_revert_api.py:241` |
| Test podglądu bez zapisu | spełnione | `services/api/tests/test_geometry_correction_revert_api.py:280` |
| Test cofnięcia i powtórzenia z kluczem | spełnione | `services/api/tests/test_geometry_correction_revert_api.py:304`, `services/api/tests/test_geometry_correction_revert_api.py:339` |
| Każdy kod 409 objęty testem mapowania | niespełnione | `services/api/tests/test_geometry_correction_revert_api.py:384`; P1-1 |
| Proxy dopuszcza wyłącznie trzy właściwe kombinacje tras i metod | spełnione | `apps/reviewer/src/security/reviewer-proxy-policy.ts:137`; `apps/reviewer/test/reviewer-proxy-policy.test.mjs:107` |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P1-1.

## Proponowane testy

- Uzupełnić `services/api/tests/test_geometry_correction_revert_api.py` o odmowę `GEOMETRY_REVERT_RENDER_FAILED`, z asercjami statusu 409, kodu i komunikatu. Po poprawce uruchomić: `..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_revert_api.py -q`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, zmienione routery i schematy, podłączenie zależności, istotne fragmenty serwisu i zabezpieczeń, zmiany kontraktu, wygenerowane operacje klienta, wrappery oraz testy API, proxy i klienta. Sprawdzono jawne `game_storage_scope`, autoryzację gry i importu oraz przekazywanie tokenów CAS i klucza idempotencji.

Nie uruchamiano testów, usług, migracji ani generatorów. Wyniki wykonania zapisane w Outcome są deklaracjami wykonawcy. Audyt nie potwierdza działania na PostgreSQL ani trwałości po restarcie; logika cofania z TASK-0966/0967 pozostawała poza zakresem tego przeglądu.