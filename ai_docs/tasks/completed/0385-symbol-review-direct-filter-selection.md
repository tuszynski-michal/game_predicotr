---
title: Direct symbol review filter selection
status: done
version: 0.10.87
---

# TASK-0385 — Bezpośredni wybór filtrów Weryfikacji symboli

## Goal

Nie pobierać domyślnej strony cropów po wejściu, ale usunąć zbędny krok
`Zatwierdź wybór` / `Zmień wybór`.

## Scope

- domyślnie niewybrana gra i symbol,
- automatyczne pobranie po ustawieniu obu wartości,
- reset symbolu po zmianie gry,
- zachowanie ostrzeżenia przed wyczyszczeniem istniejącego zaznaczenia,
- regresyjne testy stanu i kontraktu workspace'u,
- aktualizacja wymagań, Current State i Decision Log.

## Out of scope

- zmiany API, OpenAPI i backendu,
- zmiana stronicowania, atlasów, liczników lub operacji masowych,
- zmiana silnika cropów.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Definition of Done

- wejście nie wybiera automatycznie gry ani symbolu i nie pobiera strony,
- wybór samej gry pobiera katalog symboli i status projekcji, ale nie stronę,
- wybór zakresu symbolu automatycznie pobiera pierwszą stronę,
- nie istnieją przyciski `Zatwierdź wybór` i `Zmień wybór`,
- zmiana filtrów czyści cache strony, viewport i zaznaczenie zgodnie z
  istniejącą ochroną,
- skoncentrowane testy, lint, typecheck i build Admina przechodzą.

## Outcome

- Usunięto stan potwierdzania i blokowania filtrów oraz oba dodatkowe przyciski.
- Gra i symbol startują jako `null`; kompletna para automatycznie uruchamia
  bounded odczyt strony, a zmiana gry ponownie zeruje symbol.
- Ostrzeżenie przed utratą jawnego zaznaczenia działa dla zmiany gry i symbolu.
- Testy Admina: 360/360, lint, typecheck i produkcyjny build zakończone
  powodzeniem.
