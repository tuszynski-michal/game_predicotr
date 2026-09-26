# TASK-0707 — Stały kadr podczas gestu i automatyczny podgląd

## Status

done

## Goal

W Reviewerze 3001 pojedyncza odroczona plansza pokazuje obraz po każdym
wejściu; kadr dopasowuje się i preview odświeża dopiero po puszczeniu siatki.

## Context / Scope

Użytkownik zastępuje checkbox „Aktywne przesuwanie” automatycznym dopasowaniem
po zakończeniu gestu. Narożnik zmienia geometrię, wnętrze przesuwa cały quad.
Podczas gestu viewport jest stały. Automatyczny preview nie zapisuje geometrii.
Dotyczy tylko DeferredBoardCellGeometryEditor; bez zmian API i laboratorium.

## Relevant docs

- ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md
- ai_docs/process/DEFINITION_OF_DONE.md

## Acceptance criteria

- [x] Obraz rysuje się przy pierwszym i kolejnych wejściach oraz po remount.
- [x] Pointer move nie zmienia kadru ani nie wysyła preview; release dopasowuje
      kadr i generuje preview końcowej geometrii.
- [x] Cancel/lost capture kończy gest; drugi pointer nie przejmuje gestu.
- [x] Starsza odpowiedź preview nie nadpisuje nowszej ani następnej planszy.
- [x] Checkbox usunięty; zapis pozostaje jawną akcją po aktualnym preview.

## Technical notes / Expected files

Edytor deferred: snapshot viewportu na czas gestu, image readiness i redraw
po montażu, auto-preview po ustaniu gestu. Test komponentu w test-interactions
z mockiem obrazu, canvasa i API. Aktualizacja istniejącego testu kontraktu
UI, wymagań i CURRENT_STATE. Brak blokujących decyzji.

## Verification

Test interakcji, testy Reviewera, lint, typecheck i format; każdy proces
testowy ograniczony do 120 sekund. Odbiór nie zapisuje danych użytkownika.

## Outcome

### Changed

- Snapshot viewportu/rect/pointer ID na czas gestu; dopasowanie dopiero po
  release, także poprawne zakończenie cancel/lost capture. Auto-preview po
  release, wejściu i kwalifikacji; ręczne ponowienie dostępne po błędzie.
- Obraz jest stanem związanym z URL; layout effect maluje canvas również
  po remount. Starsze callbacki obrazów i odpowiedzi preview są ignorowane.
- Usunięto checkbox. Port 3001 serwował stary build (proces 6664), co
  potwierdziła także stara domyślna zakładka. Nowy production build wystartował
  przez istniejący skrypt lifecycle, instance 04d94b98-91b4-47b8-ad79-734d1bf828af.

### Verification results

- Test komponentu obejmuje fixed crop podczas hold, finalny pointerup,
  drugi pointer, cancel, spóźniony konflikt, przejście zdjęć i remount.
- `tsx --tsconfig apps/reviewer/tsconfig.json --test apps/reviewer/test-interactions/*.test.mjs`: 4/4.
  Sandbox blokuje userInfo Windows; przebieg poza sandboxem zaliczony.
- `node --experimental-strip-types --test test/*.test.mjs`: 203/203.
- ESLint zmienionych modułów, tsc --noEmit, Prettier, git diff --check: PASS.
- `npm run reviewer:build`: PASS. Odbiór nowego procesu na 3001: domyślne
  niepełne siatki, zdjęcia 122404 i 122446 widoczne bez klikania centrowania,
  drag narożnika automatycznie odświeżył cropy, następna plansza również.
- Kryteria taska sprawdzone; API i zapis nie zmienione. Bez automatycznego
  zatwierdzania, push, zmian danych i ingerencji w laboratorium 3102.

### Not completed

Fizyczny Android i restart całego komputera nie były testowane. Aktualny
build jest zapisany na dysku i sprawdzony w nowym procesie produkcyjnym.

### Documentation updates

Wymagania/architektura iteracyjnego importu oraz CURRENT_STATE.

### Recommended next task

Brak dalszego taska w tym zakresie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0707 | gpt-6-astra | medium | Cykl obrazu i wyścigi odpowiedzi w jednym edytorze | Testy interakcji, bez delegowania |
