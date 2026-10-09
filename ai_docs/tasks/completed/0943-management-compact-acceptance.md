---
title: Odbiór kompaktowego panelu i instrukcja operatorska
status: done
last_updated: 2026-10-09
---

# TASK-0943 — Odbiór kompaktowego panelu i instrukcja operatorska

## Status

`done`

## Goal

Potwierdzić cały przepływ na ograniczonych fixture'ach i pozostawić kompletną dokumentację wdrożenia/odtworzenia.

## Context

Operator chce minimalnego UI i szybkiego przechodzenia między punktami, maszynami
i stawkami. Cały plan jest zaakceptowany i uruchomiony; koszt oraz manualne audyty
zostały uzgodnione. Nie trzeba rekonstruować historii rozmowy.

## Dependencies / entry conditions

TASK-0940 zakończony, kod/testy0941–0942 przygotowane; D-536 i aktualne API/UI
udokumentowane. Zgoda operatora z2026-10-09 pozwala przygotować kod/testy0943
przed odroczonymi audytami i commitami0941–0942. Cały plan nadal wymaga tych
audytów przed done i merge. Bez zgody na rollout danych/usług operatora.

## Recommended execution

gpt-6-sol / medium. Wzrokowy odbiór operatora i migracja jego danych wymagają odrębnego czasu/zgody. Żadnych benchmarków ani testów na jego bazie. Niezwiązany wcześniejszy błąd opisać poza taskiem, nie rozszerzać zakresu.
Wymagany niezależny ręczny review claude-opus-5-5 / medium przed commitem. Konfiguracja musi
odpowiadać końcowej tabeli planu; niedostępność albo zmiana ryzyka wymagają jawnej
aktualizacji, bez ukrytej zamiany modelu.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md — sekcje TASK-0943 i reguły wspólne.
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DECISION_LOG.md — D-536 i D-533.
- ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md

## Scope

- Finite browser fixture:40points, do40machinespoint, cases1/4tiles, gameIds200; desktop1440/1920 i390px.
- Zintegrowane Home→point→machine→stake→search→save→reset→replace→delete z dirty/recovery/conflict/session guards.
- Restart read w nowym procesie i application-role disposable PG; backup/restore tylko osobna testDB.
- Spójna dokumentacja requirements/architecture/operations/traceability/D-533/D-536/README/CURRENT_STATE.
- Ograniczony końcowy build/regression i konkretne pozostałe rollout gates operatora.

## Out of scope

- Push, merge, deployment, dane/baza operatora i lifecycle API/Admin.
- Nowa kopia wyszukiwarki/kalkulatora, konta/chmura/Redis/Celery i benchmarki.
- Usuwanie katalogu gier, symboli, plansz, globalnych korekt i innych dzienników.
- Taski innych torów oraz niezwiązane wcześniejsze błędy.

## Acceptance criteria

- [x] Wszystkie kryteria planu mają dowód testu albo jawny niewykonany odbiór operatora; brak fikcyjnego PASS.
- [x] Desktop i telefon bez horizontaloverflow, max320 i touch44; niezależne UI Admin/Reviewer zgodne.
- [x] Fresh process trwałe receipty/saves/history i denied revoked session; rollback całej transakcji.
- [x] Read-only migration preview z count legacy fallback oraz provisioning check i jedna głowa w torze panelu.
- [x] Guide opisuje backup binarny i restore do osobnej DB, preview/confirm/migrację/manualrestart; nie obiecuje dataprollback przez downgrade.
- [x] Requirements/architecture nie zawierają sprzecznego zakazu hard delete tego modułu ani archive-only workflow.
- [x] Audyt Claude, Outcome i osobny commit kończą zlecony plan; brak push/merge/deployment.

## Technical notes

