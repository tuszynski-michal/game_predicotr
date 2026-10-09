---
title: Minimalistyczne stawki, zapisany układ i wspólny edytor
status: done
last_updated: 2026-10-09
---

# TASK-0942 — Minimalistyczne stawki, zapisany układ i wspólny edytor

## Status

`done`

## Goal

Zmniejszyć stawki i edytor panelu, wykorzystując wspólne wyszukiwanie, wyliczenia i zapisany stan bez regresji innych konsumentów.

## Context

Operator chce minimalnego UI i szybkiego przechodzenia między punktami, maszynami
i stawkami. Cały plan jest zaakceptowany i uruchomiony; koszt oraz manualne audyty
zostały uzgodnione. Nie trzeba rekonstruować historii rozmowy.

## Dependencies / entry conditions

TASK-0940 zakończony z audytem/commitem, kod i testy TASK-0941 gotowe.
Operator 2026-10-09 jawnie pozwolił wykonać kod/testy0942–0943 przed audytem0941.
Audyty i osobne commity pozostają wymagane przed zamknięciem planu/merge.
Bezpośrednio przed startem sprawdzić main pod TASK-0935/0936 i zastosować regułę
integracji planu; nie czekać na nie, jeśli jeszcze nie weszły.

## Recommended execution

gpt-6.1-sol / high. Przed startem odnotować wynik sprawdzenia wspólnych plików i main. Modyfikacja zwykłych konsumentów byłaby regresją. Przy konflikcie semantyki kosztu/snapshot version wstrzymać zależny fragment i skorygować kontrakt wspólnego helpera.
Wymagany niezależny ręczny review claude-fable-5-1 / high przed commitem. Konfiguracja musi
odpowiadać końcowej tabeli planu; niedostępność albo zmiana ryzyka wymagają jawnej
aktualizacji, bez ukrytej zamiany modelu.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md — sekcje TASK-0942 i reguły wspólne.
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DECISION_LOG.md — D-536 i D-533.
- ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md

## Scope

- Sześć małych klikalnych kafelków stawki, zapis-status i symbole20–24px, bez miniChart/przycisków Open.
- Otwieranie zapisanej query/start/range/pins, bez wyboru pierwszego trafienia; stan Save/changes/new/replace/clear według planu.
- Wariant compact jako opcjonalny prop BoardSearchWorkspace, reuse ApproximateWinBalanceChart/approximateWin*.
- Szybkie wiersze z pin metadata, wykres dopiero po rozwinięciu do wyboru0–6pinów, axesPLN/spins/zero.
- Tabela i journal collapsed, pełny wynik on demand; stale replies/CAS/recovery/sessionloss zachowują szkic.

## Out of scope

- Push, merge, deployment, dane/baza operatora i lifecycle API/Admin.
- Nowa kopia wyszukiwarki/kalkulatora, konta/chmura/Redis/Celery i benchmarki.
- Usuwanie katalogu gier, symboli, plansz, globalnych korekt i innych dzienników.
- Taski innych torów oraz niezwiązane wcześniejsze błędy.

## Acceptance criteria

- [x] Karta ma tylko stawkę, zapis-status i potrzebny symbol-preview; cała klikalna, selected wyraźny.
- [x] Stored start z managementSavedSelection odtworzony deterministycznie; brak top-hit autochoose.
- [x] Nowy układ/reset nie czyści slotu; Save changes vs Replace wymaga właściwego CAS i confirm, Clear jawny.
- [x] Spin/Wkład/Netto/Na maszynie zgodne ze wspólnymi helperami; zero i losing dozwolone, unavailable jawne.
- [x] 0–6 pinów i osie widoczne w rozwiniętym wykresie; nie ma nieczytelnych black dot miniCharts.
- [x] Quick preview nie pobiera full result; full tabela/history tylko po rozwinięciu; queue≤2.
- [x] Default ordinary search/share zachowane, optional props i regression testy.
- [x] Zmiana globalnych symboli nadal zapisuje natychmiast, reset szkicu tego nie cofa.

## Technical notes

