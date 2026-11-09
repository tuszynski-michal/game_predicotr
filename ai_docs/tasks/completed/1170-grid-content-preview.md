---
title: TASK-1170 — Czytelny podgląd siatki i obrysów
status: done
last_updated: 2026-11-09
---

# TASK-1170 — Czytelny podgląd siatki i obrysów

## Status

`done`

## Goal

Zgodność zwykłego podglądu API/Admin/HTML bez wycieku do ślepego pomiaru.

## Context

Operator zaakceptował cały plan i koszt 6–10 h; audyty tylko terminalowe.
Zatwierdzenie kosztu nie obejmuje operatorowego treningu, wdrożenia ani merge.

## Dependencies / entry conditions

brak; main v1.7.581. Przed kodem ponownie odczytać przypisaną sekcję zaakceptowanego planu.

## Recommended execution

gpt-6.1-sol/high. Uzasadnienie: Zgodność zwykłego podglądu API/Admin/HTML bez wycieku do ślepego pomiaru. Nierozwiązane P0/P1 blokują commit;
nie zmieniać modelu niejawnie. Review Claude Code claude-opus-5-5/high.

## Relevant docs

- `ai_docs/delivery/GRID_SYMBOL_CROP_PREVIEW_PLAN_20261109.md` — T1 i kryteria wspólne.
- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-593--izolowane-etykietowanie-i-dowodowy-eksport-html`.
- D-590/D-591/D-592 w tym samym pliku, przez wyszukanie odpowiednich sekcji.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-594--przypięty-zwykły-podgląd-siatki-i-produkcyjnych-wycinków`.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.

## Scope

Sekcja T1 planu i niezbędne testy regresji. Brak quadu nie daje obrysu; 24 zapisane punkty bez modyfikacji; trzy niezależne przełączniki; revision/provenance; wycofanie generatora koloru; read-only oraz blind isolation.

## Out of scope

Aktywacja modelu/marginesu, operatorowy GPU/trening/import691, mutacje etykiet,
restarty usług, migracja operatora, merge/push oraz klasyfikator nowej architektury.

## Acceptance criteria

- [x] Każdy punkt T1 planu ma implementację lub jawny warunek zależny od danych.
- [x] Brak quadu nie daje obrysu; 24 zapisane punkty bez modyfikacji; trzy niezależne przełączniki; revision/provenance; wycofanie generatora koloru; read-only oraz blind isolation.
- [x] Istniejące historyczne kontrakty i ręczne korekty są zachowane.
- [ ] Właściwe testy, lint, typy i docs/map; niezależny Opus audit i receipt.

## Technical notes

T1 rozszerza istniejący GET reference o opcjonalną parę pinów i ordinaryPreview.
Bez pinów pozostaje historyczny odczyt trzech pól; zwykłe zapisy są zachowane.
Zapisane24punkty i footprinty aktualnego manifestu są wyłącznie warstwami
odczytu. Rysowanie nie wywołuje zapisu. Źródła każdej zapisanej ślepej sesji
są chronione po normalized pixel SHA we wszystkich slotach/UUID/fazach; B/REG
także po roli. Pomocnicza galeria eksportuje tylko niechronione TRAIN.
Brak aktualnego manifestu nie pozwala wyprowadzić footprintu z pełnego pola.

Domyślny pomocniczy workflow używa nowego GET-only eksportu bieżących adnotacji;
nie uruchamia untracked prepare_proposals.py/build_review.py z root artifacts.
Powiększenie pokazuje otoczenie i zakres cropu, nie wytwarza nowych danych GT.
Oddzielny T4 odpowiada za15rastrów klasyfikatora i rzeczywiste wejście NN.

Źródłem prawdy są rewizje zapisanych adnotacji, frozen snapshot i pinned render.
Nie zamieniać pudełka podglądu w GT. Nie wyświetlać podpowiedzi w blind; chronić
całe źródła użyte w pomiarze. Brak danych jest jawnym stanem, nie PASS.
Artykuły pomocnicze są w root artifacts/full-symbol-training-20261109; nie nadpisywać
ich ani bazy. Odczyt operatorski tylko read-only; wyniki do artifacts tego worktree.

## Expected files

- API/schema/application/storage: istniejące `grid_cell_content.py` oraz nowy
  `services/api/src/game_predictor_api/storage/grid_content_preview.py`.
  `grid_cell_content_targets.py` wykorzystano bez zmiany source-only kontraktu.
- Admin: `grid-content-ordinary.tsx`, `grid-content-canvas.tsx`,
  `grid-correction-learning.css`, ich istniejący test interakcji.
- SDK: OpenAPI, wygenerowane typy/index, wrapper i request test.
- Nowy helper `scripts/export_grid_content_preview.py`; nowe testy
  `test_grid_content_preview.py`, `test_grid_content_preview_export.py` oraz
  rozszerzony `integration/test_grid_content_targets_postgres.py`.
- Wymagania/architektura VISION_LAB i `quality/TASK-1170_VERIFICATION.md`.

## Test cases

Kryteria planu: ghost quad, wspólne granice/perspektywa, J/10/obramowania/ciemne
symbole, sąsiad, brak pikseli/rzędu, blind isolation, CAS/currentness i restart/replay.
Testy specyficzne dla taska doprecyzować przed implementacją w raporcie weryfikacji.

