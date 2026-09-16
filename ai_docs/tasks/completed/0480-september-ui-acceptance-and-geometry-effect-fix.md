---
title: September UI acceptance and geometry effect fix
status: done
last_updated: 2026-09-06
---

# TASK-0480 — Odbiór zmian 5–6 września i poprawka efektów geometrii

## Goal

Potwierdzić na działającym panelu, że dostarczone 5–6 września funkcje są
widoczne i zgodne z API, oraz usunąć wykryty błąd pełnego lintowania w panelu
rozliczania problematycznych plansz bez zmiany jego zachowania domenowego.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/tasks/completed/0453-geometry-guard-resolution-admin-ui.md`
- `ai_docs/tasks/completed/0473-unreadable-board-virtual-previews.md`
- `ai_docs/tasks/completed/0474-direct-ready-grid-editing.md`
- `ai_docs/tasks/completed/0475-direct-grid-pointer-drag.md`
- `ai_docs/tasks/completed/0476-active-symbol-model-cohort-filter.md`
- `ai_docs/tasks/completed/0477-fix-selected-crop-directory-discovery.md`
- `ai_docs/tasks/completed/0478-deferred-source-slot-manual-geometry.md`
- `ai_docs/tasks/completed/0479-four-point-selected-crop-registration.md`

## Scope

- Zweryfikować działający filtr `Kohorta aktywnego modelu`, miniatury i akcje
  jakościowe na realnym lokalnym API.
- Uruchomić regresję Admina, klienta API, lokalnego cropa oraz backendu symboli,
  geometrii i geometry guard.
- Odroczyć inicjalizujące aktualizacje stanu dwóch efektów Reacta do
  anulowalnego callbacku, aby pełny ESLint nie raportował synchronicznego
  `setState` w efekcie.
- Zachować dokładnie ten sam refresh, wybór pierwszego celu i cleanup po zmianie
  zależności lub unmount.
- Nie zmieniać danych, aktywnych jobów, stagingów ani wersji silnika.

## Definition of Done

- Filtr kohorty działa na uruchomionym API i zwraca checksum-bound elementy
  aktywnej kohorty.
- Pełny lint Admina, testy i typecheck są zielone.
- Inicjalizacja panelu geometry guard nie wykonuje synchronicznej kaskady
  renderów i anuluje oczekujący callback przy zmianie kontekstu.
- OpenAPI i wygenerowany klient pozostają zgodne.
- Wynik audytu jest zapisany w `CURRENT_STATE.md`, a task ma osobny commit.

## Outcome

- Odbiór działającego panelu potwierdził obecność filtra
  `Kohorta aktywnego modelu`, rozmiarów strony `500/1000/2000/2500`, start bez
  wybranej gry i symbolu, brak przycisku `Zmień wybór`, checkbox
  `Niewyraźny` oraz miniatury cropów. Dla gry `777 v0.2` filtr kohorty zwrócił
  948 bieżących elementów na dwóch stronach.
- Zweryfikowano commity i ukończone taski z 5–6 września. Nie znaleziono
  brakującego wdrożenia w zamkniętym zakresie; niewidoczny filtr wynikał ze
  starego stanu wcześniej otwartej karty, a nie z braku kodu lub kontraktu API.
- Usunięto dwa błędy pełnego lintowania w panelu rozliczania problematycznych
  plansz. Inicjalizacja efektów jest wykonywana przez anulowalny callback i nie
  pozostawia spóźnionych aktualizacji stanu po zmianie kontekstu.
- Przeszły: 410 testów Admina, 51 testów klienta API, 84 testy lokalnego core,
  81 testów API dotyczących symboli i geometrii, pełny lint i typecheck Admina,
  kontrola OpenAPI oraz produkcyjny build.
- Nie zmieniono danych użytkownika, stagingów, aktywnych jobów ani domyślnych
  wariantów silników. Nieaktywne v11 nadal pozostaje poza wdrożeniem, ponieważ
  jego odrębna bramka jakości TASK-0472 nie została spełniona.

## Commit

`v0.10.194 - finalize september admin changes`