Obowiązuje produktowa tabela stanów planu i sekcja reużycia/integracji. Nie kopiować wykresu/search/modali ani obliczać wkładu przez sumę spinów. Przy zmiennym koszcie Mumii użyć wspólnej infrastruktury z golden fixtures, nie reinterpretować zamrożonych historycznych payloadów. Stable machine/game/stake scopeKey chroni dirty editor przed zmianą background identity. Wszystkie kafelki compact są button; default poprzednich konsumentów nie zmienia się.

## Expected files

- Istniejące: packages/board-search-ui/src/management/management-cards.tsx, management-game-workspace.tsx, management-result-view.tsx, management-slot-state.ts, management.css.
- Istniejące: packages/board-search-ui/src/board-search-workspace.tsx oraz board-search-approximate-win.tsx i board-search-approximate-win-state.ts — opcjonalny compact i helpery.
- Istniejące: management-data-source.ts / management-journal.tsx — on demand, collapse, recovery.
- Testy interakcji board-search-ui, Admin geometry i Reviewer geometry; fixtures wspólnych wyliczeń.

## Test cases

- Stored start niepierwszego trafienia po reload → ten sam sequence/query/range/pins.
- Reset/new + wyjście/cancel/Save failed → stary zapis pozostaje do Replace success.
- Pin0/przegrany/6/7/unavailable → dokładna granica i wartości; zmienny koszt jeśli zintegrowany.
- History wartości/rules bez zmian po aktualizacji globalnych reguł.
- Default search/share flow → poprzednie controls i zachowanie; tylko compact uproszczony.
- Late responses, revisionconflict, pendinglostresponse i sesjaodmowa → draft zachowany, brak cichego overwrite.

## Verification

Katalog: root oddzielnego worktree. Każdą poniższą skończoną komendę wykonaj
z wymuszonym timeoutem 120s w runnerze; provisioning check:30s. PG wyłącznie
disposable DB, GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 tylko w procesie testowym.
Brak venv/node_modules worktree wymaga izolowanego środowiska; nie buduj dist
ani aplikacji w głównym checkout operatora. Testy poniżej są planowane,
nie zostały jeszcze uruchomione. Najpierw pion, potem lint/typecheck/scoped
format, dopiero regresje/build. Znany build >120s poprzedź komunikatem.

```powershell
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test:geometry --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/board-search-ui
npm run reviewer:management:browser
```

Nowe moduły muszą dostać własne testy razem z kodem. Po zmianach Python uruchom
Ruff i mypy odpowiednich plików z istniejącej konfiguracji; TS: lint/typecheck
zmienionych workspace. PG ownership/provisioning uruchamiaj tylko na bazie
izolowanej. Każde pominięcie/skip i istniejący niezwiązany błąd podaj w Outcome.
Warunek zakończenia: kryteria potwierdzone, wymagany audyt bez otwartych P0/P1,
osobny commit i dokumentacja stanu. Według zgody operatora z2026-10-09
brak audytu nie blokuje kodu/testów0943, ale blokuje done i merge.

## Risks / open questions

Przed startem odnotować wynik sprawdzenia wspólnych plików i main. Modyfikacja zwykłych konsumentów byłaby regresją. Przy konflikcie semantyki kosztu/snapshot version wstrzymać zależny fragment i skorygować kontrakt wspólnego helpera.

## Outcome

### Changed

