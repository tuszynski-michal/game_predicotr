# TASK-1153 — Propozycje modelu w korekcie i pełny kadr

## Status

`done`

## Goal

Operator uruchamia istniejące przygotowanie propozycji, widzi je bezpośrednio w Korekcie cięcia siatki i sam przyjmuje/edytuje, a edytor i HTML pozwalają zobaczyć otoczenie oraz całe zdjęcie.

## Context and authorization

Operator 2026-11-03 potwierdził problem w obu widokach i jawnie zatwierdził cały zakres, koszt 45–90 min i Opus 5.5. Aktualny main c6f9597a, model 3ed60010 jako default i Mumie A2 revision 2. Istniejący reinference dla grid_issue produkuje proposal_ready, nie zapisuje zaakceptowanej geometrii. GridGeometryProposals jest dziś wyłącznie w operational-review-workspace; główna correction queue go nie montuje. Edytor jawnie używa35% kadru, HTML 8%; model ma odrębny margin15%,320x192 i detektor całego zdjęcia768.

## Recommended execution

gpt-6-astra/high; jeden claude-opus-5-5/high przed commitem. Bez delegacji wykonania.

## Relevant docs

- AGENTS.md; process/DEFINITION_OF_DONE.md; delivery/GRID_REVIEW_PROPOSALS_VIEWPORT_20261103.md.
- requirements/ADMIN_APP.md: Ponowne rozpoznanie wybranego zakresu V3 i korekta geometrii.
- architecture/API_CONTRACT.md: grid-reinference i grid-geometry-proposals.
- requirements/VISION_LAB.md i architecture/VISION_LAB.md: ludzkie etykiety, ochrona ról, obecne modele.
- architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md.

## Scope

1. Wyraźny skrót w Adminie do istniejącego narzędzia ponownego rozpoznania; jawne prepare/freeze/start i ograniczenia pilot/broader zachowane. Wejście/otwarcie niczego nie rozpoczyna. Opis grid_issue mówi o propozycjach do ręcznej oceny.
2. Wrapper przy aktualnej reported planszy w Korekcie odczytuje tę samą operational review i montuje istniejące GridGeometryProposals. Przyjmij/Edytuj/Odrzuć używają obecnego API/CAS/UUIDreceiptów. Zmiana planszy/rewizji odrzuca spóźniony odczyt, błędy mają retry; żadne POST na mount. Po decyzji odczytać kolejkę na nowo; zapisane ręczne etykiety i podział danych bez zmian. Starsi klienci bez opcjonalnych metod zachowują działanie ręcznej korekty.
3. W edytorze kolejki i edytorze propozycji opcjonalne sterowanie kadrem: szerszy kontekst70% oraz całe zdjęcie obejmujące również wszystkie punkty. Zmiana/centrowanie/przeciąganie zachowują wybrany tryb i nie zmieniają punktów/flags/draft. Inni konsumenci wspólnego edytora domyślnie zachowują35%.
4. Trwały renderer porównania HTML na bazie istniejącego plikowego raportu: szerszy kadr i całe zdjęcie, przełączanie bez zmiany danych, widoczne wszystkie24 punkty i oryginał. Przebudować aktualny raport150 plansz/101 zdjęć na zapisanych checksum-bound wynikach, bez kolejnego inference lub DBwrites.

## Out of scope

Zmiana detektora, marginu/canvas/wejścia modelu, trening, autoakceptacja, przenoszenie kontroli do TRAIN, migracje/API, automatyczne uruchomienie realnego batcha po otwarciu strony. Merge/push i restarty wymagają końcowej zgody operatora.

## Expected files

Reviewer: board-geometry-correction-workspace.tsx, grid-geometry-proposals.tsx, deferred-board-cell-geometry-editor.tsx, operational-review-state.ts; nowy correction-grid-proposals.tsx. Admin: grid-model-workspace.tsx oraz opis grid-reinference-preview.tsx. Nowe scripts/render_grid_correction_comparison.py i scripts/templates/grid-correction-comparison.html, adaptujące dotychczasowy artifact renderer. Odpowiednie testy istniejących ścieżek i nowej integracji, docs/map/task/audyt.

