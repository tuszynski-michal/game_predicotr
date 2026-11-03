# TASK-1153 — Weryfikacja propozycji i kadru

## Wynik implementacji

- Admin ma widoczny skrót do istniejącego narzędzia ponownego rozpoznania. Otwiera disclosure i nie wykonuje POST; pilot/szeroki zakres, zamrożenie, start i historia zachowane.
- Główna kolejka Korekty montuje istniejące propozycje dla zgłoszonej planszy. Wrapper kontroluje grę, import, identyfikator, SHA źródła i obie rewizje; ignoruje spóźnione odpowiedzi. Retry jest odczytem. Starsi klienci bez metod propozycji zachowują ręczny workflow.
- Przyjęcie/edycja używają dotychczasowych CAS/receiptów i human approval. Odrzucenie pozostawia zgłoszenie otwarte. W korekcie każda decyzja odczytuje kolejkę ponownie; opcjonalny callback odrzucenia zachowuje domyślne zachowanie innych konsumentów. Modal edycji wyłącza skróty edytora w tle.
- Opcjonalny kadr70% i pełne zdjęcie działają w głównej korekcie i edycji propozycji. Centrowanie, drag release oraz zmiana kwalifikacji zachowują tryb. Domyślny wspólny edytor pozostaje35%. Punkty/szkic nie zmieniają się przy zmianie kadru.
- Trwały renderer CLI i szablon HTML zastępują zależność od jednorazowego kodu w artifacts. Sprawdza przypięte modele i SHA; status zastosowania pochodzi wyłącznie z pasujących ukończonych receiptów. Nie uruchamia inferencji i nie zapisuje danych domenowych.

## Testy i kontrole

- Reviewer:59/59 PASS — board-geometry-correction, grid-geometry-proposals, deferred-geometry, operational-review-state. Obejmują legacy35%, brak POST na mount, retry/spóźnione odpowiedzi, utratę odpowiedzi i ponowienie z tym samym UUID, accept/edit/reject, walidację edytowanej geometrii przez rzeczywisty backend, zachowanie punktów/kadru i kwalifikacji.
- Admin:16/16 PASS — grid-model-workspace, w tym otwarcie skrótu bez mutacji i zachowanie starego procesu.
- Renderer:3/3 unittest PASS — brak dowodu zastosowania, kompletne/popsute receipty, rozbieżne modele/SHA, zachowanie geometrii oraz Node VM test obu kadrów/topologii/filtrów.
- Scoped ESLint obu aplikacji PASS; tsc obu aplikacji PASS. Produkcyjne buildy Reviewer i Admin PASS (z pełnym TypeScript i generowaniem stron). Pierwszy Admin build zatrzymał Windows EPERM przy mkdir; ponowienie z właściwym dostępem PASS. Istniejące ostrzeżenie Next o dwóch lockfile w worktree pozostaje poza zakresem.
- Prettier zmienionych TS/TSX/MJS/CSS PASS; Ruff format/check nowych skryptów PASS.
- Regeneracja CODE_MAP/CODE_MAP_SYMBOLS; docs:check i code-map:check przed audytem, ponownie przy zamknięciu.
- Logi: D:/game_predicotr/artifacts/task1153/. Testy Python używają TEMP/TMP w tym katalogu z powodu ograniczeń domyślnego katalogu tymczasowego środowiska wykonania. Nie zmieniono konfiguracji projektu.

## Rzeczywisty zapisany raport

D:/game_predicotr/artifacts/grid-applied-comparison-20261103/comparison.html i index.html przebudowane na150planszach/101zdjęciach z zapisanych wyników. Node VM PASS: pełny kadr obejmuje źródło i punkty, również skrajne poza źródłem; zmiana kadru nie zmienia danych, działają paginacja/wyszukiwanie/filtr/linie, topologia i ścieżki obrazów.

