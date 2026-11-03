---
title: Wdrożenie 777 A2 — blokada istniejącego usuwania innej gry
status: active
last_updated: 2026-11-03
---

# Stan zatwierdzonego wdrożenia

Operator wyraźnie zatwierdził scalenie/push, stop/start usług, migrację0171→0177, dołączenie TASK-1138 i koordynację migracji drugiego okna. Nie zatwierdził dokończenia osobnej operacji usuwania innej gry. Ta operacja jest rzeczywistym blokerem; zabezpieczeń nie pominięto i nie zmieniono jej statusu.

## Wykonane przygotowanie

- Merge main fa38a3cd do gałęzi roboczej: c58bd63e (v1.7.538); tylko konflikty dokumentów, zachowane pełne historie i wymagane okna. Docs4/map oraz78testów worker PASS.
- Dołączono oba zatwierdzone commity TASK-1138,961b6b47 i3562ab1a:87f0870e(v1.7.539).22testy panelu po integracji PASS. Pierwsza próba bez tsconfig nie rozwiązała aliasu @/api; poprawne wywołanie repozytoryjne tsx --tsconfig apps/admin/tsconfig.json przeszło.
- Naprawiono rzeczywisty rozjazd kontroli startu0174/0177 w TASK-1146:5660c2b0 i60f50c64(v1.7.540/541).23testy, lint, produkcyjny scoped mypy, docs/map i rzeczywisty Opus5.5/high PASS.
- Drugie okno zapisało niewdrożoną migrację0178_grid_correction_growth (7881711b); kolizja0172 usunięta. Jego pełne zmiany1139/1140/1145 nie należą do tego wdrożenia i nie zostały tu scalone.
- Historyczne kolizje numerów wersji oraz dwie kotwice D-578 pozostają jawne zgodnie z D-579; nie przepisano historii.

## Próba migracji i bloker

Po kontrolowanym zatrzymaniu API/Admina/Reviewera i dwóch działających workerów wykonano lokalny fast-forward main do60f50c649ae9f3d2f3f7bf268282b627aad9fbc1. Przygotowanie recording-capability zakończyło się poprawnie. Migracja0172 zatrzymała się na GAME_STORAGE_LIFECYCLE_IN_PROGRESS. Dodanie wartości enum job_type.symbol_readability nastąpiło w autocommit przed guardem; nie utworzono żadnego joba tego typu. Transakcja właściwej migracji została wycofana; Alembic pozostał0171_grid_correction_learning, manifesty sześciu lokalizacji pozostająv19.

Blokująca operacja:

- id4eb5c1d4-b837-47fc-bcce-0945b4189a55;
- gra f0ea7306-24fd-4117-b515-37fc181e04a0, code777v2, nazwa „777 a2 del”;
- operation_kind=delete, status=running, manifestv19, checkpoint18;
- utworzona i ostatnio aktualizowana2026-10-20; lokalizacja ma statusdeleting.

Readonly preview pozostałego zakresu:71partycji, łącznie1wiersz (image_geometry_rollout_states). source_images, recognized_boards, image_symbol_review_cells, modele i kohorty tej gry mają0wierszy. Publiczne symbols/rules_versions/jobs też0. Pozostają wpis katalogu gry, lokalizacja oraz1przypisanie game_grid_model_assignments (FK CASCADE dla tej gry). Nie oznacza to zgody na skasowanie tych struktur ani na ustawienie done. Nie sprawdzano ani nie kasowano osieroconych plików poza bazą.

## Bezpieczne przywrócenie

Nie resetowano ani nie usuwano commitów. Lokalny main zachowuje60f50c64; origin/main lokalnie nadal fa38a3cdedf4aa9f85cf62df0512330788f8dd6c. Push i sprzątanie worktree wstrzymane. Główny katalog przełączono z powrotem na poprzedni codex/grid-learning-refresh,3562ab1a868ae26cb2c36bf453197c1790561015, zgodny z bazą0171.

API8000, Admin3000 i Reviewer3001 po przywróceniu zwracająHTTP200. General worker działa z7wątkami; grid-training z1; image-selection pozostaje wyłączony jak przed operacją. Pierwsza próba stopu workera miała za krótki limit10s dla zapisu statusu; po sprawdzeniu procesów dokończono stop z30s. Działające usługi mają zapisane PID/logi; bez nowych zadań, treningu czy aktywacji modeli.

Kontrola przed/po:166971zdjęć,1500019plansz,22248975pól; sumy aktywacji symboli i profili geometrii identyczne. Active jobs puste. Żadne zdjęcie użytkownika nie zostało przez to wdrożenie usunięte.

Dowody operacyjne poza git: D:/game_predicotr/artifacts/deploy-777a2-20261103/ (services-before/after, workers-before, database-before/restored, lifecycle-blocker, old-game-delete-preview i logi). Podgląd wykonywano wyłącznie read-only.

## Następny krok

Potrzebna osobna decyzja operatora: dokończyć rozpoczęte usuwanie opisanej pustej gry i jej pozostałej konfiguracji, czy zachować ją i osobno naprawić lifecycle. Po rozwiązaniu blokady ponowić zatwierdzone wdrożenie; nie wykonywać DELETE ani nie fałszować receiptu w ramach samej zgody na migrację. Drugie okno poinformowane; nie prowadzi równoległego wdrożenia.
