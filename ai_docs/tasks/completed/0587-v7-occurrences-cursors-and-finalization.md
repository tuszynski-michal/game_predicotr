---
title: TASK-0587 — V7 occurrences, cursors and finalization
status: done
last_updated: 2026-09-21
---

# TASK-0587 — Wystąpienia, kursory i finalizacja V7

## Status

`done`

## Goal

Udostępnić czysty, odtwarzalny stan skanu V7, który zbiera wszystkie
udowodnione wystąpienia zakresów, utrzymuje luki i finalizuje globalne
kandydatury dopiero po EOF bez cofania sekwencji.

## Context

T02 dostarcza source-local proof, ale nie może określić granic wystąpienia ani
podjąć decyzji o reprezentancie. W szczególności późniejsze A w `A → B → A`
musi należeć do rankingu A, a `A → C → B` ma później wypełnić lukę B bez
cofnięcia kursora.

## Dependencies / entry conditions

- T00–T02 są ukończone. T02 nadal blokuje automatyczny proof do T05, ale testy
  T03 używają jawnych, już zweryfikowanych `V7RangeProofResult`.
- T07 będzie właścicielem przypiętego manifestu źródeł i trwałego zapisu
  checkpointu; T03 definiuje wyłącznie walidowany payload checkpointu.

## Recommended execution

`gpt-5.6-terra` z reasoning `xhigh`; wymagany niezależny review
`gpt-6-astra medium` przed commitem. Eskalować, jeśli czysty kontrakt wymaga
zmiany istniejącego API, migracji albo nadania zakresu na podstawie sąsiadów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/tasks/completed/0586-v7-label-localization-and-proof.md`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_range_proof.py`

## Scope

- Deterministyczne wystąpienia, luki, trzy niezależne kursory, pause/cancel,
  EOF i checkpoint czystego silnika.
- Globalna, idempotentna lista kandydatów wystąpień po EOF dla późniejszego
  rankingu T04.

## Out of scope

- OCR, lokalizacja, ocena jakości, ranking reprezentantów, manifest plików,
  baza, API, UI, output writer i automatyczny zapis JPEG-a.

## Acceptance criteria

- [x] `A → B → A → EOF` zachowuje dwa wystąpienia A i jedno B; kursor sekwencji
  pozostaje na B, a globalna finalizacja zwraca oba A bez drugiego outputu.
- [x] `A → C → B` utrzymuje lukę B po C i usuwa ją po późniejszym B bez cofania
  kursora.
- [x] Bez dowodu, pause i restart nie zamykają ani nie zmieniają wystąpienia;
  EOF zamyka je raz, a ponowiona finalizacja nie tworzy nowych decyzji.
- [x] Checkpoint odtwarza aktywne/zamknięte wystąpienia, luki, trzy kursory i
  fazę; nieprawidłowy checkpoint kończy się fail-closed.
- [x] `cancelled` nie finalizuje ani nie publikuje wyniku, a operatorowy podgląd
  nie może zmienić postępu workera lub sekwencji.

## Technical notes

- Konsumowane obserwacje mają ściśle rosnący `source_index`. `none` jest
  zachowywane jako brak dowodu. Mocny albo prawidłowy 3+3 proof może otworzyć
  wystąpienie tylko deklarowanego `expected_range`.
- Nowy potwierdzony zakres zamyka poprzednie aktywne wystąpienie; same klatki
  bez proofu jedynie rozszerzają jego przedział. Pause nie ma skutku na granice.
- `sequence_cursor_index` jest najwyższym kiedykolwiek potwierdzonym indeksem
  w kolejności konfiguracji. Indeks niższy dołącza kandydaturę i ewentualnie
  usuwa lukę, ale nie może obniżyć kursora.
- `viewed_source_index` jest trwałym stanem operatora, niezależnym od
  `next_source_index` i `sequence_cursor_index`.
- `finish()` jest dozwolone wyłącznie w fazie `running`; po EOF faza `complete`
  jest niezmienna. T07 wykorzysta stabilne identyfikatory wystąpień, aby
  ponowiona finalizacja nie stworzyła nowych operacji writer'a.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_occurrences.py`.
- Nowe: `services/worker/tests/test_v7_occurrences.py`.
- Istniejące: `TEMP PLAN V7.md`, `CURRENT_STATE.md` i task outcome.

## Test cases

- `A-B-A`, `A-C-B`, same A rozdzielone nieudowodnionymi klatkami, EOF,
  checkpoint/restore, pause/restore, cancel, błędna kolejność źródeł,
  proof dla obcego zakresu i zmiana operatorowego podglądu.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_occurrences.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_occurrences.py services/worker/tests/test_v7_occurrences.py
```

## Risks / open questions

- Przypisanie dwóch słabych klatek 3+3 do jednego occurrence wymaga granic
  budowanych przez ten silnik przy integracji T07. T03 nie może zezwolić na
  potwierdzenie między różnymi occurrence.

## Outcome

- Dodano czysty silnik occurrence v7 z deterministycznymi identyfikatorami,
  trzema niezależnymi kursorami i fail-closed checkpointem. Skan zachowuje
  globalne kandydatury po EOF, natomiast nie tworzy decyzji rankingu ani
  operacji outputu.
- `A → B → A` zbiera późniejsze A bez cofnięcia kursora, a `A → C → B`
  uzupełnia lukę B. Poprawne słabe 3+3 może rozpocząć następny zakres po
  nieudowodnionym kadrze, lecz nie może przejść przez ostatni lokalny dowód
  innego occurrence.
- Checkpoint przechowuje zmapowaną historię zeskanowanych source ID, wiąże
  potwierdzone zakresy z occurrence proof i odrzuca overlap, sfałszowane
  wsparcie, niepełny rejestr źródeł oraz nieukończony skan bez active
  occurrence.
- Weryfikacja: 25 testów T02/T03, Ruff i mypy zmienionego modułu — PASS.
  Self-audyt uszczelnił kształt dowodów oraz identyfikatory occurrence.
  Astra Medium wykryła pięć przypadków granicznych checkpointu/3+3; wszystkie
  poprawiono, objęto testami regresyjnymi i końcowy review został zatwierdzony.
