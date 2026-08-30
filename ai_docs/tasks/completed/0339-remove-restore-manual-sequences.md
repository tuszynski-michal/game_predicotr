---
title: TASK-0339 Remove and restore manual sequences
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0339 — Usuwanie i jednopoziomowe przywracanie

## Goal

Pozwolić operatorowi przejrzeć istniejące `seq_*` pojedynczo, usunąć błędny
wybór i odtworzyć wyłącznie ostatni plik z pamięci bieżącej karty.

## Scope

- numeryczna lista ze stałym skokiem 1;
- F/przycisk usuwa po zapisaniu intentu i sprawdzeniu SHA-256;
- A/Ctrl+A przywraca ostatni Blob pod pierwotną nazwą;
- drugie usunięcie zastępuje undo buffer, a reload go usuwa;
- repair/output manifest i trace są aktualizowane po każdej mutacji.

## Out of scope

- kosz systemowy i wielopoziomowa historia binariów;
- montaż sekcji w głównym workspace i integracja kohorty treningowej.

## Outcome

- Tryb usuwa numerycznie uporządkowany bieżący plik ze stałym skokiem 1 po
  zapisaniu intentu i sprawdzeniu SHA-256.
- Jedyny Blob undo pozostaje w refie bieżącej karty; A/Ctrl+A przywraca go pod
  pierwotną nazwą, a kolejne usunięcie zastępuje buffer.
- Repair/output manifest, trwałe luki i trace są aktualizowane po delete oraz
  restore; obcy cel i drift checksummy pozostają blokowane.
- Focused testy, lint i typecheck Admina przeszły poprawnie.