Polecenie operatora z 2026-10-09 obejmuje końcowy audyt całej funkcjonalności
z Claude Code. Operator sprostował, że „Gy” i „RooPaudit” były błędem
transkrypcji Aqua Voice, a nie dodatkowymi audytorami. Końcowy brief ma reużyć wcześniejsze raporty
i wyniki, oceniać pełny przepływ oraz wygodę kompaktowego UI. Jedna runda uwag,
jedna ograniczona runda poprawek, testy tylko zmienionego zachowania; żadnej
automatycznej pętli audytów. Zasady P0/P1 i wymagany model Claude pozostają
zgodne z zaakceptowanym planem.

Regresje wcześniejszych tasków nie są ponawiane bez potrzeby: końcowy test obejmuje realny zintegrowany przepływ i nowe rozmiary. Istniejący browser runner uruchamia kontrolowaną headless przeglądarkę i statyczną fixture, nie usługi operatora. Fizyczne urządzenie, live tunnel/ingress i reboot operatora pozostają gates. Nie uznawać mock za wynik realnej produkcji. Dokładny nextversion z gitlog, nie z nazwy branch.

## Expected files

- Istniejące: scripts/prepare_management_browser_fixture.py i scripts/verify_management_panel_browser.mjs — finite acceptance.
- Istniejące: ai_docs/requirements/MANAGEMENT_PANEL.md, architecture/MANAGEMENT_PANEL.md, process/MANAGEMENT_PANEL_OPERATIONS.md, project/TRACEABILITY.md.
- Istniejące: ai_docs/process/DECISION_LOG.md (adnotacja D-533 i D-536), CURRENT_STATE.md, README.md i bieżący plan/task.
- Nowy, proponowany: ai_docs/quality/ADMIN_COMPACT_PANEL_ACCEPTANCE.md — dowody/pomiary i niewykonane rollout gates.
- Nowy test izolowanego restore: services/api/tests/integration/test_management_backup_restore_postgres.py.
- Istniejący package.json — runner browser używa dostępnego `python` bez worktree-local `.venv`.

## Test cases

- End-to-end compact fixture w1440/1920/390 i1/4/40tiles → czytelny minimalny układ.
- Lost response + świeży proces/session identity → receipt/recovery bez duplikacji.
- Purge + rollback/fault injection i wspólny wynik innych maszyn → integralność.
- Backup restore osobna testDB → liczby obiektów/frozen results/receipts zgodne.
- Stare ordinary share i management online gates → zakres uprawnień nieposzerzony.

## Verification

Katalog: root oddzielnego worktree. Każdą poniższą skończoną komendę wykonaj
z wymuszonym timeoutem 120s w runnerze; provisioning check:30s. PG wyłącznie
disposable DB, GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 tylko w procesie testowym.
Brak venv/node_modules worktree wymaga izolowanego środowiska; nie buduj dist
ani aplikacji w głównym checkout operatora. Testy poniżej są planowane,
nie zostały jeszcze uruchomione. Najpierw pion, potem lint/typecheck/scoped
format, dopiero regresje/build. Znany build >120s poprzedź komunikatem.

```powershell
npm run reviewer:management:browser
npm run test:interactions --workspace @game-predictor/board-search-ui
npm run test --workspace @game-predictor/reviewer
npm run openapi:check
npm run typecheck --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/reviewer
```

Nowe moduły muszą dostać własne testy razem z kodem. Po zmianach Python uruchom
Ruff i mypy odpowiednich plików z istniejącej konfiguracji; TS: lint/typecheck
zmienionych workspace. PG ownership/provisioning uruchamiaj tylko na bazie
izolowanej. Każde pominięcie/skip i istniejący niezwiązany błąd podaj w Outcome.
Warunek zakończenia: kryteria potwierdzone, wymagany audyt bez otwartych P0/P1,
osobny commit i dokumentacja stanu. Brak audytu zatrzymuje następny task.

## Risks / open questions

Wzrokowy odbiór operatora i migracja jego danych wymagają odrębnego czasu/zgody. Żadnych benchmarków ani testów na jego bazie. Niezwiązany wcześniejszy błąd opisać poza taskiem, nie rozszerzać zakresu.

