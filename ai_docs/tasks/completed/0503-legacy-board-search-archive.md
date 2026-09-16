---
title: TASK-0503 — Niezależne archiwum wyszukiwania starej gry
status: done
last_updated: 2026-09-07
---

# TASK-0503 — Niezależne archiwum wyszukiwania starej gry

## Status

`done`

## Goal

Odłączyć wyszukiwanie plansz zachowywanego zakresu starej gry `777 v0.1` od
operacyjnych rekordów review, plansz, importów i jobów, bez usuwania danych w
tym tasku.

## Context

TASK-0502 potwierdził, że zakres `45163–499995` ma 369 554 kompletne dokumenty
wyszukiwania i zgodne obrazy całych plansz. Bieżący read path nadal rozwiązuje
wynik oraz obraz przez `image_board_search_fast_documents`,
`image_review_items` i `recognized_boards`. Jest to ostatnia znana blokada
bezpiecznego odchudzenia danych operacyjnych starej gry.

## Dependencies / entry conditions

- Ukończony TASK-0502 i jego kanoniczny preview.
- Stara gra: `80f3c7ec-6110-4e20-a263-2675ee5b15d6`, kod `777`, nazwa
  `777 v0.1`.
- Chroniona nowa gra: `03d64bfe-4d29-47dd-9153-76bd99b3b5d9`.
- Brak aktywnych jobów starej gry podczas odczytu TASK-0502.

## Recommended execution

`gpt-6-astra` z poziomem `high`: task zmienia schemat, routing odczytu,
checksum-bound assety i przygotowuje granicę późniejszego destrukcyjnego
cleanupu. Przed użyciem wyniku do usuwania wymagany jest niezależny review w
`gpt-6-astra high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/quality/LEGACY_GAME_CLEANUP_INVENTORY.md`

## Scope

- Dodać niezależny, zamrożony read model archiwum bez FK do review, planszy,
  importu albo joba.
- Zachować w dokumencie symboliczny dowód wyszukiwania, status, ścieżkę obrazu
  całej planszy i checksumę, bez danych binarnych.
- Dodać wznawialny, przypięty do starej gry builder z trybem preview oraz
  jawnym wykonaniem.
- Przełączać wyszukiwanie na archiwum wyłącznie po pełnym stanie `ready`;
  budowane lub uszkodzone archiwum działa fail-closed.
- Udostępnić osobny checksum-bound asset archiwalny i rozszerzyć spójnie
  OpenAPI, klienta oraz Admina.
- Zachować dotychczasową projekcję i assety dla wszystkich gier bez gotowego
  archiwum.

## Out of scope

- Usuwanie rekordów, plików, stagingów, modeli lub raportów.
- Zmiana katalogu `C:\Users\user\Documents\777`.
- Wyłączenie funkcji starej gry poza wyszukiwaniem.
- VACUUM, restart usług albo automatyczne uruchomienie cleanupu.
- Przenoszenie lub ponowne kodowanie obrazów plansz.

## Acceptance criteria

- [x] Gotowe archiwum wystarcza do rankingu i odczytu obrazu bez joinu do
      operacyjnych tabel starej gry.
- [x] Dokument archiwum nie ma FK do review, recognized board, importu ani joba.
- [x] Obraz jest rozwiązywany wyłącznie przez bezpieczną ścieżkę i oczekiwaną
      checksumę; drift kończy się jawnym błędem.
- [x] Stan inny niż `ready` nie przełącza runtime na częściowe archiwum.
- [x] Builder jest idempotentny, wznawialny i weryfikuje przypięte UUID, zakres
      oraz fingerprint preview przed zapisem.
- [x] Standardowe wyszukiwanie pozostałych gier zachowuje dotychczasowy read
      path i zachowanie.
- [x] Migracja downgrade usuwa wyłącznie nowe struktury archiwum.
- [x] Nie wykonano destrukcyjnego cleanupu danych użytkownika.

## Expected files

- `services/api/alembic/versions/0098_legacy_board_search_archive.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/storage/board_search_projection_repository.py`
- `services/api/src/game_predictor_api/domain/board_search.py`
- `services/api/src/game_predictor_api/application/board_search.py`
- `services/api/src/game_predictor_api/application/board_search_assets.py`
- `services/api/src/game_predictor_api/api/board_search.py`
- `services/api/src/game_predictor_api/schemas/board_search.py`
- `scripts/build_legacy_board_search_archive.py`
- testy API, repozytorium, buildera, klienta i Admina
- dokumentacja wymagań, architektury, decyzji i stanu

