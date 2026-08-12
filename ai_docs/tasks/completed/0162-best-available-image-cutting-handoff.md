---
title: TASK-0162 best available image cutting handoff
status: done
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0162 — Słabsze zdjęcie jako kontrolowane wejście do cięcia

## Status

`done`

## Goal

Zagwarantować, że pojedyncza nierozpoznana grupa pomiędzy dwoma pewnymi
zakresami nie zostanie pominięta wyłącznie z powodu słabej ekspozycji,
przyciętej ramy albo niepełnej geometrii. Najlepsze dekodowalne zdjęcie ma
otrzymać zakres z jednoznacznej luki i trafić do późniejszej próby cięcia.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Scope

- utrwalić kontrakt best-available dla ostrzeżeń jakości/geometrii,
- dodać regresję z kodami zaobserwowanymi dla realnego zakresu `73–81`,
- rozróżnić w UI wstępny licznik podczas skanowania od wyniku końcowego,
- nie zatrzymywać ani nie zmieniać fingerprintu trwającego runu v5.

## Out of scope

- automatyczne zgadywanie zakresu bez dwóch pewnych sąsiadów,
- przyjmowanie uszkodzonego JPEG-a, błędu skanu lub jawnego zasłonięcia,
- uruchamianie pełnego pipeline'u przed ukończeniem Selekcji zdjęć,
- restart trwającego joba.

## Acceptance criteria

- [x] ostrzeżenia `QUALITY_FRAME_CROPPED`, `GEOMETRY_INCOMPLETE`,
      `FRAME_NOT_FULLY_VISIBLE` i `RANGE_UNKNOWN` nie blokują odzyskania jednej
      jednoznacznej luki,
- [x] wynik wybiera najlepszy kandydat, nadaje `73–81` i oznacza oba powody
      best-available oraz bounded-gap,
- [x] podczas `created/processing` UI pokazuje `Wstępnie nierozpoznane`,
- [x] twarde błędy pozostają blokujące,
- [x] testy i kontrole jakości zmienionych części przechodzą.

## Outcome

Produkcja już wykonywała końcowe bounded-gap recovery, dlatego nie zmieniono
algorytmu ani fingerprintu trwającego `fast-image-selector-v5`. Dodano natomiast
jawną gwarancję produktu i regresję odwzorowującą rzeczywisty zestaw pomiędzy
`64–72` oraz `82–90`.

Test potwierdza, że kandydat zachowujący `QUALITY_FRAME_CROPPED`,
`GEOMETRY_INCOMPLETE`, `FRAME_NOT_FULLY_VISIBLE` i `RANGE_UNKNOWN` zostaje
wybrany automatycznie, otrzymuje zakres `73–81`, `QUALITY_BEST_AVAILABLE` oraz
`RANGE_INFERRED_FROM_BOUNDED_GAP`. Tym samym publisher przekaże JPEG do Importu
layoutów, który podejmie próbę cięcia.

Admin pokazuje `Wstępnie nierozpoznane` dla aktywnego runu i dopiero po jego
zakończeniu `Nierozpoznane zestawy`. Weryfikacja: 37 testów selektora i 165
testów Admina, Ruff, TypeScript oraz ESLint przeszły. Bieżący job nie został
przerwany podczas implementacji. Następnie, na osobne jawne polecenie
właściciela, został bezpiecznie anulowany na checkpointcie `2016/32079`, aby
kolejny run rozpocząć świadomie; staging nie został usunięty.