## Outcome

### Changed

- Ograniczona fixture rzeczywistego React/CSS z publicznym mock transportem:
  390/1440/1920px, 1/4/40 punktów, 40 maszyn na punkt i 200 aktywnych gier.
- Browser flow obejmuje wybór stawki, search/save, reset szkicu, replace startu
  #10, clear oraz potwierdzone delete maszyny/punktu. Wyodrębnienie danych
  Reviewera pomija deklarację testu jednostkowego. Uruchamianie skryptu działa
  w izolowanym worktree bez jego własnego venv.
- Wymagania, architektura, instrukcja operatorska, traceability, README oraz
  adnotacja D-533/D-536 są zgodne z kompaktowym przepływem. Raport odbioru:
  `ai_docs/quality/ADMIN_COMPACT_PANEL_ACCEPTANCE.md`.

### Verification results

- `npm run reviewer:management:browser`: PASS, 10/10 scenariuszy, około 17s.
  Max kafelka 320px przy 390px i 303px przy 1440/1920px; odpowiednio 1 i
  4 kolumny; bez horizontal overflow, nested buttons i touch poniżej 44px.
  390px flow: 6 stawek, 3 operacje dziennika, 2 strukturalne delete.
- Pierwszy przebieg ujawnił CSS `max-width:100%` nadpisujący 320px.
  TASK-0942 naprawił selektor; końcowy przebieg potwierdził limit.
- Python AST parse, Node `--check` dla obu skryptów JS, Prettier zmienionych
  skryptów/`package.json` i statyczny bundle fixture: PASS.
- Offline Alembic heads: jedyna głowa `0152_management_compact_panel`, exit0,
  dowód przekazany przez głównego wykonawcę. Wcześniejsze 59 testów backend
  i 5 modułów PG z TASK-0940 wykorzystane bez powtórzenia.
- 55/55 wspólnego UI, 175/175 Admin, 14/14 scoped Reviewer management
  oraz scoped lint/typecheck z TASK-0942: PASS; tworzenie punktu/maszyny
  ma odrębne testy interakcji TASK-0941.
- Izolowany test PostgreSQL backup/restore: 1 PASS w 33,22 s. Osobne `*_test`
  źródło i cel, `pg_dump -Fc`, `pg_restore --list` i `--exit-on-error`;
  zgodne count punkt/slot/receipt/journal oraz digest wyniku. Po teście
  odczyt katalogu `pg_database`: 0 baz `game_predictor_t0943%_test`.
- Admin production build PASS (około 32s), Reviewer production build PASS
  (około 25s), w izolowanym worktree. Ostatnia zmiana po buildach dotyczyła
  wyłącznie CSS ikon/motywu; końcowy browser run 10/10 i format PASS.
- Ruff check/format nowego testu i preparera PASS; Prettier skryptów JS i
  `package.json` PASS; `git diff --check` własnych plików PASS. Repo nie ma
  konfiguracji ESLint dla `scripts/*.mjs`; Node `--check` obu plików PASS.
- Nowy proces PowerShell: `python --version` = Python 3.12.10. Ten interpreter
  wykonał stdlib-only preparer przez `npm run reviewer:management:browser`.

### Not completed at initial handoff (historical)

- Produkcyjny read-only classifier i provisioning `--check` pozostają gate
  operatora po doprowadzeniu jego bazy do właściwej rewizji. Izolowane
  testy receipt-backfill/provisioning/fresh-process z TASK-0940 mają 5 modułów
  PG PASS; to wynik wcześniejszy, bez nowego uruchomienia. OpenAPI check z
  TASK-0940 PASS; TASK-0943 nie zmienił API.
- Ręczny audyt Claude TASK-0941–0943, rozwiązanie jego uwag i osobne commity.
  Brak formalnego `done`; push/merge/deployment i baza operatora nietknięte.

### Documentation updates

