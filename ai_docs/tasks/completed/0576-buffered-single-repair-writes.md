---
title: TASK-0576 — Bufor dziesięciu zapisów pojedynczej naprawy selekcji
status: done
last_updated: 2026-09-17
---

# TASK-0576 — Bufor dziesięciu zapisów pojedynczej naprawy selekcji

## Goal

Operator może kolejno zatwierdzić do dziesięciu uzupełnień luk albo pojedynczych
usunięć, podczas gdy zapisy do katalogu wykonują się kolejno w tle.

## Context

Aktualny widok blokuje następną decyzję już po pierwszym zapisie w tle. Opóźnia
to ręczną korektę mimo że operacje katalogowe mają już kolejkę serializującą.

## Recommended execution

`gpt-5.6-sol`, `high`. Zmiana dotyka trwałego manifestu i recovery lokalnego
workflowu, więc wymaga zachowania kolejności zapisu, bezpiecznego zatrzymania
po błędzie oraz testu regresji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Bufor maksymalnie 10 pojedynczych operacji fill albo delete.
- Natychmiastowe przejście do następnej pozycji i kolejne, serializowane zapisy.
- Na błędzie: anulowanie niezaczętych wpisów, powrót kursora do wadliwej
  pozycji, zachowanie wcześniej zakończonych zapisów i blokada dalszej mutacji
  do odtworzenia katalogu.

## Out of scope

- Usuwanie zbiorcze, zmiana formatu manifestu i równoległe zapisy katalogu.

## Acceptance criteria

- [x] Fill i delete przyjmują do 10 decyzji tego samego rodzaju.
- [x] Jeden writer wykonuje je w kolejności decyzji.
- [x] Jedenasty wpis nie jest przyjmowany przed zwolnieniem miejsca.
- [x] Błąd bieżącego zapisu anuluje wpisy oczekujące, odtwarza trwały snapshot
  i kieruje kursor na wadliwą pozycję.
- [x] Wcześniejsze udane wpisy pozostają trwałe, a recovery nie pomija danych.

## Outcome

### Changed

- Fill oraz pojedynczy delete dodają decyzje do ograniczonej kolejki o długości
  10. Jeden writer serializuje mutacje pliku, journalu i manifestów.
- UI zachowuje osobny snapshot trwały oraz optymistyczny. Po błędzie usuwa tylko
  niezaczęte intencje, przywraca trwały stan i wraca kursorem do pozycji błędu.

### Verification results

- 48 skoncentrowanych testów ręcznej selekcji i naprawy, kontrola typów, lint
  zmienionych modułów oraz build panelu zaliczone.

### Not completed

- Nie zmieniano istniejących plików `seq_*`, manifestów ani bieżących sesji
  użytkownika.
