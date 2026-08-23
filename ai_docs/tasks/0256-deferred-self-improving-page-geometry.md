---
title: TASK-0256 deferred self-improving page geometry
status: in_progress
release: "0.7"
last_updated: 2026-08-22
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
- [x] Testy API, workera, Admina i Reviewera oraz lint, typecheck i OpenAPI
      przechodzą dla zrealizowanych pionów.

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
- Rzeczywisty preflight stagingu `70363–93861` ujawnił regresję końcowego
  raportowania: pierwszy przebieg publikował `152` tymczasowe pozycje review,
  a auto-kotwice próbowały później zmniejszyć ten monotoniczny licznik. Worker
  kończył po `2611/2611` kodem `JOB_PROGRESS_REGRESSION`, zanim zapisał finalny
  manifest. Preflight v2 publikuje teraz tymczasowe review wyłącznie w
  checkpoint payload, a wspólny licznik review ustala dopiero przy finalizacji.
- Testowy kontekst preflightu egzekwuje monotoniczność `current`, `success`,
  `failure` i `review`, dzięki czemu przypadek rozwiązania strony przez
  auto-kotwicę nie może ponownie przejść z cofającym się licznikiem.
- Walidacja poprawki: `18/18` testów preflightu i domeny jobów, Ruff oraz
  formatowanie przeszły. Celowany mypy nie wykazał nowego błędu, ale nadal
  raportuje dwa istniejące błędy w
  `symbol_model_iteration_repository.py`.
- TASK-0264 dodał niezależny trwały kontrakt wyjątków geometrii komórek. Nie
  zmienia preflightu strony ani pełnego pipeline'u: pozwala przyszłemu adapterowi
  zapisać fail-closed planszę bez syntetycznych cropów i zachować human-wins.
- TASK-0265 podłączył ten kontrakt do pełnego pipeline'u wyłącznie jako jawny
  opt-in `board-cell-processing-v20-verified-v19-v1`. Domyślny v18 pozostaje
  bez zmian; domyślna aktywacja jest nadal poza zakresem.
- TASK-0266 domknął backend ręcznej korekty pojedynczego deferred. Checksum-bound
  preview niczego nie zapisuje, a właściwa komenda materializuje dokładnie 15
  cropów, predykcje pinned modelu i zwykły item istniejącej kolejki. UI tej
  korekty dostarczył następnie TASK-0267.
- TASK-0267 dodał osobny bounded tryb końcowej korekty w Reviewerze oraz licznik
  i dostęp deferred-only w launcherze Admina. Aktualny preview jest wymagany do
  zapisu, exact retry zachowuje idempotency key, a konflikty przeładowują stan
  bez nadpisania human-wins. Po zapisie plansza trafia do istniejącej zwykłej
  kolejki review.
- TASK-0268 udostępnił właścicielowi staging-local wybór v20 w Adminie. V18
  pozostaje domyślny, a v20 wymaga potwierdzenia komunikatu o wyniku `93,78%`,
  braku fallbacku oraz deferred. Start przesyła wybrany tryb i kontroluje
  zgodność zwróconego snapshotu joba; próg `98%` nie został obniżony.