- Aktualizacja dokumentów właścicielskich i instrukcji operatorskiej;
  raport odbioru odróżnia fixture od fizycznego rollout.

### Recommended next task

- Odbiór operatorski po zakończeniu planu, bez automatycznego wdrożenia.

### Końcowa weryfikacja po audytach (2026-10-09)

- Claude0941 fokusowa runda2 PASS, P1 zamknięte;0942 PASS, czteryP2 poprawione.
- Final browser10/10 obejmuje wycentrowane modale, ich motyw i pełną szerokość pola, kontenery1000/750/500/320 i4/3/2/1 kolumny. Reviewer geometry41/41 i oba buildy PASS.
- Nowa asercja shared suite powodowała55/56; poprawiono wyłącznie test i sprawdzono go osobno1/1 PASS. Nie powtarzano pełnej suite ani wcześniej zakończonych testów backendu/PG.
- docs:check nie istnieje w bazie gałęzi; npm zwraca Missing script. Narzędzia0938/0939 pozostają zależnością integracyjną, nie wynikiem PASS.
- Main1b97ad65/v1.7.285 zawiera już0935/0936 i0152_super_game_series. Scalanie wspólnego UI, kosztu per pozycja i głów migracji jest osobnym krokiem przed merge; bez autoryzacji nie wykonujemy merge ani zmian danych operatora.

### Rozstrzygnięcia audytu Claude (jedna ograniczona runda)

- TASK-0943_AUDIT_claude-opus-5-5.md: PASS, brakP0/P1. P2-1 usunięto przedwczesny upgrade head i zdublowaną procedurę apply; instrukcja wymaga preview, zweryfikowanego backupu i zgody przed zapisem. P2-4 zaktualizowano nazwy akcji w architekturze. P2-5 digest ma jawny ORDER BY.
- P2-2 zaakceptowane: stdlib-only preparer używa globalnego Python3.12 sprawdzonego w nowym procesie, dzięki czemu fixture działa w worktree bez venv. Brak interpretera kończy test błędem, nigdy PASS; jest to jawna zależność przenoszonego środowiska.
- P2-3 doprecyzowane w raporcie: pierwszy zapis pustej stawki ma pokrycie interakcyjne0942; browser flow zaczyna od istniejącego slotu20PLN. Nie rozszerzamy bramki o powtórny scenariusz bez potrzeby.
- Raport zachowano. Poprawki dotyczą dokumentacji i testu; nie zmieniają zachowania aplikacji i nie wymagają drugiego audytu.

- Test backup/restore po P2-5:1/1 PASS w43,09s; Ruff check/format PASS. Odczyt pg_database po sprzątaniu:0 baz0943. Żadnych zmian bazy operatora.


### Końcowe zamknięcie (2026-10-09)

- Końcowy niezależny audyt całej funkcjonalności Claude `claude-opus-5-5 / medium`:
  ai_docs/quality/TASK-0943_AUDIT_claude-opus-5-5.md i rozstrzygnięcia wykonawcy.
  Commit jest dozwolony wyłącznie bez otwartych P0/P1.
- Browser10/10, kontenery4/3/2/1, wycentrowane modale z motywem,
  Reviewer geometry41/41 i oba buildy PASS. Wykorzystano wcześniejsze dowody
  backendu i ograniczonego PostgreSQL backup/restore1/1.
- Wersja commita: v1.7.276. Pełny hash zapiszemy w małym kolejnym commicie
  dokumentacyjnym bez zmiany implementacji.
- Urządzenia fizyczne/live ingress/dane operatora, preview backfillu migracji,
  zweryfikowany backup produkcyjny i restart usług przez operatora pozostają bramkami.
  Nie wykonano push, merge, deployment ani zmiany danych/usług operatora.

### Commit

v1.7.276 — d7b37368646a5c9b8a039505646a5fc6f4c55518. Osobny commit potwierdzony przez git log/show; pełny hash utrwalony w następnym commicie dokumentacyjnym.