`comparison-data.json` jest identyczny bajtowo przed i po; SHA256 `73a56c15f9374510b1d5899b2c1fc4fa3c961cce8436f6e932b4f0df9b677960`. Zachowana kopia comparison-before-viewport.html. Bez nowej inferencji, treningu, zmiany modelu ani zapisu geometrii. Raport nie deklaruje trafności nieopisanych plansz. Status zastosowania jest historycznym snapshotem receiptów.

## Granice weryfikacji i operacje

Brak migracji/zmian API/bazy lub polityki TRAIN/holdout. Nie uruchamiano realnego batcha ponownego rozpoznania ani usług z worktree. Bez testu wizualnego gotowego HTML przez browsertool: file protocol jest zabroniony, nie stosowano obejścia. Interakcje sprawdzono JSDOM/NodeVM oraz buildami. Live przegląd nowego UI wymaga wdrożenia po osobnej zgodzie.

Wejście modelu pozostaje odrębne: detektor analizuje całe zdjęcie (long_side768), a sieć siatki korzysta z rektyfikowanego320x192 z margin0.15. Nowe przyciski kadru nie zmieniają tego wejścia. Niedokładny quad detektora wymagałby osobnego eksperymentu; ten task nie twierdzi, że poprawił sieć.

## Audyt i odbiór

Opus5.5/high runda1: REVISE (P1-1: brak mypy/adnotacji nowych testów; P2-1/2/3: uruchamianie testów i UX). Poprawki jednej rundy wykonane:

- P1-1: jawne adnotacje testów i kontrolowany błąd ładowania renderera przy braku spec/loadera; strict mypy obu nowych plików PASS (`python-types.log`). To zmienia obsługę błędu wskazaną w P1 i uzasadnia ograniczoną rundę2 według claude-audit.
- P2-1: jawne komendy unittest oraz mypy w VISION_LAB.md; domyślny szeroki test serwisów nie zmieniony.
- P2-2: trwałe komunikaty przyjęcia/odrzucenia; odrzucenie odczytuje bieżący kursor i zachowuje historię. Nowy test integracyjny po pominięciu planszy PASS.
- P2-3: osobny błąd API i niezgodność tożsamości; jawne „Odśwież kolejkę” odczytuje aktualną wersję. Nowy test pierwszej planszy i błąd API PASS.
- Po poprawkach59/59 Reviewer i3/3 unittest PASS, scoped ESLint/Ruff PASS; ponowny build Reviewera PASS (pełny TypeScript i7/7stron); docs:check/code-map:check PASS. Także Reviewer wymagał ponowienia builda z właściwym dostępem do .next po EPERM.

Pierwszy raport zachowany jako TASK-1153_AUDIT_ROUND1.md. Runda2 to focused review zamknięcia wymienionych uwag, bez ponownego audytu niezmienionych części i bez następnej pętli poprawek. Merge/push/restart Admina i Reviewera wymagają końcowej akceptacji operatora. API i workery nie wymagają zmian.


### Końcowy odbiór po rundzie 2

Opus 5.5/high: PASS, brak otwartych P0/P1. Raport rundy 2:
TASK-1153_AUDIT_claude-opus-5-5.md; oryginalna runda 1 pozostaje zachowana.
P2-4 zamknięte kontrolami na ostatecznych plikach: final-reviewer-tests.log
(59/59), final-reviewer-lint.log, final-admin-lint.log i final-ruff.log (PASS).
Świeże final-docs-check.log i final-code-map-check.log są zapisywane przez
procedurę task-close. Ostateczne SHA kodu są w final-source-hashes.json.
Nie zmieniono kodu po tych testach; dalsze zmiany obejmują wyłącznie zamknięcie
taska i zapis hasha commita. Bez trzeciej rundy audytu.

Kryteria DoD: propozycje/read-only/CAS i błędy odczytu — testy interakcji;
kadr i zgodność starszych konsumentów — testy widoku/geometrii; HTML — unittest
oraz rzeczywisty snapshot z niezmienionym SHA; typy/lint/build — PASS;
dokumentacja i mapy — kontrole przy zamknięciu. Nie przeprowadzono live UI
przed wdrożeniem, rzeczywistego reprocessingu ani nowego treningu.
