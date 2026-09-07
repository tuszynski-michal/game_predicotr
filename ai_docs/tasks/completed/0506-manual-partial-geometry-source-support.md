---
title: Narożniki poza zdjęciem i bezpieczne brakujące komórki
status: done
last_updated: 2026-09-07
---

# TASK-0506 — Narożniki poza zdjęciem i bezpieczne brakujące komórki

## Status

`done`

## Goal

Narożniki poza zdjęciem i bezpieczne brakujące komórki, według zaakceptowanego planu „Niepełne plansze i wykluczanie niepewnej geometrii z uczenia”.

## Context

Operator zlecił całą serię 0505–0509 wraz z audytami; bez zatrzymywania po każdym tasku.

## Dependencies / entry conditions

TASK-0505; jego implementacja oraz wymagany audyt muszą być odebrane. Obce zmiany i pozostałości TASK-0504 pozostają poza commitem. Bez restartów usług i operacji na danych operatora.

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

- Wyłącznie nowy ręczny kontrakt pozwala wyjść quadom poza źródło, w granicach -W..2W oraz -H..2H. Normalne quady nadal wymagają podparcia.
- Zachować EXIF, wypukłość, nieosobliwość transformacji, kolejność i numerację slotów. Nie powiększać bitmapy ani clampować zapisanej geometrii.
- Automatyczna maska wynika z właściwych obszarów komórek tą samą transformacją co renderer. Maska ręczna może ją wyłącznie rozszerzyć. Padding nie zastępuje oceny właściwej komórki.
- Niedostępne komórki mają logiczny placeholder, bez obrazu/inferencji; wszystkie 15 mogą być niedostępne. Dostępne renderowane normalnie.
- Viewer ma szare otoczenie dla przeciągania narożników. Częściowa geometria rozlicza korektę, ale nie pełny layout.

## Out of scope

Detektor produkcyjny v0.10, OCR, lokalny auto-crop, aktywne joby, dane operatora, cleanup. Warunkowa prośba o eksperymentalny v0.10.4 wymaga osobnej analizy po odbiorze tej serii.

## Acceptance criteria

- [x] Nowy ręczny kontrakt dopuszcza -W..2W/-H..2H; normalna geometria nadal wymaga podparcia.
- [x] EXIF, wypukłość/kolejność i indeksy pozostają; brak powiększenia bitmapy i clampowania zapisanej geometrii.
- [x] Automaska właściwych pól oraz ręczne rozszerzenie, niezależnie od paddingu.
- [x] Renderer pomija niedostępne logiczne indeksy, także 15/15; placeholder read modelu jest integracją 0508.
- [x] Opt-in szare otoczenie edytorów; podłączenie kontrolek 0507 i rozliczenie workflow 0508.
- [x] Testy i niezależny audyt fundamentu oraz zgodność historyczna.

## Technical notes

Granica odbioru to obliczanie podparcia, render dostępnych pól, page override
oraz opt-in otoczenie edytorów. Publiczne kontrolki i ich połączenie z tym
fundamentem należą do 0507; kanoniczny zapis/reconciliacja/placeholdery read
modelu i konsumenci treningu/importu do 0508. Nie aktywujemy ich przed odbiorem.

Kanoniczny właściciel kwalifikacji to snapshot rewizji źródła; nullable projekcje nie są alternatywną prawdą. Nowe oznaczenia nie mogą zniknąć przez historyczny zapis. Żaden szablon nie tworzy fikcyjnego cropa ani zatwierdzenia.

## Expected files

- Istniejący: `services/api/src/game_predictor_api/domain/image_geometry_v2.py`.
- Istniejący: `services/api/src/game_predictor_api/application/virtual_grid_geometry.py`.
- Istniejący: `services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py`.

## Test cases

Każde kryterium zakresu otrzymuje test zachowania, w tym przypadki negatywne i zgodność historyczna. Nie osłabiać testów dla zielonego wyniku.

## Verification

Komendy ustalić ze skryptów repo po identyfikacji zmienionych modułów; każdy skończony krok z timeoutem do 120 s. Znane buildy wymagają jawnego dłuższego limitu. Najpierw testy pionu, potem typy/lint i szersza kontrola. Poniższe wyniki nie są jeszcze zaliczone.

## Risks / open questions

Samo zapisanie wykluczenia nie odtrenowuje aktywnego profilu. Bezpieczne read-only fixture’y nie dowodzą odbioru UI na urządzeniu operatora.

## Outcome

### Changed

Kwalifikowana ręczna geometria 3×5: podpisane współrzędne, ograniczony obszar
edycji, automaska właściwych pól i pomijanie niedostępnych przed renderem.
Page override scala maskę przed checksumą, waliduje kolejność i nienakładanie.
Dotychczasowy fingerprint i granice pozostają bez zmian dla braku kwalifikacji.
Opt-in SVG/canvas dodaje szare otoczenie bez powiększenia bitmapy; domyślnie
wyłączony, do podłączenia przez 0507. API/OpenAPI/klient zsynchronizowane.

### Verification results

- 36 testów Python: partial source support, 15/15, replay renderu, EXIF historyczny,
  domena oraz HTTP page override — passed (1,82 s).
- 16 testów stanu Reviewera i 53 klienta — passed; oba webowe typecheck passed.
- Mypy 5 modułów oraz Ruff zmienionych plików — passed; OpenAPI check passed.
- ESLint zmienionych komponentów i stanu, uruchomiony z konfiguracji obu aplikacji — passed.
- Niezależny audyt `gpt-6-astra high` przeszedł po poprawce błędu roundoff:
  współrzędna 199.00000000000003 nie tworzy fałszywej niedostępności.
  Tolerancja 1e-6 dotyczy nowego kontraktu, nie historycznej ścieżki.

### Not completed

Brak wizualnego odbioru przeglądarki oraz migracji/restartów/importów na danych
operatora. Kontrolki i trwałe szkice pozostają w 0507; pełny workflow i read
model niedostępnych pozycji w 0508, integracyjny odbiór w 0509.

### Documentation updates

CURRENT_STATE oraz poniższa granica odbioru.

### Recommended next task

TASK-0507 — kontynuacja już zlecona.