## Test cases

- Brak archiwum używa operacyjnego fast documentu bez zmiany wyniku.
- `building` i `failed` nie zwracają częściowych wyników archiwalnych.
- `ready` wyszukuje wyłącznie archiwum i nie wymaga operacyjnych UUID.
- `approved_only`, alternatywy, unknown i deterministyczne remisy są zgodne z
  dotychczasowym rankingiem.
- Asset odrzuca niezgodną checksumę, brak pliku, symlink i traversal.
- Builder odrzuca inne gry, zakresy i fingerprinty, a retry nie dubluje
  dokumentów.
- UI buduje właściwy adres dla assetu operacyjnego i archiwalnego.

## Verification

Najpierw testy skupione API, buildera, klienta i Admina, następnie Ruff, mypy,
lint, typecheck, OpenAPI check i build Admina. Każda komenda otrzyma timeout do
120 sekund; migracja i pełny backfill danych rzeczywistych nie są uruchamiane
automatycznie przez testy.

## Risks / open questions

- Gotowe archiwum nadal celowo chroni istniejące pliki całych plansz; fizyczne
  usuwanie pozostałych plików musi uwzględnić te nowe referencje.
- Pełny backfill 369 554 dokumentów wymaga odbioru oraz osobnego potwierdzenia
  przed późniejszym cleanupem, choć sam builder nie usuwa danych.

## Outcome

### Changed

- Migracja 0098 dodała dwa niezależne modele archiwum. Dokument wskazuje obraz
  bezpośrednio i nie ma operacyjnych FK.
- Runtime wybiera gotowe archiwum dla całej gry; `building` i `failed` są
  fail-closed, a brak stanu zachowuje fast documents.
- API, wygenerowany klient i Admin obsługują jawne tryby
  `operational_review` oraz `legacy_archive` i osobny checksum-bound asset.
- Addytywny builder wymaga dokładnego fingerprintu pełnego preview, porównuje
  deterministycznie źródło z wynikiem i nie kopiuje obrazów ani nie dotyka
  katalogu operatora.

### Data acceptance

- Zastosowano migrację 0098.
- Zamrożono 369 554 dokumenty zakresu `45163–499995`.
- Fingerprint źródła i archiwum:
  `7053d7ac8db72583fd930d66289a8951b2bdfba96f62be5e2ef5f8431e7f15ff`.
- Drugie identyczne wykonanie zakończyło się tym samym licznikiem i
  fingerprintem, potwierdzając idempotencję.
- Rzeczywisty wynik starej gry zwrócił `legacy_archive` bez trzech UUID
  operacyjnych, asset 45170 zwrócił zgodny PNG, a nowa gra nadal zwróciła
  `operational_review`.

### Verification results

- Skupione testy API, repozytorium, buildera i OpenAPI: 36 passed.
- Testy Admina: 426 passed; testy klienta: 52 passed.
- Ruff check i format check zmienionych modułów: passed.
- Mypy zmienionego rdzenia i buildera: passed. Szerszy przebieg nadal wykrywa
  wcześniejsze błędy brakujących stubów oraz niezwiązane błędy typów.
- OpenAPI check i generated client drift: passed.
- Lint, typecheck i produkcyjny build Admina: passed.
- Globalny `format:check` nadal zgłasza 35 wcześniejszych, niezwiązanych plików;
  żaden plik TASK-0503 poza chronionym `apps/admin/next-env.d.ts` nie jest na
  tej liście.

### Not completed

- Nie usunięto żadnych danych ani plików. Nie uruchomiono VACUUM ani cleanupu.
- Przed destrukcyjnym etapem potrzebny jest nowy preview, ochrona ścieżek
  archiwum, jawna zgoda użytkownika i niezależny review w `gpt-6-astra high`.

### Recommended next task

- TASK-0504 — bezpieczne usunięcie zdublowanych zakresów 1–45162 i ciężkiego
  grafu operacyjnego starej gry z ochroną gotowego archiwum.
