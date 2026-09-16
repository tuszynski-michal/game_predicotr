---
title: TASK-0439 Safe v0.10 pending reinference
status: done
last_updated: 2026-09-04
---

# TASK-0439 — Bezpieczne przeliczanie oczekujących w v0.10

## Problem

Dla gry `siedem` akcja przeliczenia symboli utworzyła pozornie poprawny job z
globalnym bootstrapem, mimo że jego angielskie klasy nie odpowiadają polskim
kodom aktywnego katalogu gry. Akcja przeliczenia siatki zakwalifikowała 45
plansz `virtual_source`, w tym 36 z ręcznie zatwierdzoną geometrią, po czym job
zakończył się przed pierwszą planszą błędem
`IMAGE_GRID_REINFERENCE_VIRTUAL_ASSET_UNAVAILABLE`.

## Scope

- blokować nowy import i reinferencję, gdy bootstrap nie jest dokładnie zgodny
  z aktywnym katalogiem symboli gry,
- zachować odczyt historycznych predykcji bootstrapu,
- kwalifikować do plikowego recropu v19 wyłącznie nierozstrzygnięte,
  niezatwierdzone geometrie `legacy_file`,
- powtórzyć ochronę statusu, rewizji, zatwierdzenia geometrii oraz asset mode w
  workerze bezpośrednio przed zapisem,
- raportować osobno wirtualne siatki v0.10 wymagające walidacji lub ręcznej
  korekty i nie tworzyć dla nich nieobsługiwanego legacy joba,
- doprecyzować w Adminie, że v19 jest modułem siatki 3×5, a nie całym silnikiem
  importu v0.10.

## Out of scope

- automatyczne mapowanie kodów symboli według kolejności albo nazwy,
- automatyczna aktywacja lub trening modelu,
- konwersja `virtual_source` do trwałych board/cell PNG,
- automatyczny metadata-only recrop wirtualnej geometrii; wymaga osobnego
  snapshotu, proweniencji oraz bramki jakości v0.10,
- ponawianie jobów lub modyfikowanie danych gry bez osobnej zgody użytkownika.

## Relevant docs

- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- bootstrap niezgodny z katalogiem zwraca stabilny konflikt przed utworzeniem
  joba,
- zatwierdzona geometria nie trafia do preview ani workera przeliczenia,
- `virtual_source` nie jest raportowany jako możliwy do plikowego recropu,
- endpoint startu nie tworzy pustego lub nieobsługiwanego joba,
- UI pokazuje liczbę wirtualnych siatek oraz właściwy następny krok,
- testy API, workera i Admina odtwarzają zgłoszony przypadek,
- dokumentacja i OpenAPI są zgodne z implementacją.

## Outcome

- Resolver snapshotu blokuje globalny bootstrap kodem
  `SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED`, gdy klasy nie są dokładnie zgodne z
  aktywnym katalogiem gry. Zgodne historyczne katalogi zachowują bootstrap.
- Preview rozdziela zatwierdzone geometrie, `virtual_source`, aktualne v19 i
  rzeczywiście kwalifikujące się `legacy_file`. Worker ponownie sprawdza
  `asset_mode` oraz brak zatwierdzonej rewizji przed zapisem.
- Admin pokazuje osobny licznik wirtualnych siatek v0.10 i nazywa uruchamiany
  proces plikowym modułem siatek 3×5 v19. OpenAPI oraz wygenerowany klient
  zawierają nowe pole `unsupportedVirtualBoardCount`.
- Testy: 31 skoncentrowanych testów API/workera, 393 testy Admina i 51 testów
  klienta API przeszły; Ruff, ESLint, TypeScript, Prettier, kontrola OpenAPI i
  produkcyjny build Admina przeszły.
- Pełny mypy API/workera nie zwrócił wyniku przez 60 sekund i został przerwany
  zgodnie z limitem repozytorium. Nie ponowiono istniejących jobów i nie
  zmieniono danych gry.