## Verification

Z katalogu worktree: właściwe testy pytest przez D:/game_predicotr/.venv/Scripts/python.exe
z PYTHONPATH własnego services/api/src i services/worker/src; testy Admin
`npm run test:geometry --workspace @game-predictor/admin`, scoped lint/typecheck,
`npm run docs:check`, `npm run code-map:check`. Każda komenda ma timeout.
Szerszy build dopiero po testach pionu. Audyt według CROSS_AUDIT do 1800 s.

## Risks / open questions

Brak GT i rodowodu może blokować wynik jakości, nie implementację narzędzia.
Nie deklarować poprawy wytrenowanego modelu bez rzeczywistego eksperymentu.

## Outcome

Commit: v1.7.582 (hash dopisuje kolejny commit).

### Changed

- Zwykły podgląd ma trzy niezależne warstwy, dokładne zapisane24punkty,
  tekstową legendę, zoom otoczenia i produkcyjny footprint z aktualnego manifestu.
- Piny źródła, rewizji/slotu, geometrii, manifestu i renderSpec są sprawdzane
  bez zapisu. Rewizja/pochodzenie/autor/zatwierdzenie oraz braki są jawne.
- Przypięty preview i galeria chronią całe obrazy ślepych sesji, kopie i sloty;
  B/REG nie dostają nowych hintów. Historyczne zwykłe odczyty/zapisy zachowane.
- GET-only eksport HTML zastępuje domyślne pomocnicze generowanie koloru/
  jasności; rysuje aktualny quad, nigdy boxInPreview lub stary overlay PNG.
  Fragment/unknown ma opis i odrębny przerywany styl, bez deklaracji pełnego GT.

### Verification results

- Niezależny terminalowy Opus5.5/high R2 PASS, otwarteP0=0/P1=0.
  Raport i zweryfikowany receipt: `quality/TASK-1170_AUDIT_claude-opus-5-5.md`;
  pierwotny REVISE i receipt zachowane byte-exact w plikach `_R1`.
- Root po poprawkach: docs:check, regeneracja mapy i code-map:check PASS.

- Po jednej rundzie poprawek Opus R1: API/domain/HTML52PASS; rzeczywisty eksport
  GET-only objęty testem ochrony obrazów, SHA i limitów. Style siatki/cropu mają
  test computed style, piny kontrolera i ukrywanie uchwytów są sprawdzane.
- Pełne `npm run test:geometry --workspace @game-predictor/admin`:
  428PASS/10FAIL (438testów). Te same10niezwiązanych błędów supergames
  potwierdzone na main (ograniczony baseline24PASS/10FAIL). Przejściowy picker
  z pierwszej próby przeszedł w końcowym biegu i w baseline. SDK request4PASS.
  Nie deklarujemy pełnego zielonego suite.
- Standardowy Admin typecheck
  i scoped mypy6plików PASS; scoped Ruff i ESLint PASS. OpenAPI --check PASS.
- Rzeczywisty disposable PostgreSQL: alias normalized pixel SHA z innegoUUID/
  slotu/frozenphase chroni źródło; legacy reference pozostaje czytelny,
  SQL preview jest read-only, nowy proces zachowuje ochronę; cleanup0baz/0ról.
  R1 dodatkowo potwierdza15footprintów rzeczywistego renderera z prawdziwego
  board_render_manifest. Write DTO nie zawiera już read-only ordinaryPreview;
  kontrakt i SDK zregenerowane. Szczegóły R1: `quality/TASK-1170_FIXES_R1.md`.
  Szczegóły/receipt i ograniczenia środowiska: `quality/TASK-1170_VERIFICATION.md`.

### Not completed

- Operatorowy trening, inferencja, import691, wdrożenie i zmiany modelu/marginesu
  nie należą do T1; nie wykonano restartów ani mutacji adnotacji/bazy operatora.
- Pełny build pozostaje bramką T4; pełny test Admin ma10zastanych FAIL supergames,
  potwierdzonych na main. Zmieniony pion jest zaliczony; nie naprawiano obcego zakresu.
- P2-7 (edycja przy ukrytej warstwie) i P2-8 (pominięcie HTML bez nodes) są
  jawnie przyjęte jako ograniczenia T1 i zaplanowane do domknięcia w T4.

### Documentation updates

- Sekcje T1 w requirements/architecture VISION_LAB; szczegółowy raport T1.
  CURRENT_STATE, log decyzji, mapa i zamknięcie pozostają u agenta głównego.

### Accepted residual risk (P2-4)

D-594 chroni role w przekazanej kohorcie i źródła już zapisanych ślepych sesji.
Nie gwarantuje globalnej nieekspozycji obrazu w innych kohortach ani ochrony
zdjęcia, które dopiero później zostanie wybrane do pomiaru. Ryzyko przyszłej
ekspozycji pozostaje jawnie zaakceptowane w tym zakresie; T1 nie rozszerza
polityki wyboru i nie deklaruje niezależności przyszłego pomiaru na takim źródle.

### Recommended next task

- Po audycie i commicie T1: TASK-1171, porównanie rzeczywistych wycinków.
