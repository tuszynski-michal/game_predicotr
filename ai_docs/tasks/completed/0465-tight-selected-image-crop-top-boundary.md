---
title: TASK-0465 Tight selected image crop top boundary
status: done
---

# TASK-0465 — Ciaśniejsza górna granica lokalnego auto-cropa

## Goal

Usunąć pozostały panel nagłówka z automatycznie przygotowanych zdjęć bez
ryzyka przecięcia górnego rzędu plansz.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- nowa wersja polityki z górnym paddingiem 3%;
- brak rozszerzania górnej granicy w stronę panelu wypłat;
- zachowanie dolnego marginesu i jednokrokowej ochrony dolnej granicy;
- rzeczywista próbka przed ponownym przetwarzaniem istniejących wyników;
- historyczne polityki v4–v7 pozostają czytelne.

## Definition of Done

- próbka `seq_70363-70371.jpg` zaczyna się bezpośrednio nad panelem plansz;
- górny rząd plansz pozostaje w całości widoczny;
- testy core i kontrakty Admina przechodzą;
- żaden istniejący katalog nie jest nadpisany przed wizualną kontrolą próbki.

## Outcome

- Dodano wersjonowaną politykę v8 z górnym paddingiem 3%, bez ekspansji w
  stronę panelu wypłat, oraz zachowano odczyt polityk v4–v7.
- Minimalna wysokość wykrytego pasa wynosi 28%; bardzo płytki dowód nadal
  przechodzi do `safe_wide`.
- Na rzeczywistym `seq_70363-70371.jpg` uzyskano `topY=648`, `bottomY=1224`
  przy 1080×1920. Pierwszy rząd i bezpieczny margines pozostają widoczne.
- Core przechodzi 53/53. Istniejących katalogów v7 nie nadpisano przed oceną
  wizualną próbki.
