# TASK-0714 — Limit odczytu listy symboli 20 sekund

## Status

done

## Goal

Domyślny limit SQL listy Weryfikacji symboli wynosi 20000 ms zamiast 5000 ms.

## Context

Operator zlecił ustawienie 20 sekund po odtworzeniu HTTP 503 QUERY_TIMEOUT.

## Relevant docs

- ai_docs/architecture/API_CONTRACT.md
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/guides/LOCAL_OPERATION_GUIDE.md

## Scope

Domyślne ustawienia API i serwisu zapytań, przykład środowiska, dokumentacja i test konfiguracji.
Jawne nadpisania środowiska pozostają obsługiwane. Liczniki zachowują 15000 ms.

## Out of scope

Optymalizacja SQL, zmiany API, danych i automatyczne wdrożenie/restart usługi.

## Acceptance criteria

- [x] Nowy proces odczytuje domyślnie 20000 ms dla listy i 15000 ms dla liczników.
- [x] Testy konfiguracji i nadpisania środowiska przechodzą.
- [x] Dokumentacja opisuje 20 sekund i konieczność restartu istniejącego procesu.

## Expected files

- services/api/src/game_predictor_api/config.py
- services/api/src/game_predictor_api/application/image_symbol_reviews.py
- services/api/tests/test_config.py
- .env.example
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/guides/LOCAL_OPERATION_GUIDE.md
- ai_docs/process/CURRENT_STATE.md

## Verification

Test konfiguracji, Ruff i kontrola ustawień w nowym procesie Python; limit każdego kroku 120 s.

## Outcome

Commit: `v1.7.32` / `7bb63a793ddfa589fecfe994b1e86c1ca2f3d000`.
Staged check/stat/list i post-commit show/stat/status PASS; wcześniejsze zmiany poza commitem.

Zmieniono oba domyślne limity listy, przykład środowiska i dokumentację.
Testy konfiguracji: 41 PASS; Ruff check i format: PASS (3 pliki).
Nowy proces potwierdził list=20000ms, counts=15000ms.
Pierwszy start Pythona z sandboxa zablokowany; testy przeszły po eskalacji.
Bez restartu istniejącej usługi, wdrożenia i optymalizacji SQL; typy i kontrakt
odpowiedzi bez zmian, pełny build pominięty dla zmiany stałych.
Wszystkie kryteria odbioru spełnione. Następny krok: restart API przez operatora.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0714 | gpt-6-sol | low | Lokalna zmiana wartości konfiguracji zgodnie z poleceniem. | Niewymagany; ponowna analiza przy zmianie zakresu. |
