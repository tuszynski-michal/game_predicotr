---
title: Wdrożenie 777 A2 — blokada rozwiązana i odbiór bazy0177
status: active
last_updated: 2026-11-03
---

# Stan zatwierdzonego wdrożenia

## Odbiór po rozwiązaniu blokady — 2026-11-03

Operator po świeżym preview osobno i wyraźnie zatwierdził dokończenie usuwania pustej gry „777 a2 del”, jej konfiguracji i przypisania modelu, a następnie kontynuację migracji, startu i pushu. Blokada jest rozwiązana. Poniższe dalsze sekcje zachowują historię pierwszej próby, nie opisują już bieżącego blokera.

- Ponowny preview:0zdjęć/0plansz/0pól i71pozostałych partycji z1wierszem konfiguracji. Na zgodnym starym kodzie171/v19 zweryfikowano checkpoint18 oraz prefiks manifestu89tabel. Istniejący GamePartitionLifecycleRepository.run_next wykonał oddzielne transakcje do checkpoint89 i finalizacji. Receipt4eb5c1d4-b837-47fc-bcce-0945b4189a55 ma rzeczywisty statusdone. Nie aktualizowano statusu ręcznie. Katalog, lokalizacja i assignment wyłącznie tej gry nie istnieją; shared modele i pliki poza bazą nie były usuwane.
- Migracja Alembic0171→0177_source_replacement_purge:PASS3,52s, recording-capability i provisioning ról:PASS. Pięć pozostałych lokalizacji active, manifestv21. Odczyt po restarcie potwierdza właściwy head i trwały receipt done. Nie uruchomiono purge żadnego zdjęcia użytkownika; purged_sources=0.
- Poprawka konieczna do standardowego rootbuilda: [TASK-1148](../tasks/completed/1148-workspace-react-build-alignment.md),879db371(v543),169983b9(v544). Ujednolicenie typów React i wersji biblioteki, bez aliasów/skipTypecheck. npm11.18.0ci, Admin32,36s, Reviewer21,11s,113testów panelu, mobiletypecheck, Prettier i niezależny Opus5.5/high:PASS. P2 i odmowa npm12 opisane w Outcome.
- Równoległy Selektor1.0.5 przesunął main/origin do0bcabfc4. Wszystkie jego zmiany zachowane; merge516b4172(v545) miał wyłącznie konflikty dokumentów, pełne sekcje archiwum i10ostatnich wpisów zachowano. Własny staging zależności zweryfikowano i odtworzono względem aktualnegoHEAD, nie nadpisano lockaSelektora. Cztery docs checkery/map/diff:PASS. Kolizje numerów wersji historyczne i równoległe pozostają bez przepisywania commitów.
- API8000/Admin3000/Reviewer3001 po uruchomieniu:HTTP200. Nowy kontrakt OpenAPI i readonly GET workspace czytelności rzeczywistej gry777a2:HTTP200. General worker7 i grid-training1 działają; image-selection nadal stopped. Bez ręcznie zleconych jobów, treningu, skanu czy aktywacji.
- Końcowy odczyt po restarcie:166971zdjęć,1500019plansz,22248975pól; checksumy aktywacji identyczne z bazą przed wdrożeniem. Active jobs puste. Świeże PID/creationtime/executable/command/porty i statusy lane zachowano w artifacts/deploy-777a2-20261103/services-final.json oraz workers-final.json; database-final.json i live-verification.json zawierają dowody.
- Drugie okno posiada osobne zatwierdzenie zakresu0178; przejmie usługi dopiero po końcowym pushu i wyraźnym handover tego wdrożenia. Nie włączono jego niewdrożonej migracji do tego zakresu.

Push i sprzątanie zostaną potwierdzone końcowym raportem czatu; ten dokument zapisuje odbiór przed ich wykonaniem. Nie wykonano operatorowego pilota/fit/skanu ani wymiany zdjęć777A2; funkcje są wdrożone, ich użycie wymaga wyboru i weryfikacji przez operatora.

## Historia pierwszej próby

Operator wyraźnie zatwierdził scalenie/push, stop/start usług, migrację0171→0177, dołączenie TASK-1138 i koordynację migracji drugiego okna. Przed osobną zgodą na delete pustej gry operacja była rzeczywistym blokerem; zabezpieczeń nie pominięto i nie zmieniono jej statusu.

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

## Historyczny następny krok przed osobną zgodą

Potrzebna osobna decyzja operatora: dokończyć rozpoczęte usuwanie opisanej pustej gry i jej pozostałej konfiguracji, czy zachować ją i osobno naprawić lifecycle. Po rozwiązaniu blokady ponowić zatwierdzone wdrożenie; nie wykonywać DELETE ani nie fałszować receiptu w ramach samej zgody na migrację. Drugie okno poinformowane; nie prowadzi równoległego wdrożenia.
