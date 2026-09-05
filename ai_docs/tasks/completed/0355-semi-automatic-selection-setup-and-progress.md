# TASK-0355 — Konfiguracja i progres półautomatycznej selekcji

Status: `done`

## Cel

Udostępnić niezależny od gry, lokalny konfigurator globalnego runu
półautomatycznej selekcji oraz jego widoczny, odporny na reload monitoring.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `.tmp/TASK-0350-0357-semi-automatic-selection-plan.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Zakres

- osobna pozycja nawigacji Admina, bez `gameId`;
- wybór katalogu źródłowego i docelowego File System Access API;
- walidacja granic sekwencji, kierunku i liczby oczekiwanych zakresów;
- globalny browser staging, widoczny postęp plików i bajtów, retry oraz
  anulowanie niedokończonego uploadu;
- odczyt capabilities API, widoczny stan flagi serwerowej i blokada UI;
- sekwencyjny polling statusu runu, liczniki, pause/resume/cancel i odtworzenie
  ostatniego `runId` oraz uchwytów folderów po reloadzie.

## Poza zakresem

- `REVIEW_MODE` i `EDIT_SOURCE_MODE`;
- przegląd oczekiwanych zakresów, ręczne dodanie/zastąpienie zdjęcia i końcowa
  synchronizacja outputu;
- nowe endpointy API, OpenAPI, migracje, worker oraz zmiana algorytmu OCR.

## Invarianty

- workflow nie należy do gry i staging ma `gameId = null` oraz purpose
  `semi_automatic_selection`;
- źródło zawiera wyłącznie naturalnie uporządkowane JPEG-i, a folder docelowy
  nie jest w tym tasku mutowany;
- capabilities API jest jedynym źródłem flagi; wyłączona funkcja nie wysyła
  mutacji z UI;
- upload przechowuje możliwość wznowienia, ale IndexedDB nie przechowuje Blobów
  ani bajtów JPEG;
- polling jednego runu nie nakłada requestów i kończy się dla stanu terminalnego;
- TASK nie zawiera końcowego review ani edycji źródeł.

## Weryfikacja

- kontrakt nawigacji, flagi, bounds, uploadu, progressu i braku trybów
  końcowego review;
- transport klienta capabilities/lifecycle;
- testy Admina i klienta, lint, typecheck, build Admina, format check oraz
  kontrola diffu.

## Outcome

- Dodano globalny workspace `Półautomatyczny wybór zdjęć` oraz typ nawigacji;
  sekcja pozostaje niezależna od gry.
- Konfigurator wykorzystuje File System Access API do źródła i docelowego
  katalogu, waliduje inkluzywne bounds, kierunek i liczbę zakresów z capabilities.
- Upload używa istniejącego globalnego stagingu, ma cztery bounded transfery,
  trzy próby na plik, widoczny postęp potwierdzony API oraz retry/anulowanie.
- Run jest odtwarzany z lokalnego klucza i operator-local store; monitor pokazuje
  etap oraz liczniki i obsługuje pause/resume/cancel bez nakładania pollingu.
- UI respektuje serwerową flagę capabilities i nie zawiera `REVIEW_MODE` ani
  `EDIT_SOURCE_MODE`.
- Przeszły: 12 skoncentrowanych testów Admina, 47 testów klienta API, Admin
  typecheck, Admin lint, produkcyjny build oraz format check plików tego taska.
- Pełny test Admina zatrzymał się na istniejącym, niezwiązanym kontrakcie
  `unreadable-board-review-workspace-contract.test.mjs`: test oczekuje
  `savingCell`, podczas gdy bieżąca, nieobjęta tym taskiem implementacja używa
  `savingBoard`. Nie zmieniano tego pionu w TASK-0355.
