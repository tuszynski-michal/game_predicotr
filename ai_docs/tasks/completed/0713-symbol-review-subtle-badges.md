# TASK-0713 — Dyskretne badge na kafelkach symboli

## Status
`done`

## Goal
Zastąpić kwadratowe Źródło kompaktowym badge i ograniczyć zasłanianie obrazu przez oznaczenia.

## Context / scope
Korekta użytkownika po wdrożeniu T1–T4: minimalna ramka, położenie przy rogu,
mocno przezroczyste tło. Przyczyna: sourceContextButton ma minimum 44 × 44 px
i tło 86%. Zakres to CSS kafelków Weryfikacji Symboli i dokumentacja.
Założenie: ta sama lekka oprawa dotyczy Źródła, jakości i numeru planszy.
Bez zmian API, danych i obsługi kliknięć. Brak blokujących pytań.

## Relevant docs
- ai_docs/requirements/ADMIN_APP.md — Weryfikacja symboli
- ai_docs/architecture/TECH_STACK.md — Admin web
- ai_docs/process/DEFINITION_OF_DONE.md

## Expected files
- apps/admin/src/features/symbol-reviews/symbol-review-workspace.module.css
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/process/CURRENT_STATE.md

## Acceptance criteria / verification
- Kompaktowe Źródło przy prawym dolnym rogu, ramka 1 px i tło o małej nieprzezroczystości.
- Pozostałe badge przy krawędziach; czytelny tekst i widoczny fokus klawiatury.
- Format i kompilacja CSS w Adminie oraz wizualny odbiór i kliknięcie podglądu.
- Bez nowych testów imitujących deklaracje CSS; istniejąca obsługa zdarzeń bez zmian.

## Outcome
- SourceContextButton zmniejszony z minimum 44 × 44 do rozmiaru tekstu;
  badge źródła/jakości/numeru: ramka 1 px, tło 22%, odstęp 1 px, zaokrąglenie.
- Fokus klawiatury jawny; tekst ma cień dla czytelności nad zdjęciem.
- Prettier --check CSS PASS (nowy proces Node, timeout 30 s), kompilacja
  przez działający Next dev i odbiór przeglądarkowy PASS na rzeczywistych cropach.
- Pomiar DOM: Źródło 40.72 × 16.48 px, rgba(5,11,20,0.22), ramka 1 px,
  prawy i dolny odstęp 1 px. Podgląd planszy 20/pola 4 działa ze zdjęciem i siatką.
- Zmiana wyłącznie CSS: bez nowych testów deklaracji, zmian TypeScript/API/danych.
  Nie uruchamiano pełnego buildu w .next używanym przez działający proces dev.
  Wymagania i CURRENT_STATE zaktualizowane; kryteria sprawdzone.
- Commit v1.7.19 / 9d55534573fe9a9345208454bab97da3cdb56e2e;
  sprawdzono staged diff/check/stat, git show --stat i pozostały status.
