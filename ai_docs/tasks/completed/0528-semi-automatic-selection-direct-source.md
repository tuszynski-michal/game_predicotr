---
title: TASK-0528 — Semi-automatic selection without image staging
status: done
last_updated: 2026-09-08
---

# TASK-0528 — Półautomatyczna selekcja bez stagingu zdjęć

## Status

`done`

## Goal

Nowy run półautomatycznej selekcji ma czytać JPEG-i bezpośrednio z lokalnego
katalogu, pokazać operatorowi wybrane źródło i zapisać dopiero zatwierdzony lub
zmieniony JPEG, bez kopiowania całego wejścia do `browser-selections`.

## Context

Obecny Admin wybiera katalog przez File System Access API, przesyła wszystkie
JPEG-i do browser stagingu i dopiero wtedy tworzy run. Jest to sprzeczne z
oczekiwanym workflowem: źródła mają pozostać w katalogu operatora, a trwałym
wynikiem mają być tylko zaakceptowane pliki `seq_*` oraz mały audyt decyzji.
TASK-0527 zdjął jedynie estymację pojemności i nie usunął kopiowania.

## Dependencies / entry conditions

- HEAD po TASK-0527: `v0.10.235`.
- Lokalny Admin API i worker działają na tym samym komputerze Windows i mają
  dostęp do wybranego katalogu C:/E:.
- Historyczne runy schema v1/v2 oraz filename verification zachowują browser
  staging i replay.

## Recommended execution

`gpt-6-astra high`, ponieważ zmiana przecina UI, API, trwały manifest źródeł i
loader workera. Eskalować do dodatkowego review przed commitem, jeśli nowa
ścieżka wymaga migracji tabel albo nie da się odseparować cleanupu historycznego
stagingu od katalogu użytkownika.

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

- Dodać kontrolowany wybór lokalnego źródła dla workflowu `selection`.
- Zbudować content-addressed manifest metadanych i checksum bez kopiowania
  JPEG-ów; katalog użytkownika nigdy nie jest zasobem zarządzanym ani celem GC.
- Utworzyć payload joba schema v3 ze źródłem `local_folder`, zachowując replay
  schema v1/v2 ze stagingu.
- Worker ma czytać dokładne pliki z katalogu źródłowego i fail-closed reagować
  na brak, zmianę rozmiaru/checksummy, zmianę kolejności lub ucieczkę ścieżki.
- API ma listować checksumowane źródła i serwować asset bezpośrednio z katalogu,
  aby Admin mógł pokazać wybór i pozwolić wskazać inne zdjęcie.
- Admin zapisuje do katalogu wynikowego dopiero zatwierdzony JPEG i manifest
  decyzji; nowy start nie wywołuje żadnego browser-upload endpointu.

## Out of scope

Zmiana OCR, grupowania i wyboru reprezentanta, import plansz, usuwanie
historycznych stagingów, tryb `filename_verification`, zdalny Admin oraz zapis
pełnych JPEG-ów w bazie lub katalogu artefaktów.

## Acceptance criteria

- [x] Start nowej półautomatycznej selekcji nie tworzy katalogu
  `imports/browser-selections/<id>` i nie wysyła JPEG-ów endpointem uploadu.
- [x] Worker wybiera identycznie jak wcześniej, czytając checksum-bound lokalne
  źródła.
- [x] Ekran review pokazuje automatyczny wybór, pozwala przejść po źródłach i
  zapisać zaakceptowany/zastąpiony JPEG do folderu wynikowego.
- [x] Zmiana źródła po utworzeniu runu blokuje tylko użycie zmienionego pliku
  stabilnym błędem, bez zapisu błędnego wyniku.
- [x] Historyczne runy i filename verification nadal działają ze stagingu.
- [x] API/OpenAPI/klient, testy API/workera/Admina, lint, typecheck i build są
  spójne.

## Technical notes

Nowy manifest przechowuje tylko `sourceRoot`, naturalnie uporządkowane
`relativePath`, `sizeBytes` i `checksumSha256`. Jego artefakt znajduje się pod
zarządzanym rootem, ale katalog źródłowy i JPEG-i nie są kopiowane ani usuwane.
Nowy job zawiera wersję, rodzaj źródła, bezpieczną ścieżkę manifestu i jego
checksummę. `source_upload_id` w historycznym modelu SQL pozostaje stabilnym
UUID źródła dla zgodności; dla schema v3 oznacza `sourceSelectionId`, nie
browser upload. Nie jest potrzebna migracja.

## Expected files

- API/application: `image_imports.py`, `semi_automatic_image_selections.py`.
- Domain/schema/router/main oraz OpenAPI i wygenerowany klient.
- Worker: `semi_automatic_selection/job.py`.
- Admin: workspace, actions, review adapter i testy.
- Nowy moduł małego lokalnego manifestu źródeł wraz z testami.

## Test cases

- Lokalny folder → manifest → schema v3 run → worker odczytuje oryginały bez
  browser stagingu.
- Brak/zmiana JPEG-a, checksummy, ścieżki lub manifestu → fail-closed.
- Lista i asset wymagają bieżącej checksummy.
- Admin startuje przez local-source endpoint i nie wywołuje create/upload/finalize
  browser stagingu.
- Historyczny schema v2 nadal ładuje `_browser_manifest.json`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest <focused API and worker tests> -q
npm test --workspace @game-predictor/admin
npm run openapi:check
npm run typecheck --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

Kryterium zakończenia: test interakcji potwierdza brak wywołań browser uploadu,
a test systemowy brak katalogu stagingu i poprawny zapis jednego wybranego JPEG-a.

## Risks / open questions

- Lokalna ścieżka działa wyłącznie wtedy, gdy API i worker widzą ten sam system
  plików; capabilities musi oznaczyć ten tryb jako local-only.
- Hashowanie wszystkich wejść pozostaje konieczne dla wykrycia zmian, ale nie
  rezerwuje miejsca proporcjonalnego do zdjęć.

## Outcome

Nowe runy `selection` korzystają z kontrolowanego lokalnego pickera, trwałego
manifestu schema v3 oraz bezpośredniego, checksum-bound odczytu JPEG-ów przez
worker i endpoint assetu. Admin nie tworzy, nie wysyła i nie finalizuje browser
stagingu; w review odtwarza listę źródeł z API i zapisuje wyłącznie wybrany plik
do katalogu wynikowego. Historyczny loader schema v1/v2 i workflow
`filename_verification` pozostały bez zmian.

Weryfikacja: 36 skoncentrowanych testów API/workera i 447 testów Admina passed;
Ruff, scoped mypy, typecheck klienta i Admina, OpenAPI drift check, lint oraz
produkcyjny build Admina passed. Nie wykonano operacji na danych użytkownika,
nie usunięto historycznych stagingów i nie dodano migracji bazy.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0528 | `gpt-6-astra` | `high` | Zmiana pełnego lokalnego pionu źródło → worker → review przy zachowaniu replay historycznych jobów. | Wymagany tylko jeśli analiza ujawni migrację lub ryzyko dotknięcia katalogu użytkownika przez cleanup. |
