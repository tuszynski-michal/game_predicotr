---
title: Ochrona uczenia i ponowna korekta
status: done
last_updated: 2026-09-07
---

# TASK-0508 — Ochrona uczenia i ponowna korekta

## Status

`done`

## Goal

Ochrona uczenia i ponowna korekta, według zaakceptowanego planu „Niepełne plansze i wykluczanie niepewnej geometrii z uczenia”.

## Context

Operator zlecił całą serię 0505–0509 wraz z audytami; bez zatrzymywania po każdym tasku.

## Dependencies / entry conditions

TASK-0505–0507; jego implementacja oraz wymagany audyt muszą być odebrane. Obce zmiany i pozostałości TASK-0504 pozostają poza commitem. Bez restartów usług i operacji na danych operatora.

## Recommended execution

`gpt-6-astra high`, zgodnie z końcową tabelą zaakceptowanego planu. Wymagany niezależny audyt `gpt-6-astra high` przed zamknięciem: geometria, trwałość lub integracja właściwa dla zakresu. Eskalacja przy konflikcie kontraktu lub bezpieczeństwa danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — ręczna kompletność i kwalifikacja
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md` — D-371

## Scope

- Domknąć roundtrip kanonicznej source revision: command DTO, mapping odpowiedzi Grid Review i walidacja qualification wszystkich slotów w source repository. Dopiero potem usunąć foundation NOT_ENABLED; jawne ustalenie audytu TASK-0505.
- Wykluczać partial i ręcznie wykluczone geometrie z nowych kohort, ocen i kotwic. Jakikolwiek wykluczony slot uniemożliwia kotwicę całej strony; pewne plansze mogą kalibrować niezależnie.
- Raportować liczby i powody wykluczeń. Widoczne symbole mają własną kwalifikację; aktywny profil nie zostaje odtrenowany.
- Nowy kontrakt obsługuje pełna→partial i partial→partial, zdejmując starą blokadę tylko w obsługiwanej wersji.
- Atomowy zapis geometrii, maski, obserwacji i review; nowe piksele nie dziedziczą starych zatwierdzeń. Historia/frozen cohorts nienaruszone, retry bez duplikatów.
- Włączyć konsumentów manifestu guard v3 i kwalifikowanych override’ów dopiero po ochronie kotwic i reconciliacji. Historyczny replay nie zmienia zachowania.

## Out of scope

Detektor produkcyjny v0.10, OCR, lokalny auto-crop, aktywne joby, dane operatora, cleanup. Warunkowa prośba o eksperymentalny v0.10.4 wymaga osobnej analizy po odbiorze tej serii.

## Acceptance criteria

- [x] Wykluczać partial i ręcznie wykluczone geometrie z nowych kohort, ocen i kotwic. Jakikolwiek wykluczony slot uniemożliwia kotwicę całej strony; pewne plansze mogą kalibrować niezależnie.
- [x] Raportować liczby i powody wykluczeń. Widoczne symbole mają własną kwalifikację; aktywny profil nie zostaje odtrenowany.
- [x] Nowy kontrakt obsługuje pełna→partial i partial→partial, zdejmując starą blokadę tylko w obsługiwanej wersji.
- [x] Atomowy zapis geometrii, maski, obserwacji i review; nowe piksele nie dziedziczą starych zatwierdzeń. Historia/frozen cohorts nienaruszone, retry bez duplikatów.
- [x] Włączyć konsumentów manifestu guard v3 i kwalifikowanych override’ów dopiero po ochronie kotwic i reconciliacji. Historyczny replay nie zmienia zachowania.
- [x] Testy i niezależny audyt zakresu oraz zgodność historyczna.

## Technical notes

Pre-audyt wskazał, że stare review cells mają historyczne FK RESTRICT.
Przejście full→partial nie może ich usuwać; bieżące read paths muszą
respektować rewizję i maskę, w tym szeroki licznik D-370. Bramki aktywacji
pozostają do przejścia testów wszystkich konsumentów. Dodatkowe dotknięte
pliki: application/virtual_grid_geometry.py, jego repository, current-cell
selectors, domain/image_reviews.py i źródłowy revision repository workera.
Nie zmieniamy starych profili ani zapisanych jobów. Pionowe ucięcie oznacza
problem wejścia według D-372, a nie nowy automatycznie wykryty typ planszy.

Ustalenie integracji: nowa addytywna migracja 0101 dodaje source_available
z domyślnym true. To projekcja dostępności bieżących komórek, nie nowy stan
decyzji. Umożliwia zachowanie FK/eventów dawnych cropów oraz lokalny predykat
szerokiego licznika D-370 bez powrotu do kosztownego joinu całej geometrii.
Nie modyfikujemy wcześniejszych migracji. Brak uruchomienia migracji na
danych użytkownika; downgrade jest blokowany, jeśli istnieją nieaktywne pola.

Kanoniczny właściciel kwalifikacji to snapshot rewizji źródła; nullable projekcje nie są alternatywną prawdą. Nowe oznaczenia nie mogą zniknąć przez historyczny zapis. Żaden szablon nie tworzy fikcyjnego cropa ani zatwierdzenia.

## Expected files

- Istniejący: `services/api/src/game_predictor_api/storage/grid_calibration_repository.py`.
- Istniejący: `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`.
- Istniejący: `services/worker/src/game_predictor_worker/images/page_geometry_preflight.py`.
- Istniejący: `services/worker/src/game_predictor_worker/images/pipeline_store.py`.

## Test cases

Każde kryterium zakresu otrzymuje test zachowania, w tym przypadki negatywne i zgodność historyczna. Nie osłabiać testów dla zielonego wyniku.

## Verification

Komendy ustalić ze skryptów repo po identyfikacji zmienionych modułów; każdy skończony krok z timeoutem do 120 s. Znane buildy wymagają jawnego dłuższego limitu. Najpierw testy pionu, potem typy/lint i szersza kontrola. Poniższe wyniki nie są jeszcze zaliczone.

## Risks / open questions

Samo zapisanie wykluczenia nie odtrenowuje aktywnego profilu. Bezpieczne read-only fixture’y nie dowodzą odbioru UI na urządzeniu operatora.

## Outcome

Zintegrowano kwalifikowane rewizje, guard v3, produkcyjny render dostępnych
komórek, reinference, fast search, backfill, liczniki i nowe kohorty/kotwice.
Migracja 0101 zachowuje historyczne FK przez source_available zamiast DELETE.
Naprawiono utratę odpowiedzi, łączenie niezależnych zapisów pod jednym kluczem,
brak projekcji przy materializacji deferred i odwrotną kolejność blokad.
Nieprzygotowana wcześniej projekcja ma bounded initializer, bez globalnego scan.

Weryfikacja: 175 testów zmienionych modułów API, 96 workera; 54 testy klienta,
mypy 33 źródeł (`--follow-imports=silent`), Ruff i typecheck obu aplikacji passed.
Nowe HTTP testy obejmują EXIF 6, signed quady i zmienioną SHA/rozmiar źródła.
Niezależny audyt gpt-6-astra high: 137 testów, następnie 16 po poprawie locków;
brak dalszych konkretnych blockerów kodu. OpenAPI i wrapper zostały uaktualnione.

Ograniczenia: nie wykonano migracji 0100/0101, nie testowano rzeczywistej
wielotransakcyjnej współbieżności PostgreSQL ani UI na urządzeniu operatora.
Pełny odbiór i buildy: TASK-0509. Nowa kwalifikacja dotyczy managed virtual
geometry; legacy assets są read-compatible i jawnie odmawiają nowego zapisu.
Nie zmieniono danych, aktywnych profili/jobów/importów, OCR ani detektora.
Kontynuacja serii wynika z jawnego polecenia operatora wykonania wszystkich tasków.
