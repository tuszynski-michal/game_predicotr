---
title: TASK-0773 — Nieaktualny odczyt planszy w oknie linii i odświeżenie jednej planszy
status: done
last_updated: 2026-09-30
---

# TASK-0773 — Nieaktualny odczyt planszy w oknie linii

## Status

`done`

## Goal

Okno planszy z liniami nie kończy się błędem
`BOARD_SEARCH_BOARD_REVISION_CONFLICT` dla planszy, której siatka zmieniła
się po zapisaniu dokumentu wyszukiwania, i pozwala odświeżyć odczyt tej
jednej planszy.

## Context

Zgłoszenie operatora z 2026-09-30 (plansza #67755, spin 1443). Diagnoza
tylko do odczytu: dokument wyszukiwania z 2026-09-24 (suma `205f…`), rewizja
geometrii 1 planszy `virtual_source` z 2026-09-25 (suma `afee…`); dokumentu
nie odświeżono. W grze 7 takich dokumentów jest 88 260 z 500 000, wszystkie
`pending`. Tabela „Przybliżonej wygranej” liczy je ze starego odczytu.

## Dependencies / entry conditions

- TASK-0763, TASK-0764, TASK-0772 done.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Audyt: niezależny agent
`claude-opus-5-5` (`high` warunkowo).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/requirements/ADMIN_APP.md`

## Scope

- Szczegóły planszy: `documentStale` zamiast 409; linie z dokumentu,
  `view = null`, `cells = null`.
- `POST .../board-search/boards/{n}/refresh` (`sync_review_item` jednej
  planszy operacyjnej), klient i wrapper.
- Okno: ostrzeżenie, schemat, przycisk „Odśwież odczyt tej planszy”,
  przeliczenie tabeli po zamknięciu.

## Out of scope

- Odświeżenie wszystkich 88 260 nieaktualnych dokumentów (osobna operacja na
  danych z podglądem i zgodą).
- Naprawa ścieżki, która zapisała rewizje geometrii bez synchronizacji
  projekcji (osobne zadanie diagnostyczne).

## Acceptance criteria

- [x] Nieaktualny dokument: 200 z `documentStale = true`, liniami, bez widoku
  i pól; widok nadal 409.
- [x] Odświeżenie przebudowuje dokument; potem `documentStale = false`,
  widok i pola wracają; archiwum → 409, brak dokumentu → 404.
- [x] Okno pokazuje ostrzeżenie i schemat zamiast błędu; odświeżenie działa i
  przelicza tabelę po zamknięciu.

## Outcome

### Changed

- API: szczegóły planszy zwracają `documentStale` zamiast 409 dla
  nieaktualnego dokumentu (linie z dokumentu, bez widoku i pól);
  `POST .../board-search/boards/{n}/refresh` przebudowuje dokument pozycji
  (`sync_review_item` + `sync_sequence_candidates`, `expire_all` po zapisie) i
  zwraca `{ documentRemoved, detail }`; kod `BOARD_SEARCH_BOARD_REFRESH_UNSUPPORTED`.
- Klient: `refreshBoardSearchBoardDocument`.
- Admin: ostrzeżenie, schemat 3 × 5, „Odśwież odczyt tej planszy”, obsługa
  błędu i usuniętego dokumentu, nagłówek „Po odświeżeniu”, przeliczenie
  tabeli po zamknięciu.
- Dokumentacja: `API_CONTRACT.md`, `ADMIN_APP.md`, plan §4.2 i T4, D-474.

### Verification results

- Diagnoza tylko do odczytu na bazie deweloperskiej: #67755 — dokument
  2026-09-24 (`205f…`), rewizja geometrii 1 z 2026-09-25 (`afee…`); 88 260
  nieaktualnych dokumentów `pending` w grze 7, 0 w pozostałych grach.
- Testy API szczegółów i widoku: 37 PASS, 1 pominięty (dowiązania
  symboliczne); integracja PostgreSQL 2/2 PASS (stan nieaktualny, przebudowa,
  brak zapisów przy odczycie); ruff czysto; OpenAPI i klient aktualne;
  `admin-api-client` 68/68.
- Admin: interakcje `board-search-*` 30/30 (nieaktualna plansza, błąd
  odświeżenia, odświeżenie, przeliczenie), typecheck i lint bez błędów.
- Audyt niezależnego agenta `claude-opus-5-5` (poziom rozumowania agenta
  nieustawialny z sesji): cykl 1 FAIL — P2 przebudowa usuwająca dokument
  kończyła się 404 i wycofaniem zapisu; P3 cache ORM, pozostali kandydaci
  pozycji, testy, dokumentacja, nagłówek. Poprawki naniesione; cykl 2 PASS
  (uwaga P3a poprawiona przed commitem `v1.7.92`).

### Not completed

- Masowe odświeżenie 88 260 dokumentów i naprawa ścieżki, która pominęła
  synchronizację (zgłoszone jako osobne zadanie).
