---
title: TASK-0776 — Kafelek „Maksymalny wkład” w „Przybliżonej wygranej”
status: done
last_updated: 2026-10-01
---

# TASK-0776 — Kafelek „Maksymalny wkład” w „Przybliżonej wygranej”

## Status

`done`

## Goal

Operator widzi, ile gotówki musi mieć od zera, aby przejść przez zakres do
najniższego punktu bilansu (nie zabrakło mu na spin przed wypłatą).

## Context

Zgłoszenie operatora z 2026-10-01: wykres schodzi np. do −2000 kredytów
(200 zł) — czy tyle trzeba „wsadzić do maszyny”? Odpowiedź: tak, ale dołek
jest głębszy niż wartości po wypłatach, bo każdy spin jest opłacany przed
swoją wypłatą. Wartość jest wyznaczana w przeglądarce z wierszy i
podsumowania wyniku zakresu — bez zmian API.

## Scope

- `packages/board-search-ui/src/board-search-approximate-win-state.ts`:
  `approximateWinMaximumStake(result)` → `{ credits, spinNumber } | null`
  (minimum z: −koszt spinu, bilans przed każdą wypłatą, bilans końcowy;
  pierwsze wystąpienie).
- Czwarty kafelek w podsumowaniu z podpisem i numerem spinu; skalowany
  stawką i jednostką jak pozostałe.
- `ADMIN_APP.md`.

## Acceptance criteria

- [x] Kafelek pokazuje najgłębszy dołek od zera (także gdy wypłata jest na
  pierwszym spinie i gdy nie ma żadnej wypłaty).
- [x] Wartość skaluje się ze stawką i jednostką.

## Outcome

### Verification results

- Pakiet UI: testy jednostkowe 78/78 (dołek na końcu zakresu, wypłata na
  pierwszym spinie, brak wypłat, dołek przed wypłatą ponad bilansem
  końcowym, pusty zakres), interakcje 37/37 (kafelek w kredytach, przy
  stawce 6 zł i w złotych).
- Ręcznie na `127.0.0.1:3010` (gra 777, zakres 2500): bilans końcowy
  −2807,50 zł, „Maksymalny wkład” 2822,50 zł przy spinie 2499 — dołek
  przed wypłatą głębszy niż stan końcowy.
- Audyt niezależnego agenta `claude-opus-5-5`: PASS (wyprowadzenie minimum
  ścieżki potwierdzone), dwa P3 w fixture'ach testu poprawione.
