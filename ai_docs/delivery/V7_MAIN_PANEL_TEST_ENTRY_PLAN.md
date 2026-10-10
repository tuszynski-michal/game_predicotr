---
title: Working V7 test entry from the main Admin
status: accepted
last_updated: 2026-10-07
---

# Stan i cel

Operator chce testować poprawiony półautomat z zakładki na Admin3000.
Read-only HTTP potwierdza: główny API8000 ma configuration-v1 i start blocked;
zatwierdzony pilot API8020/Admin3020 ma configuration-v2, startEnabled=true,
operator_selected_local_folder i działa na branchu z pełnym pokryciem draftów.
Main HEAD v1.7.248. Nie przenosimy eksperymentalnej aktywacji do głównej bazy.

## TASK-0919 — wejście do działającego półautomatu

1. W main Admin dodać jawny link do odrębnego panelu wyborów, kiedy starszy
   lokalny V7 jest blocked, a globalna flaga selekcji nadal enabled. To nawigacja
   do istniejącego zatwierdzonego runtime'u, nie obejście jego bramek ani nowy API.
   Bez kopiowania run ID, game ID lub zapisów pomiędzy bazami.
2. Nowa czysta funkcja `localV7PilotHref` przyjmuje origin głównego panelu oraz
   opcjonalny NEXT_PUBLIC_V7_SELECTION_PILOT_ORIGIN. Domyślny lokalny port3020
   odpowiada istniejącej instalacji pilota; konfiguracja może podać inny HTTP
   loopback origin. Remote origin, credentials, ścieżka/query/hash i ten sam
   origin są odrzucane. Pusty jawny override wyłącza link. SSR nie odczytuje window;
   `useSyncExternalStore` udostępnia origin dokumentu dopiero po hydratacji.
3. Pokazać instrukcję wyboru źródła, miejsca zapisu i numerów. Gdy nie ma
   historycznego runu, ukryć niedziałający stary formularz. Existing run/review,
   active V7, flag-off, crop workflow oraz normalne API zachowują zachowanie.
4. Przez prawdziwy browser wejść z URL użytkownika na3000, kliknąć nowy link,
   potwierdzić aktywny source/output picker i istniejące zapisane wybory na3020.
   Nie uruchamiać joba ani nie zatwierdzać zdjęć za operatora. Gdy usługi nie
   działają, podać komendy użytkownikowi; agent ich nie uruchamia/restartuje.

## Weryfikacja i granice

Planned tests: local-only routing, override/self/credentials/remote rejection,
blocked main entry/hiding old setup, enabled and disabled regressions, navigation
no source/run submit; focused selection tests, ESLint/Prettier/Admin types.
Live entry -> pilot picker/review bez joba i nowych decyzji. Potwierdzić zmiany
w nowym procesie testowym; no API/Admin lifecycle, migration, data writes,
release-gate weakening, branch merge, push, model activation or monitor.
Pełne pokrycie i output picker są istniejącymi zmianami pilota (TASK-0886–0888);
to zadanie udostępnia ich test z głównego panelu, nie wdraża ich do API8000.
Oszacowane numery pozostają do korekty; błędy źródłowych plików/zapisu są jawne.

## Odbiór wykonania

TASK-0919: 19/19 focused tests, 6/6 rendered regressions, Prettier/ESLint/Admin
types PASS. Browser potwierdził URL użytkownika3000 ->3020, enabled source/output
picker, saved review i oszacowany JPEG. Odczyt nazw istniejących JPEG-ów daje
3135/3135 oraz 3190/3190 grup bez braków; nie mierzy poprawności OCR. Main gate
i obie bazy zachowane. Bez lifecycle, job start/decisions, model activation,
merge, pełnego builda, monitorowania lub wdrożenia. Evidence: artifacts/
v7-main-panel-entry-20261007/. Commit v1.7.249 zapisany w Outcome i CURRENT_STATE.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0919 | gpt-6.1-sol | high | Ograniczona zmiana nawigacji wymaga utrzymania izolacji runów i prawdziwego odbioru UI. Konfiguracja dostępna w bieżącym środowisku. | Własny review; bez delegowania. |