- Kod i testy TASK-0942 są przygotowane w izolowanym worktree `admin-compact-panel`. Niezależny audyt `claude-fable-5-1 / high`, runda 1, zakończył się rzeczywistym `PASS`: brak P0/P1, pięć P2. Oryginalny raport zachowano bez zmiany werdyktu. Osobny commit i dokumentacja zamknięcia pozostają wymagane przed statusem `done` oraz merge.
- Jedna ograniczona runda poprawek zamyka P2-1–P2-4. Anulowanie zastąpienia używa dedykowanego `BoardSearchSaveCancelled`, pokazywanego jako `role="status"`; szkic pozostaje brudny, zapis nie jest wykonywany, a ponowienie jest dostępne. Nie zmieniono domyślnego mapowania pozostałych błędów ani `api-error.ts`.
- P2-2: disclosure „Pełny zapisany wynik” jest kontrolowany przez aktualny `view`. Po otwarciu i zamknięciu edytora pozostaje rozwinięty przy widocznym wyniku; zbędne zdarzenie rozwinięcia nie zmienia widoku ani nie powtarza pobrania. Zamknięcie disclosure usuwa bieżący widok, zachowując odrębny widok historyczny.
- P2-3: dostępny pin z brakującą metryką pokazuje „—”, a pin poza zakresem nadal „niedostępny”. Brak pinów pokazuje „Brak przypiętych punktów” zamiast pustej tabeli. Nie dodano kalkulatora ani pobierania pełnego wyniku dla szybkich wierszy.
- P2-4: instrukcja zapisu szkicu nie odwołuje się już do nieaktualnej etykiety „Zapisz układ”; obejmuje również „Zapisz zmiany” i „Zastąp układ”. Domyślne opcje zwykłego search/share pozostają zachowane.
- Sprawdzenie integracji: main pozostaje na `3bc6c64b` (`v1.7.271`); TASK-0935/0936 nie zostały zintegrowane. Worktree pozostaje na `0625512d4a37072f1d6d44f3f85ef225e7db1835` (`v1.7.273`, TASK-0940). Nie zmieniono semantyki stałego kosztu ani zamrożonych wyników; wspólne helpery wykresu pozostają źródłem obliczeń.
- Odbiór przeglądarkowy TASK-0943 wykrył nadpisanie limitu320px przez bardziej specyficzny selektor kafelków. Usunięto konflikt, ustawiając `max-width: min(100%, 320px)` dla kafelków panelu, z zachowaniem celów44px i kolumn4/3/2/1. Ponowny odbiór tego przypadku prowadzi TASK-0943.
- Druga ograniczona korekta po obejrzeniu rzeczywistych screenshotów TASK-0943 przywraca pierwotne UX: ołówek i kosz znajdują się w górnym prawym rogu, nazwa ma rezerwę104px, a dolny sztuczny zapas54px został usunięty. Przyciski nagłówka Punkty/Cofnij oraz ikony korzystają ze wspólnej istniejącej grupy stylu i hover panelu. Zachowano minimum100px kafelka, cele44px, limit320px oraz kolumny4/3/2/1. Zmieniono wyłącznie CSS; browser geometrię ponawia TASK-0943.
- Sześć stawek jest w całości klikalnymi przyciskami z `aria-pressed`, statusem zapisu i miniaturami 24px. Usunięto miniwykresy, dodatkowe przyciski kart i szczegóły obciążające zwykły podgląd. Katalog symboli jest współdzielony przez karty i edytor; nieudany odczyt nie pozostaje w trwałym cache, a ponowne otwarcie umożliwia odzyskanie katalogu.
- Wspólne `BoardSearchWorkspace`, `BoardSearchResults` oraz `BoardSearchApproximateWin` otrzymały opcjonalny `compact`, zachowując domyślne zachowanie zwykłego wyszukiwania i share. Etykieta Save jest opcjonalnym portem hosta. Zapisany start, query, zakres i piny są odtwarzane bez ponownego wyszukiwania i wyboru pierwszego trafienia.
- Nowy układ i reset zmieniają wyłącznie szkic. Zapis zmian tego samego startu używa CAS; nowy układ zastępuje zapis dopiero po potwierdzeniu i trwałej odpowiedzi. Anulowanie, odmowa, konflikt rewizji, utrata odpowiedzi i sesji pozostawiają właściwy szkic oraz stary zapis. Jawne Clear pozostaje ograniczone do bieżącego slotu.
- Szybkie wiersze Spin/Wkład/Wygrana netto/Na maszynie używają pin metadata w kredytach. W edytorze te same wiersze korzystają ze wspólnych helperów wykresu. Spin zero ma zera, niedostępne metryki pozostają jawne; nie powstaje drugi kalkulator.
- Wykres jest montowany po rozwinięciu „Wybierz punkty na wykresie” z osiami spiny/PLN i dotychczasową obsługą0–6 pinów. Pełna tabela i dziennik są zwinięte, a dziennik oraz zapisany pełny wynik są pobierane na żądanie. Pełny bieżący wynik może wczytać otwarty edytor, zgodnie z planem.
- Dostosowano testy Admin i Reviewer do zmienionego kontraktu przycisków oraz lazy disclosures. Zachowano asercje immutable history, natychmiastowych globalnych korekt, CAS, dirty draft, identity fence, stale replies i exact UUID recovery.

