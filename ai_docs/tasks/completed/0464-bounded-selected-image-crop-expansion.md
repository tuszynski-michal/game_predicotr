---
title: TASK-0464 Bounded selected image crop expansion
status: done
---

# TASK-0464 — Ograniczenie ekspansji granic i uruchomienie kolejki cut

## Goal

Usunąć regresję ujawnioną na rzeczywistym `seq_70363-70371.jpg`, w której
poprawnie znaleziony pas plansz był rozszerzany przez panel wypłat aż niemal do
górnej krawędzi obrazu, a następnie uruchomić bezpieczną kolejkę brakujących
katalogów `cut` w rosnącej kolejności.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- wersjonowana polityka z jednokrokową, ograniczoną ekspansją granic;
- zachowanie replay polityk v4–v6;
- regresja dla długiego, połączonego sygnału nad planszami;
- rzeczywista próba na pierwszym pliku katalogu `70363 - 93861`;
- lokalny, wznawialny runner zgodnego formatu sesji, użyty tylko dlatego, że
  automatyzacja nie może obsłużyć natywnego `showDirectoryPicker`;
- capacity guard zachowujący 30 GiB rezerwy i 20% marginesu.

## Definition of Done

- ekspansja nie może przejść przez wiele sąsiednich pasów zawartości;
- rzeczywista próba nie może zwrócić niemal pełnej wysokości;
- kolejka pomija istniejące katalogi `cut` i idzie według pierwszego numeru;
- wynik pozostaje zgodny z kafelkowym review aplikacji;
- brak miejsca zatrzymuje kolejkę przed utworzeniem następnego katalogu.

## Outcome

- Dodano politykę v7 z jednokrokową ekspansją granic i zachowano walidację
  historycznych polityk v4–v6.
- Regresja syntetyczna potwierdza, że pas plansz nie rozszerza się rekurencyjnie
  przez panel wypłat. Pełny zestaw core przechodzi 53/53.
- Na rzeczywistym `seq_70363-70371.jpg` wynik zmienił się z `safe_wide`/niemal
  pełnego obrazu na `topY=504`, `bottomY=1224` przy rozmiarze 1080×1920.
- Uruchomiono w tle wznawialną kolejkę 18 brakujących katalogów, zaczynając od
  `70363 - 93861`. Pierwszy checkpoint miał 60/2611 plików i zero błędów.
- Runner zachowuje 30 GiB twardej rezerwy i 20% marginesu; przy niedostatku
  miejsca zatrzyma się przed utworzeniem kolejnego katalogu.
