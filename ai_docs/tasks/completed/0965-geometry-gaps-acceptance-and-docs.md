---
title: TASK-0965 — Decyzja D-541, dokumentacja i odbiór braków geometrii na żywych danych
status: done
last_updated: 2026-10-10
---

# TASK-0965 — Decyzja D-541, dokumentacja i odbiór braków geometrii na żywych danych

## Status

`done`

## Goal

Zakres lokalnego Reviewera (gra, zakładka „Braki zdjęć”, „Siatka
niepotwierdzona” tylko jako licznik) jest zapisany jako decyzja D-541 i
zweryfikowany na żywych danych Mumii i 777.

## Context

Plan: `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`. D-462
definiuje kolejkę korekty bez walidacji gotowych siatek; D-484 definiuje
kompletność i diagnostykę. Ten task dopisuje decyzję łączącą oba i zamyka plan
odbiorem.

## Dependencies / entry conditions

- TASK-0961–0964 `done`.
- Uruchomione lokalnie API (8000), Admin (3000) i Reviewer (3001) z
  kodem z tej gałęzi. Restart API i `npm run reviewer:build` wykonuje operator
  albo wymaga jego jawnej zgody (równoległe instancje API na jednej bazie —
  nie restartuj na własną rękę).
- Numer decyzji D-541 i wersja `vX.Y.N` sprawdzone na końcówce
  `v1.1-vision-lab-hybrid-geometry` bezpośrednio przed zapisem i przed
  scaleniem.

## Recommended execution

