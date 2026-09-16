---
title: TASK-0484 — Zachowanie podglądów aktywnej strony symboli
status: done
last_updated: 2026-09-06
---

# TASK-0484 — Zachowanie podglądów aktywnej strony symboli

## Goal

Nie przeładowywać atlasów niezmienionych cropów po decyzji na aktywnej stronie
`Weryfikacji symboli`, a jednocześnie nie przechowywać w stanie UI atlasów
innych stron.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0483-stable-symbol-review-and-unreadable-protection.md`

## Scope

- związać ładowanie atlasów z niezmienną listą pobranej strony, a nie z lokalną
  listą pomniejszaną po każdej decyzji;
- zachować gotowe tile dla pozostałych kart aktywnej strony;
- wyczyścić referencje do tile i dostępności natychmiast po zmianie strony,
  filtra albo gry;
- dodać test regresyjny kontraktu UI.

## Out of scope

- zmiana serwerowego cache'u atlasów;
- przechowywanie Blobów albo pełnych obrazów w stanie React;
- zmiana metadanych strony, API lub PostgreSQL.

## Invariants

- checksum-bound atlas nadal jest źródłem obrazu;
- lokalne ukrycie jednej karty nie unieważnia obrazów innych kart;
- stan UI zawiera mapę tile wyłącznie dla aktualnie otwartej strony;
- zmiana strony usuwa referencje poprzedniej przed pokazaniem nowej.

## Acceptance criteria

- decyzja na jednej karcie nie uruchamia ponownie requestów atlasów strony;
- pozostałe widoczne miniatury nie znikają i nie pokazują loadera;
- przejście na inną stronę czyści poprzednią mapę tile;
- powrót może skorzystać z trwałego cache'u HTTP/serwera, ale nie z mapy React
  poprzedniej strony.

## Outcome

Atlas jest teraz ładowany względem niezmiennego `currentPage.items`, podczas gdy
`hiddenCellIds` wpływa wyłącznie na renderowaną listę. Ukrycie poprawnie
zmienionego cropa nie zmienia wejścia efektu atlasów i nie zastępuje mapy tile
częściowym wynikiem nowego requestu. Istniejące czyszczenie mapy przy nawigacji
i zmianie zakresu pozostaje bez zmian, więc pamięć UI nadal obejmuje tylko
aktywną stronę.

Weryfikacja: 14 testów workspace'u i atlasów, pełny lint oraz typecheck Admina,
Prettier dla zmienionych plików i produkcyjny build — zielone. Generowany
`apps/admin/next-env.d.ts` był zmieniony przez działający proces przed taskiem i
pozostaje poza zakresem oraz commitem.