## Acceptance criteria

- [x] Propozycje w korekcie bez POST na otwarciu; accept/edit/reject mają ten sam istniejący workflow; konflikty, retry i spóźnione odpowiedzi nie przechodzą na inną planszę.
- [x] Nowy skrót nie uruchamia treningu/rozpoznania samodzielnie; pełny obecny workflow i pilot/broader zachowane.
- [x] Szerszy i pełny kadr pokazują punkty i otoczenie w obu widokach; zmiana kadru nie zmienia geometrii; starsze konsumenty mają regresję domyślnego 35%.
- [x] Renderer HTML nie myli zmian z trafnością; źródła/dane/metryki/provenance zachowane, aktualny raport przebudowany i statycznie sprawdzony.
- [x] Właściwe testy, lint/typecheck/build Reviewer i Admin, docs/map, Opus bez P0/P1, task-close i osobny commit/hash.

## Verification

Testy geometrii i interakcji Reviewer przez tsx; regresje grid-geometry-proposals i board correction. Testy Admin workflow bez automatycznego POST. Statyczne testy rendererHTML/paginacji/filtrów/trybów/topologii/assetów. Scope lint/types obu aplikacji i produkcyjne buildy po nich. Każda komenda ma timeout≤120s, build wyjątek po uprzedzeniu. Nie uruchamiać usług z worktree.

## Risks / open questions

Dostępne istniejące endpointy i model odpowiedzi mają być wystarczające; rozszerzenie API byłoby zmianą zakresu i wymaga jawnej informacji przed kodowaniem. Scope przygotowania dotyczy grid_issue/deferred zgodnie istniejącym narzędziem; nie omijać ograniczeń większych operacji. HTML nie da się otworzyć przez browsertool(file policy); bez obejścia, zweryfikować statycznie i przekazać plik.

## Focused review po jednej rundzie poprawek

Runda 2 audytu powinna sprawdzić wyłącznie zamknięcie P1-1/P2-1/2/3 z
ai_docs/quality/TASK-1153_AUDIT_ROUND1.md i dowody w TASK-1153_VERIFICATION.md.
P1 zmienia również runtime: zamiast wywołania opcjonalnego loadera bez kontroli
jest jawny błąd ładowania modułu. Brak kolejnej rundy automatycznych poprawek,
gdyby pozostało P0/P1. Pozostałe części miały pozytywną ocenę statyczną rundy 1.

## Outcome

Commit: v1.7.556 (hash dopisuje kolejny commit).

### Changed

Zaimplementowano pełny zakres. Szczegóły i granice dowodu: ai_docs/quality/TASK-1153_VERIFICATION.md. Bez zmiany API, migracji, wejścia modelu, treningu i danych operatora.

### Verification results

Reviewer 59/59, Admin 16/16, renderer 3/3; scoped ESLint/tsc, produkcyjne buildy obu aplikacji, Prettier/Ruff PASS. Raport 150/101 ma oba kadry i identyczny hash danych. docs/map przed audytem i przy zamknięciu; Opus 5.5/high runda1 REVISE; P1-1/P2-1/2/3 poprawione w jednej rundzie, strict mypy dwóch plików PASS. Focused runda 2 Opus PASS, bez P0/P1; raport ai_docs/quality/TASK-1153_AUDIT_claude-opus-5-5.md. P2-4 (świeżość logów) zamknięto końcowymi logami final-reviewer-tests/lint, final-admin-lint, final-ruff oraz kontrolami docs/map przy zamknięciu. Weryfikacja szczegółowa zawiera zamknięcie każdej uwagi. Logi D:/game_predicotr/artifacts/task1153/.

### Not completed

Wdrożenie i rzeczywisty reprocessing operatora poza bieżącą zgodą implementacji.
