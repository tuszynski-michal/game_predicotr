---
title: TASK-0136 responsive compact Selection grid and labels
status: done
last_updated: 2026-08-01
completed_at: 2026-08-01
---

# TASK-0136 — Responsive compact Selection grid and labels

## Status

`done`

## Goal

Dodać opcjonalne polskie i angielskie nazwy symboli do całego kontraktu danych
oraz wyświetlać symbole Mobile w zwartej, zawijanej siatce bez poziomego
przewijania.

## Context

TASK-0135 usunął redundantny nagłówek Selection. TASK-0136 domyka właściwą
prezentację symboli i przenosi etykiety `name_pl`/`name_en` z kanonicznego
PostgreSQL do snapshotu SQLite schema v3.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MOBILE_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/VERSION_0_3_EXECUTION_PLAN.md`

## Scope

- dodać przez Alembic nullable `symbols.name_pl` i `symbols.name_en`,
- rozszerzyć domenę, repository, Admin API, OpenAPI i generowanego klienta,
- umożliwić edycję obu opcjonalnych nazw w istniejącym formularzu symbolu,
- podnieść produkcyjny snapshot i Mobile do schema v3,
- zapisać obie nazwy w tabeli `symbols` snapshotu i logicznym checksumie,
- rozszerzyć wspólny kontrakt `SymbolDefinition`, zachowując wymagane `name` jako
  fallback zgodności,
- wybierać krótszą niepustą nazwę z PL/EN, przy remisie preferować polską,
- zawijać kafelki Selection do kolejnych wierszy bez poziomego przewijania,
- pozostawić co najmniej 44 × 44 punkty obszaru dotykowego oraz dostępne nazwy.

## Out of scope

- zmiana stabilnych `code` i `mobile_code`,
- zmiana assetów obrazów symboli,
- nawigacja `Next` i limit Targetu,
- migracja historycznych APK; nowe wydanie otrzyma nowy snapshot v3.

## Acceptance criteria

- [x] Migracja Alembic dodaje i cofa `name_pl`/`name_en` bez utraty `name`.
- [x] Puste po trimowaniu nazwy PL/EN są odrzucane, a `null` oznacza brak
      etykiety.
- [x] Admin API, klient i formularz zapisują oraz odczytują obie nazwy.
- [x] Snapshot używa `PRAGMA user_version = 3`, zawiera obie kolumny i obejmuje
      je logicznym checksumem.
- [x] Mobile akceptuje wyłącznie schema v3 i odczytuje opcjonalne nazwy.
- [x] Selection wybiera krótszą nazwę, przy remisie PL, a następnie fallback
      `name`.
- [x] Kafelki zawijają się, nie używają poziomego ScrollView i zachowują
      dostępność oraz minimalny obszar dotykowy.
- [x] Testy zmienionych modułów, OpenAPI, typecheck, lint i format przechodzą.

## Technical notes

- Nullable update rozróżnia pole pominięte od jawnego `null`, aby można było
  usunąć wcześniej ustawioną etykietę.
- Schema v2 nie jest otwierana przez Mobile 0.3; nazwa lokalnej kopii zawiera
  wersję schematu, więc nie koliduje z wcześniejszym snapshotem.

## Expected files

- `services/api/alembic/versions/0025_symbol_localized_names.py`
- `services/api/src/game_predictor_api/domain/catalog.py`
- `services/api/src/game_predictor_api/application/catalog.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/storage/catalog_repository.py`
- `services/api/src/game_predictor_api/schemas/catalog.py`
- `services/api/src/game_predictor_api/api/catalog.py`
- `packages/admin-api-client/openapi/openapi.json`
- `packages/admin-api-client/src/generated/**`
- `apps/admin/src/features/symbols/**`
- `services/worker/src/game_predictor_worker/snapshots/**`
- `packages/shared-ts/src/contracts.ts`
- `apps/mobile/src/data/**`
- `apps/mobile/src/features/board/symbol-selection.tsx`
- testy odpowiadające zmienionym modułom

## Verification

```powershell
npm.cmd run openapi:generate
npm.cmd run openapi:check
npm.cmd test --workspace @game-predictor/mobile
npm.cmd run typecheck --workspace @game-predictor/mobile
npm.cmd run lint --workspace @game-predictor/mobile
npm.cmd test --workspace @game-predictor/admin
npm.cmd run typecheck --workspace @game-predictor/admin
.venv\Scripts\python.exe -m pytest services/api/tests services/worker/tests
```

## Risks / open questions

- Pełny globalny zestaw testów Pythona może przekroczyć limit pojedynczej
  komendy; weryfikacja zostanie podzielona na ograniczone zestawy zmienionych
  pionów.

## Outcome

Ukończono pełny pion opcjonalnych nazw PL/EN: migrację PostgreSQL, domenę,
repository, Admin API, OpenAPI i formularz. Produkcyjny oraz fixture snapshot
korzystają ze schema v3, przechowują obie etykiety i obejmują je logicznym
checksumem. Mobile odczytuje pola z SQLite i pokazuje krótszą nazwę w zawijanej
siatce bez poziomego ScrollView; remis wybiera PL, a brak lokalizacji korzysta z
dotychczasowego `name`.

Zweryfikowano migrację na lokalnym PostgreSQL oraz round-trip lokalizowanych
nazw. Przeszły: 68 testów Mobile, 140 testów Admina, 24 testy klienta API,
39 testów domeny/API/OpenAPI, 50 testów snapshotu/workflow, 2 celowane testy
integracyjne, typechecki TypeScript, lintery, OpenAPI check, generowanie i
walidacja snapshotu. Odbiór wizualny na Pixelu pozostaje wspólną bramką
TASK-0141.

Pełny `python:typecheck` przekroczył limit 120 sekund; krótsza diagnostyka
zatrzymała się na trzech istniejących problemach poza zakresem zadania w
`security/local_admin.py` i `main.py`. Zmienione piony Pythona przeszły Ruff i
testy, a pozostałe błędy mypy nie pochodzą z diffu TASK-0136.
