# TASK-1024 — Zamknięcie nieaktualnych tasków na `main`

## Status

`done`

## Goal

Na `main` nie ma aktywnych plików tasków, które opisują nieaktualny stan;
okno `CURRENT_STATE.md` i indeks dokumentacji pokazują stan bieżący.

## Context

Przegląd TASK-1021 wykazał 15 rozbieżności (R1–R15) między oknem stanu a
plikami 42 aktywnych tasków (TASK-0290–0972). Operator 2026-10-16 uznał
wszystkie te taski za nieaktualne: funkcjonalności, których dotyczyły, są
przetestowane w późniejszych pracach. Polecił je zamknąć i scalić wynik do
`main`.

## Recommended execution

claude-opus-5-5 (sesja leada), bez audytu Codex (decyzja operatora 2026-10-16).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/quality/CURRENT_STATE_REVIEW_20261016.md` (sekcja 5)

## Scope

- 42 pliki z `ai_docs/tasks/` przeniesione do `ai_docs/tasks/completed/`
  ze statusem `done`, z zachowaniem poprzedniego statusu w linii statusu i
  sekcją „Zamknięcie (2026-10-16, TASK-1024)”; front matter `status: done`.
- `CURRENT_STATE.md`: brak wskaźników aktywnych tasków; tabela planów tylko
  z planem V3 (tor `codex/v3-grid-fine-tuning`); usunięte pytania R1–R15;
  ograniczenia dotyczące wyłącznie zamkniętych tasków przeniesione do
  archiwum, pięć ograniczeń przepisanych (gałąź `main`, cykl usług, migracje
  do `0155`, operacje destrukcyjne, narzędzia tokenowe).
- `ai_docs/README.md`: statusy planów z zamkniętymi taskami.

## Out of scope

- Kod, baza, migracje, usługi; usuwanie danych z dysku C (TASK-0957 zamknięty
  bez wykonania podglądu czyszczenia).
- Nagłówki statusu w samych plikach planów `delivery/` (stan bieżący podaje
  `README.md`).
- Taski toru V3 na gałęzi `codex/v3-grid-fine-tuning`.

## Acceptance criteria

- [x] `ai_docs/tasks/` nie zawiera plików tasków; każdy z 42 plików jest w
      `completed/` bez utraty treści poza linią statusu.
- [x] `npm run docs:check` PASS z budżetami.
- [x] Usunięte i przepisane teksty okna są bez zmian na początku archiwum Q4
      (sekcja „Zamknięte z okna 2026-10-16 (TASK-1024)”).

## Outcome

Commit: v1.7.375 (hash dopisuje kolejny commit).

### Changed

- 42 pliki tasków: TASK-0290, 0305, 0472, 0517, 0603 (`0603-v7-real-777-calibration.md`),
  0611, 0645–0647, 0649–0653 (pliki `grid-nn-*`), 0654, 0668, 0671–0678,
  0687–0691, 0694, 0695, 0698, 0802, 0928, 0937, 0939, 0947–0949, 0956, 0957,
  0972.
- `CURRENT_STATE.md` 23 036 → ok. 9 300 B; archiwum Q4: 138 linii
  przeniesionego tekstu; `README.md`: sześć opisów planów.

### Verification results

- Pierwsze podejście skryptu popełniło dwa błędy, wykryte przed commitem:
  (1) poprawka front matter wybierała plik po numerze i trafiła w pięć
  ukończonych plików o kolidujących numerach (0603 shape v2, 0649 i 0651–0653
  „Przybliżona wygrana”); przywrócono je z HEAD; (2) w TASK-0472 status bez
  pustej linii pochłonął listę „Relevant docs” i został ucięty. Wszystkie 42
  pliki odbudowano z HEAD po pełnej nazwie, bez ucinania poprzedniego statusu.
- `git diff -M` dla 42 przeniesień: zmienione tylko linie statusu i front
  matter oraz dopisana sekcja zamknięcia.
- `npm run docs:check`: PASS (0 aktywnych tasków, 10 wpisów `done`, 9/9
  budżetów).

### Not completed

- Brak.

### Recommended next task

- Brak; kolejne prace zakładają nowe taski.
