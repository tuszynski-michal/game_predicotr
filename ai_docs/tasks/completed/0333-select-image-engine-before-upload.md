---
title: TASK-0333 Select image engine before browser upload
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0333 — wybór silnika przed uploadem

## Goal

Usunąć błąd pierwszego przebiegu nowej gry, w którym operator może wybrać
`structured_shadow` dopiero po automatycznym uruchomieniu preflightu
`verified_v19` wymagającego nieistniejącego profilu.

## Scope

- ustawienie silnika jest widoczne przed wyborem folderu i gotowego stagingu;
- wybór folderu jest zablokowany do odczytania bieżącej polityki gry;
- zmiana polityki unieważnia stary raport, a dla aktywnego stagingu automatycznie
  przygotowuje nowy raport bez ponownego uploadu;
- picker nie jest dublowany wewnątrz pojedynczego stagingu;
- historyczny `verified_v19` nadal zachowuje bramkę profilu geometrii.

## Out of scope

- zmiana domyślnej polityki nowych gier;
- promocja Geometry v2 poza shadow;
- zmiana licznika plikowego uploadu na postęp bajtowy.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Definition of Done

- nową politykę można wybrać przed wskazaniem folderu;
- upload nie może wystartować przed załadowaniem ustawienia gry;
- przełączenie aktywnego stagingu na shadow automatycznie odtwarza raport;
- nowy raport nie uruchamia legacy preflightu i nie zwraca
  `IMAGE_PAGE_GEOMETRY_PROFILE_EMPTY`;
- testy Admina, lint, typecheck i build przechodzą.

## Outcome

- Picker silnika przeniesiono nad cały workflow importu.
- Wybór folderu jest blokowany do wczytania polityki gry.
- Zmiana polityki przy aktywnym stagingu automatycznie odświeża jego raport.
- Usunięto zduplikowany picker z pojedynczej karty stagingu.
- Testy Admina, lint, typecheck i produkcyjny build przechodzą.
