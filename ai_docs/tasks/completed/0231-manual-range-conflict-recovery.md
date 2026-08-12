---
title: TASK-0231 manual range conflict recovery
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0231 — Obsługa konfliktu zakresu w ręcznej selekcji

## Goal

Pozwolić właścicielowi przejść dalej po błędzie
`IMAGE_SELECTION_RANGE_CONFLICT` bez nadpisania istniejącego pliku i bez
szukania ukrytej akcji w dolnej części modala.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0229-manual-duplicate-range-discard.md`

## Implementation

- rozpoznać stabilny kod konfliktu zwrócony przez API,
- pokazać przy komunikacie widoczną akcję `Odrzuć duplikat i dalej`,
- przełączyć główny przycisk oraz ponowne `Enter`/`→` na tę samą jawną akcję,
- utrzymać jeden klucz idempotencji dla ponowień odrzucenia,
- wyczyścić stan konfliktu po zmianie zakresu albo przejściu do innej grupy,
- usunąć grupę z kolejki dopiero po potwierdzeniu backendu.

## Outcome

Modal nie zatrzymuje już użytkownika na surowym błędzie konfliktu. Pierwsza
próba zatwierdzenia nadal bezpiecznie wykrywa zajęty zakres i niczego nie
zmienia. Następna świadoma akcja odrzuca zweryfikowany duplikat przez istniejący
endpoint, ustawia `skipped_existing_range` i przechodzi dalej. Typecheck oraz
186 testów Admina przeszły razem z lintem. Lokalna baza została bezpiecznie
podniesiona z `0039` do wymaganej migracji `0040`; test migracji i dwa testy API
duplikatów przeszły. Bieżący job v10.5 ani jego usługi nie zostały przerwane.