### Verification results

Wszystkie poniższe skończone kroki miały wymuszony `subprocess.run(timeout=120)`; użyto Node/npm i Python z dostępnego środowiska, bez uruchamiania usług.

- Runda poprawek P2-1–P2-4: `management-cards.test.mjs` PASS,26/26. Regresje obejmują anulowanie jako status bez alertu, zachowanie szkicu i ponowienie, kontrolowany disclosure po powrocie z edytora z jednym pobraniem oraz rozróżnienie brakujących metryk/niedostępnych pinów i pusty stan.
- Runda poprawek: shared `typecheck` i `lint` PASS; scoped ESLint testu Admin PASS; końcowy Prettier `--check` pięciu zmienionych plików PASS. Format testów wymagał uprawnienia zapisu do autoryzowanego worktree poza domyślnymi writable roots. Końcową korektę formatowania wykonano przez patch i potwierdzono odczytem Prettier.
- Nowa regresja shared saved-selection początkowo miała błąd pomocniczy `text is not defined` (12/13); poprawiono go do `document.body.textContent`. Pełny wynik odebrany przez leada wyniósł55/56: nowa regresja błędnie objęła istniejący alert fixture niedostępnej zapisanej planszy. Asercja porównująca cały element DOM z null próbowała wypisać rozbudowany obiekt i zakończyła się `RangeError: Array buffer allocation failed`. Naprawiono zakres asercji do banera błędu zapisu oraz porównania boolean, zachowując wymaganie statusu anulowania, brudnego szkicu i ponowienia. Implementacja anulowania nie wymagała zmian. Wyłącznie `--test-name-pattern "host save cancellation"` po poprawce: PASS,1/1,0,51s test/2,85s runner, wymuszony timeout45. Pierwszy izolowany przebieg osiągnął timeout45; odczyt procesów potwierdził brak pozostawionej własnej instancji przed ponowieniem. Nie powtarzano pełnej suite.
- P2-5 pełnego Reviewer `test:geometry` oraz końcowy browser acceptance po zamrożeniu zmian0941/0942 wykonuje lead raz. Nie uruchamiano ich równolegle ani nie powtarzano audytu. Scoped `git diff --check` w procesie wykonawcy nie uzyskał dostępu do cwd worktree; końcową kontrolę przejmuje lead.

- `npm run test:interactions --workspace @game-predictor/board-search-ui`: PASS,55/55. Obejmuje zwykłe search/share/replay/correction oraz nowe compact restore/pin rows/disclosure/result buttons.
- `node node_modules/tsx/dist/cli.mjs --tsconfig packages/board-search-ui/tsconfig.json --test packages/board-search-ui/test-interactions/board-search-saved-selection.test.mjs`: PASS,12/12 po uściśleniu oczekiwanych metryk przegranego spinu według istniejącego helpera (wkład60, netto−60, na maszynie0).
- `node node_modules/tsx/dist/cli.mjs --tsconfig apps/admin/tsconfig.json --test apps/admin/test-interactions/management-cards.test.mjs`: PASS,22/22. Nowe przypadki obejmują katalog raz na grę, odzyskanie katalogu po błędzie, brak pełnego wyniku/journalu przed rozwinięciem oraz reset/anulowany lub odrzucony Replace/potwierdzony CAS.
- `npm run typecheck --workspace @game-predictor/board-search-ui`: PASS.
- `npm run lint --workspace @game-predictor/board-search-ui`: PASS. Scoped ESLint zmienionych testów Admin i Reviewer: PASS z katalogów ich konfiguracji. Pierwsze wywołanie scoped Admin ESLint z root nie znalazło konfiguracji; poprawiono katalog uruchomienia bez zmiany konfiguracji repozytorium.
- Scoped Prettier `--write` oraz końcowy `--check`12 zmienionych plików TS/TSX/CSS/MJS: PASS.
- `npm run test:geometry --workspace @game-predictor/admin`: PASS,175/175.
- `npm run test:geometry --workspace @game-predictor/reviewer`: pierwsze uruchomienie ujawniło5 testów panelu opartych na starych selektorach kart i eager journal. Pozostałe testy były zielone. Po dostosowaniu kontraktu ponowiono wyłącznie zmieniony pion: `node node_modules/tsx/dist/cli.mjs --tsconfig apps/reviewer/tsconfig.json --test apps/reviewer/test-interactions/management-panel.test.mjs`: PASS,14/14.
- Scoped `git diff --check`: PASS. Istniejące ostrzeżenia React o powtarzanych kluczach w niezwiązanych fixtures zwykłego search/Admin nie powodują niepowodzeń; nie rozszerzano zakresu.

