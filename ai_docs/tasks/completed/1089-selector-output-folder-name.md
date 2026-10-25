---
title: Selector output folder labels
status: done
last_updated: 2026-10-23
---

# TASK-1089 — Nazwa folderu wynikowego selektora

## Status

`done`

## Goal

Nowa partia tworzy folder `gra aktualizacja pierwsza-ostatnia`, np. `777 a2 1-500`, i zachowuje nazwy JPEG.

## Context

Operator zmienił wcześniejsze ustalenie D-571: aktualizacja i gra mają nazywać także folder wynikowy. Kontynuacja gałęzi z gotowym TASK-1088, bez zgody na scalenie.

## Dependencies / entry conditions

Selektor 1.0.2 i zapisane metadane gry/aktualizacji. Brak blokujących pytań. Zakres nazwy pochodzi z formularza; pusta ostatnia plansza oznacza 500000. Nazwa zostaje ustalona przy utworzeniu partii, późniejsza edycja zakresu nie przenosi plików.

## Recommended execution

gpt-6.1-sol / high. Wąska zmiana tworzenia i podglądu ścieżki; bez delegacji i dodatkowego audytu. Eskalacja przy konieczności przenoszenia istniejących danych.

## Relevant docs

- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-572--nazwa-folderu-wynikowego-selektora`
- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Nazwa wyniku nowej partii zawiera grę, aktualizację i początkową konfigurację zakresu.
- Podgląd pokazuje prawdziwą ścieżkę po uzupełnieniu formularza.
- Walidacja nazwy folderu Windows; kolizja z niepustym wynikiem blokuje zapis.
- Paczka 1.0.3 oraz testy utworzenia, wznowienia i niezmienionych nazw JPEG.

## Out of scope

Przenoszenie istniejących projektów, zmiany nazw zdjęć, formatu manifestu i numeracji; merge/push.

## Acceptance criteria

- [x] `777`, `a2`, 1–500 tworzą sąsiedni folder `777 a2 1-500`.
- [x] Podgląd i native tworzą identyczną nazwę; końcowy numer domyślny 500000.
- [x] Niepoprawne znaki ścieżki są odrzucane przed zapisem; obce dane nie są nadpisywane.
- [x] Nowy folder działa przy ponownym wyborze źródła, projektu i wyniku, również po restarcie.
- [x] Stare projekty zachowują ścieżki, JPEG-i nadal mają nazwy `seq_<od>-<do>.jpg`.
- [x] Gotowa sprawdzona paczka Windows 1.0.3.

## Technical notes

Wspólny czysty builder nazwy, bez modyfikowania identyfikatorów gry. Znaki niedozwolone w folderach Windows dają czytelny błąd; brak cichego zastępowania znaków. Cała nazwa komponentu ma limit 255 jednostek UTF-16. Projekt postępu pozostaje obok źródła jako `<źródło> selekcja`, więc rozpoznanie istniejącego projektu nadal opiera się na jego zapisanej ścieżce outputRoot. Starsze jawne lokalizacje i przejęcie legacy zachowują obecne zachowanie.

## Expected files

- `apps/selector-desktop/src/contracts.ts`: builder nazwy, NewProjectDraft.
- `apps/selector-desktop/src/native/project-controller.ts`: beginSource/create.
- `apps/selector-desktop/src/renderer/App.tsx`: podgląd wyniku.
- Testy start-resume, nowy test nazwy folderu, skrypty smoke games/workflow/start.
- Wersja aplikacji, dokumentacja obszaru, mapa kodu i raport jakości.

## Test cases

Dokładny przykład operatora; domyślny koniec; znaki ścieżki, limity długości i granice numeracji; istniejący niepusty wynik; odczyt manifestu i JPEG; ponowne otwarcie z izolowanego nowego procesu; starszy projekt.

## Verification

`node scripts/run-bounded.mjs 120 ...` w katalogu selektora: testy zmienionego pionu, lint, typecheck, release, smoke:release:games i smoke:release:workflow. Kontrole głównego repo: docs:check i code-map:check. Build wydania ma wewnętrzny timeout 110 s.

## Risks / open questions

Nazwa odzwierciedla konfigurację początkową; późniejsza edycja numeracji nie zmienia istniejącego katalogu. Nie modyfikujemy danych operatora.

## Outcome

Commit: v1.7.469 / `54c33f1ae3fbbf1c44aa1632f96fa8065e7f6db1`.

### Changed

- `outputDirectoryName` waliduje wspólną nazwę wyniku, a nowy draft przekazuje rodzica docelowego katalogu. UI pokazuje dokładną ścieżkę, native wyznacza ją ponownie.
- Nowe partie tworzą folder gry, aktualizacji i początkowego zakresu. Stare ścieżki i JPEG-i pozostają bez zmian. Kolizja nie nadpisuje istniejących danych.
- Paczka 1.0.3, regresje native i skrypty smoke uwzględniające nowe ścieżki.

### Verification results

- 21/21 testów output-folder/start-resume, lint i typecheck PASS.
- Build wydania, weryfikacja ZIP/SHA-256/app.asar, smoke games i workflow PASS.
- Końcowy ZIP 1.0.3 z commita v1.7.469, applicationSourceDirty=false: ponowny smoke games PASS. Gotowa kopia w `artifacts/selector-releases/1.0.3/`; parametry i SHA-256 w raporcie jakości.
- docs:check i code-map:check PASS; dokumentacja ponownie sprawdzana po zamknięciu.
- Kryteria i DoD: dokładna nazwa, podgląd, ochrona danych, odczyt po restarcie oraz stare projekty pokryte testami. Zmiana dotyczy Windows i lokalnego IPC, bez OpenAPI, bazy i migracji.

### Not completed

Bez fizycznego restartu systemu, drugiego komputera, przenoszenia starych wyników i merge/push. Audyt krzyżowy nie był wymagany; brak delegacji.

### Documentation updates

D-572, wymagania i architektura obszaru, mapa kodu oraz `ai_docs/quality/SELECTOR_OUTPUT_FOLDER_1_0_3_20261023.md`.

### Recommended next task

Odbiór paczki 1.0.3 i po akceptacji scalenie gałęzi obejmującej TASK-1088 i TASK-1089.

### Kontrole integracji 2026-10-25

Operator zatwierdził merge, push i cleanup całej gałęzi. Kontrole po połączeniu z main oraz ponowny odbiór gotowego ZIP 1.0.3 zapisano w `../../quality/SELECTOR_OUTPUT_FOLDER_1_0_3_20261023.md`, sekcja „Kontrole integracji z main”. Historyczne wyniki i ograniczenia powyżej pozostają zapisem chwili zamknięcia taska.
