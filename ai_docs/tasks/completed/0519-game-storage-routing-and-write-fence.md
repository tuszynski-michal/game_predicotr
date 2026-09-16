---
title: TASK-0519 — Routing magazynu gry i blokada zapisu
status: done
last_updated: 2026-09-09
---

# TASK-0519 — Routing magazynu gry i blokada zapisu

## Status

`done`

## Goal

Zapewnić jeden wersjonowany adapter wyboru magazynu gry oraz transakcyjną
blokadę, która uniemożliwia zapis podczas migracji lub z nieaktualną generacją.

## Context

TASK-0518 utworzył pusty schemat `game_data_v2` i trwały registry, ale celowo
pozostawił go write-closed. Przed kopiowaniem danych aplikacja, worker i skrypty
utrzymaniowe muszą używać tego samego kontraktu lokalizacji i generacji.

## Dependencies / entry conditions

- TASK-0518 zakończony w `v0.10.238`.
- Migracja 0105 jest wyłącznie częścią toru; nie jest automatycznie wykonywana
  na bazie użytkownika w tym zadaniu.
- Dane i artefakty użytkownika nie są modyfikowane.

## Recommended execution

`gpt-6-astra` z reasoning `high`. Niezależny review: `gpt-6-astra high` po
przejściu testów skoncentrowanych, ze szczególnym naciskiem na blokady,
transakcje i zachowanie starych jobów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- Wspólny adapter lokalizacji `public` / `game_data_v2` dla API, workera,
  repozytoriów i skryptów.
- Jawny scope `game_id`, intencja read/write i oczekiwana generacja.
- Transakcyjny fence zapisu oparty o registry i blokadę współdzieloną.
- Stabilne błędy dla maintenance, stale generation i braku scope.
- Stan storage i dostępność zapisu w katalogu gier przez backend, OpenAPI,
  wygenerowany klient, wrapper i Admin.
- Testy routing/fence/restart oraz audyt użyć game-owned danych.

## Out of scope

- Kopiowanie danych, tworzenie partycji konkretnej gry i cutover.
- Projekcja bieżących symboli, liczniki i optymalizacja listy.
- Reset lokalnej bazy, restart usług i operacje na danych użytkownika.

## Acceptance criteria

- [x] Brak registry oznacza historyczny `public`, generację 1 i zapis dostępny.
- [x] V2 wymaga jawnego scope gry i ustawia lokalną ścieżkę tylko w transakcji.
- [x] Write fence blokuje `migrating`, `deleting`, `blocked` i stale generation.
- [x] Zmiana generacji nie może wejść między sprawdzenie fence a commit zapisu.
- [x] Jedna sesja nie może po cichu przełączyć się na inną grę lub generację.
- [x] Surowy SQL korzysta z kwalifikowanych nazw z zamrożonego manifestu.
- [x] Odpowiedź gry pokazuje store, generację, status i write availability.
- [x] Historyczne publiczne joby pozostają globalne i nie tracą payloadu.

## Technical notes

Adapter rozwiązuje registry wyłącznie z `public`, a następnie przypina scope do
transakcji. Dla zapisu blokuje wiersz registry w trybie współdzielonym;
cutover musi uzyskać blokadę wyłączną. Ustawienie `search_path` nie zastępuje
scope `game_id`: helpery SQL i zapytania ORM nadal muszą zawierać właściciela.

## Expected files

- Nowe: `services/api/src/game_predictor_api/storage/game_storage_routing.py`.
- Nowe: migracja zabezpieczeń runtime po 0105.
- Istniejące: katalog domenowy, repozytorium katalogu, schema/API gry.
- Istniejące: OpenAPI, wygenerowany klient, wrapper i katalog Admina.
- Nowe lub istniejące: testy jednostkowe, PostgreSQL i interakcji Admina.
- Dokumentacja procesu i architektury.

## Test cases

- Legacy bez registry, aktywne public i aktywne v2.
- Migrating/deleting/blocked oraz niezgodna generacja.
- Dwa zapisy kontra próba cutoveru i restart sesji.
- Próba zmiany game scope w tej samej transakcji.
- Nieznana tabela raw SQL i brak game scope.
- Roundtrip API/OpenAPI/UI stanu maintenance.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest <focused tests> -q
.venv\Scripts\python.exe -m ruff check <changed Python files>
.venv\Scripts\python.exe -m mypy <changed Python files>
npm run openapi:check
npm run typecheck --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin
```

## Risks / open questions

- Pełny cutover pozostaje zamknięty do odbioru migratora i utworzenia partycji.
- Lokalny superuser PostgreSQL może omijać RLS; podstawową ochroną jest fence i
  jawny adapter, a testy muszą dowodzić zachowania niezależnie od roli DB.

## Outcome

Zaimplementowano wspólny router magazynu i transakcyjny write fence. Registry
jest rozwiązywane z `public`; brak wpisu zachowuje legacy generation 1. Scope
ustawia lokalnie `search_path`, `game_id` i generację, a commit/rollback usuwa
binding. Każdy zapis uzyskuje współdzieloną blokadę advisory gry i `FOR SHARE`,
przez co cutover czeka na zakończenie transakcji także przed utworzeniem registry.
Raw SQL o nieznanej semantyce jest traktowany jak zapis.

Worker przypina grę tylko na czas wykonania handlera. Migracja 0106 dodała RLS,
domyślny scope i schema-aware triggery do wszystkich 65 parentów v2. Katalog API,
OpenAPI, klient i Admin pokazują stan magazynu; mutacje katalogu są wyłączone w
maintenance.

Wyniki bramek:

- 108 skoncentrowanych testów API/workera — passed;
- 4 izolowane testy PostgreSQL pełnego toru migracji — passed;
- 448 testów Admina — passed;
- Ruff i mypy zmienionego pionu — passed;
- typecheck klienta i Admina, OpenAPI check oraz produkcyjny build Admina — passed;
- szerszy test API został ograniczony po 120 sekundach zgodnie z polityką;
  pierwsze 39% przeszło bez błędu po poprawieniu czterech historycznych testów
  offline, które błędnie generowały cały `head` zamiast własnej migracji.

Globalny `npm run format:check` nadal wskazuje 31 wcześniejszych, niezwiązanych
plików. Wszystkie pliki TypeScript/TSX/CSS/JSON zmienione w TASK-0519 przechodzą
osobny Prettier check; obcych zmian nie formatowano ani nie dołączono.

Nie wykonano migracji na bazie użytkownika, nie utworzono partycji gry, nie
przełączono routingu żadnej gry i nie uruchomiono usług. Audyt znajduje się w
`ai_docs/quality/game-storage-routing-audit-2026-09-08.md`.
