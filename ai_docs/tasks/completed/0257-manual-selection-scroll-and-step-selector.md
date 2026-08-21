---
title: TASK-0257 manual selection scroll and step selector
status: done
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0257 — Stabilny scroll i czytelny wybór skoku

## Goal

Ręczna selekcja zachowuje pionową pozycję powiększonego zdjęcia przy przejściu
na sąsiedni JPEG, a lista skoku strzałek jest czytelna w ciemnym interfejsie i
udostępnia również wartości 3, 4 oraz 6.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- zapamiętać bieżący `scrollTop` viewportu obrazu w pamięci aktywnej sesji,
- przywrócić pozycję dopiero po załadowaniu i ułożeniu następnego JPEG-a,
- nie zapisywać zdarzeń scrolla do IndexedDB ani śladu uczenia,
- dodać skoki `3`, `4` i `6`, zachowując wszystkie istniejące wartości,
- nadać selectowi i jego opcjom jawne ciemne tło oraz czytelny tekst,
- uzupełnić regresje UI i dokumentację.

## Out of scope

- trwałe przywracanie scrolla po restarcie przeglądarki,
- osobna pozycja scrolla dla każdego zdjęcia,
- zmiana zoomu, bufora JPEG-ów, skrótów albo zapisu plików,
- zmiana IndexedDB, API lub workera.

## Acceptance criteria

- [x] Przejście strzałką lub po zatwierdzeniu nie wraca samoczynnie na górę.
- [x] Przywrócenie następuje po gotowości nowego obrazu i respektuje limit
      scrolla przeglądarki dla krótszego JPEG-a.
- [x] Scroll nie powoduje zapisu do IndexedDB ani kosztownego renderowania.
- [x] Select zawiera `1, 2, 3, 4, 5, 6, 7, 10, 15, 20`.
- [x] Rozwinięte opcje mają czytelne tło i tekst w ciemnym motywie.
- [x] Testy Admina, typecheck, lint, format i build przechodzą.

## Outcome

- `scrollTop` jest przechowywany w `useRef`, przechwytywany wyłącznie przy
  faktycznej zmianie indeksu i przywracany w następnym `requestAnimationFrame`
  po gotowości wymiarów nowego JPEG-a.
- Handler scrolla nie wykonuje `setState`, zapisu IndexedDB ani aktualizacji
  trace; koszt ogranicza się do przypisania jednej liczby.
- Lista skoku zawiera wartości `1, 2, 3, 4, 5, 6, 7, 10, 15, 20`. Select i
  `option` mają jawne ciemne tło, jasny tekst oraz `color-scheme: dark`.
- Przeszły: Admin `224/224`, typecheck, celowany ESLint bez błędów (jedno
  istniejące ostrzeżenie o celowym `<img>` dla lokalnego Blob URL), Prettier,
  `git diff --check` i produkcyjny build Admina.
- Lokalny panel został otwarty w kontrolowanej przeglądarce i poprawnie
  wyrenderował workspace. Pełnego scenariusza z folderami nie uruchamiano, aby
  nie przejmować ani nie zmieniać bieżącej sesji operatora.
