---
title: TASK-0256 deferred self-improving page geometry
status: in_progress
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0256 — Automatyczna geometria z korektą odroczoną na koniec

## Goal

Import plansz ma uruchamiać cięcie dla źródeł z bezpiecznie zweryfikowaną
geometrią bez wymagania wcześniejszej ręcznej korekty wszystkich wyjątków.
Preflight odzyskuje swój stan po ponownym wejściu i wykonuje ograniczone,
fail-closed rozszerzenie wzorców na podstawie najmocniejszych własnych wyników.

## Context

- Pierwszy staging przeszedł z `575` nierozwiązanych stron do `0` po kolejnych
  ulepszeniach profilu, bez ręcznych override'ów wszystkich stron.
- Stagingi `19810–45162` i `70363–93861` mają odpowiednio `54` i `152` strony
  nierozwiązane, mimo że pozostałe źródła mają kompletną zweryfikowaną siatkę.
- Admin po ponownym wejściu nie odzyskuje istniejącego preflightu i pokazuje
  mylące `Przygotuj geometrię stron`.
- Wygasający token legacy usunął sfinalizowany staging używany przez aktywny
  preflight. Trwały staging nie może dzielić czasu życia z tokenem 15-minutowym.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- chronić sfinalizowany staging przed czyszczeniem wygasłego tokenu,
- odzyskiwać istniejący geometry preflight po wybraniu raportu stagingu,
- wykonać deterministyczne, ograniczone auto-anchor passes wyłącznie z wyników
  spełniających zaostrzoną bramkę jakości,
- przypinać pełny manifest geometrii, ale kierować do pipeline'u wyłącznie
  źródła `registered`; `review_required` pozostają odroczone,
- pozwolić uruchomić import rozpoznanych stron przy niezerowym liczniku
  odroczonych źródeł,
- zachować osobną końcową kolejkę korekty ręcznej i fail-closed cropper.

## Out of scope

- automatyczna akceptacja symboli albo plansz,
- osłabianie progów czerwonej ramki, RANSAC lub kompletności 3×3,
- syntetyczne quady i klasyczny detektor jako fallback,
- zmiana numerów z poświadczonych nazw `seq_*`,
- uczenie online modelu neuronowego.

## Acceptance criteria

- [x] Nowy upload nie usuwa innego sfinalizowanego stagingu ani źródeł
      aktywnego preflightu.
- [x] Wybranie raportu odzyskuje istniejący job i jego licznik bez tworzenia
      duplikatu.
- [x] Auto-anchor używa wyłącznie pełnej geometrii 3×3 przechodzącej
      zaostrzoną bramkę i ma ograniczoną liczbę przebiegów oraz wzorców.
- [x] Wynik auto-anchor nadal zachowuje wszystkie dotychczasowe twarde progi
      finalnej rejestracji.
- [x] Import z częściowym manifestem przetwarza tylko `registered` i nie tworzy
      błędnych, pustych ani syntetycznych cropów dla `review_required`.
- [x] Odroczone strony pozostają widoczne do ponownego preflightu i końcowej
      korekty ręcznej.
- [x] Kanoniczne, zaakceptowane numery pozostają chronione.
- [ ] Testy API, workera i Admina oraz lint, typecheck i OpenAPI przechodzą.

## Outcome

- Wygasanie 15-minutowego tokenu legacy nie usuwa sfinalizowanego browser
  stagingu. Regresja odtwarza finalizację pierwszego uploadu, upływ czasu i
  rozpoczęcie drugiego uploadu.
- Preflight v2 wykonuje maksymalnie dwa przebiegi z maksymalnie 21
  zaostrzonymi auto-kotwicami na przebieg. Test z nierozpoznaną stroną
  potwierdza jej rozwiązanie przez drugi, automatyczny przebieg.
- Produkcyjny import filtruje źródła przed kopiowaniem: do managed originals i
  pipeline'u trafia tylko `registered`; `review_required` pozostaje w stagingu.
- Admin automatycznie tworzy lub odzyskuje job po pokazaniu raportu, nie blokuje
  startu przy odroczonych stronach i przenosi korektę ręczną do zwijanej sekcji
  końcowej.
- Przeszły celowane testy API/workera `46/46`, pełny Admin `222/222`, klient
  OpenAPI `39/39`, build i typecheck Admina, Ruff oraz kontrola OpenAPI.
- Pełny wrapper testów API przekroczył limit 120 sekund bez wyniku i został
  przerwany. Mypy zmienionych modułów dochodzi do dwóch istniejących błędów w
  `symbol_model_iteration_repository.py`; zmienione moduły nie zgłosiły nowego
  błędu przed tym transytywnym problemem.