### Not completed at initial handoff (historical)

- Osobny commit i formalne przeniesienie taska do completed. Audyt jest `PASS`, nie ma otwartych P0/P1; P2-1–P2-4 zostały poprawione, a P2-5 wymaga końcowego wyniku pełnej suite Reviewer od leada. Nie oznaczono taska jako done.
- Browser acceptance `npm run reviewer:management:browser`, fizyczny odbiór1440/1920/390px i końcowy odbiór całego przepływu należą do TASK-0943. Nie powtarzano całej suite Reviewer po zielonym ponownym sprawdzeniu zmienionego pionu.
- Nie zmieniano backendu/API/OpenAPI/bazy, nie powtarzano59 zaliczonych testów TASK-0940, nie uruchamiano usług API/Admin, migracji produkcyjnych, destrukcyjnych operacji danych, benchmarków, push ani merge. Ruff/mypy nie dotyczą tego taska, ponieważ nie zmieniono Python.

### Documentation updates

- Task pozostaje `in_progress` z powyższym rozdzieleniem ukończonego kodu/testów oraz oczekujących audytu/commita. Dowody i dokładna lista plików przekazane właścicielowi CURRENT_STATE oraz stage snapshot. Wymagania, instrukcję operatorską i odbiór całego planu aktualizuje TASK-0943.
- Pliki TASK-0942: `packages/board-search-ui/src/board-search-workspace.tsx`, `board-search-results.tsx`, `board-search-approximate-win.tsx`; `packages/board-search-ui/src/management/management-cards.tsx`, `management-data-source.ts`, `management-game-workspace.tsx`, `management-journal.tsx`, `management-result-view.tsx`, `management.css`; `packages/board-search-ui/test-interactions/board-search-saved-selection.test.mjs`; `apps/admin/test-interactions/management-cards.test.mjs`; `apps/reviewer/test-interactions/management-panel.test.mjs`; ten task. Zmiany TASK-0941/0943 w worktree pozostają poza przypisanym zakresem.

### Recommended next task

- TASK-0943: zintegrowany browser acceptance i dokumentacja. Następnie odroczone niezależne audyty oraz osobne commity TASK-0941–0943 w zatwierdzonej kolejności; brak audytu nadal blokuje done i merge.


### Końcowe zamknięcie (2026-10-09)

- Claude `claude-fable-5-1 / high`: PASS, brak P0/P1. P2-1–P2-4 poprawione;
  oryginalny raport zachowano. P2-5 zamknięte wynikiem Reviewer geometry41/41 PASS.
- Shared suite55/56 ujawniła zbyt szeroką nową asercję. Zawężono ją do błędu
  zapisu, po czym pojedyncza regresja1/1 przeszła. Zmiana dotyczyła wyłącznie testu;
  nie ponawiano całej suite. Admin cards26/26 i management/cards39/39,
  typecheck/lint/format PASS. Końcowy browser10/10 i oba buildy PASS.
- Wersja commita: v1.7.275. Pełny hash zapisujemy po commicie z dokumentacją kolejnego taska.
- Main po rozpoczęciu implementacji przesunął się do1b97ad65/v1.7.285 i zawiera
  TASK-0935/0936. Przed integracją trzeba rozwiązać konflikty wspólnych komponentów
  i sprawdzić koszt per pozycja. Osobna gałąź nie została scalona.

### Commit

v1.7.275 — af1218b0685b5d472f2e7eb4842934b205f2ec26. Osobny commit potwierdzony przez git log/show; zapis dołączany z dokumentacją kolejnego taska.
