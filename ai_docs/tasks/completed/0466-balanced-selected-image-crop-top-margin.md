---
title: TASK-0466 Balanced selected image crop top margin
status: done
---

# TASK-0466 — Zbalansowany górny margines lokalnego auto-cropa

## Goal

Zwiększyć margines nad pierwszym rzędem plansz po tym, jak próby v8 wykazały,
że 3% bywa zbyt ciasne, bez ponownego zachowywania panelu wypłat.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wersjonowana polityka z górnym paddingiem 4,5%;
- brak górnej ekspansji pozostaje bez zmian;
- historyczne polityki v4–v8 pozostają czytelne;
- rzeczywista próbka przed ponownym uruchomieniem kolejki;
- spójne usunięcie wyłącznie nieprzejrzanych wyników v8 tego runnera.

## Definition of Done

- próbka zachowuje większy margines nad pierwszym rzędem niż v8;
- panel wypłat pozostaje poza wynikiem;
- testy core i kontrakty Admina przechodzą;
- ponowne przetwarzanie nie miesza polityk w jednym katalogu.

## Outcome

- Dodano politykę v9 z górnym paddingiem 4,5% i zachowano odczyt v4–v8.
- Rzeczywista próbka 1080×1920 otrzymała `topY=618`, `bottomY=1224`; panel
  wypłat pozostaje poza wynikiem, a pierwszy rząd ma około 30 px więcej zapasu
  niż w v8.
- Core przechodzi 53/53, kontrakty Admina 15/15, typecheck i format są zielone.
- Zatrzymano runner v8 i usunięto wyłącznie cztery jego katalogi bez review.
  Ponowne uruchomienie zaczyna spójny przebieg v9 od najmniejszego zakresu.
