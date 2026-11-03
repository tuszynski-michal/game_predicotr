# TASK-1147 — Integracja przyrostu korekt i wymiany źródeł

## Status

`done`

## Goal

Połączyć obie zatwierdzone funkcje w jednym grafie Alembic 0178 po 0177, zachowując ochronę historii, wymiany źródeł i uczenia, a następnie wykonać skoordynowane wdrożenie i odbiór.

## Context

Operator zatwierdził integrację, push, migrację, restart i odbiór. Wykonawca przygotowuje wyłącznie worktree; prowadzący koordynuje późniejsze operacje z oknem mającym wyłączną kontrolę root/main/usług/bazy.

## Dependencies / entry conditions

Nasza baza `7881711b` (v1.7.542); stabilny import `60f50c64` obejmuje wdrożenie symboli, wymianę źródeł i TASK-1146. Merge rozpoczęty bez commita w `D:/game_predicotr/worktrees/grid-correction-growth`. Bez zmian historycznych audytów i już wdrożonych migracji 0172–0177.

## Recommended execution

`gpt-6-astra` / `high`; focused `claude-opus-5-5` / `high` przed commitem prowadzącego. Sprzeczność ochrony domeny albo konieczność zmiany danych wymaga eskalacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_CORRECTION_GROWTH_PLAN_20261103.md`
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md`
- `ai_docs/delivery/777A2_PHYSICAL_SOURCE_PURGE_PLAN_20261103.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — wyłącznie konflikty D-582/D-583.
- `ai_docs/archive/CURRENT_STATE_2026Q4.md` — wyłącznie kolidujące sekcje merge.

## Scope

Rozwiązanie konfliktów, zachowanie dokumentów obu historii, ograniczenie okna stanu i indeksu decyzji, parent 0177 dla migracji 0178, jeden head i readiness 0178, zgodny OpenAPI/SDK, testy integracji obu pionów.

Po zwolnieniu okna operacyjnego prowadzący wykonuje zatwierdzone scalenie/push, migrację, restart i odbiór według planu. Wykonanie tych kroków pozostaje obecnie zablokowane; gotowy kod nie oznacza ukończenia całego zadania.

## Out of scope

Wykonawca nie zmienia root/main, usług, bazy operatora ani modeli. Nie wykonuje commita, audytu ani push. Nie naprawia znanych niezwiązanych błędów reset_game/stats.

## Technical notes

0175 dodaje SQL strażników current/retired/reserved oraz blokadę sequence-ownership. 0178 zastępuje te same funkcje, więc samo przepięcie parent usunęłoby ochronę. Prowadzący zaakceptował mały wspólny helper z dokładnym strażnikiem 0175, używany przy instalacji v6 oraz odtworzeniu v4/v5 na downgrade do 0177. Funkcje upgrade/downgrade zachowują strukturę; logika uczenia i zwolnień nie zmienia się. Gwarancja identycznego wygenerowanego SQL jest celowo zastąpiona zachowaniem obu ochron.

## Expected files

- Konflikty dokumentacyjne: CURRENT_STATE, archiwum Q4, DOC_INDEX, indeksy decyzji i pełne wpisy; żadna sekcja historyczna nie ginie.
- `0178_grid_correction_growth.py`, `schema_readiness.py`, aktywne testy readiness/migracji.
- Proponowany `storage/source_recording_replacement_sql.py`; integracja z `source_recording_sql_v6.py`.
- Test PostgreSQL ochron rejestru po upgrade i downgrade; istniejące testy partial v1/v2 i UI.
- Generowane OpenAPI/SDK i mapa; dokumentacja planu, domeny, verification.

## Acceptance criteria

- [x] Jedyny head 0178, parent 0177, zachowane starsze rewizje.
- [x] SQL chroni wycofane i zarezerwowane źródła po upgrade oraz downgrade; historia i replay pozostają bezpieczne.
- [x] Zachowane funkcje obu gałęzi, kontrakty, partial v1/v2 i UI.
- [x] Dokumenty obu historii zachowane, okna i budżety przechodzą kontrolę.
- [x] Wymagane testy, lint/types/build worktree i focused audyt rozliczone przed commitem; standardowy build root jest częścią odbioru operacyjnego.
- [x] Skoordynowane wdrożenie i odbiór operatora wykonane po usunięciu blokady przez uprawnionego koordynatora.

## Test cases

Readiness poprzednich rewizji; 0177 → 0178 → 0177 → 0178; guarded downgrade z historią; retired/reserved źródła i utrwalony replay; atomowe zwolnienia rezerw v1 i hard v2; partial controls obu polityk; odświeżanie i ręczna aktualność oceny; API klient obejmuje oba zestawy metod.

## Verification

Każde skończone polecenie z timeout do 120 s, jawny workdir i PYTHONPATH worktree. Disposable PostgreSQL. Audyt organizuje prowadzący. Wyniki w `quality/TASK-1147_VERIFICATION.md`.

## Risks / open questions

Wdrożenie napotkało `GAME_STORAGE_LIFECYCLE_IN_PROGRESS`: stary running delete gry z 2026-10-20. Operator następnie osobno zatwierdził dokończenie usuwania pustej gry 777v2 wraz z pozostałą konfiguracją i przypisaniem. Zgodę odczytano w czacie koordynatora `01a19d0a-ab63-7200-a96b-9ac0237d662e`. Koordynator realizuje lifecycle i wcześniejszą migrację do 0177; do jawnego przekazania okna zachowuje wyłączną kontrolę usług, root/main i bazy.

## Outcome

Commit: v1.7.551 / `95ce934e43f5c61680fdee8afdbe98e1e8110a30`.

### Changed

Merge `60f50c64` do gałęzi o HEAD `7881711b` przygotowany bez commita. Wszystkie dziewięć konfliktów rozwiązane i oznaczone w indeksie. 0178 ma parent 0177 i zachowuje dokładny strażnik 0175 przez wspólny helper zarówno w nowym SQL v6, jak i przy przywróceniu v4/v5. Logika splitu, release i obu polityk pozostaje niezmieniona. OpenAPI i klient wygenerowane ponownie; wrapper zachowuje metody obu funkcji.

### Verification results

PG guarded migration wraz z current/retired/reserved/retention na 0178 → 0177 → 0178 PASS; core registry z restartem PASS; rzeczywiste replacement guards PASS. API/worker 104 PASS, evaluator v1/v2 z restartem 5 PASS, UI 74 PASS, requesty klienta 9 PASS. Ruff 11 plików i mypy 8 modułów PASS; TypeScript Admin/klienta, ESLint i build Admina PASS z lokalnymi aliasami. Docs:check PASS, budżet 44765/45000 B. Pełne sekcje archiwum stanu i decyzji obu rodziców zachowane, potwierdzone porównaniem tekstu. Szczegóły i znane porażki retencji: `quality/TASK-1147_VERIFICATION.md`.

### Historical checkpoint before operational acceptance

Focused Opus 5.5/high R1: PASS, bez P0/P1. Raport: `quality/TASK-1147_AUDIT_claude-opus-5-5.md`. Integrację zapisano w `08a9ffcf`, synchronizację w `5cfe292b`. Prowadzący wdrożył 0178 i uruchomił pojedynczy przebieg z UI; wynik treningu pozostaje niepotwierdzony. Ten wykonawca tylko odczytał dowody i przygotował dokumentację. Zadania nie zamknięto, pełnego odbioru ani zastosowania modelu nie zgłoszono.

### Documentation updates

Plan, aktualna architektura i kontrakt, CURRENT_STATE, DOC_INDEX oraz rozwiązane indeksy/archiwa obu historii. Historyczne audyty i ukończone zadania bez zmian treści.

### Recommended next task

Operator może osobno zastosować kandydata po zapoznaniu się z raportem i zakresem dowodu. Ta integracja nie obejmuje automatycznej aktywacji ani ponownego rozpoznania historycznych importów.

### Audit dispositions

- Opus R1 PASS obejmuje wąski kod integracji; nie jest ponownym audytem całego przychodzącego pionu ani dowodem wdrożenia. Raport statyczny zachowany bez zmian.
- P2-1/P2-3: zamknięte. Końcowe 29 unit/readiness oraz trzy PG PASS; ruff check/format bez fix 12 plików i scoped mypy 8 modułów PASS. Dodatkowy test zgodności SQL w jednej rundzie poprawek; wyniki w verification.
- P2-2: zamknięte. Po fast-forward root standardowe typecheck i build Admina bez aliasów PASS; dowody w raporcie odbioru 0178.
- P2-4: prowadzący akceptuje odłożenie dwóch zastanych FAIL retencji do osobnej naprawy. Zmiana nie wprowadza ich; obecne zabezpieczenie produktu jest fail-closed. Ryzyko i dowód baseline zapisane również w CURRENT_STATE. Nie zgłaszamy pełnego quality PASS.
- P2-5: zamknięte. Przed migracją 0178 odczytano tożsamość bazy operatora i rewizję 0177, następnie potwierdzono upgrade i role. Zachowana instrukcja planu nadal blokuje automatyczne przejście przy niespodziewanym wcześniejszym 0178.
- Bez drugiego audytu: brak uwag P0/P1 i zmian zachowania produktu w tej rundzie; nowe testy i udokumentowane bramki operacyjne. Task pozostaje in_progress, bez task-close przed odbiorem wdrożenia.

### Integration checkpoint

Integrację kodu zapisano jako v1.7.543 / `08a9ffcf`. Checkpoint nie zamyka
TASK-1147; odbiór operatora i task-close nastąpią po zatwierdzonym wdrożeniu.

Po zgodzie koordynatora przygotowano merge bez commita stabilnego
`be10f90e8d6d8121f70577be7243946ab5ee8979` do tego checkpointu. Dwa konflikty
dotyczyły wyłącznie okna i archiwum CURRENT_STATE. Zachowano pełne sekcje obu
historii, ograniczono okno do 10 zakończonych tasków i zachowano aktualne
informacje o wdrożonym 0177. Poprawka zależności React z TASK-1148, lockfile
oraz Selector 1.0.5 są zgodne z przychodzącym refem. Bez nowych zmian produktu
i bez ponawiania testów PG/UI. Kontrole synchronizacji i zachowania historii
są zapisane w `quality/TASK-1147_VERIFICATION.md`. Migracja i odbiór 0178
pozostawały wtedy przed nami; dalszy checkpoint operacyjny opisano poniżej.

### Deployment checkpoint

Prowadzący wdrożył `5cfe292b` na root/main, wykonał migrację 0177 → 0178
i kontrolę ról. Liczby źródeł/plansz/komórek oraz hashe aktywacji nie zmieniły
się; purged 0. Standardowy root Admin typecheck/build bez aliasów PASS.
API/Admin oraz general 7 / grid-training 1 działają. Odświeżanie panelu
i weryfikacja aktualności sprawdzone w UI; Apply nie uruchomiono.

Ready przed startem: 196 plansz na 133 zdjęciach, TRAIN 146/98 (77 zapisanych
oraz 69 nowych plansz), VALIDATION 17/13, REGRESSION 21/13, wyłączenia 12/9.
Przycisk UI utworzył pojedynczy przebieg
`cc7e739e-027c-4f44-87d8-8088c0d86bb1`, potwierdzony odpowiedzią i późniejszym
odczytem historii. Ostatni opisany odczyt z 11:17:19 UTC: processing,
kohorta zapisana, trainingRunId null. Bez deklaracji sukcesu treningu.
Prowadzący monitoruje ten sam przebieg; nie ponawiać startu.

Dowody i ograniczenia: `quality/GRID_CORRECTION_GROWTH_DEPLOYMENT_20261103.md`.
Raport opisuje także przejściowy Windows Stop KillAccessDenied, sprawdzenie
tożsamości i zakończenia procesów, pojedynczy idempotentny retry oraz poprawkę
ignorowanego runnera na wyjście plikowe. Bez zmian produktu i duplikatów usług.

## Checkpoint rzeczywistego odbioru — blokady1149/1150

Pierwszy freeze parenta `cc7e739e-027c-4f44-87d8-8088c0d86bb1` przekroczył60s. Normalny replay tego samego polecenia `freeze:163` i oryginalnego klucza zamroził kohortę `8c4d3ab4-4d01-59fe-a826-46883b72ddfe` do rewizji164 w53,515s; blokady wejść33,641s. To dowód poprawnego zapisu, ale nie trwała naprawa kosztu; TASK-1149 ogranicza per-row SQL do partii200 bez zmiany blokad/limitów.

Oficjalne resume tego samego parenta zachowało historię i utworzyło tylko run `7a1b3835-639c-4439-8f49-3dfaea5e650a`. Dziecko zakończyło się na kroku488: `PermissionError [WinError5]` w atomowym `os.replace` pliku postępu. Budget pozostał488/8000 kroków i161,969/7200 sekund, attempt1; brak kandydata i zmiany defaultu. TASK-1150 dodaje krótki ograniczony retry tej samej podmiany. Nie wznowiono ponownie przed poprawką.

Bramka odbioru pozostaje otwarta: sam PASS statycznego audytu1147 i poprawne liczniki nie stanowią sukcesu uczenia. Źródła: root `artifacts/grid-growth-deploy-20261103/freeze-profile-result.json`, `failed-training-job.json`, `latest-training.json` oraz diagnostyka runa. Zakres naszego178 nie został jeszcze wypchnięty.


## Checkpoint po audytach 1149/1150 i pauza operacyjna

TASK-1149 zamknięto jako v1.7.546 / `4827f2a6`; TASK-1150 jako v1.7.547 / `5efb3ea0`. Oba rzeczywiste audyty Claude Code Opus 5.5/high zakończyły się PASS bez P0/P1. Drobne uwagi P2 rozliczono testami. Zmiany pozostają na gałęzi roboczej; root/main nadal `5cfe292b`, DB0178, origin/main `be10f90e`.

Kontrolowany odczyt blokad nowym helperem na tej samej kohorcie trwał 3,968s zamiast poprzednich 33,641s; transakcja została jawnie wycofana, stan frozen/revision164 pozostał niezmieniony. Testy Windows obejmują rzeczywisty uchwyt pliku bez FILE_SHARE_DELETE. Są to dowody napraw mechanizmu, nie ukończenia treningu.

Koordynator drugiego okna potwierdził osobną regresję wyszukiwania plansz w filtrze źródeł 0175/0176. Zarezerwował TASK-1151 i migrację0179. Uzgodniono pauzę: bez kolejnych freeze, restartów i resume do gotowej, przetestowanej i audytowanej poprawki oraz ustalenia jednego właściciela wspólnego wdrożenia. Nie uruchomiono nowych zadań GPU. Zachowano parent `cc7e739e-027c-4f44-87d8-8088c0d86bb1`, dziecko `7a1b3835-639c-4439-8f49-3dfaea5e650a` i ich dotychczasowe zużycie budżetu.


## Odbiór końcowy — 0179 i rzeczywiste uczenie PASS

Po skoordynowanym wdrożeniu root/main i origin/main `d01a0f07cc72d44f54711cd1a1a60a27df4823df` baza ma jedyny head `0179_empty_replacement_search`. Kontrola ról compliant, API/Admin działają, worker general7 i grid-training1 uruchomione z nowego procesu. Dane przed/po179 identyczne:166971źródeł,1500019plansz,22248975pól, purged0, te same hashe aktywacji. TASK-1151 zamknięto osobno po rzeczywistym wyszukiwaniu; naprawa nie zmienia danych ani zakresu modeli.

Oficjalne resume12:53:41UTC wznowiło ten sam parent `cc7e739e-027c-4f44-87d8-8088c0d86bb1` i dziecko `7a1b3835-639c-4439-8f49-3dfaea5e650a`. Nie powstał drugi run ani nowy budżet. Attempt2 poprawnie zapisał checkpointy i eksport; wykonał2400kroków, zakończył przez early_stopping i wybrał checkpoint1200 na VALIDATION. Progress3600/3600 oznacza zamknięcie planu, nie wykonanie3600kroków. Łączne zużycie2888/8000kroków zawiera wcześniejsze488; czas865,313/7200s, bez resetu/odnowienia. `result-1.json` zachowuje wcześniejszy błąd, `result-2.json` potwierdza exported/early_stopping.

Automatyczna ocena `eeb70311-2ab7-4e2e-9961-4ff9aac6821a` zakończyła się13:07:04UTC wynikiem PASS, raport `0cd1539a-412f-561c-a022-838577c09f62`, kandydat `3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e`. Porównano te same oryginalne zdjęcia:

| Rola | Zdjęcia / opisane plansze | Poprawne baza / kandydat | Średni znormalizowany błąd baza / kandydat | Spadek błędu |
|---|---:|---:|---:|---:|
| VALIDATION |13/17|12/14|0,01734436/0,01316342|24,11%|
| REGRESSION |13/21|15/17|0,01442749/0,01180831|18,15%|

Wykryte odpowiednio17/17 i21/21 dla obu modeli. Gate v2 PASS i ONNX parity PASS. Wszystkie zdjęcia kontrolne są częściowo opisane: ocena dotyczy opisanych plansz, bez miary fałszywych detekcji poza nimi. Dowód photo-only nie potwierdza niezależności sesji ani nieznanego wykorzystania danych przez przodków; zweryfikowany zakres obejmuje wyłącznie MumieA2. Nie deklarujemy jakości innych gier ani istotności statystycznej.

Po freeze liczniki:196zatwierdzonych/133zdjęcia, TRAIN146/98; zapisane TRAIN146/98 i nowe0/0, VALIDATION17/13, REGRESSION21/13. Nowe69plansz z poprzedniego podglądu weszły do zamrożonego TRAIN; dlatego licznik nowych spadł do0. Bufor12opisanychplansz/53źródła, wyłączone12/9 bez zmian. Zachowano niezależną od TRAIN pulę testową i ochrony.

Rzeczywisty Admin po restarcie pokazał PASS i powyższe liczniki. Przycisk sprawdzenia aktualności przeszedł w loading, zakończył się potwierdzeniem i nowym preview. Zaznaczenie potwierdzenia odblokowało Apply; checkbox następnie odznaczono, Apply nie kliknięto. Default oraz przypisanie MumieA2 pozostały Mumie v1, revision1. Kandydat oczekuje na osobne zastosowanie operatora. Starsze importy i ręczna geometria nie zostały przeliczone.

Dowody w root `artifacts/grid-growth-deploy-20261103`: `before-resume-afterfix.json`, `learning-resume-afterfix-intent.json`, `learning-resume-afterfix-response.json`, `afterfix-history.jsonl`, `latest-afterfix.json`, `final-evaluation.json`, `latest-ready.json`, `database-before179.json`, `database-after179.json`, `final-panel-pass.png`. Rzeczywisty obraz panelu pokazuje tabelę15→17poprawnych w kontroli końcowej. Historyczne checkpointy raportu powyżej pozostają zapisem kolejnych etapów, nie aktualnym blockerem.

DoD: kod i kontrakt, migracje/restart, liczniki, aktualność i rzeczywisty trening/ocena potwierdzone. Audyty1139/1140/1145/1147/1149/1150 i1151 rzeczywiste, bez otwartych P0/P1; P2 oraz zastane niepowiązane FAIL opisane w raportach. Nie zgłaszamy pełnego globalnego quality/mypy PASS. Końcowy commit dokumentuje odbiór, a późniejszy metadata commit zapisze jego hash oraz finalny push.
