---
title: TASK-0527 — Semi-automatic selection capacity exemption
status: done
last_updated: 2026-09-08
---

# TASK-0527 — Wyłączenie estymacji artefaktów dla wyboru półautomatycznego

## Status

`done`

## Goal

Pozwolić rozpocząć browser staging wyboru półautomatycznego na podstawie
rzeczywistego rozmiaru źródeł i wolnego miejsca, bez konserwatywnej estymacji
cropów, których ten etap nie tworzy.

## Context

Wspólny `BrowserImageSelectionService.begin` wywołuje
`check_image_write(expected_total_bytes)` dla każdego celu stagingu. Guard
powiększa wejście o koszt przyszłych artefaktów i blokuje półautomat kodem
`STORAGE_CAPACITY_INSUFFICIENT`, mimo że ten workflow tylko stage'uje zdjęcia
do wyboru. Niezależna kontrola rzeczywiście wolnego miejsca już wymaga
zadeklarowanego rozmiaru plików oraz 512 MiB rezerwy.

## Dependencies / entry conditions

- Aktualny HEAD `v0.10.234`.
- Istniejące rozróżnienie `ImageSelectionPurpose`.
- Brudne zmiany TASK-0517 i repozytorium geometrii należą do równoległej
  pracy i nie mogą wejść do commita.

## Recommended execution

`gpt-5.6-sol medium`. Zmiana jest małym, izolowanym kontraktem aplikacyjnym;
eskalacja jest wymagana, jeżeli test wykaże, że półautomat materializuje
zarządzane cropy przed utworzeniem runu albo współdzieli rezerwację z importem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Pominąć `ImageWriteCapacityGuard` wyłącznie dla
  `SEMI_AUTOMATIC_SELECTION`.
- Zachować limit liczby i rozmiaru plików oraz kontrolę fizycznego wolnego
  miejsca z rezerwą 512 MiB.
- Zachować guard bez zmian dla `LAYOUT_IMPORT` i `PHOTO_SELECTION`.
- Dodać testy regresyjne i opisać rozdzielenie obu zabezpieczeń.

## Out of scope

Zmiana progów magazynu, czyszczenie danych, przenoszenie stagingu między
dyskami, zmiany UI/API/OpenAPI oraz wyłączenie guardu dla importu plansz albo
zwykłego wyboru zdjęć.

## Acceptance criteria

- [x] Półautomat nie zwraca `STORAGE_CAPACITY_INSUFFICIENT` z estymacji
  przyszłych artefaktów.
- [x] Półautomat nadal odmawia startu, jeśli źródła wraz z rezerwą 512 MiB nie
  mieszczą się fizycznie na woluminie stagingu.
- [x] Import plansz i zwykły wybór zdjęć nadal wywołują capacity guard.
- [x] Skoncentrowane testy, Ruff i kontrola typów zmienionego pionu przechodzą.

## Technical notes

Rozstrzygnięcie ma zostać wykonane w `BrowserImageSelectionService.begin`
przed utworzeniem katalogu uploadu. Nie wolno łapać ani tłumić błędu guardu;
warunek ma jawnie wykluczyć tylko `SEMI_AUTOMATIC_SELECTION`. Późniejszy
`shutil.disk_usage` pozostaje wspólny dla wszystkich celów.

## Expected files

- Istniejące:
  `services/api/src/game_predictor_api/application/image_imports.py` — warunek
  wywołania `ImageWriteCapacityGuard`.
- Istniejące: `services/api/tests/test_image_imports_api.py` — regresje celu i
  rezerwy fizycznej.
- Istniejące: wymagania, architektura, kontrakt API, decision log i current
  state.
- Nowe: ten plik zadania; po zakończeniu przeniesiony do `completed/`.

## Test cases

- Guard zawsze odrzuca → półautomat rozpoczyna staging i guard nie jest
  wywołany.
- Ten sam guard → layout import i photo selection zachowują błąd.
- Niski wynik `disk_usage.free` → półautomat zwraca
  `IMAGE_BROWSER_SELECTION_DISK_SPACE_INSUFFICIENT` i nie tworzy uploadu.

## Verification

```powershell
pytest services/api/tests/test_image_imports_api.py -k "capacity or semi_automatic" -q
ruff check services/api/src/game_predictor_api/application/image_imports.py services/api/tests/test_image_imports_api.py
mypy services/api/src/game_predictor_api/application/image_imports.py
```

Warunkiem zakończenia są zielone testy trzech zachowań oraz commit zawierający
wyłącznie pliki TASK-0527.

## Risks / open questions

- Brak pytań blokujących. Świadomie nie zwalniamy `PHOTO_SELECTION`, ponieważ
  użytkownik wskazał wyłącznie wybór półautomatyczny.

## Outcome

### Changed

- `BrowserImageSelectionService.begin` pomija estymację zarządzanych artefaktów
  tylko dla `SEMI_AUTOMATIC_SELECTION`.
- Dodano regresje dla półautomatu, obu chronionych purpose i fizycznej rezerwy.

### Verification results

- `pytest test_image_imports_api.py test_semi_automatic_image_selections.py`:
  57 passed.
- Ruff check oraz format check zmienionych plików: passed.
- Scoped mypy z pominięciem analizy zależności: passed.
- Standardowy mypy zmienionego modułu: zatrzymany przez wcześniejsze braki
  `py.typed` workera i wcześniejszy `no-any-return` w `application/jobs.py`.

### Not completed

- Nie restartowano działającego API, aby nie przerywać równoległej pracy.
- Nie zmieniano UI, API/OpenAPI, stagingów ani ustawień storage.

### Documentation updates

- Uaktualniono wymagania i architekturę selekcji, kontrakt API, D-372 oraz
  `CURRENT_STATE.md`.

### Recommended next task

- Po restarcie API ponowić wybór katalogu w półautomacie i obserwować wyłącznie
  rzeczywistą kontrolę wolnego miejsca stagingu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0527 | `gpt-5.6-sol` | `medium` | Izolowana zmiana warunku aplikacyjnego z testem regresyjnym chroniącym pozostałe cele stagingu. | Niewymagany; testy pokrywają oba ramiona warunku i fizyczną rezerwę. |