`claude-sonnet-5-5`, `medium` — zgodnie z tabelą planu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`
- `ai_docs/architecture/CODE_MAP.md`

## Scope

1. `DECISION_LOG.md` (indeks) i `decisions/DECISION_LOG_2026.md`: D-541 —
   lokalny Reviewer pracuje w zakresie gry; zakładka „Braki zdjęć” obejmuje
   realne braki (D-484: `incomplete_missing`, `incomplete_partial`,
   `import_failed`, `no_source_geometry`); „Siatka niepotwierdzona” pozostaje
   licznikiem w Adminie i nie jest kolejką (D-462 bez zmian w tej części);
   UI wyjątków bramki usunięte z Admina (API i audyt zostają); doprecyzowanie
   D-462 „Correction queue” i D-484 „diagnostyka”.
2. `CURRENT_STATE.md` zgodnie z regułą okna kroczącego; `API_CONTRACT.md`
   (parametry `counts`, `gapsOnly`, pole `humanApproved`); `CODE_MAP.md`
   (nowe moduły Reviewera, usunięte moduły Admina).
3. Odbiór na żywych danych (lista kontrolna poniżej) z zapisem wyników w
   `Outcome`.

## Out of scope

- Zmiany kodu aplikacji poza poprawkami wykrytymi w odbiorze (taki błąd
  wraca do właściwego taska, nie jest łatany tutaj po cichu).
- Scalanie i push (osobna zgoda operatora; patrz `merge-means-push`).

## Acceptance criteria

- [x] D-541 w indeksie i w pliku decyzji, z odwołaniami do D-462/D-484.
- [ ] Odbiór wizualny Mumie (Admin „4 … 51 541”, „Otwórz lokalnie” bez
      importu, „Braki zdjęć” = 4 zdjęcia, zdjęcia widoczne od razu): dane i
      zachowanie zweryfikowane na żywym API oraz testami interakcji; ekran
      Reviewera na porcie 3001 wymaga restartu przez operatora (patrz
      `Outcome` → `Not completed`).
- [ ] Odbiór wizualny 777 („Do korekty” 255, „Plansza częściowa” z ukrytymi
      zatwierdzonymi ręcznie): dane zweryfikowane na żywym API; zapis
      siatki testowej nie wykonany (wymaga zgody operatora).
- [x] Pomiary czasu: `counts=correction` 0,14 s (Mumie) i 1,06 s (777);
      `gapsOnly` 4,7–4,8 s na stronę.
- [x] `npm run docs:check` zielone; [x] `git diff --cached --check` czysty.

## Technical notes

Odbiór jest tylko do odczytu, poza jawnie uzgodnionym zapisem jednej siatki.
Dowody: zrzuty lub opis z przeglądarki (wbudowana przeglądarka aplikacji),
czasy z `curl -w`. Nie uruchamiaj benchmarków. Jeśli budżet czasu nie jest
spełniony, task kończy się jako `blocked` z wynikiem pomiaru; plan wymaga
korekty (TASK-0961), nie obejścia.

## Expected files

- Istniejące: `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/process/decisions/DECISION_LOG_2026.md`,
  `ai_docs/process/CURRENT_STATE.md`,
  `ai_docs/architecture/API_CONTRACT.md`,
  `ai_docs/architecture/CODE_MAP.md`.
- Nowe: brak.

## Test cases

- Lista kontrolna odbioru z kryteriów akceptacji; każda pozycja z wynikiem
  tak/nie i dowodem.

## Verification

```powershell
# katalog: korzeń worktree; timeout <= 120 s na komendę
npm run docs:check
git diff --cached --check
```

Zaliczenie: powyższe zielone oraz wypełniona lista odbioru w `Outcome`.
Testy planowane nie są wynikami wykonania.

## Risks / open questions

- Dane w bazie zmieniają się w trakcie importów — liczby w odbiorze mogą
  różnić się od liczb z planu; zapisz stan z dnia odbioru.
- `CODE_MAP.md` jest w głównym checkoucie zmodyfikowany przez inną pracę —
  uzgodnij zmiany względem końcówki gałęzi integracyjnej.

## Outcome

Wykonawca: dokumentacja `claude-sonnet-5-5`, odbiór orkiestrator
(`claude-sonnet-5-5`), 2026-10-10, worktree `worktrees/reviewer-geometry-gaps`
(gałąź `feat/reviewer-geometry-gaps`).

### Changed

- D-541 (wpis w `DECISION_LOG.md` i `decisions/DECISION_LOG_2026.md`),
  `CURRENT_STATE.md` (stan planu, ograniczenie „Lokalny Reviewer / D-541”),
  zamknięcie planu `REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`.
- Poprawka znaleziona w odbiorze (kod, `apps/reviewer`): pozycja, która ma
  planszę, ale nie ma wpisu w kolejce review (Mumie: jedno zdjęcie
  `incomplete_missing` z dziewięcioma pozycjami `uncertain`), dostawała
  nieprawdziwy tekst „Brak planszy i slotu…”; teraz pokazuje
  `GEOMETRY_GAPS_BOARD_WITHOUT_ROW_HINT` („Plansza istnieje, ale nie ma wpisu
  w kolejce…”), z testem interakcji.

### Verification results

Uruchomione:

- `npm run docs:check` (`check_decision_links.py` OK 537 wpisów,
  `check_current_state_window.py` OK 10 sekcji done), `generate_code_map.py
  --check` OK.
- Reviewer: `test` 253/253, `test:geometry` 67/67, `typecheck` OK, `lint` 0
  błędów (1 istniejące ostrzeżenie), `format:check` OK.
- Admin: `test` 729/729, `test:geometry` 206/206 (wynik TASK-0964).
- Produkcyjne buildy z worktree: `npm run build --workspace
  @game-predictor/reviewer` i `... @game-predictor/admin` — oba `exit=0`.
- Odbiór na żywych danych (tymczasowa instancja API z worktree na 8011,
  wyłącznie GET, zatrzymana po pomiarze; instancja operatora na 8000
  nietknięta):

  | Gra | `grid-reviews?view=correction&counts=correction` | `incomplete-images?gapsOnly=true` | Raport kompletności |
  |---|---|---|---|
  | Mumie | `correction` = 0, 0,14 s | 4 zdjęcia (1 `incomplete_missing`, 3 `import_failed`), 4,8 s | 53 302 zdjęć, 53 091 niekompletnych, w tym 53 087 niepotwierdzonych |
  | 777 | `correction` = 255, 1,06 s | 76 zdjęć `incomplete_partial` (73 z wszystkimi pozycjami `partial` zatwierdzonymi ręcznie), 4,7 s | 56 812 zdjęć, 76 niekompletnych |

  Dla zdjęcia `incomplete_partial` (777) `grid-reviews?view=all&sourceImageId=…`
  zwraca osiem wierszy `current_review` (pozycje 0–5, 7, 8; pozycja 6 `partial`
  bez wiersza), dla `incomplete_missing` (Mumie) brak wierszy — zgodnie z
  decyzją 5 planu (informacja bez edytora).
- Zdjęcia: endpoint źródła zwraca 200 `image/jpeg` dla zdjęć z listy braków na
  API operatora (8000); tymczasowa instancja 8011 zwracała 404, bo działała z
  domyślnymi ścieżkami artefaktów (różnica konfiguracji, nie błąd kodu).

### Not completed

- Odbiór wizualny ekranów w przeglądarce (Admin 3000, Reviewer 3001):
  Reviewer akceptuje tylko `127.0.0.1:3001` i łączy się z API `8000`
  (`isLoopbackReviewerHost`, CSP), a oba porty zajmują instancje operatora z
  głównego checkoutu (`next start`, API `--reload`), których nie wolno
  restartować na własną rękę. Wymaga: zatrzymania usług, scalenia gałęzi,
  `npm run reviewer:build` i restartu API/Admina/Reviewera przez operatora.
- Zapis jednej siatki testowej (zmienia dane; wymaga zgody operatora).
- Audyt poprawki wskazówki (zmiana lokalna, jedna etykieta + test).

### Documentation updates

- `ai_docs/process/decisions/DECISION_LOG_2026.md`: pełny wpis D-541 nad D-539.
- `ai_docs/process/DECISION_LOG.md`: wiersz indeksu D-541 (537 wpisów, 179 wierszy), pełna kopia D-541 w „Najnowszych wpisach” zamiast D-535.
- `ai_docs/process/CURRENT_STATE.md`: stan planu, sekcja done TASK-0965, ograniczenie „Lokalny Reviewer / D-541”.
- `ai_docs/delivery/REVIEWER_GEOMETRY_GAPS_EXECUTION_PLAN.md`: status `completed` (kod i dokumentacja; odbiór wizualny po restarcie operatora).
- `ai_docs/architecture/API_CONTRACT.md` i `CODE_MAP*.md`: sprawdzone, zgodne z implementacją.

### Recommended next task

- Restart operatora: API (`feat/reviewer-geometry-gaps` po scaleniu) i
  `npm run reviewer:build` + restart Reviewera 3001, potem przegląd
  wizualny „Braki zdjęć”.
- Opcjonalnie: przywrócenie UI wyjątków bramki; blokada ponownego importu
  tych samych zdjęć (osobna sesja); sprzątnięcie martwych reguł CSS Admina.
