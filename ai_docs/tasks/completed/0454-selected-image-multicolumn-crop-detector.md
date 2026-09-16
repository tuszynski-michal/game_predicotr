---
title: TASK-0454 Selected image multicolumn crop detector
status: in_progress
last_updated: 2026-09-05
---

# TASK-0454 — Wielokolumnowy detektor panelu v4

## Goal

Zastąpić jednowymiarową decyzję auto-cropa konserwatywnym detektorem, który
potwierdza panel plansz w wielu częściach szerokości i nigdy nie zaciska
niepewnego wyniku wokół pojedynczego lokalnego sygnału.

## Scope

- policy `selected-image-board-band-v4-conservative-multicolumn`;
- podgląd do 512 px i dziewięć pionowych pasów;
- niezależny dowód chromatyczny i strukturalny;
- pokrycie co najmniej pięciu pasów oraz lewej, środkowej i prawej części;
- bezpieczna obwiednia dla pochylenia, asymetryczny padding i kontrola
  zawartości przy granicy;
- klasy `high_confidence`, `conservative` i `safe_wide`;
- regresyjne testy czystej domeny.

## Out of scope

- trwała proweniencja propozycji w shardach sesji;
- przeliczanie istniejących plików `cut`;
- badge i filtr klas w Adminie;
- OCR, API, PostgreSQL, obrót i homografia.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- pojedynczy lokalny sygnał nie może wyznaczyć automatycznego cropa;
- niepewny obraz zwraca jawny, edytowalny pas `5–95%`;
- granica z mocnym, szerokim sygnałem jest odsuwana na zewnątrz;
- EXIF, render 1:1 i pełna szerokość pozostają bez zmian;
- testy core, typecheck, lint/format zmienionych plików są zielone.

## Outcome

- Dodano policy v4 analizujące podgląd do 512 px w dziewięciu pionowych pasach.
- Zachowano szybki niebieski sygnał v3 jako składnik dowodu chromatycznego i
  połączono go z nasyceniem, kontrastem oraz powtarzalnymi krawędziami.
- Kandydat wymaga wsparcia co najmniej pięciu pasów oraz lewej, środkowej i
  prawej części. Zgodność rodzin dowodu daje `high_confidence`, rozbieżność
  `conservative`, a brak dowodu `safe_wide` 5–95%.
- Lokalne granice są agregowane percentylami, a mocna zawartość w strefie 3%
  może wyłącznie rozszerzyć crop. Wynik niższy niż 40% jest odrzucany.
- Zaktualizowano minimalne transportowe typy Web Workera i tekst propozycji;
  trwały zapis pełnej proweniencji pozostaje poza tym taskiem.

### Verification

- `npm run test --workspace @game-predictor/manual-image-selection-core` —
  45/45 passed.
- testy kontraktowe crop storage/workspace Admina — 13/13 passed.
- typecheck core i Admin — passed.
- skoncentrowany ESLint zmienionych modułów Admina — passed.
- `npm run admin:build` — passed.
- Prettier check zmienionych plików i `git diff --check` — passed.
- Globalny `format:check` nadal wskazuje wcześniejsze, niezwiązane pliki poza
  zakresem taska; zmienione pliki są sformatowane.
