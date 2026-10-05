---
title: TASK-0853 — Mumie: przygotowanie aktualnych etykiet symboli
status: done
last_updated: 2026-10-05
---

# TASK-0853 — Mumie: aktualne etykiety

## Status

`done` — pakiet i kontrola zakończone; T06b/T07 nadal wymagają kwalifikacji.

## Goal

Przygotować i sprawdzić niezmienny pakiet bieżących ręcznych etykiet Mumii,
z jawną kwalifikacją i granicą dalszego treningu.

## Context

Operator zakończył przypisywanie i zlecił pracę do najdalszego etapu bez jego
udziału. Stan rev63: 339 świeżych approve w 10 klasach, w tym 27 Mumii.
Liczność 30 jest celem zbierania przykładów, nie obowiązkowym minimum.

## Dependencies / entry conditions

Aktywna referencja D-496, zatwierdzony słownik v1 i pełne geometrie.
Źródła trzech grup mają nierozstrzygnięte pochodzenie; split symboli nie
istnieje. Brak potwierdzenia nagrań zatrzymuje tylko trening zależny, nie
kontrolę aktualności i pakiet przygotowawczy.

## Recommended execution

gpt-6.1-sol, high. Samodzielny przegląd i testy; bez delegowania.
Zmiana ról/zgód albo wymaganie użycia holdoutu zatrzymuje zależne działanie.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/delivery/MUMIE_SYMBOL_PREPARATION_20261005.md`
- `ai_docs/delivery/MUMIE_TRAINING_RESUME_20261004.md`
- `ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md` (D-489, D-496)

## Scope

CLI przygotowania/verify, aktualne decyzje D-496, dokładne istniejące cropy,
create-only publikacja, pełna historia symboli, raport duplikatów i bramek.

## Out of scope

Trening bez kwalifikacji rodzin/splitu, automatyczne etykiety Super,
interpretacja wypłat, DB, migracje, zmiany anotacji, aktywacja, shadow,
push, merge i wdrożenie. T06b/T07 nie są ukończone przez ten pakiet.

## Acceptance criteria

- [x] Pakiet zawiera wyłącznie aktualne approve aktywnej wersji etykiet.
- [x] Dokładne crop bytes/bindingi i pełna historia są checksumowane.
- [x] Chronione źródła są blokowane przed odczytem cropów.
- [x] Report zawiera klasy, komponenty, duplikaty i bramki treningu.
- [x] Retry i verify w nowym procesie PASS; magazyny bez zmian.
- [x] Testy, lint, format, typy i własny audyt PASS; osobny commit poniżej.

## Technical notes

Plan wykonawczy powyżej określa kontrakt. Pakiet ma trainable=false i brak
assignments; żaden obecny adapter treningu nie akceptuje tego formatu.
Nieważna świeża decyzja zatrzymuje operację z jawnym błędem, bez cichego
zmniejszania zbioru. Brak nowych decyzji daje jawny empty error.

## Expected files

- Istniejące: `symbol_store.py::local_row/locked/preview_grant`, bez zmian.
- Proponowane: `vision_lab/symbol_preparation.py`, test oraz raport jakości.
- Dokumentacja: wymagania, architektura, CURRENT_STATE, ten task.

## Test cases

Fresh/legacy/superseded/withdrawn; protected przed bytes; tamper i retry;
duplikaty identycznych pikseli z różnymi klasami; brak zmian store po odczycie.

## Verification

Main `.venv/Scripts/python.exe`, PYTHONPATH worktree/services/worker/src,
pytest nowego modułu i `test_vision_lab_symbol_dataset_version.py` (120 s),
Ruff check/format (60 s) i scoped Mypy (120 s), przez ograniczony runner.
CLI prepare i verify (120 s) w nowych procesach na istniejących danych.

## Risks / open questions

Pytanie wysłane: relacja nagrań `1 - 23175`, `76555 - 103221`,
`156538 - 182853`. Żaden z tych faktów nie może być zgadywany z numeracji.
Obecne etykiety nie rozróżniają oddzielnie ramki Super.

## Outcome

### Changed

Nowy CLI prepare/verify, niezmienny qualification_only pakiet z 339 aktualnych
approve w 10 klasach, 13 zdjęć / 3 komponenty, 27 Mumii. Oryginalne PNG,
pełna historia symboli i receipts, report klas/duplikatów/blokerów. Brak
mutacji store, trainable=false, brak assignments. Osobny commit `v1.7.199`;
pełny hash zostanie dopisany po commicie.

### Verification results

20 testów PASS (13 nowych, 7 D-496). Ruff check/format i scoped Mypy PASS.
Publikacja 24,44 s, verify w nowym procesie 11,44 s; ponowne prepare odzyskuje
ten sam ID. Magazyny SHA identyczne ze stanem sprzed taska. 341 plików,
9 219 147 bajtów. Własny audyt i porównanie wszystkich kryteriów z planem/DoD
PASS. Kontaktowy podgląd przykładów obejrzany, bez zastąpienia zgód człowieka.

### Not completed

T06b/T07 i trening pozostają nieodebrane: nierozstrzygnięte nagrania oraz
brak splitu symboli. Pytanie o trzy grupy pending. Zero osobnych decyzji
ramki Super; bez jej etykiet lub treningu. Bez DB, migracji, aktywacji,
shadow, materializacji, push, merge i wdrożenia. API/UI nie wymagają restartu.

### Documentation updates

Plan, wymagania/architektura, CURRENT_STATE i raport jakości
`ai_docs/quality/MUMIE_SYMBOL_PREPARATION_20261005.md`. Pakiet:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-preparation-20261005\7fb60ce3edc52081d5f9cf016083a8cd6b048766db30d8df8b008fca0dccb1c8`.

### Recommended next task

Rozstrzygnięcie nagrań, kwalifikacja i osobny podział symboli, następnie T07.
